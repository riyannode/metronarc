from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CLI = ROOT / "skills/metron-policy/scripts/run.py"
WALLET = "0x1111111111111111111111111111111111111111"


class InvoiceWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name) / "metron"
        self.home.mkdir()
        self.env = {**os.environ, "METRON_HOME": str(self.home)}
        self.call("init")
        self.call("config-set", data={"chain": "ARC-TESTNET", "operating_wallet": WALLET})
        goal = self.call(
            "goal-create",
            data={
                "revenue_target": "10",
                "policy": {"operating_budget": "5", "max_spend_per_action": "1", "max_daily_spend": "5"},
            },
        )
        self.goal_id = goal["id"]
        deal = self.call(
            "deal-create",
            data={
                "goal_id": goal["id"],
                "customer": "Fixture Customer",
                "external_ref": "billing@example.invalid",
                "amount": "12.30",
                "terms": {
                    "payer_wallet": WALLET,
                    "due_at": "2026-11-12",
                    "billing_email": "billing@example.invalid",
                    "service_description": "Approved fixture service",
                    "line_items": [
                        {"description": "Research", "quantity": 1, "unit_price_atomic": 7500000},
                        {"description": "Delivery", "quantity": 1, "unit_price_atomic": 4800000},
                    ],
                },
            },
        )
        self.deal_id = deal["id"]
        self.call("deal-update", identifier=self.deal_id, status="NEGOTIATING")
        self.call("deal-accept", identifier=self.deal_id)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_standard_invoice_terms_do_not_require_custom_terms_approval(self) -> None:
        deal = self.call(
            "deal-create",
            data={
                "goal_id": self.goal_id,
                "customer": "Standard Terms Customer",
                "external_ref": "standard@example.invalid",
                "amount": "12.30",
                "terms": {
                    "payer_wallet": WALLET,
                    "service_description": "Research and delivery",
                    "line_items": [{"description": "Research", "quantity": 1, "unit_price_atomic": 12300000}],
                    "due_at": "2026-11-12",
                    "billing_name": "Standard Terms Customer",
                    "billing_email": "standard@example.invalid",
                    "billing_address": "123 Example Street",
                    "tax_atomic": 0,
                    "fee_atomic": 0,
                },
            },
        )

        self.assertEqual(deal["policy_result"], "ALLOW")
        self.assertEqual(deal["escalation_reasons"], [])
        self.call("deal-update", identifier=deal["id"], status="NEGOTIATING")
        accepted = self.call("deal-accept", identifier=deal["id"])
        self.assertEqual(accepted["status"], "PENDING_HUMAN")

    def test_explicit_custom_terms_and_below_minimum_still_escalate(self) -> None:
        custom = self.call(
            "deal-create",
            data={
                "goal_id": self.goal_id,
                "customer": "Custom Terms Customer",
                "amount": "12.30",
                "custom_or_legal_terms": True,
                "terms": {"payer_wallet": WALLET, "service_description": "Custom service"},
            },
        )
        self.assertEqual(custom["policy_result"], "ESCALATE")
        self.assertEqual(custom["escalation_reasons"], ["CUSTOM_OR_LEGAL_TERMS"])
        self.call("deal-update", identifier=custom["id"], status="NEGOTIATING")
        custom_accept = subprocess.run(
            [sys.executable, "-B", str(CLI), "deal-accept", "--id", custom["id"]],
            env=self.env, capture_output=True, text=True,
        )
        self.assertEqual(json.loads(custom_accept.stdout)["error"]["code"], "METRON_CUSTOM_TERMS_APPROVAL_REQUIRED")

        low_goal = self.call(
            "goal-create",
            data={
                "revenue_target": "10",
                "policy": {
                    "operating_budget": "5",
                    "max_spend_per_action": "1",
                    "max_daily_spend": "5",
                    "minimum_deal": "15",
                },
            },
        )
        below_minimum = self.call(
            "deal-create",
            data={
                "goal_id": low_goal["id"],
                "customer": "Below Minimum Customer",
                "amount": "12.30",
                "terms": {"payer_wallet": WALLET, "service_description": "Standard service"},
            },
        )
        self.assertEqual(below_minimum["policy_result"], "ESCALATE")
        self.assertEqual(below_minimum["escalation_reasons"], ["BELOW_MINIMUM_DEAL"])
        self.call("deal-update", identifier=below_minimum["id"], status="NEGOTIATING")
        minimum_accept = subprocess.run(
            [sys.executable, "-B", str(CLI), "deal-accept", "--id", below_minimum["id"]],
            env=self.env, capture_output=True, text=True,
        )
        self.assertEqual(json.loads(minimum_accept.stdout)["error"]["code"], "METRON_DEAL_BELOW_MINIMUM")

    def call(self, operation: str, *, identifier: str | None = None, status: str | None = None, data: dict | None = None) -> dict | list:
        command = [sys.executable, "-B", str(CLI), operation]
        if identifier:
            command.extend(["--id", identifier])
        if status:
            command.extend(["--status", status])
        if data is not None:
            input_path = self.home / "request.json"
            input_path.write_text(json.dumps(data), encoding="utf-8")
            command.extend(["--input", str(input_path)])
        result = subprocess.run(command, env=self.env, capture_output=True, text=True)
        payload = json.loads(result.stdout)
        if result.returncode:
            raise AssertionError(payload.get("error", {}).get("code", result.stderr))
        return payload["data"]

    def test_final_approval_is_required_and_invoice_create_post_are_idempotent(self) -> None:
        rejected = subprocess.run(
            [sys.executable, "-B", str(CLI), "invoice-create", "--id", self.deal_id],
            env=self.env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(json.loads(rejected.stdout)["error"]["code"], "METRON_HUMAN_APPROVAL_REQUIRED")

        self.call("deal-approve", identifier=self.deal_id, data={"payer_wallet": WALLET})
        unapproved_date = subprocess.run(
            [sys.executable, "-B", str(CLI), "invoice-create", "--id", self.deal_id, "--input",
             str(self.write_request({"due_at": "2026-12-01"}))],
            env=self.env, capture_output=True, text=True,
        )
        self.assertEqual(json.loads(unapproved_date.stdout)["error"]["code"], "METRON_INVALID_INPUT")
        invoice = self.call("invoice-create", identifier=self.deal_id)
        posted = self.call("invoice-post", identifier=invoice["id"])
        reused = self.call("invoice-create", identifier=self.deal_id)
        reposted = self.call("invoice-post", identifier=invoice["id"])
        document = self.call("invoice-get", identifier=invoice["id"])
        journals = self.call("journal-list")

        self.assertEqual(reused["id"], invoice["id"])
        self.assertEqual(reused["status"], "OPEN")
        self.assertEqual(reposted["journal_id"], posted["journal_id"])
        self.assertEqual(document["invoice"]["status"], "OPEN")
        self.assertEqual(document["customer"]["email"], "billing@example.invalid")
        self.assertEqual(document["business"]["operating_wallet"], WALLET)
        self.assertEqual(document["deal"]["terms"]["service_description"], "Approved fixture service")
        self.assertEqual(len([row for row in journals if row["source_type"] == "SALES_INVOICE"]), 1)

        database = self.home / "metron.sqlite"
        with sqlite3.connect(database) as db:
            terms = json.loads(db.execute("SELECT terms_json FROM deals WHERE id=?", (self.deal_id,)).fetchone()[0])
            terms["billing_email"] = "different@example.invalid"
            db.execute("UPDATE deals SET terms_json=? WHERE id=?", (json.dumps(terms), self.deal_id))
        mismatch = subprocess.run([sys.executable, "-B", str(CLI), "invoice-get", "--id", invoice["id"]],
                                  env=self.env, capture_output=True, text=True)
        self.assertEqual(json.loads(mismatch.stdout)["error"]["code"], "METRON_EMAIL_IDENTITY_MISMATCH")

    def test_invoice_delivery_uses_existing_thread_and_never_retries_ambiguous_send(self) -> None:
        self.call("deal-approve", identifier=self.deal_id, data={"payer_wallet": WALLET})
        invoice = self.call("invoice-create", identifier=self.deal_id)
        self.call("invoice-post", identifier=invoice["id"])

        account = "operator@example.invalid"
        owner_result = self.call("email-state", data={"action": "run-acquire", "account_email": account})
        owner = owner_result["owner_token"]
        thread = "fixture-thread"
        conversation = self.call(
            "email-state",
            data={
                "action": "conversation-upsert",
                "account_email": account,
                "owner_token": owner,
                "conversation_key": "fixture-customer",
                "gmail_thread_id": thread,
                "customer_email": "billing@example.invalid",
                "state": "INVOICED",
                "deal_id": self.deal_id,
            },
        )
        action_key = f"invoice:{invoice['id']}"
        prepared = self.call(
            "email-state",
            data={
                "action": "send-prepare",
                "account_email": account,
                "owner_token": owner,
                "conversation_id": conversation["conversation_id"],
                "action_key": action_key,
                "action_kind": "INVOICE",
                "invoice_id": invoice["id"],
                "recipient_email": "billing@example.invalid",
                "content_sha256": "a" * 64,
            },
        )
        self.assertEqual(prepared["status"], "PREPARED")
        self.call("email-state", data={"action": "send-limit-set", "account_email": account,
                                       "max_outbound_per_24h": 0})
        blocked = self.call("email-state", data={"action": "send-start", "account_email": account,
                                                  "owner_token": owner, "action_key": action_key})
        self.assertEqual(blocked["error_code"], "METRON_EMAIL_SEND_LIMIT_REACHED")
        self.assertEqual(blocked["status"], "PREPARED")
        self.call("email-state", data={"action": "send-limit-set", "account_email": account,
                                       "max_outbound_per_24h": 10})
        self.call("email-state", data={"action": "send-start", "account_email": account, "owner_token": owner, "action_key": action_key})
        self.call("email-state", data={"action": "send-unknown", "account_email": account, "owner_token": owner, "action_key": action_key})

        retry = subprocess.run(
            [
                sys.executable, "-B", str(CLI), "email-state", "--input",
                str(self.write_request({"action": "send-prepare", "account_email": account, "owner_token": owner,
                                        "conversation_id": conversation["conversation_id"], "action_key": action_key,
                                        "action_kind": "INVOICE", "invoice_id": invoice["id"],
                                        "recipient_email": "billing@example.invalid", "content_sha256": "a" * 64})),
            ],
            env=self.env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(json.loads(retry.stdout)["error"]["code"], "METRON_EMAIL_SEND_UNRESOLVED")

        confirmed = self.call(
            "email-state",
            data={"action": "send-confirm", "account_email": account, "owner_token": owner, "action_key": action_key,
                  "gmail_message_id": "fixture-message", "gmail_thread_id": thread, "confirmation_source": "gmail_readback"},
        )
        self.assertEqual(confirmed["status"], "CONFIRMED")
        attempts = self.call("email-state", data={"action": "state-list", "account_email": account})["send_attempts"]
        self.assertEqual(len([item for item in attempts if item["action_key"] == action_key]), 1)

        self.call("email-state", data={"action": "conversation-upsert", "account_email": account,
                                        "owner_token": owner, "conversation_key": "opted-out-thread",
                                        "gmail_thread_id": "another-customer-thread",
                                        "customer_email": "billing@example.invalid", "state": "OPTED_OUT"})
        second_thread = self.call("email-state", data={"action": "conversation-list", "account_email": account})
        opted_out = next(item for item in second_thread if item["gmail_thread_id"] == "another-customer-thread")
        suppressed = subprocess.run(
            [sys.executable, "-B", str(CLI), "email-state", "--input",
             str(self.write_request({"action": "send-prepare", "account_email": account, "owner_token": owner,
                                     "conversation_id": opted_out["id"], "action_key": action_key,
                                     "action_kind": "INVOICE", "invoice_id": invoice["id"],
                                     "recipient_email": "billing@example.invalid", "content_sha256": "a" * 64}))],
            env=self.env, capture_output=True, text=True,
        )
        self.assertEqual(json.loads(suppressed.stdout)["error"]["code"], "METRON_EMAIL_OPTED_OUT")

        other_account = "other-operator@example.invalid"
        other_owner = self.call("email-state", data={"action": "run-acquire", "account_email": other_account})["owner_token"]
        other_conversation = self.call(
            "email-state",
            data={"action": "conversation-upsert", "account_email": other_account, "owner_token": other_owner,
                  "conversation_key": "same-invoice", "gmail_thread_id": "second-account-thread",
                  "customer_email": "billing@example.invalid", "state": "INVOICED", "deal_id": self.deal_id},
        )
        duplicate_delivery = subprocess.run(
            [sys.executable, "-B", str(CLI), "email-state", "--input",
             str(self.write_request({"action": "send-prepare", "account_email": other_account,
                                     "owner_token": other_owner, "conversation_id": other_conversation["conversation_id"],
                                     "action_key": action_key, "action_kind": "INVOICE", "invoice_id": invoice["id"],
                                     "recipient_email": "billing@example.invalid", "content_sha256": "a" * 64}))],
            env=self.env, capture_output=True, text=True,
        )
        self.assertEqual(json.loads(duplicate_delivery.stdout)["error"]["code"], "METRON_EMAIL_ACTION_CONFLICT")

    def test_existing_email_outbox_rows_survive_the_invoice_action_migration(self) -> None:
        account = "operator@example.invalid"
        owner = self.call("email-state", data={"action": "run-acquire", "account_email": account})["owner_token"]
        conversation = self.call(
            "email-state",
            data={"action": "conversation-upsert", "account_email": account, "owner_token": owner,
                  "conversation_key": "existing-outreach", "gmail_thread_id": "old-thread",
                  "customer_email": "billing@example.invalid", "state": "ACTIVE"},
        )
        attempt = self.call(
            "email-state",
            data={"action": "send-prepare", "account_email": account, "owner_token": owner,
                  "conversation_id": conversation["conversation_id"], "action_key": "outreach:existing",
                  "action_kind": "OUTREACH", "recipient_email": "billing@example.invalid", "content_sha256": "b" * 64},
        )
        database = self.home / "metron.sqlite"
        with sqlite3.connect(database) as db:
            db.execute("PRAGMA foreign_keys=OFF")
            db.execute("DROP INDEX IF EXISTS idx_email_one_invoice_per_invoice")
            db.execute("ALTER TABLE email_send_attempts RENAME TO email_send_attempts_new")
            db.execute(
                "CREATE TABLE email_send_attempts ("
                "id TEXT PRIMARY KEY,account_email TEXT NOT NULL,action_key TEXT NOT NULL,"
                "conversation_id TEXT NOT NULL REFERENCES email_conversations(id),"
                "action_kind TEXT NOT NULL CHECK(action_kind IN ('OUTREACH','REPLY','FOLLOW_UP')),"
                "source_message_id TEXT,recipient_email TEXT NOT NULL,content_sha256 TEXT NOT NULL CHECK(length(content_sha256)=64),"
                "status TEXT NOT NULL CHECK(status IN ('PREPARED','SUBMITTING','CONFIRMED','UNKNOWN','FAILED')),"
                "gmail_message_id TEXT,gmail_thread_id TEXT,error_code TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,confirmed_at TEXT,"
                "UNIQUE(account_email,action_key),UNIQUE(account_email,gmail_message_id))"
            )
            db.execute(
                "INSERT INTO email_send_attempts(id,account_email,action_key,conversation_id,action_kind,source_message_id,recipient_email,content_sha256,status,created_at,updated_at) "
                "SELECT id,account_email,action_key,conversation_id,action_kind,source_message_id,recipient_email,content_sha256,status,created_at,updated_at "
                "FROM email_send_attempts_new"
            )
            db.execute("DROP TABLE email_send_attempts_new")
            db.commit()

        self.call("init")
        state = self.call("email-state", data={"action": "state-list", "account_email": account})
        restored = [row for row in state["send_attempts"] if row["id"] == attempt["attempt_id"]]
        with sqlite3.connect(database) as db:
            integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
            columns = {row[1] for row in db.execute("PRAGMA table_info(email_send_attempts)")}
        self.assertEqual(len(restored), 1)
        self.assertEqual(restored[0]["status"], "PREPARED")
        self.assertIn("invoice_id", columns)
        self.assertEqual(integrity, "ok")

    def write_request(self, data: dict) -> Path:
        path = self.home / "request.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path


if __name__ == "__main__":
    unittest.main()
