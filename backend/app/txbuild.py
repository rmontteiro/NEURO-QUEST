"""Empacota compra, venda, stop e pool numa transação não assinada.

A transação que a Phantom assina não transfere tokens: em Solana são
memos no mesmo bloco de instruções; na Base é uma chamada à própria
carteira com as ordens em ABI. As chamadas oficiais do SwapRouter02 e
do NonfungiblePositionManager ficam à parte, para não saírem juntas
numa assinatura só.
"""

from __future__ import annotations

import base64
from decimal import Decimal, ROUND_DOWN
from typing import Any

from eth_abi import encode
from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price
from solders.hash import Hash
from solders.instruction import AccountMeta, Instruction
from solders.message import Message
from solders.pubkey import Pubkey
from solders.signature import Signature
from solders.transaction import Transaction
from web3 import Web3

MEMO_PROGRAM = Pubkey.from_string("MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr")
SWAP_ROUTER_02 = "0x2626664c2603336E57B271c5C0b26F421741e481"
POSITION_MANAGER = "0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1"
BASE_CHAIN_ID = 8453
ZERO = "0x0000000000000000000000000000000000000000"
KIND = {"compra": 1, "venda": 2, "stop": 3, "pool": 4}
TOKEN_DECIMALS = {"ETH": 18, "WETH": 18, "USDC": 6}
# Tick cheio do Uniswap v3, alinhado ao spacing de 60 da fee 0,3%.
TICK_LOWER = -887220
TICK_UPPER = 887220
PREVIEW_DEADLINE = 1_893_456_000

EXACT_INPUT_SINGLE = "exactInputSingle((address,address,uint24,address,uint256,uint256,uint160))"
MULTICALL = "multicall(uint256,bytes[])"
MINT = "mint((address,address,uint24,int24,int24,uint256,uint256,uint256,uint256,address,uint256))"
PACK = "packOrders((uint8,address,address,uint256,uint256,uint256)[])"


def _selector(signature: str) -> bytes:
    return Web3.keccak(text=signature)[:4]


def _micro(value: float | None) -> int:
    if value is None:
        return 0
    quant = Decimal(str(value)).scaleb(6)
    return int(quant.to_integral_value(rounding=ROUND_DOWN))


def _base_units(amount: float, decimals: int) -> int:
    quant = Decimal(str(amount)) * (Decimal(10) ** decimals)
    return int(quant.to_integral_value(rounding=ROUND_DOWN))


def _checksum(address: str) -> str:
    return Web3.to_checksum_address(address)


def memo_text(order: dict[str, Any]) -> str:
    gatilho = order.get("gatilho_usd")
    gatilho_txt = "" if gatilho is None else f"{float(gatilho):.8f}"
    par = order.get("simbolo_par") or ""
    return (
        f"NQ|{order['tipo']}|{order['simbolo']}|{par}|"
        f"{float(order['quantidade']):.8f}|{float(order['preco_usd']):.8f}|"
        f"{gatilho_txt}|{order['rede']}"
    )


def build_solana(orders: list[dict[str, Any]], payer: str, blockhash: str | None) -> dict[str, Any]:
    try:
        payer_key = Pubkey.from_string(payer)
    except Exception as exc:
        raise ValueError("A chave pública Solana não é válida.") from exc
    provisional = not blockhash
    try:
        recent = Hash.from_string(blockhash) if blockhash else Hash(bytes([7]) * 32)
    except Exception as exc:
        raise ValueError("O blockhash Solana não é válido.") from exc
    instructions: list[Instruction] = [
        set_compute_unit_limit(80_000),
        set_compute_unit_price(1_000),
    ]
    for order in orders:
        instructions.append(
            Instruction(
                MEMO_PROGRAM,
                memo_text(order).encode("utf-8"),
                [AccountMeta(payer_key, is_signer=True, is_writable=True)],
            )
        )
    message = Message.new_with_blockhash(instructions, payer_key, recent)
    tx = Transaction.new_unsigned(message)
    raw = bytes(tx)
    if len(raw) > 1232:
        raise ValueError("As ordens não cabem numa transação Solana.")
    if tx.signatures[0] != Signature.default():
        raise RuntimeError("A transação saiu assinada. Isso não pode seguir.")
    return {
        "rede": "solana",
        "efeito": "atestado",
        "move_tokens": False,
        "pagador": str(payer_key),
        "blockhash": str(recent),
        "blockhash_provisorio": provisional,
        "instrucoes": ["limite de compute", "preço de compute", *[memo_text(order) for order in orders]],
        "serialized_base64": base64.b64encode(raw).decode("ascii"),
        "tamanho_bytes": len(raw),
    }


def _pack_data(orders: list[dict[str, Any]]) -> str:
    tuples = []
    for order in orders:
        token = _checksum(order["token_base"]) if order.get("token_base") else _checksum(ZERO)
        pair = _checksum(order["token_par_base"]) if order.get("token_par_base") else _checksum(ZERO)
        tuples.append(
            (
                KIND[order["tipo"]],
                token,
                pair,
                _micro(float(order["quantidade"])),
                _micro(float(order["preco_usd"])),
                _micro(order.get("gatilho_usd")),
            )
        )
    body = encode(["(uint8,address,address,uint256,uint256,uint256)[]"], [tuples])
    return "0x" + (_selector(PACK) + body).hex()


