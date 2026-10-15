from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import call, patch


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "skills/metron-policy/scripts"))

import circle


PAYER = "0x1111111111111111111111111111111111111111"
PAYEE = "0x2222222222222222222222222222222222222222"
TX_HASH = "0x" + "a" * 64
BLOCK_HASH = "0x" + "b" * 64
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
NATIVE_USDC_EMITTER = "0xfffffffffffffffffffffffffffffffffffffffe"
ERC20_USDC_CONTRACT = "0x3600000000000000000000000000000000000000"


def word(value: str) -> str:
    return "0x" + "0" * 24 + value.removeprefix("0x")


def circle_record() -> dict:
    return {
        "id": "circle-transaction-1",
        "state": "COMPLETE",
        "transactionType": "INBOUND",
        "operation": "TRANSFER",
        "blockchain": "ARC-TESTNET",
        "amounts": ["22"],
        "sourceAddress": PAYER,
        "destinationAddress": PAYEE,
        "txHash": TX_HASH,
        "blockHeight": 12345,
        "blockHash": BLOCK_HASH,
        "firstConfirmDate": "2026-10-15T13:37:11Z",
    }


def arc_receipt() -> dict:
    return {
        "status": "0x1",
        "transactionHash": TX_HASH,
        "blockNumber": hex(12345),
        "blockHash": BLOCK_HASH,
        "transaction": {
            "hash": TX_HASH,
            "blockNumber": hex(12345),
            "blockHash": BLOCK_HASH,
            "from": PAYER,
            "to": PAYEE,
            "value": "0x" + f"{22 * 10**18:064x}",
        },
        "logs": [
            {
                "address": NATIVE_USDC_EMITTER,
                "topics": [TRANSFER_TOPIC, word(PAYER), word(PAYEE)],
                "data": "0x" + f"{22 * 10**18:064x}",
                "transactionHash": TX_HASH,
                "blockNumber": hex(12345),
                "blockHash": BLOCK_HASH,
                "removed": False,
            }
        ],
    }


