from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "skills/metron-policy/scripts"))

import circle
import finance
import store


PAYER = "0x1111111111111111111111111111111111111111"
PAYEE = "0x2222222222222222222222222222222222222222"
MERCHANT = "0x3333333333333333333333333333333333333333"
TX_HASH = "0x" + "a" * 64
BLOCK_HASH = "0x" + "b" * 64
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
NATIVE_USDC_EMITTER = "0xfffffffffffffffffffffffffffffffffffffffe"
GATEWAY_TRANSFER_ID = "00000000-0000-4000-8000-000000000001"


def word(value: str) -> str:
    return "0x" + "0" * 24 + value.removeprefix("0x")


def incoming_circle_record() -> dict:
    return {
        "id": "circle-incoming-1",
        "state": "COMPLETE",
        "transactionType": "INBOUND",
        "operation": "TRANSFER",
        "blockchain": "ARC-TESTNET",
        "amounts": ["0.5"],
        "sourceAddress": PAYER,
        "destinationAddress": PAYEE,
        "txHash": TX_HASH,
        "blockHeight": 12345,
        "blockHash": BLOCK_HASH,
    }


def arc_receipt(sender: str, recipient: str) -> dict:
    return {
        "status": "0x1",
        "transactionHash": TX_HASH,
        "blockNumber": hex(12345),
        "blockHash": BLOCK_HASH,
        "transaction": {
            "hash": TX_HASH,
            "blockNumber": hex(12345),
            "blockHash": BLOCK_HASH,
            "from": sender,
            "to": recipient,
            "value": "0x" + f"{5 * 10**17:064x}",
        },
        "logs": [{
            "address": NATIVE_USDC_EMITTER,
            "topics": [TRANSFER_TOPIC, word(sender), word(recipient)],
            "data": "0x" + f"{5 * 10**17:064x}",
            "transactionHash": TX_HASH,
            "blockNumber": hex(12345),
            "blockHash": BLOCK_HASH,
            "removed": False,
        }],
    }


def gateway_transfer(status: str = "confirmed") -> dict:
    return {
        "id": GATEWAY_TRANSFER_ID,
        "status": status,
        "amount": "500000",
        "token": "USDC",
        "sendingNetwork": "eip155:5042002",
        "recipientNetwork": "eip155:5042002",
        "fromAddress": PAYER,
        "toAddress": MERCHANT,
        "nonce": "0x" + "1" * 64,
        "createdAt": "2026-10-15T13:37:11Z",
        "updatedAt": "2026-10-15T13:38:11Z",
        "txHash": TX_HASH,
    }


class PaymentEvidenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        state_home = Path(self.temporary.name)
        self.store_paths = patch.multiple(
            store,
            STATE_HOME=state_home,
            DATABASE=state_home / "metron.sqlite",
            CONFIG=state_home / "config.json",
        )
        self.store_paths.start()
        store.initialize()
        store.write_config({"chain": "ARC-TESTNET", "operating_wallet": PAYER})
        self.db = store.connect()
        self.goal = finance.create_goal(self.db, {
            "revenue_target": "50",
            "policy": {
                "operating_budget": "10",
                "max_spend_per_action": "2",
                "max_daily_spend": "8",
                "minimum_wallet_balance": "0",
                "minimum_deal": "1",
                "reinvestment_bps": 2000,
            },
        })["id"]

    def tearDown(self) -> None:
        self.db.close()
        self.store_paths.stop()
        self.temporary.cleanup()

    def create_intent(self, scheme: str = "exact", payment_id: str | None = None) -> str:
        intent = finance.propose_spend(self.db, {
            "goal_id": self.goal,
            "provider": "TEST-MERCHANT",
            "service_url": "https://example.com/pay",
            "http_method": "POST",
            "payment_scheme": scheme,
            "accepted_chains": ["eip155:5042002"],
            "payee_address": MERCHANT,
            "purpose": "test payment evidence",
            "reason": "isolated regression fixture",
            "expected_output": "test response",
            "quoted_cost": "0.5",
            "max_cost": "0.5",
            "body": {},
        })
        with store.transaction(self.db):
            self.db.execute(
                "UPDATE spend_intents SET status='SUBMITTED',provider_payment_id=?,provider_amount_atomic=500000,executed_payment_scheme=? WHERE id=?",
                (payment_id, scheme, intent["id"]),
            )
        return intent["id"]

    def add_invoice(self, suffix: str) -> str:
        counterparty = f"CP-{suffix}"
        deal = f"DEAL-{suffix}"
        invoice = f"INV-{suffix}"
        timestamp = finance.now()
        self.db.execute(
            "INSERT INTO counterparties(id,kind,name,created_at) VALUES (?,?,?,?)",
            (counterparty, "CUSTOMER", "Fixture", timestamp),
        )
        self.db.execute(
            "INSERT INTO deals(id,counterparty_id,goal_id,amount_atomic,currency,terms_json,status,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (deal, counterparty, self.goal, 500000, "USDC", json.dumps({"payer_wallet": PAYER}), "INVOICED", timestamp),
        )
        self.db.execute(
            "INSERT INTO sales_invoices(id,deal_id,counterparty_id,amount_atomic,currency,status) VALUES (?,?,?,?,?,?)",
            (invoice, deal, counterparty, 500000, "USDC", "OPEN"),
        )
        return invoice

    def test_arc_exact_payment_creates_one_balanced_expense_record(self) -> None:
        intent_id = self.create_intent()
        record = incoming_circle_record()
        record["transactionType"] = "OUTBOUND"
        record["destinationAddress"] = MERCHANT
        evidence = circle.normalize_transaction(
            record, arc_receipt(PAYER, MERCHANT)
        )
        evidence.update(direction="OUT")

        result = finance.record_spend_result(self.db, intent_id, evidence)

        self.assertEqual(result["status"], "CONFIRMED")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM payment_entries").fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM payment_evidence").fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0], 1)
        self.assertEqual(
            tuple(self.db.execute("SELECT SUM(debit_atomic),SUM(credit_atomic) FROM journal_lines").fetchone()),
            (500000, 500000),
        )

    def test_gateway_batched_is_unknown_until_circle_reports_settled(self) -> None:
        intent_id = self.create_intent("GatewayWalletBatched")
        pending = circle.normalize_gateway_x402_transfer(gateway_transfer("batched"), GATEWAY_TRANSFER_ID, "ARC-TESTNET")

        result = finance.record_spend_result(self.db, intent_id, pending, expected_sender=PAYER)

        self.assertEqual(result["status"], "UNKNOWN")
        self.assertFalse(pending["settlement_verified"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM payment_entries").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0], 0)

    def test_gateway_x402_confirmed_evidence_is_recorded_once(self) -> None:
        intent_id = self.create_intent("GatewayWalletBatched")
        evidence = circle.normalize_gateway_x402_transfer(gateway_transfer(), GATEWAY_TRANSFER_ID, "ARC-TESTNET")

        result = finance.record_spend_result(self.db, intent_id, evidence, expected_sender=PAYER)

        self.assertEqual(result["status"], "CONFIRMED")
        self.assertTrue(evidence["settlement_verified"])
        self.assertEqual(self.db.execute("SELECT evidence_type FROM payment_evidence").fetchone()[0], "CIRCLE_GATEWAY_X402_TRANSFER")

    def test_gateway_evidence_cannot_fall_back_to_exact_scheme(self) -> None:
        intent_id = self.create_intent("exact")
        evidence = circle.normalize_gateway_x402_transfer(gateway_transfer(), GATEWAY_TRANSFER_ID, "ARC-TESTNET")

        result = finance.record_spend_result(self.db, intent_id, evidence, expected_sender=PAYER)

        self.assertEqual(result["status"], "UNKNOWN")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM payment_entries").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0], 0)

    def test_gateway_unknown_can_reconcile_once_without_double_spend(self) -> None:
        intent_id = self.create_intent("GatewayWalletBatched")
        pending = circle.normalize_gateway_x402_transfer(gateway_transfer("batched"), GATEWAY_TRANSFER_ID, "ARC-TESTNET")
        finance.record_spend_result(self.db, intent_id, pending, expected_sender=PAYER)
        settled = circle.normalize_gateway_x402_transfer(gateway_transfer("confirmed"), GATEWAY_TRANSFER_ID, "ARC-TESTNET")

        result = finance.record_spend_result(self.db, intent_id, settled, expected_sender=PAYER)

        self.assertEqual(result["status"], "CONFIRMED")
        with self.assertRaises(finance.DomainError) as replay:
            finance.record_spend_result(self.db, intent_id, settled, expected_sender=PAYER)
        self.assertEqual(replay.exception.code, "METRON_SPEND_DENIED")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM payment_entries").fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0], 1)

    def test_provider_reference_replay_across_spend_intents_fails_atomically(self) -> None:
        first = self.create_intent(payment_id="circle-outgoing-1")
        second = self.create_intent()
        record = {
            "provider": "CIRCLE",
            "provider_ref": "circle-outgoing-1",
            "evidence_type": "CIRCLE_TRANSACTION",
            "status": "confirmed",
            "settlement_verified": True,
            "direction": "OUT",
            "amount_atomic": 500000,
            "currency": "USDC",
            "from_address": PAYER,
            "to_address": MERCHANT,
            "chain": "ARC-TESTNET",
            "raw_evidence_hash": "a" * 64,
        }
        finance.record_spend_result(self.db, first, record)

        with self.assertRaises(finance.DomainError) as replay:
            finance.record_spend_result(self.db, second, record)

        self.assertEqual(replay.exception.code, "METRON_PAYMENT_ALREADY_CONSUMED")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM payment_entries").fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM payment_evidence").fetchone()[0], 1)

    def test_same_arc_transaction_hash_cannot_be_recorded_under_another_circle_reference(self) -> None:
        first = self.create_intent(payment_id="circle-outgoing-1")
        second = self.create_intent(payment_id="circle-outgoing-2")
        record = {
            "provider": "CIRCLE",
            "provider_ref": "circle-outgoing-1",
            "evidence_type": "CIRCLE_TRANSACTION",
            "status": "confirmed",
            "settlement_verified": True,
            "direction": "OUT",
            "amount_atomic": 500000,
            "currency": "USDC",
            "from_address": PAYER,
            "to_address": MERCHANT,
            "chain": "ARC-TESTNET",
            "tx_hash": TX_HASH,
            "raw_evidence_hash": "a" * 64,
        }
        finance.record_spend_result(self.db, first, record)

        with self.assertRaises(finance.DomainError) as error:
            finance.record_spend_result(
                self.db,
                second,
                {
                    **record,
                    "provider_ref": "circle-outgoing-2",
                    "tx_hash": TX_HASH[:2] + TX_HASH[2:].upper(),
                },
            )

        self.assertEqual(error.exception.code, "METRON_PAYMENT_ALREADY_CONSUMED")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM payment_entries").fetchone()[0], 1)

    def test_gateway_batch_hash_can_be_shared_by_distinct_transfer_ids(self) -> None:
        first = self.create_intent("GatewayWalletBatched", "gateway-transfer-1")
        second = self.create_intent("GatewayWalletBatched", "gateway-transfer-2")
        first_transfer = {**gateway_transfer(), "id": "00000000-0000-4000-8000-000000000001"}
        second_transfer = {**gateway_transfer(), "id": "00000000-0000-4000-8000-000000000002"}
        first_evidence = circle.normalize_gateway_x402_transfer(first_transfer, first_transfer["id"], "ARC-TESTNET")
        second_evidence = circle.normalize_gateway_x402_transfer(second_transfer, second_transfer["id"], "ARC-TESTNET")
        first_evidence["provider_ref"] = "gateway-transfer-1"
        second_evidence["provider_ref"] = "gateway-transfer-2"

        finance.record_spend_result(self.db, first, first_evidence, expected_sender=PAYER)
        finance.record_spend_result(self.db, second, second_evidence, expected_sender=PAYER)

        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM payment_entries").fetchone()[0], 2)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0], 2)

    def test_incoming_payment_replay_across_open_invoices_fails_atomically(self) -> None:
        first = self.add_invoice("1")
        second = self.add_invoice("2")
        store.write_config({"chain": "ARC-TESTNET", "operating_wallet": PAYEE})
        evidence = circle.normalize_transaction(
            incoming_circle_record(), arc_receipt(PAYER, PAYEE)
        )

        result = finance.reconcile_invoice(self.db, first, evidence)

        self.assertEqual(result["status"], "PAID")
        with self.assertRaises(finance.DomainError) as replay:
            finance.reconcile_invoice(self.db, second, evidence)
        self.assertEqual(replay.exception.code, "METRON_PAYMENT_ALREADY_CONSUMED")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM payment_entries").fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM payment_evidence").fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT status FROM sales_invoices WHERE id=?", (second,)).fetchone()[0], "OPEN")

    def test_same_arc_transaction_hash_cannot_be_reconciled_under_another_circle_reference(self) -> None:
        first = self.add_invoice("1")
        second = self.add_invoice("2")
        store.write_config({"chain": "ARC-TESTNET", "operating_wallet": PAYEE})
        evidence = circle.normalize_transaction(
            incoming_circle_record(), arc_receipt(PAYER, PAYEE)
        )
        finance.reconcile_invoice(self.db, first, evidence)

        with self.assertRaises(finance.DomainError) as error:
            finance.reconcile_invoice(
                self.db,
                second,
                {
                    **evidence,
                    "provider_ref": "different-circle-reference",
                    "tx_hash": TX_HASH[:2] + TX_HASH[2:].upper(),
                },
            )

        self.assertEqual(error.exception.code, "METRON_PAYMENT_ALREADY_CONSUMED")
        self.assertEqual(self.db.execute("SELECT status FROM sales_invoices WHERE id=?", (second,)).fetchone()[0], "OPEN")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM payment_entries").fetchone()[0], 1)

    def test_circle_complete_without_receipt_cannot_reconcile_invoice(self) -> None:
        invoice = self.add_invoice("1")
        store.write_config({"chain": "ARC-TESTNET", "operating_wallet": PAYEE})
        unverified = circle.normalize_transaction(incoming_circle_record())

        with self.assertRaises(finance.DomainError) as error:
            finance.reconcile_invoice(self.db, invoice, unverified)

        self.assertEqual(error.exception.code, "METRON_RECONCILIATION_MISMATCH")
        self.assertEqual(self.db.execute("SELECT status FROM sales_invoices WHERE id=?", (invoice,)).fetchone()[0], "OPEN")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM payment_entries").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0], 0)

    def test_legacy_payment_entry_reference_is_still_consumed(self) -> None:
        invoice = self.add_invoice("1")
        store.write_config({"chain": "ARC-TESTNET", "operating_wallet": PAYEE})
        evidence = circle.normalize_transaction(
            incoming_circle_record(), arc_receipt(PAYER, PAYEE)
        )
        self.db.execute(
            "INSERT INTO payment_entries(id,source_type,source_id,direction,amount_atomic,currency,provider,provider_payment_id,status,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("PE-LEGACY", "LEGACY", "LEGACY-1", "IN", 500000, "USDC", "CIRCLE", evidence["provider_ref"], "RECONCILED", finance.now()),
        )

        with self.assertRaises(finance.DomainError) as replay:
            finance.reconcile_invoice(self.db, invoice, evidence)

        self.assertEqual(replay.exception.code, "METRON_PAYMENT_ALREADY_CONSUMED")
        self.assertEqual(self.db.execute("SELECT status FROM sales_invoices WHERE id=?", (invoice,)).fetchone()[0], "OPEN")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM payment_entries").fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
