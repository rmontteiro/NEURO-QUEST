import base64
import unittest

from eth_abi import decode
from solders.keypair import Keypair
from solders.signature import Signature
from solders.transaction import Transaction
from web3 import Web3

from app.txbuild import MULTICALL, build_bundle


class TxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payer_solana = str(Keypair().pubkey())
        self.payer_base = "0x0000000000000000000000000000000000000001"
        self.orders = [
            {
                "tipo": "venda",
                "simbolo": "ETH",
                "simbolo_par": "USDC",
                "rede": "ethereum",
                "quantidade": 0.18,
                "preco_usd": 3450.0,
                "gatilho_usd": None,
                "token_base": "0x4200000000000000000000000000000000000006",
                "token_par_base": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            },
            {
                "tipo": "compra",
                "simbolo": "AAVE",
                "simbolo_par": "USDC",
                "rede": "arbitrum",
                "quantidade": 0.21,
                "preco_usd": 168.0,
                "gatilho_usd": None,
                "token_base": None,
                "token_par_base": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            },
            {
                "tipo": "stop",
                "simbolo": "ETH",
                "simbolo_par": None,
                "rede": "ethereum",
                "quantidade": 0.18,
                "preco_usd": 3450.0,
                "gatilho_usd": 2932.5,
                "token_base": "0x4200000000000000000000000000000000000006",
                "token_par_base": None,
            },
            {
                "tipo": "pool",
                "simbolo": "ETH",
                "simbolo_par": "WBTC",
                "rede": "ethereum",
                "quantidade": 0.036,
                "preco_usd": 3450.0,
                "gatilho_usd": None,
                "token_base": "0x4200000000000000000000000000000000000006",
                "token_par_base": None,
            },
        ]

    def test_one_unsigned_transaction_per_network(self) -> None:
        bundle = build_bundle(self.orders, self.payer_solana, self.payer_base, None)
        self.assertFalse(bundle["move_tokens"])
        self.assertEqual(bundle["ordens"], ["venda", "compra", "stop", "pool"])

        solana = bundle["solana"]
        raw = base64.b64decode(solana["serialized_base64"])
        self.assertLessEqual(len(raw), 1232)
        parsed = Transaction.from_bytes(raw)
        self.assertEqual(parsed.signatures[0], Signature.default())
        blob = raw
        for kind in (b"NQ|venda|ETH", b"NQ|compra|AAVE", b"NQ|stop|ETH", b"NQ|pool|ETH"):
            self.assertIn(kind, blob)
        self.assertTrue(solana["blockhash_provisorio"])
        self.assertNotIn("private_key", solana)

        base = bundle["base"]
        tx = base["transacao"]
        self.assertEqual(tx["from"], tx["to"])
        self.assertEqual(tx["value"], "0x0")
        self.assertEqual(tx["chainId"], "0x2105")
        body = bytes.fromhex(tx["data"][2:])[4:]
        decoded = decode(["(uint8,address,address,uint256,uint256,uint256)[]"], body)
        self.assertEqual([item[0] for item in decoded[0]], [2, 1, 3, 4])
        self.assertTrue(any(call["tipo"] == "multicall" and call["data"].startswith("0x5ae401dc") for call in base["chamadas_prontas"]))
        self.assertTrue(all(call["incluida_na_transacao"] is False for call in base["chamadas_prontas"]))
        self.assertIn("04e45aaf", next(call["data"] for call in base["chamadas_prontas"] if call["tipo"] == "multicall"))
        self.assertEqual(Web3.keccak(text=MULTICALL)[:4].hex(), "5ae401dc")

    def test_rejects_missing_payer(self) -> None:
        with self.assertRaises(ValueError):
            build_bundle(self.orders, None, None, None)


if __name__ == "__main__":
    unittest.main()
