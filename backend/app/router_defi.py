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

import httpx
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
SOL_DECIMALS = {"SOL": 9, "USDC": 6}
JUPITER_BASES = ("https://api.jup.ag/swap/v1", "https://lite-api.jup.ag/swap/v1")
PROTECAO_SOLANA = (
    "A proteção que espera a queda não foi armada. A ordem pública da Jupiter, "
    "com limite abaixo do preço, venderia na hora. O stop que fica esperando entrega o saldo a um cofre."
)

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


def _call(
    to: str,
    signature: str,
    types: list[str],
    values: list[Any],
    value: int = 0,
    descricao: str = "",
    papel: str = "movimento",
) -> dict[str, Any]:
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
        "papel": papel,
    }


def _decode_approve(data: str) -> tuple[str, int]:
    raw = bytes.fromhex(data[10:])
    spender, amount = decode(["address", "uint256"], raw)
    return _checksum(spender), int(amount)


def chamada_approve(token: str, spender: str, amount: int, descricao: str, papel: str = "movimento") -> dict[str, Any]:
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
        papel=papel,
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
        papel="protecao",
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
    packed["descricao"] = "Swap na Jupiter"
    return packed


def conferir_lote_jupiter(raw: bytes, payer: str) -> dict[str, Any]:
    """Aceita a V0 da Jupiter só se estiver sem assinatura, no pagador e na lista."""
    if len(raw) > 1232:
        raise ValueError("O lote Solana não cabe numa Transaction V0.")
    try:
        transaction = VersionedTransaction.from_bytes(raw)
    except Exception as exc:
        raise ValueError("A transação da Jupiter não pôde ser lida.") from exc
    if not transaction.signatures or transaction.signatures[0] != Signature.default():
        raise ValueError("A transação da Jupiter chegou assinada.")
    message = transaction.message
    if str(message.account_keys[0]) != payer:
        raise ValueError("O pagador da transação não é a carteira conectada.")
    programs = []
    for instruction in message.instructions:
        index = instruction.program_id_index
        if index >= len(message.account_keys):
            raise ValueError("A Jupiter escondeu um programa numa tabela de endereços.")
        program = str(message.account_keys[index])
        if program not in SOLANA_PROGRAMS:
            raise ValueError(f"Programa Solana fora da lista: {program}")
        programs.append({"programa": program, "nome": SOLANA_PROGRAMS[program]})
    return {
        "rede": "solana",
        "versao": "v0",
        "custodia": False,
        "move_tokens": True,
        "pagador": payer,
        "programas": programs,
        "serialized_base64": base64.b64encode(raw).decode("ascii"),
        "tamanho_bytes": len(raw),
        "protocolo": "Jupiter",
        "slippage_bps": SLIPPAGE_BPS,
        "blockhash": str(message.recent_blockhash),
    }


def _preco_sol(orders: list[dict[str, Any]]) -> Decimal | None:
    for order in orders:
        if str(order.get("simbolo", "")).upper() == "SOL" and float(order.get("preco_usd") or 0) > 1:
            return Decimal(str(order["preco_usd"]))
    return None


def _par_jupiter(order: dict[str, Any], preco_sol: Decimal | None) -> tuple[str, str, int, str]:
    kind = order["tipo"]
    symbol = str(order["simbolo"]).upper()
    pair = str(order.get("simbolo_par") or "USDC").upper()
    quantidade = Decimal(str(order["quantidade"]))
    if kind == "venda":
        entrada, saida = symbol, pair
        texto = f"Venda de {symbol} por {saida} na Jupiter"
    elif kind == "compra":
        entrada, saida = pair, symbol
        texto = f"Compra de {symbol} com {entrada} na Jupiter"
    else:
        raise ValueError("Esta proposta não é um swap.")
    if entrada not in SOL_MINTS or saida not in SOL_MINTS:
        raise ValueError(f"{entrada}/{saida} não tem par cotado na Jupiter.")
    if kind == "compra" and symbol == "USDC" and entrada == "SOL":
        if preco_sol is None or preco_sol <= 0:
            raise ValueError("Sem preço do SOL para calcular a compra de USDC.")
        amount = _units(quantidade / preco_sol, SOL_DECIMALS["SOL"])
    else:
        amount = _units(quantidade, SOL_DECIMALS[entrada])
    if amount <= 0:
        raise ValueError("A quantidade do swap Solana ficou zerada.")
    return SOL_MINTS[entrada], SOL_MINTS[saida], amount, texto