def _exact_input(order: dict[str, Any], recipient: str) -> str | None:
    if order["tipo"] != "venda":
        return None
    token_in = order.get("token_base")
    token_out = order.get("token_par_base")
    if not token_in or not token_out:
        return None
    decimals = TOKEN_DECIMALS.get(order["simbolo"])
    if decimals is None:
        return None
    amount_in = _base_units(float(order["quantidade"]), decimals)
    if amount_in <= 0:
        return None
    params = (
        _checksum(token_in),
        _checksum(token_out),
        3000,
        _checksum(recipient),
        amount_in,
        0,
        0,
    )
    encoded = encode(["(address,address,uint24,address,uint256,uint256,uint160)"], [params])
    return "0x" + (_selector(EXACT_INPUT_SINGLE) + encoded).hex()


def _mint_preview(order: dict[str, Any], recipient: str) -> str | None:
    if order["tipo"] != "pool":
        return None
    token_a = order.get("token_base")
    token_b = order.get("token_par_base")
    if not token_a or not token_b or token_a.lower() == token_b.lower():
        return None
    left, right = sorted([_checksum(token_a), _checksum(token_b)])
    decimals = TOKEN_DECIMALS.get(order["simbolo"], 18)
    amount = _base_units(float(order["quantidade"]), decimals)
    params = (
        left,
        right,
        3000,
        TICK_LOWER,
        TICK_UPPER,
        amount,
        0,
        0,
        0,
        _checksum(recipient),
        PREVIEW_DEADLINE,
    )
    encoded = encode(
        ["(address,address,uint24,int24,int24,uint256,uint256,uint256,uint256,address,uint256)"],
        [params],
    )
    return "0x" + (_selector(MINT) + encoded).hex()


def router_calls(orders: list[dict[str, Any]], recipient: str) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    swaps = []
    for order in orders:
        swap = _exact_input(order, recipient)
        if swap:
            swaps.append(swap)
            calls.append(
                {
                    "tipo": "venda",
                    "contrato": _checksum(SWAP_ROUTER_02),
                    "funcao": EXACT_INPUT_SINGLE,
                    "data": swap,
                    "incluida_na_transacao": False,
                }
            )
        mint = _mint_preview(order, recipient)
        if mint:
            calls.append(
                {
                    "tipo": "pool",
                    "contrato": _checksum(POSITION_MANAGER),
                    "funcao": MINT,
                    "data": mint,
                    "incluida_na_transacao": False,
                }
            )
    if swaps:
        payload = encode(
            ["uint256", "bytes[]"],
            [PREVIEW_DEADLINE, [bytes.fromhex(item[2:]) for item in swaps]],
        )
        calls.append(
            {
                "tipo": "multicall",
                "contrato": _checksum(SWAP_ROUTER_02),
                "funcao": MULTICALL,
                "data": "0x" + (_selector(MULTICALL) + payload).hex(),
                "incluida_na_transacao": False,
            }
        )
    return calls


def build_base(orders: list[dict[str, Any]], payer: str) -> dict[str, Any]:
    try:
        account = _checksum(payer)
    except Exception as exc:
        raise ValueError("O endereço da Base não é válido.") from exc
    data = _pack_data(orders)
    gas = 80_000 + 12_000 * len(orders)
    transaction = {
        "from": account,
        "to": account,
        "value": "0x0",
        "data": data,
        "chainId": hex(BASE_CHAIN_ID),
        "nonce": "0x0",
        "gas": hex(gas),
        "maxFeePerGas": hex(1_000_000_000),
        "maxPriorityFeePerGas": hex(100_000_000),
        "type": "0x2",
    }
    return {
        "rede": "base",
        "chain_id": BASE_CHAIN_ID,
        "efeito": "atestado",
        "move_tokens": False,
        "pagador": account,
        "destino": account,
        "nonce_definido_pela_carteira": True,
        "transacao": transaction,
        "chamadas_prontas": router_calls(orders, account),
        "contratos": {
            "swap_router_02": _checksum(SWAP_ROUTER_02),
            "position_manager": _checksum(POSITION_MANAGER),
        },
    }


def build_bundle(
    orders: list[dict[str, Any]],
    payer_solana: str | None,
    payer_base: str | None,
    blockhash: str | None,
) -> dict[str, Any]:
    if not orders:
        raise ValueError("Não há ordens para empacotar.")
    if not payer_solana and not payer_base:
        raise ValueError("Informe a chave pública Solana, o endereço da Base, ou os dois.")
    kinds = [order["tipo"] for order in orders]
    bundle: dict[str, Any] = {
        "efeito": "atestado",
        "move_tokens": False,
        "ordens": kinds,
        "solana": build_solana(orders, payer_solana, blockhash) if payer_solana else None,
        "base": build_base(orders, payer_base) if payer_base else None,
    }
    return bundle