class CircleTransactionNormalizationTest(unittest.TestCase):
    def test_circle_complete_without_receipt_stays_unverified(self) -> None:
        result = circle.normalize_transaction(circle_record())

        self.assertEqual(result["status"], "unverified")
        self.assertEqual(result["provider_status"], "complete")
        self.assertIsNone(result["amount_atomic"])
        self.assertIsNone(result["currency"])
        self.assertFalse(result["settlement_verified"])

    def test_circle_confirmed_before_terminal_completion_stays_unverified(self) -> None:
        record = circle_record()
        record["state"] = "CONFIRMED"
        record["currency"] = "USDC"
        record["amount"] = "22"

        result = circle.normalize_transaction(record)

        self.assertEqual(result["status"], "unverified")
        self.assertEqual(result["provider_status"], "confirmed")
        self.assertFalse(result["settlement_verified"])

    def test_native_usdc_complete_is_confirmed_from_verified_receipt(self) -> None:
        result = circle.normalize_transaction(circle_record(), arc_receipt())

        self.assertEqual(result["status"], "confirmed")
        self.assertEqual(result["direction"], "IN")
        self.assertEqual(result["currency"], "USDC")
        self.assertEqual(result["amount_atomic"], 22_000_000)
        self.assertEqual(result["from_address"], PAYER)
        self.assertEqual(result["to_address"], PAYEE)
        self.assertEqual(result["chain"], "ARC-TESTNET")
        self.assertTrue(result["settlement_verified"])

    def test_find_transaction_fetches_receipt_before_confirming_complete(self) -> None:
        response = {"data": {"transactions": [circle_record()]}}
        with patch.object(circle, "arc_transaction_receipt", return_value=arc_receipt()) as fetch:
            result = circle.find_transaction(response, "circle-transaction-1")

        fetch.assert_called_once_with(TX_HASH)
        self.assertEqual(result["status"], "confirmed")
        self.assertEqual(result["amount_atomic"], 22_000_000)

    def test_unrelated_token_transfer_does_not_become_usdc(self) -> None:
        receipt = arc_receipt()
        receipt["logs"][0]["address"] = "0x3333333333333333333333333333333333333333"

        with self.assertRaises(circle.CircleError) as error:
            circle.normalize_transaction(circle_record(), receipt)

        self.assertEqual(error.exception.code, "METRON_RECONCILIATION_MISMATCH")

    def test_circle_amount_must_match_receipt_transfer(self) -> None:
        record = circle_record()
        record["amounts"] = ["23"]

        with self.assertRaises(circle.CircleError) as error:
            circle.normalize_transaction(record, arc_receipt())

        self.assertEqual(error.exception.code, "METRON_RECONCILIATION_MISMATCH")

    def test_circle_sender_and_recipient_must_match_transfer_log(self) -> None:
        for field in ("sourceAddress", "destinationAddress"):
            with self.subTest(field=field):
                record = circle_record()
                record[field] = "0x4444444444444444444444444444444444444444"

                with self.assertRaises(circle.CircleError) as error:
                    circle.normalize_transaction(record, arc_receipt())

                self.assertEqual(error.exception.code, "METRON_RECONCILIATION_MISMATCH")

    def test_failed_or_mismatched_receipt_cannot_confirm(self) -> None:
        for mutate in (
            lambda receipt: receipt.update(status="0x0"),
            lambda receipt: receipt.update(transactionHash="0x" + "c" * 64),
            lambda receipt: receipt.update(blockHash="0x" + "d" * 64),
            lambda receipt: receipt.update(blockNumber=hex(12346)),
        ):
            with self.subTest(mutate=mutate):
                receipt = copy.deepcopy(arc_receipt())
                mutate(receipt)
                with self.assertRaises(circle.CircleError):
                    circle.normalize_transaction(circle_record(), receipt)

    def test_duplicate_matching_transfer_logs_are_rejected(self) -> None:
        receipt = arc_receipt()
        receipt["logs"].append(copy.deepcopy(receipt["logs"][0]))

        with self.assertRaises(circle.CircleError) as error:
            circle.normalize_transaction(circle_record(), receipt)

        self.assertEqual(error.exception.code, "METRON_RECONCILIATION_MISMATCH")

    def test_additional_native_usdc_transfer_is_rejected(self) -> None:
        receipt = arc_receipt()
        extra = copy.deepcopy(receipt["logs"][0])
        extra["topics"] = [TRANSFER_TOPIC, word(PAYER), word("0x4444444444444444444444444444444444444444")]
        extra["data"] = "0x" + f"{10**18:064x}"
        receipt["logs"].append(extra)

        with self.assertRaises(circle.CircleError) as error:
            circle.normalize_transaction(circle_record(), receipt)

        self.assertEqual(error.exception.code, "METRON_RECONCILIATION_MISMATCH")

    def test_unrecognized_transfer_emitter_is_rejected(self) -> None:
        receipt = arc_receipt()
        extra = copy.deepcopy(receipt["logs"][0])
        extra["address"] = "0x4444444444444444444444444444444444444444"
        extra["topics"] = [TRANSFER_TOPIC, word(PAYER), word("0x5555555555555555555555555555555555555555")]
        receipt["logs"].append(extra)

        with self.assertRaises(circle.CircleError) as error:
            circle.normalize_transaction(circle_record(), receipt)

        self.assertEqual(error.exception.code, "METRON_RECONCILIATION_MISMATCH")

    def test_non_usdc_asset_annotation_is_rejected_even_with_matching_amount(self) -> None:
        record = circle_record()
        record["currency"] = "EUR"

        with self.assertRaises(circle.CircleError) as error:
            circle.normalize_transaction(record, arc_receipt())

        self.assertEqual(error.exception.code, "METRON_RECONCILIATION_MISMATCH")

    def test_native_and_erc20_usdc_events_are_not_counted_twice(self) -> None:
        receipt = arc_receipt()
        receipt["logs"].append({
            **copy.deepcopy(receipt["logs"][0]),
            "address": ERC20_USDC_CONTRACT,
            "data": "0x" + f"{22 * 10**6:064x}",
        })

        result = circle.normalize_transaction(circle_record(), receipt)

        self.assertEqual(result["amount_atomic"], 22_000_000)
        self.assertEqual(result["currency"], "USDC")
        self.assertTrue(result["settlement_verified"])

    def test_erc20_companion_must_match_native_transfer(self) -> None:
        for mutate in (
            lambda log: log.update(data="0x" + f"{21 * 10**6:064x}"),
            lambda log: log.update(topics=[TRANSFER_TOPIC, word(PAYER), word("0x4444444444444444444444444444444444444444")]),
            lambda log: log.update(transactionHash="0x" + "c" * 64),
        ):
            with self.subTest(mutate=mutate):
                receipt = arc_receipt()
                companion = copy.deepcopy(receipt["logs"][0])
                companion["address"] = ERC20_USDC_CONTRACT
                companion["data"] = "0x" + f"{22 * 10**6:064x}"
                mutate(companion)
                receipt["logs"].append(companion)

                with self.assertRaises(circle.CircleError) as error:
                    circle.normalize_transaction(circle_record(), receipt)

                self.assertEqual(error.exception.code, "METRON_RECONCILIATION_MISMATCH")

    def test_receipt_cannot_confirm_wrong_circle_chain(self) -> None:
        record = circle_record()
        record["blockchain"] = "BASE-SEPOLIA"

        with self.assertRaises(circle.CircleError) as error:
            circle.normalize_transaction(record, arc_receipt())

        self.assertEqual(error.exception.code, "METRON_RECONCILIATION_MISMATCH")

    def test_receipt_cannot_confirm_unsupported_circle_operation(self) -> None:
        record = circle_record()
        record["operation"] = "CONTRACT_EXECUTION"

        with self.assertRaises(circle.CircleError) as error:
            circle.normalize_transaction(record, arc_receipt())

        self.assertEqual(error.exception.code, "METRON_RECONCILIATION_MISMATCH")

    def test_native_amount_must_convert_exactly_to_six_decimal_accounting_units(self) -> None:
        receipt = arc_receipt()
        receipt["logs"][0]["data"] = "0x" + f"{22 * 10**18 + 1:064x}"

        with self.assertRaises(circle.CircleError) as error:
            circle.normalize_transaction(circle_record(), receipt)

        self.assertEqual(error.exception.code, "METRON_RECONCILIATION_MISMATCH")

    def test_receipt_lookup_requires_arc_testnet_chain_id(self) -> None:
        with patch.object(circle, "_arc_rpc", side_effect=["0x1"]) as request:
            with self.assertRaises(circle.CircleError) as error:
                circle.arc_transaction_receipt(TX_HASH)

        request.assert_called_once_with("eth_chainId", [])
        self.assertEqual(error.exception.code, "METRON_RECONCILIATION_MISMATCH")

    def test_receipt_lookup_reads_receipt_only_after_chain_identity_matches(self) -> None:
        receipt = arc_receipt()
        transaction = receipt["transaction"]
        receipt = {key: value for key, value in receipt.items() if key != "transaction"}
        with patch.object(circle, "_arc_rpc", side_effect=["0x4cef52", transaction, receipt]) as request:
            result = circle.arc_transaction_receipt(TX_HASH)

        self.assertEqual(result, {**receipt, "transaction": transaction})
        self.assertEqual(request.call_args_list, [
            call("eth_chainId", []),
            call("eth_getTransactionByHash", [TX_HASH]),
            call("eth_getTransactionReceipt", [TX_HASH]),
        ])


if __name__ == "__main__":
    unittest.main()
