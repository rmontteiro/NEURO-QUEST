"""Roteia as missões para Jupiter, Uniswap e Aave. A agência não custodia a chave.

Solana sai numa Transaction V0 com várias instruções. Ethereum sai como
chamadas em sequência: approve do valor exato, swap e supply. A ordem
limitada é um pedido CoW que o usuário assina; o relayer oficial só
move o token se o preço da ordem for respeitado.
"""

from __future__ import annotations

import base64
from decimal import Decimal, ROUND_DOWN
from typing import Any

from eth_abi import decode, encode
from solders.compute_budget import set_compute_unit_limit
from solders.hash import Hash
from solders.instruction import AccountMeta, Instruction
from solders.message import MessageV0
from solders.pubkey import Pubkey
from solders.signature import Signature
from solders.transaction import VersionedTransaction
from web3 import Web3

SLIPPAGE_BPS = 100
ETH_CHAIN_ID = 1

JUPITER_V6 = "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"
SOLANA_PROGRAMS = {
    JUPITER_V6: "Jupiter Aggregator v6",
    "ComputeBudget111111111111111111111111111111": "Compute Budget",
    "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL": "Associated Token Account",
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA": "Token Program",
    "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb": "Token-2022",
    "11111111111111111111111111111111": "System Program",
    "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr": "Memo",
}

SWAP_ROUTER_02 = "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45"
AAVE_POOL = "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2"
COW_SETTLEMENT = "0x9008D19f58AAbD9eD0D60971565AA8510560ab41"
COW_VAULT_RELAYER = "0xC92E8bdf79f0507f65a392b0ab4667716BFE0110"
WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
USDC = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
WBTC = "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599"
AAVE = "0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9"
ZERO = "0x0000000000000000000000000000000000000000"
# appData de "{}" usado pelo CoW Protocol.
APP_DATA = "0xb48d38f93eaa084033fc5970bf96e559c33c4cdc07d889ab00b4d63f9590739d"

TOKENS = {
    "ETH": {"address": WETH, "decimals": 18, "native": True},
    "WETH": {"address": WETH, "decimals": 18, "native": False},
    "USDC": {"address": USDC, "decimals": 6, "native": False},
    "WBTC": {"address": WBTC, "decimals": 8, "native": False},
    "AAVE": {"address": AAVE, "decimals": 18, "native": False},
}
EVM_ALLOW = {
    Web3.to_checksum_address(item)
    for item in (SWAP_ROUTER_02, AAVE_POOL, COW_VAULT_RELAYER, WETH, USDC, WBTC, AAVE)
}

SOL_MINT = "So11111111111111111111111111111111111111112"
USDC_SOL = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
SOL_MINTS = {"SOL": SOL_MINT, "USDC": USDC_SOL}

FALHA_FUNDOS = "A transação não seguiu: saldo insuficiente para o valor e a taxa de rede."
FALHA_SLIPPAGE = "A transação não seguiu: o preço saiu do limite de 1%."
FALHA_RECUSA = "A assinatura foi recusada na carteira. Nenhuma ordem foi enviada."
FALHA_ROTA = "A rota não pôde ser concluída. Nenhuma ordem nova foi enviada."


def classificar_falha(texto: str, code: int | None = None) -> str:
    blob = (texto or "").lower()
    if code == 4001 or any(part in blob for part in ("user rejected", "rejected the request", "recus", "denied")):
        return FALHA_RECUSA
    if any(part in blob for part in ("insufficient", "insufficient funds", "lamport", "0x1 insufficient")):
        return FALHA_FUNDOS
    if any(part in blob for part in ("slippage", "0x1771", "0x1781", "pricetolerance", "amount out")):
        return FALHA_SLIPPAGE
    return FALHA_ROTA


def _units(amount: Decimal, decimals: int) -> int:
    quant = amount * (Decimal(10) ** decimals)
    return int(quant.to_integral_value(rounding=ROUND_DOWN))


def _min_out(amount: Decimal, price: Decimal, decimals: int, bps: int = SLIPPAGE_BPS) -> int:
    if bps > SLIPPAGE_BPS:
        raise ValueError("O slippage passa de 1%.")
    raw = amount * price * (Decimal(10) ** decimals)
    kept = raw * Decimal(10_000 - bps) / Decimal(10_000)
    value = int(kept.to_integral_value(rounding=ROUND_DOWN))
    if value <= 0:
        raise ValueError("O mínimo de saída ficou zerado.")
    return value


def _checksum(address: str) -> str:
    return Web3.to_checksum_address(address)