async def _jup_json(client: httpx.AsyncClient, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    for base in JUPITER_BASES:
        try:
            response = await client.request(method, f"{base}{path}", **kwargs)
        except httpx.HTTPError:
            continue
        if response.status_code == 200:
            payload = response.json()
            if isinstance(payload, dict):
                return payload
        if response.status_code == 400:
            try:
                detail = response.json().get("error")
            except ValueError:
                detail = None
            if isinstance(detail, str) and detail:
                raise ValueError("A Jupiter recusou este lote.")
    raise ValueError("A cotação da Jupiter não chegou.")


async def _um_swap_jupiter(
    client: httpx.AsyncClient,
    order: dict[str, Any],
    payer: str,
    preco_sol: Decimal | None,
) -> dict[str, Any]:
    entrada, saida, amount, texto = _par_jupiter(order, preco_sol)
    quote = await _jup_json(
        client,
        "GET",
        "/quote",
        params={
            "inputMint": entrada,
            "outputMint": saida,
            "amount": str(amount),
            "slippageBps": str(SLIPPAGE_BPS),
        },
    )
    if int(quote.get("slippageBps") or 10_000) > SLIPPAGE_BPS:
        raise ValueError("A Jupiter devolveu slippage acima de 1%. O swap ficou de fora.")
    if str(quote.get("inAmount")) != str(amount):
        raise ValueError("A quantidade cotada não confere com a proposta.")
    if quote.get("inputMint") != entrada or quote.get("outputMint") != saida:
        raise ValueError("O par cotado não confere com a proposta.")
    built = await _jup_json(
        client,
        "POST",
        "/swap",
        json={
            "quoteResponse": quote,
            "userPublicKey": payer,
            "wrapAndUnwrapSol": True,
            "dynamicComputeUnitLimit": True,
        },
    )
    encoded = built.get("swapTransaction")
    if not isinstance(encoded, str) or not encoded:
        raise ValueError("A Jupiter não devolveu a transação do swap.")
    lote = conferir_lote_jupiter(base64.b64decode(encoded), payer)
    lote["descricao"] = texto
    altura = built.get("lastValidBlockHeight")
    if isinstance(altura, int):
        lote["last_valid_block_height"] = altura
    return lote


async def cotar_swaps_jupiter(
    orders: list[dict[str, Any]], payer: str
) -> tuple[list[dict[str, Any]], list[str]]:
    """Cota cada swap Solana e devolve as V0 já conferidas."""
    try:
        Pubkey.from_string(payer)
    except Exception as exc:
        raise ValueError("A chave Solana da Phantom não é válida.") from exc
    swaps = [
        order
        for order in orders
        if order.get("tipo") in {"compra", "venda"} and str(order.get("rede", "")).lower() == "solana"
    ]
    if not swaps:
        return [], []
    preco = _preco_sol(orders)
    lotes: list[dict[str, Any]] = []
    avisos: list[str] = []
    async with httpx.AsyncClient(timeout=20.0) as client:
        for order in swaps:
            try:
                lotes.append(await _um_swap_jupiter(client, order, payer, preco))
            except ValueError as exc:
                avisos.append(str(exc))
    return lotes, avisos


def _juntar_lotes(lotes: list[dict[str, Any]]) -> dict[str, Any]:
    programas = []
    for lote in lotes:
        if int(lote.get("slippage_bps", SLIPPAGE_BPS + 1)) > SLIPPAGE_BPS:
            raise ValueError("O slippage do lote Solana passa de 1%.")
        for program in lote.get("programas", []):
            if program["programa"] not in SOLANA_PROGRAMS:
                raise ValueError(f"Programa Solana fora da lista: {program['programa']}")
            programas.append(program)
    return {
        "rede": "solana",
        "versao": "v0",
        "custodia": False,
        "move_tokens": True,
        "protocolo": "Jupiter",
        "slippage_bps": SLIPPAGE_BPS,
        "programas": programas,
        "lotes": lotes,
        "serialized_base64": lotes[0]["serialized_base64"],
        "pagador": lotes[0].get("pagador"),
    }


def _auditar(
    chamadas: list[dict[str, Any]],
    solana: dict[str, Any] | None,
    limite: dict[str, Any] | None,
    *,
    exige_protecao: bool = True,
) -> dict[str, Any]:
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
    limite_ok = limite is not None and int(limite["slippage_bps"]) <= SLIPPAGE_BPS
    stop_ok = limite_ok if exige_protecao else True
    slippage_ok = SLIPPAGE_BPS == 100 and (solana is None or int(solana.get("slippage_bps", 100)) <= 100)
    if limite is not None and int(limite["slippage_bps"]) > SLIPPAGE_BPS:
        slippage_ok = False
    if limite_ok:
        protecao = {"rotulo": "Proteção definida: sim", "ok": True}
    elif not exige_protecao:
        protecao = {"rotulo": "Proteção de queda: fora deste lote", "ok": False}
    else:
        protecao = {"rotulo": "Proteção definida: não", "ok": False}
    ok = contracts_ok and slippage_ok and stop_ok and bool(chamadas or solana or limite)
    return {
        "ok": bool(ok),
        "slippage_max_bps": SLIPPAGE_BPS,
        "itens": [
            {"rotulo": "Slippage máximo: 1%", "ok": slippage_ok},
            {
                "rotulo": "Contratos conferidos: sim" if contracts_ok else "Contratos conferidos: não",
                "ok": contracts_ok,
            },
            protecao,
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
    lotes_solana: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Monta o lote. Sem pagador, devolve só a conferência prévia.

    A cotação ao vivo da Jupiter traz o próprio blockhash. O argumento
    `blockhash` só entra quando o teste injeta os bytes do swap.
    """
    avisos: list[str] = []
    chamadas: list[dict[str, Any]] = []
    limite = None
    viu_swap_solana = False
    viu_stop_solana = False
    recipient = pagador_ethereum or ZERO
    for order in orders:
        kind = order["tipo"]
        chain = str(order.get("rede", "")).lower()
        try:
            if kind in {"compra", "venda"} and chain == "solana":
                viu_swap_solana = True
            elif kind in {"compra", "venda"} and chain in {"ethereum", "eth"}:
                chamadas.extend(chamada_uniswap(order, recipient))
            elif kind == "pool" and chain == "solana":
                avisos.append(f"{order.get('simbolo')} não entra no Aave V3 da Ethereum.")
            elif kind == "pool":
                chamadas.extend(chamadas_aave(order, recipient))
            elif kind == "stop" and chain == "solana":
                viu_stop_solana = True
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
    if viu_stop_solana:
        avisos.append(PROTECAO_SOLANA)
    solana = None
    if viu_swap_solana and solana_swap is not None and pagador_solana and blockhash and lotes_solana is None:
        solana = _juntar_lotes([lote_jupiter(pagador_solana, blockhash, solana_swap)])
    elif lotes_solana:
        solana = _juntar_lotes(lotes_solana)
    elif viu_swap_solana and lotes_solana is None:
        avisos.append("Conecte a Phantom na Solana para a Jupiter cotar o swap.")
    elif viu_swap_solana and pagador_solana and not lotes_solana:
        avisos.append("A cotação da Jupiter não chegou. O swap Solana ficou de fora deste lote.")
    exige_protecao = any(
        order.get("tipo") == "stop" and str(order.get("rede", "")).lower() in {"ethereum", "eth"}
        for order in orders
    )
    auditoria = _auditar(chamadas, solana, limite, exige_protecao=exige_protecao)
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
