import unittest
from decimal import Decimal

from eth_abi import decode
from solders.pubkey import Pubkey

from app.router_defi import (
    AAVE_POOL,
    FALHA_FUNDOS,
    FALHA_RECUSA,
    FALHA_SLIPPAGE,
    JUPITER_V6,
    SLIPPAGE_BPS,
    SWAP_ROUTER_02,
    build_route,
    chamada_approve,
    classificar_falha,
    lote_jupiter,
    ordem_limite,
    pack_v0,
)
from solders.instruction import AccountMeta, Instruction
from solders.pubkey import Pubkey as SoldersPubkey


PAYER = "0x0000000000000000000000000000000000000001"
SOL = "So11111111111111111111111111111111111111112"
BLOCKHASH = "4uQeVj5tqViQh7yWWGStvkEG1Zmhx6uasJtWCJziofM"


def _orders() -> list[dict]:
    return [
        {
            "tipo": "venda",
            "simbolo": "ETH",
            "simbolo_par": "USDC",
            "rede": "ethereum",
            "quantidade": 0.18,
            "preco_usd": 3450.0,
            "gatilho_usd": None,
        },
        {
            "tipo": "stop",
            "simbolo": "ETH",
            "simbolo_par": "USDC",
            "rede": "ethereum",
            "quantidade": 0.18,
            "preco_usd": 3450.0,
            "gatilho_usd": 2932.5,
        },
        {
            "tipo": "pool",
            "simbolo": "ETH",
            "simbolo_par": "WBTC",
            "rede": "ethereum",
            "quantidade": 0.036,
            "preco_usd": 3450.0,
            "gatilho_usd": None,
        },
    ]


class RouterTests(unittest.TestCase):
    def test_v0_packs_jupiter_and_compute_budget(self) -> None:
        packed = lote_jupiter(SOL, BLOCKHASH, bytes([9, 9, 9]))
        self.assertEqual(packed["versao"], "v0")
        self.assertFalse(packed["custodia"])
        self.assertEqual(packed["slippage_bps"], 100)
        names = [item["programa"] for item in packed["programas"]]
        self.assertIn(JUPITER_V6, names)
        self.assertIn("ComputeBudget111111111111111111111111111111", names)
        self.assertLessEqual(packed["tamanho_bytes"], 1232)

    def test_unknown_program_is_rejected(self) -> None:
        stranger = Instruction(
            SoldersPubkey.new_unique(),
            bytes([1]),
            [AccountMeta(Pubkey.from_string(SOL), True, True)],
        )
        with self.assertRaises(ValueError):
            pack_v0(SOL, [stranger], BLOCKHASH)

    def test_slippage_above_one_percent_is_refused(self) -> None:
        from app.router_defi import _min_out

        with self.assertRaises(ValueError):
            _min_out(Decimal("1"), Decimal("100"), 6, bps=250)

    def test_preview_stays_on_the_desk(self) -> None:
        route = build_route(_orders())
        self.assertFalse(route["enviar"])
        self.assertFalse(route["custodia"])
        self.assertTrue(route["auditoria"]["ok"])
        swap = next(call for call in route["chamadas"] if call["data"].startswith("0x04e45aaf"))
        encoded = bytes.fromhex(swap["data"][10:])
        recipient = decode(["(address,address,uint24,address,uint256,uint256,uint160)"], encoded)[0][3]
        self.assertEqual(recipient, "0x0000000000000000000000000000000000000000")

    def test_foreign_chain_is_only_an_aviso(self) -> None:
        orders = _orders() + [
            {
                "tipo": "compra",
                "simbolo": "AAVE",
                "simbolo_par": "USDC",
                "rede": "arbitrum",
                "quantidade": 4.2,
                "preco_usd": 168.0,
                "gatilho_usd": None,
            }
        ]
        route = build_route(orders, pagador_ethereum=PAYER)
        self.assertTrue(any("arbitrum" in aviso for aviso in route["avisos"]))
        self.assertTrue(route["auditoria"]["ok"])

    def test_route_sets_the_three_checks(self) -> None:
        route = build_route(_orders(), pagador_ethereum=PAYER)
        labels = [item["rotulo"] for item in route["auditoria"]["itens"]]
        self.assertEqual(
            labels,
            [
                "Slippage máximo: 1%",
                "Contratos conferidos: sim",
                "Proteção definida: sim",
            ],
        )
        self.assertTrue(route["auditoria"]["ok"])
        self.assertEqual(route["limite"]["slippage_bps"], SLIPPAGE_BPS)
        targets = {call["para"].lower() for call in route["chamadas"]}
        self.assertIn(SWAP_ROUTER_02.lower(), targets)
        self.assertIn(AAVE_POOL.lower(), targets)
        swap = next(call for call in route["chamadas"] if call["data"].startswith("0x04e45aaf"))
        encoded = bytes.fromhex(swap["data"][10:])
        params = decode(["(address,address,uint24,address,uint256,uint256,uint160)"], encoded)[0]
        self.assertEqual(params[3].lower(), PAYER.lower())
        expected_min = int(Decimal("0.18") * Decimal("3450") * Decimal("0.99") * Decimal(10) ** 6)
        self.assertEqual(params[5], expected_min)
        supply = next(call for call in route["chamadas"] if call["data"].startswith("0x617ba037"))
        self.assertEqual(supply["para"].lower(), AAVE_POOL.lower())
        for call in route["chamadas"]:
            if call["data"].startswith("0x095ea7b3"):
                spender, amount = decode(["address", "uint256"], bytes.fromhex(call["data"][10:]))
                self.assertLess(amount, 2**256 - 1)
                self.assertIn(spender.lower(), {SWAP_ROUTER_02.lower(), AAVE_POOL.lower(), "0xc92e8bdf79f0507f65a392b0ab4667716bfe0110"})

    def test_foreign_spender_fails_before_the_audit(self) -> None:
        with self.assertRaises(ValueError):
            chamada_approve(
                "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
                "0x0000000000000000000000000000000000000002",
                10,
                "approve ruim",
            )

    def test_stop_buy_amount_is_one_percent_under_the_trigger(self) -> None:
        limit = ordem_limite(_orders()[1], PAYER)
        message = limit["typed_data"]["message"]
        self.assertEqual(message["kind"], "sell")
        self.assertEqual(message["feeAmount"], "0")
        self.assertEqual(message["buyAmount"], str(int(Decimal("0.18") * Decimal("2932.5") * Decimal("0.99") * Decimal(10) ** 6)))

    def test_game_dialogs_for_the_three_failures(self) -> None:
        self.assertEqual(classificar_falha("insufficient funds for gas"), FALHA_FUNDOS)
        self.assertEqual(classificar_falha("SlippageToleranceExceeded"), FALHA_SLIPPAGE)
        self.assertEqual(classificar_falha("User rejected the request", code=4001), FALHA_RECUSA)


if __name__ == "__main__":
    unittest.main()