def _call(to: str, signature: str, types: list[str], values: list[Any], value: int = 0, descricao: str = "") -> dict[str, Any]:
    target = _checksum(to)
    if target not in EVM_ALLOW:
        raise ValueError(f"Contrato fora da lista: {target}")
    selector = Web3.keccak(text=signature)[:4]
    data = "0x" + (selector + encode(types, values)).hex()
    return {
        "para": target,
        "data": data,
        "value": hex(value),
        "descricao": descricao,
        "chain_id": ETH_CHAIN_ID,
    }


def _decode_approve(data: str) -> tuple[str, int]:
    raw = bytes.fromhex(data[10:])
    spender, amount = decode(["address", "uint256"], raw)
    return _checksum(spender), int(amount)


def chamada_approve(token: str, spender: str, amount: int, descricao: str) -> dict[str, Any]:
    if amount <= 0 or amount >= 2**256 - 1:
        raise ValueError("O approve precisa ser o valor exato da missão.")
    spender_cs = _checksum(spender)
    if spender_cs not in EVM_ALLOW:
        raise ValueError("O spender não está na lista do CCO.")
    return _call(
        token,
        "approve(address,uint256)",
        ["address", "uint256"],
        [spender_cs, amount],
        descricao=descricao,
    )


def chamada_uniswap(order: dict[str, Any], recipient: str) -> list[dict[str, Any]]:
    """Swap na Ethereum: approve exato e exactInputSingle com piso de 1%."""
    symbol = str(order["simbolo"]).upper()
    pair = str(order.get("simbolo_par") or "USDC").upper()
    if str(order.get("rede", "")).lower() not in {"ethereum", "eth"}:
        raise ValueError(f"{symbol} não está na rede Ethereum desta missão.")
    token_in = TOKENS[symbol]
    token_out = TOKENS[pair]
    amount = Decimal(str(order["quantidade"]))
    price = Decimal(str(order["preco_usd"]))
    amount_in = _units(amount, token_in["decimals"])
    amount_out_min = _min_out(amount, price if pair == "USDC" else Decimal(1), token_out["decimals"])
    recipient_cs = _checksum(recipient)
    calls: list[dict[str, Any]] = []
    if token_in["native"]:
        calls.append(
            _call(
                WETH,
                "deposit()",
                [],
                [],
                value=amount_in,
                descricao="Embrulhar ETH em WETH para o swap",
            )
        )
    calls.append(
        chamada_approve(
            token_in["address"],
            SWAP_ROUTER_02,
            amount_in,
            f"Aprovar {symbol} exato no SwapRouter02",
        )
    )
    calls.append(
        _call(
            SWAP_ROUTER_02,
            "exactInputSingle((address,address,uint24,address,uint256,uint256,uint160))",
            ["(address,address,uint24,address,uint256,uint256,uint160)"],
            [
                (
                    _checksum(token_in["address"]),
                    _checksum(token_out["address"]),
                    3000,
                    recipient_cs,
                    amount_in,
                    amount_out_min,
                    0,
                )
            ],
            descricao=f"Swap Uniswap {symbol}/{pair} com piso de 1%",
        )
    )
    return calls


def chamadas_aave(order: dict[str, Any], recipient: str) -> list[dict[str, Any]]:
    symbol = str(order["simbolo"]).upper()
    if symbol not in TOKENS or str(order.get("rede", "ethereum")).lower() not in {"ethereum", "eth"}:
        raise ValueError(f"{symbol} não entra no Aave V3 da Ethereum.")
    token = TOKENS[symbol]
    amount = _units(Decimal(str(order["quantidade"])), token["decimals"])
    on_behalf = _checksum(recipient)
    calls: list[dict[str, Any]] = []
    if token["native"]:
        calls.append(
            _call(WETH, "deposit()", [], [], value=amount, descricao="Embrulhar ETH em WETH para o Aave")
        )
    calls.append(chamada_approve(token["address"], AAVE_POOL, amount, f"Aprovar {symbol} exato no Pool do Aave V3"))
    calls.append(
        _call(
            AAVE_POOL,
            "supply(address,uint256,address,uint16)",
            ["address", "uint256", "address", "uint16"],
            [_checksum(token["address"]), amount, on_behalf, 0],
            descricao=f"Depositar {symbol} no Aave V3 em nome do investidor",
        )
    )
    return calls


