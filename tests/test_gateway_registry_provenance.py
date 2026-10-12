from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "skills" / "metron" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import registry
import store


WALLET = "0x1111111111111111111111111111111111111111"
BACKING_EOA = "0x2222222222222222222222222222222222222222"
SELLER = "0x3333333333333333333333333333333333333333"
TRANSFER_ID = "6c78e302-4cfd-4ceb-9606-ab21c90b6d14"
TX_HASH = "0x" + "a" * 64


class GatewayRegistryProvenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_paths = store.STATE_HOME, store.DATABASE, store.CONFIG
        self.temp = tempfile.TemporaryDirectory()
        store.STATE_HOME = Path(self.temp.name)
        store.DATABASE = store.STATE_HOME / "metron.sqlite"
        store.CONFIG = store.STATE_HOME / "config.json"
        store.initialize()
        store.write_config({"chain": "ARC-TESTNET", "operating_wallet": WALLET})
        self.db = store.connect()
        self.add_spend_fixture()

    def tearDown(self) -> None:
        self.db.close()
        store.STATE_HOME, store.DATABASE, store.CONFIG = self.original_paths
        self.temp.cleanup()

    def add_spend_fixture(
        self,
        scheme: str = "GatewayWalletBatched",
        sender: str = BACKING_EOA,
        provider_ref: str = TRANSFER_ID,
        evidence_type: str = "CIRCLE_GATEWAY_X402_TRANSFER",
    ) -> None:
        self.db.execute(
            "INSERT INTO goals(id,revenue_target_atomic,currency,status,created_at) VALUES (?,?,?,?,?)",
            ("GOAL-000001", 2_000_000, "USDC", "ACTIVE", "2026-10-12T00:00:00Z"),
        )
        self.db.execute(
            "INSERT INTO spend_intents(id,goal_id,provider,service_url,http_method,payment_scheme,payee_address,"
            "request_body_hash,provider_payment_id,provider_amount_atomic,purpose,reason,expected_output,"
            "quoted_cost_atomic,max_cost_atomic,expected_value_atomic,expected_roi_bps,policy_result,status,"
            "reason_hash,created_at,executed_at,executed_payment_scheme) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "SI-000001", "GOAL-000001", "CIRCLE", "https://service.example.test/x402", "POST", scheme,
                SELLER, "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a", provider_ref, 5000,
                "fixture purpose", "fixture reason", "fixture output", 5000, 5000, 0, 0, "ALLOW", "EXECUTED",
                "reason-hash", "2026-10-12T00:00:00Z", "2026-10-12T00:01:00Z", scheme,
            ),
        )
        self.db.execute(
            "INSERT INTO payment_entries(id,source_type,source_id,direction,amount_atomic,currency,provider,"
            "provider_payment_id,status,created_at,confirmed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            ("PE-000001", "SPEND_INTENT", "SI-000001", "OUT", 5000, "USDC", "CIRCLE", provider_ref,
             "CONFIRMED", "2026-10-12T00:01:00Z", "2026-10-12T00:01:00Z"),
        )
        self.db.execute(
            "INSERT INTO payment_evidence(id,payment_entry_id,provider,evidence_type,provider_ref,chain,tx_hash,"
            "from_address,to_address,amount_atomic,currency,raw_evidence_hash,observed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("EV-000001", "PE-000001", "CIRCLE", evidence_type, provider_ref, "ARC-TESTNET", TX_HASH,
             sender, SELLER, 5000, "USDC", "raw-hash", "2026-10-12T00:01:00Z"),
        )
        self.db.execute(
            "INSERT INTO journal_entries(id,source_type,source_id,description,status,posted_at) VALUES (?,?,?,?,?,?)",
            ("JE-000001", "PAYMENT_ENTRY", "PE-000001", "Circle x402 acquisition expense", "POSTED", "2026-10-12T00:01:00Z"),
        )
        self.db.execute(
            "INSERT INTO journal_lines(journal_entry_id,account_code,debit_atomic,credit_atomic,currency) VALUES (?,?,?,?,?)",
            ("JE-000001", "5000", 5000, 0, "USDC"),
        )
        self.db.execute(
            "INSERT INTO journal_lines(journal_entry_id,account_code,debit_atomic,credit_atomic,currency) VALUES (?,?,?,?,?)",
            ("JE-000001", "1000", 0, 5000, "USDC"),
        )

    def gateway_balance(self) -> dict:
        return {"data": {"address": WALLET, "backingEOA": BACKING_EOA}}

    def test_gateway_sender_uses_circle_backing_eoa_and_preserves_wallet_namespace(self) -> None:
        with patch.object(registry.circle, "gateway_balance", return_value=self.gateway_balance()) as read_balance:
            fields = registry._spend_fields(self.db, "SI-000001")
        read_balance.assert_called_once_with(WALLET, "ARC-TESTNET")
        self.assertEqual(fields["operating_wallet"], WALLET)
        self.assertEqual(fields["spend_id"], "0xe5587d9f5ce85bf14058d4c670359ea5b98a536a3c319bdbf216897df55eaa98")
        self.assertEqual(fields["goal_hash"], "0xcd75fca7e7929baccec2e44d4c951841aeef72733215b8bbc82160c6f60bced1")
        self.assertEqual(fields["spend_intent_hash"], "0xfd620e8cb3b06fbb9d325302197c29769b5f25ac63995464195b7612900b1bb9")
        self.assertEqual(fields["payment_evidence_hash"], "0xe6c8a759d7bdfa3cbc048b704195acb6239c544d4e83fbb7e316e34d1d645633")

    def test_exact_payment_uses_configured_wallet_sender(self) -> None:
        self.db.execute("DELETE FROM payment_evidence WHERE id='EV-000001'")
        self.db.execute("UPDATE spend_intents SET payment_scheme='exact',executed_payment_scheme='exact' WHERE id='SI-000001'")
        self.db.execute(
            "INSERT INTO payment_evidence(id,payment_entry_id,provider,evidence_type,provider_ref,chain,tx_hash,"
            "from_address,to_address,amount_atomic,currency,raw_evidence_hash,observed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("EV-000001", "PE-000001", "CIRCLE", "CIRCLE_TRANSACTION", TRANSFER_ID, "ARC-TESTNET", TX_HASH,
             WALLET, SELLER, 5000, "USDC", "raw-hash", "2026-10-12T00:01:00Z"),
        )
        with patch.object(registry.circle, "gateway_balance") as read_balance:
            fields = registry._spend_fields(self.db, "SI-000001")
        read_balance.assert_not_called()
        self.assertEqual(fields["operating_wallet"], WALLET)

    def test_wrong_gateway_sender_fails_closed(self) -> None:
        self.db.execute("UPDATE payment_evidence SET from_address=? WHERE id='EV-000001'", (WALLET,))
        with patch.object(registry.circle, "gateway_balance", return_value=self.gateway_balance()):
            result = registry.record_spend(self.db, "SI-000001")
        self.assertEqual(result["error_code"], "METRON_REGISTRY_EVIDENCE_INVALID")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM registry_records").fetchone()[0], 0)

    def test_provider_reference_mismatch_fails_closed(self) -> None:
        self.db.execute("UPDATE payment_evidence SET provider_ref='different-transfer' WHERE id='EV-000001'")
        with patch.object(registry.circle, "gateway_balance", return_value=self.gateway_balance()):
            with self.assertRaises(registry.RegistryError):
                registry._spend_fields(self.db, "SI-000001")
        self.db.execute("UPDATE payment_evidence SET provider_ref=? WHERE id='EV-000001'", (TRANSFER_ID,))
        self.db.execute("UPDATE payment_entries SET provider_payment_id='different-transfer' WHERE id='PE-000001'")
        with patch.object(registry.circle, "gateway_balance", return_value=self.gateway_balance()):
            with self.assertRaises(registry.RegistryError):
                registry._spend_fields(self.db, "SI-000001")

    def test_gateway_identity_scheme_and_amount_mismatches_fail_closed(self) -> None:
        with patch.object(registry.circle, "gateway_balance", return_value={"data": {"address": SELLER, "backingEOA": BACKING_EOA}}):
            result = registry.record_spend(self.db, "SI-000001")
        self.assertEqual(result["error_code"], "METRON_CIRCLE_SCHEMA_CHANGED")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM registry_records").fetchone()[0], 0)

        self.db.execute("UPDATE payment_evidence SET evidence_type='CIRCLE_TRANSACTION' WHERE id='EV-000001'")
        with patch.object(registry.circle, "gateway_balance", return_value=self.gateway_balance()):
            with self.assertRaises(registry.RegistryError):
                registry._spend_fields(self.db, "SI-000001")
        self.db.execute("UPDATE payment_evidence SET evidence_type='CIRCLE_GATEWAY_X402_TRANSFER' WHERE id='EV-000001'")
        self.db.execute("UPDATE spend_intents SET executed_payment_scheme='exact' WHERE id='SI-000001'")
        with patch.object(registry.circle, "gateway_balance", return_value=self.gateway_balance()):
            with self.assertRaises(registry.RegistryError):
                registry._spend_fields(self.db, "SI-000001")
        self.db.execute("UPDATE spend_intents SET executed_payment_scheme='GatewayWalletBatched' WHERE id='SI-000001'")
        self.db.execute("UPDATE payment_evidence SET amount_atomic=4999 WHERE id='EV-000001'")
        with patch.object(registry.circle, "gateway_balance", return_value=self.gateway_balance()):
            with self.assertRaises(registry.RegistryError):
                registry._spend_fields(self.db, "SI-000001")

    def test_missing_payment_evidence_fails_closed(self) -> None:
        self.db.execute("DELETE FROM payment_evidence WHERE id='EV-000001'")
        with patch.object(registry.circle, "gateway_balance", return_value=self.gateway_balance()):
            with self.assertRaises(registry.RegistryError):
                registry._spend_fields(self.db, "SI-000001")

    def test_recovery_submits_once_and_repeat_is_idempotent(self) -> None:
        state = {"exists": False}
        reads = []

        def read_state(record: dict):
            reads.append(record["id"])
            if not state["exists"]:
                return [], False, 0
            return registry._expected_spend(record), True, 0

        def submit(*_args):
            state["exists"] = True
            return {"data": {"id": "circle-registry-tx", "txHash": TX_HASH}}

        with patch.object(registry.circle, "gateway_balance", return_value=self.gateway_balance()), \
                patch.object(registry, "_spend_state", side_effect=read_state), \
                patch.object(registry.circle, "registry_record_spend", side_effect=submit) as send:
            first = registry.recover_spend(self.db, "SI-000001")
            second = registry.recover_spend(self.db, "SI-000001")
        self.assertEqual(first["status"], "CONFIRMED")
        self.assertEqual(second["status"], "CONFIRMED")
        send.assert_called_once()
        self.assertEqual(len(reads), 2)
        record = self.db.execute("SELECT operating_wallet FROM registry_records WHERE source_entity_id='SI-000001'").fetchone()
        self.assertEqual(record["operating_wallet"], WALLET)

    def test_unknown_registry_write_is_never_resubmitted(self) -> None:
        with patch.object(registry.circle, "gateway_balance", return_value=self.gateway_balance()):
            fields = registry._spend_fields(self.db, "SI-000001")
        row = registry._insert(self.db, "SPEND", fields)
        registry._mark(self.db, row["id"], "UNKNOWN")
        with patch.object(registry.circle, "gateway_balance", return_value=self.gateway_balance()), \
                patch.object(registry, "_spend_state", return_value=([], False, 0)), \
                patch.object(registry.circle, "registry_record_spend") as send:
            result = registry.recover_spend(self.db, "SI-000001")
        self.assertEqual(result["status"], "UNKNOWN")
        send.assert_not_called()

    def test_pending_submission_claim_has_one_winner(self) -> None:
        with patch.object(registry.circle, "gateway_balance", return_value=self.gateway_balance()):
            row = registry._insert(self.db, "SPEND", registry._spend_fields(self.db, "SI-000001"))
        self.assertTrue(registry._claim_pending(self.db, row["id"]))
        self.assertFalse(registry._claim_pending(self.db, row["id"]))


if __name__ == "__main__":
    unittest.main()