def ordem_limite(order: dict[str, Any], recipient: str) -> dict[str, Any]:
    """Ordem limitada de venda no CoW. O piso é o gatilho menos 1%."""
    symbol = str(order["simbolo"]).upper()
    pair = str(order.get("simbolo_par") or "USDC").upper()
    trigger = order.get("gatilho_usd")
    if trigger is None:
        raise ValueError("A ordem de stop não tem gatilho.")
    if symbol not in TOKENS or pair not in TOKENS:
        raise ValueError("O par do stop não está na lista Ethereum.")
    sell = TOKENS[symbol]
    buy = TOKENS[pair]
    sell_amount = _units(Decimal(str(order["quantidade"])), sell["decimals"])
    buy_amount = _min_out(Decimal(str(order["quantidade"])), Decimal(str(trigger)), buy["decimals"])
    valid_to = int(order.get("valid_to") or 1_893_456_000)
    typed = {
        "domain": {
            "name": "Gnosis Protocol",
            "version": "v2",
            "chainId": ETH_CHAIN_ID,
            "verifyingContract": _checksum(COW_SETTLEMENT),
        },
        "primaryType": "Order",
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            "Order": [
                {"name": "sellToken", "type": "address"},
                {"name": "buyToken", "type": "address"},
                {"name": "receiver", "type": "address"},
                {"name": "sellAmount", "type": "uint256"},
                {"name": "buyAmount", "type": "uint256"},
                {"name": "validTo", "type": "uint32"},
                {"name": "appData", "type": "bytes32"},
                {"name": "feeAmount", "type": "uint256"},
                {"name": "kind", "type": "string"},
                {"name": "partiallyFillable", "type": "bool"},
                {"name": "sellTokenBalance", "type": "string"},
                {"name": "buyTokenBalance", "type": "string"},
            ],
        },
        "message": {
            "sellToken": _checksum(sell["address"]),
            "buyToken": _checksum(buy["address"]),
            "receiver": _checksum(recipient),
            "sellAmount": str(sell_amount),
            "buyAmount": str(buy_amount),
            "validTo": valid_to,
            "appData": APP_DATA,
            "feeAmount": "0",
            "kind": "sell",
            "partiallyFillable": False,
            "sellTokenBalance": "erc20",
            "buyTokenBalance": "erc20",
        },
    }
    approve = chamada_approve(
        sell["address"],
        COW_VAULT_RELAYER,
        sell_amount,
        f"Aprovar {symbol} exato no VaultRelayer para a ordem limitada",
    )
    return {
        "protocolo": "CoW Protocol",
        "slippage_bps": SLIPPAGE_BPS,
        "gatilho_usd": float(trigger),
        "typed_data": typed,
        "approve": approve,
    }


def pack_v0(payer: str, instructions: list[Instruction], blockhash: str) -> dict[str, Any]:
    """Empacota várias instruções numa Transaction V0 não assinada."""
    try:
        payer_key = Pubkey.from_string(payer)
        recent = Hash.from_string(blockhash)
    except Exception as exc:
        raise ValueError("A chave ou o blockhash Solana não é válido.") from exc
    message = MessageV0.try_compile(payer_key, instructions, [], recent)
    transaction = VersionedTransaction.populate(message, [Signature.default()])
    if transaction.signatures[0] != Signature.default():
        raise RuntimeError("A transação V0 saiu assinada. Isso não pode seguir.")
    programs = []
    for instruction in message.instructions:
        program = str(message.account_keys[instruction.program_id_index])
        if program not in SOLANA_PROGRAMS:
            raise ValueError(f"Programa Solana fora da lista: {program}")
        programs.append({"programa": program, "nome": SOLANA_PROGRAMS[program]})
    raw = bytes(transaction)
    if len(raw) > 1232:
        raise ValueError("O lote Solana não cabe numa Transaction V0.")
    return {
        "rede": "solana",
        "versao": "v0",
        "custodia": False,
        "move_tokens": True,
        "pagador": str(payer_key),
        "programas": programs,
        "serialized_base64": base64.b64encode(raw).decode("ascii"),
        "tamanho_bytes": len(raw),
    }


def jupiter_swap_ix(payer: str, data: bytes) -> Instruction:
    """Instrução externa do agregador. O Jupiter faz o CPI nos DEXes."""
    return Instruction(
        Pubkey.from_string(JUPITER_V6),
        data,
        [AccountMeta(Pubkey.from_string(payer), is_signer=True, is_writable=True)],
    )


def lote_jupiter(payer: str, blockhash: str, swap_data: bytes) -> dict[str, Any]:
    """Compute budget + swap do Jupiter na mesma V0."""
    instructions = [
        set_compute_unit_limit(400_000),
        jupiter_swap_ix(payer, swap_data),
    ]
    packed = pack_v0(payer, instructions, blockhash)
    packed["protocolo"] = "Jupiter"
    packed["slippage_bps"] = SLIPPAGE_BPS
    return packed


def _auditar(chamadas: list[dict[str, Any]], solana: dict[str, Any] | None, limite: dict[str, Any] | None) -> dict[str, Any]:
    contracts_ok = True
    motivos: list[str] = []
    for call in chamadas:
        target = _checksum(call["para"])
        if target not in EVM_ALLOW:
            contracts_ok = False
            motivos.append(f"Destino fora da lista: {target}")
        if call["data"].startswith("0x095ea7b3"):
            spender, amount = _decode_approve(call["data"])
            if spender not in EVM_ALLOW or amount >= 2**256 - 1:
                contracts_ok = False
                motivos.append("Approve ilimitado ou para contrato desconhecido.")
    if solana is not None:
        for program in solana.get("programas", []):
            if program["programa"] not in SOLANA_PROGRAMS:
                contracts_ok = False
                motivos.append(f"Programa fora da lista: {program['programa']}")
    stop_ok = limite is not None and int(limite["slippage_bps"]) <= SLIPPAGE_BPS
    slippage_ok = SLIPPAGE_BPS == 100 and (solana is None or int(solana.get("slippage_bps", 100)) <= 100)
    if limite is not None and int(limite["slippage_bps"]) > SLIPPAGE_BPS:
        slippage_ok = False
    ok = contracts_ok and slippage_ok and stop_ok and (chamadas or solana or limite)
    return {
        "ok": bool(ok),
        "slippage_max_bps": SLIPPAGE_BPS,
        "itens": [
            {"rotulo": "Slippage máximo: 1%", "ok": slippage_ok},
            {
                "rotulo": "Contratos conferidos: sim" if contracts_ok else "Contratos conferidos: não",
                "ok": contracts_ok,
            },
            {"rotulo": "Proteção definida: sim" if stop_ok else "Proteção definida: não", "ok": stop_ok},
        ],
        "motivos": motivos,
    }


def build_route(
    orders: list[dict[str, Any]],
    *,
    pagador_solana: str | None = None,
    pagador_ethereum: str | None = None,
    blockhash: str | None = None,
    solana_swap: bytes | None = None,
) -> dict[str, Any]:
    """Monta o lote. Sem pagador Ethereum, devolve só a auditoria prévia."""
    avisos: list[str] = []
    chamadas: list[dict[str, Any]] = []
    limite = None
    solana = None
    recipient = pagador_ethereum or ZERO
    for order in orders:
        kind = order["tipo"]
        chain = str(order.get("rede", "")).lower()
        try:
            if kind in {"compra", "venda"} and chain == "solana":
                if pagador_solana and blockhash and solana_swap is not None:
                    solana = lote_jupiter(pagador_solana, blockhash, solana_swap)
                elif chain == "solana":
                    avisos.append("A cotação da Jupiter não chegou. O swap Solana ficou de fora deste lote.")
            elif kind in {"compra", "venda"} and chain in {"ethereum", "eth"}:
                chamadas.extend(chamada_uniswap(order, recipient))
            elif kind == "pool":
                chamadas.extend(chamadas_aave(order, recipient))
            elif kind == "stop":
                limite = ordem_limite(order, recipient)
            elif kind in {"compra", "venda", "pool", "stop"}:
                avisos.append(
                    f"{kind} {order.get('simbolo')} está em {chain or 'rede desconhecida'} e não entra neste lote."
                )
        except (KeyError, ValueError) as exc:
            avisos.append(str(exc))
    if limite is not None:
        chamadas.append(limite["approve"])
    auditoria = _auditar(chamadas, solana, limite)
    return {
        "custodia": False,
        "enviar": bool(pagador_ethereum or pagador_solana),
        "chain_id": ETH_CHAIN_ID,
        "avisos": avisos,
        "auditoria": auditoria,
        "chamadas": chamadas,
        "solana": solana,
        "limite": limite,
    }


def validar_ordem_publicada(order: dict[str, Any], expected: dict[str, Any]) -> None:
    message = expected["typed_data"]["message"]
    for field in ("sellToken", "buyToken", "sellAmount", "buyAmount", "kind", "feeAmount"):
        if str(order.get(field)) != str(message[field]):
            raise ValueError("A ordem limitada não confere com a que o CCO auditou.")
    if str(order.get("receiver", "")).lower() != str(message["receiver"]).lower():
        raise ValueError("O recebedor da ordem limitada mudou.")
