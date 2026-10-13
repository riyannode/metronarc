from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
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
                "policy": {"operating_budget": "5", "max_spend_per_action": "1", "max_daily_spend": "5",
                           "minimum_wallet_balance": "0", "minimum_deal": "0", "reinvestment_bps": 0},
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

    def test_goal_creation_requires_explicit_monetary_and_reinvestment_policy(self) -> None:
        policy = {
            "operating_budget": "5",
            "max_spend_per_action": "1",
            "max_daily_spend": "5",
            "minimum_wallet_balance": "0",
            "minimum_deal": "0",
            "reinvestment_bps": 0,
        }
        required = set(policy)
        for missing in required:
            with self.subTest(missing=missing):
                incomplete = dict(policy)
                incomplete.pop(missing)
                self.assertEqual(
                    self.call_error("goal-create", data={"revenue_target": "10", "policy": incomplete}),
                    "METRON_INVALID_POLICY",
                )

        configured = self.call("goal-create", data={"revenue_target": "10", "policy": policy})
        with sqlite3.connect(self.home / "metron.sqlite") as db:
            stored = db.execute(
                "SELECT operating_budget_atomic,max_spend_per_action_atomic,max_daily_spend_atomic,"
                "minimum_wallet_balance_atomic,minimum_deal_atomic,reinvestment_bps "
                "FROM policies WHERE goal_id=?", (configured["id"],),
            ).fetchone()
        self.assertEqual(stored, (5_000_000, 1_000_000, 5_000_000, 0, 0, 0))

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
                    "minimum_wallet_balance": "0",
                    "minimum_deal": "15",
                    "reinvestment_bps": 0,
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

    def test_message_completion_requires_a_reply_or_persisted_blocker(self) -> None:
        account = "operator@example.invalid"
        owner = self.call("email-state", data={"action": "run-acquire", "account_email": account})["owner_token"]
        conversation = self.call(
            "email-state",
            data={"action": "conversation-upsert", "account_email": account, "owner_token": owner,
                  "conversation_key": "actionable-message", "gmail_thread_id": "actionable-thread",
                  "customer_email": "billing@example.invalid", "state": "NEGOTIATING"},
        )
        message_id = "actionable-message-id"
        claimed = self.call(
            "email-state",
            data={"action": "message-claim", "account_email": account, "owner_token": owner,
                  "gmail_message_id": message_id, "gmail_thread_id": "actionable-thread",
                  "customer_email": "billing@example.invalid"},
        )
        self.assertEqual(claimed["status"], "CLAIMED")

        silent_completion = subprocess.run(
            [sys.executable, "-B", str(CLI), "email-state", "--input",
             str(self.write_request({"action": "message-complete", "account_email": account,
                                     "owner_token": owner, "gmail_message_id": message_id}))],
            env=self.env, capture_output=True, text=True,
        )
        self.assertEqual(json.loads(silent_completion.stdout)["error"]["code"], "METRON_EMAIL_ACTION_REQUIRED")

        blocker = self.call(
            "email-state",
            data={"action": "blocker-record", "account_email": account, "owner_token": owner,
                  "gmail_message_id": message_id, "blocker_code": "COMMERCIAL_POLICY_UNAVAILABLE",
                  "details": {"missing": ["verified price", "available capacity", "delivery timeline"],
                              "next_action": "Configure the commercial policy."}},
        )
        self.assertEqual(blocker["status"], "RECORDED")
        duplicate_blocker = self.call(
            "email-state",
            data={"action": "blocker-record", "account_email": account, "owner_token": owner,
                  "gmail_message_id": message_id, "blocker_code": "COMMERCIAL_POLICY_UNAVAILABLE",
                  "details": {"missing": ["verified price", "available capacity", "delivery timeline"],
                              "next_action": "Configure the commercial policy."}},
        )
        self.assertEqual(duplicate_blocker["status"], "EXISTS")
        completed = self.call(
            "email-state",
            data={"action": "message-complete", "account_email": account,
                  "owner_token": owner, "gmail_message_id": message_id},
        )
        self.assertEqual(completed["status"], "ALREADY_PROCESSED")

        legacy_reported_at = "2026-10-13T00:00:00Z"
        with sqlite3.connect(self.home / "metron.sqlite") as db:
            db.execute("UPDATE email_message_events SET reported_at=? WHERE account_email=? AND gmail_message_id=?",
                       (legacy_reported_at, account, message_id))

        notification = self.call("email-state", data={"action": "blocker-report", "account_email": account,
                                                        "owner_token": owner})
        self.assertEqual(len(notification["blockers"]), 1)
        self.assertEqual(notification["blockers"][0]["gmail_message_id"], message_id)
        with sqlite3.connect(self.home / "metron.sqlite") as db:
            reported, attempted, acknowledged = db.execute(
                "SELECT reported_at,delivery_attempted_at,delivery_acknowledged_at FROM email_message_events "
                "WHERE account_email=? AND gmail_message_id=?", (account, message_id)).fetchone()
        self.assertEqual(reported, legacy_reported_at)
        self.assertIsNotNone(attempted)
        self.assertIsNone(acknowledged)
        retried_report = self.call("email-state", data={"action": "blocker-report", "account_email": account,
                                                        "owner_token": owner})
        self.assertEqual([item["id"] for item in retried_report["blockers"]],
                         [item["id"] for item in notification["blockers"]])
        acknowledgement = self.call("email-state", data={"action": "blocker-ack", "account_email": account,
                                                            "owner_token": owner,
                                                            "blocker_id": notification["blockers"][0]["id"],
                                                            "delivery_reference": "visible-run-001"})
        self.assertEqual(acknowledgement["status"], "ACKNOWLEDGED")
        self.call("email-state", data={"action": "run-release", "account_email": account, "owner_token": owner})
        restarted_owner = self.call("email-state", data={"action": "run-acquire", "account_email": account})["owner_token"]
        self.assertEqual(self.call("email-state", data={"action": "blocker-report", "account_email": account,
                                                         "owner_token": restarted_owner})["blockers"], [])
        repeated_ack = self.call("email-state", data={"action": "blocker-ack", "account_email": account,
                                                        "owner_token": restarted_owner,
                                                        "blocker_id": notification["blockers"][0]["id"],
                                                        "delivery_reference": "visible-run-001"})
        self.assertEqual(repeated_ack["status"], "ALREADY_ACKNOWLEDGED")

    def test_blocker_resolution_requires_a_verified_active_service(self) -> None:
        account = "operator@example.invalid"
        owner = self.call("email-state", data={"action": "run-acquire", "account_email": account})["owner_token"]
        self.call("email-state", data={"action": "conversation-upsert", "account_email": account,
                                       "owner_token": owner, "conversation_key": "policy",
                                       "gmail_thread_id": "policy-thread", "customer_email": "billing@example.invalid",
                                       "state": "NEGOTIATING"})
        message_id = "policy-message"
        self.call("email-state", data={"action": "message-claim", "account_email": account, "owner_token": owner,
                                       "gmail_message_id": message_id, "gmail_thread_id": "policy-thread",
                                       "customer_email": "billing@example.invalid"})
        self.call("email-state", data={"action": "blocker-record", "account_email": account, "owner_token": owner,
                                       "gmail_message_id": message_id, "blocker_code": "COMMERCIAL_POLICY_UNAVAILABLE",
                                       "details": {"missing": ["service scope", "price", "capacity", "timeline"],
                                                   "next_action": "Configure the commercial policy."}})

        def invoke(data: dict) -> dict:
            request_path = self.home / f"request-{len(list(self.home.glob('request-*.json')))}.json"
            request_path.write_text(json.dumps(data), encoding="utf-8")
            result = subprocess.run([sys.executable, "-B", str(CLI), "email-state", "--input", str(request_path)],
                                    env=self.env, capture_output=True, text=True)
            return json.loads(result.stdout)

        unresolved = invoke({"action": "blocker-resolve", "account_email": account, "owner_token": owner,
                             "gmail_message_id": message_id, "service_id": "missing-service"})
        self.assertEqual(unresolved["error"]["code"], "METRON_EMAIL_COMMERCIAL_POLICY_REQUIRED")
        forged_hash = invoke({"action": "blocker-resolve", "account_email": account, "owner_token": owner,
                             "gmail_message_id": message_id, "service_id": "missing-service",
                             "policy_fingerprint": "a" * 64})
        self.assertEqual(forged_hash["error"]["code"], "METRON_INVALID_INPUT")

        configured = self.set_service_policy(account, owner)
        service_id = configured["service"]["service_id"]
        canonical = dict(configured["service"])
        canonical.pop("policy_fingerprint")
        expected = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":"),
                                            ensure_ascii=False).encode()).hexdigest()
        self.assertEqual(configured["service"]["policy_fingerprint"], expected)
        readback = self.call("email-state", data={"action": "service-list", "account_email": account})
        self.assertEqual([item["service"]["service_id"] for item in readback["services"]], [service_id])
        self.assertEqual(readback["services"][0]["service"]["policy_fingerprint"], expected)
        incomplete_policy = self.service_policy_input(account, owner, minimum_acceptable_price_atomic=16000000)
        invalid = invoke(incomplete_policy)
        self.assertEqual(invalid["error"]["code"], "METRON_INVALID_INPUT")
        resolved = self.call("email-state", data={"action": "blocker-resolve", "account_email": account,
                                                   "owner_token": owner, "gmail_message_id": message_id,
                                                   "service_id": service_id})
        self.assertEqual(resolved["policy_fingerprint"], expected)

        with sqlite3.connect(self.home / "metron.sqlite") as db:
            db.execute("PRAGMA ignore_check_constraints=ON")
            db.execute("UPDATE email_services SET deliverables_json='[]' WHERE id=?", (service_id,))
        second_id = "incomplete-policy-message"
        self.call("email-state", data={"action": "message-claim", "account_email": account, "owner_token": owner,
                                       "gmail_message_id": second_id, "gmail_thread_id": "policy-thread",
                                       "customer_email": "billing@example.invalid"})
        self.call("email-state", data={"action": "blocker-record", "account_email": account, "owner_token": owner,
                                       "gmail_message_id": second_id, "blocker_code": "COMMERCIAL_POLICY_UNAVAILABLE",
                                       "details": {"missing": ["service scope"],
                                                   "next_action": "Configure the commercial policy."}})
        incomplete = invoke({"action": "blocker-resolve", "account_email": account, "owner_token": owner,
                             "gmail_message_id": second_id, "service_id": service_id})
        self.assertEqual(incomplete["error"]["code"], "METRON_EMAIL_COMMERCIAL_POLICY_REQUIRED")

    def test_service_catalog_is_account_scoped_and_supports_multiple_services(self) -> None:
        account = "operator@example.invalid"
        owner = self.call("email-state", data={"action": "run-acquire", "account_email": account})["owner_token"]
        first = self.set_service_policy(account, owner, service_name="Service Alpha")
        second = self.set_service_policy(
            account, owner, service_name="Service Beta", service_scope="A separate policy",
            initial_asking_price_atomic=40000000, minimum_acceptable_price_atomic=32000000,
            delivery_days=8, active=False,
        )
        changed = self.set_service_policy(account, owner, service_id=first["service"]["service_id"],
                                          service_name="Service Alpha", initial_asking_price_atomic=17000000)
        self.assertEqual(changed["service"]["service_id"], first["service"]["service_id"])
        self.assertNotEqual(changed["service"]["policy_fingerprint"], first["service"]["policy_fingerprint"])
        listed = self.call("email-state", data={"action": "service-list", "account_email": account})["services"]
        self.assertEqual({item["service"]["service_name"] for item in listed}, {"Service Alpha", "Service Beta"})
        self.assertEqual({item["service"]["active"] for item in listed}, {True, False})
        self.assertNotEqual(first["service"]["service_id"], second["service"]["service_id"])
        policies = {item["service"]["service_name"]: item["service"] for item in listed}
        self.assertEqual(policies["Service Alpha"]["minimum_acceptable_price_atomic"], 10000000)
        self.assertEqual(policies["Service Alpha"]["initial_asking_price_atomic"], 17000000)
        self.assertEqual(policies["Service Beta"]["minimum_acceptable_price_atomic"], 32000000)
        self.assertEqual(policies["Service Beta"]["initial_asking_price_atomic"], 40000000)
        self.assertEqual(policies["Service Beta"]["delivery_days"], 8)

    def test_offers_are_persisted_and_bounded_by_the_selected_service(self) -> None:
        account = "operator@example.invalid"
        owner = self.call("email-state", data={"action": "run-acquire", "account_email": account})["owner_token"]
        service = self.set_service_policy(account, owner)["service"]
        conversation = self.call("email-state", data={"action": "conversation-upsert", "account_email": account,
                                                        "owner_token": owner, "conversation_key": "offers",
                                                        "gmail_thread_id": "offers-thread", "customer_email": "billing@example.invalid",
                                                        "state": "NEGOTIATING", "service_id": service["service_id"]})
        inbound_id = "offer-inbound"
        self.call("email-state", data={"action": "message-claim", "account_email": account, "owner_token": owner,
                                       "gmail_message_id": inbound_id, "gmail_thread_id": "offers-thread",
                                       "customer_email": "billing@example.invalid"})
        terms = {"quantity": 1, "service_scope": service["service_scope"],
                 "deliverables": service["deliverables"], "delivery_days": service["delivery_days"]}
        mismatched_customer_offer = self.call_error(
            "email-state", data={"action": "offer-record", "account_email": account, "owner_token": owner,
                                 "conversation_id": conversation["conversation_id"], "service_id": service["service_id"],
                                 "direction": "INBOUND", "gmail_message_id": inbound_id,
                                 "unit_price_atomic": 8000000,
                                 "terms": {"requested_unit_price_atomic": 9000000}})
        self.assertEqual(mismatched_customer_offer, "METRON_INVALID_INPUT")
        customer_offer = self.call("email-state", data={"action": "offer-record", "account_email": account,
                                                         "owner_token": owner, "conversation_id": conversation["conversation_id"],
                                                         "service_id": service["service_id"], "direction": "INBOUND",
                                                         "gmail_message_id": inbound_id, "unit_price_atomic": 9000000,
                                                         "terms": {"requested_unit_price_atomic": 9000000}})
        self.assertEqual(customer_offer["status"], "RECEIVED")

        action_key = f"reply:{inbound_id}"
        self.call("email-state", data={"action": "send-prepare", "account_email": account, "owner_token": owner,
                                       "conversation_id": conversation["conversation_id"], "action_key": action_key,
                                       "action_kind": "REPLY", "source_message_id": inbound_id,
                                       "recipient_email": "billing@example.invalid", "content_sha256": "e" * 64})
        invalid = self.call_error("email-state", data={"action": "offer-record", "account_email": account,
                                                        "owner_token": owner, "conversation_id": conversation["conversation_id"],
                                                        "service_id": service["service_id"], "direction": "OUTBOUND",
                                                        "action_key": action_key, "unit_price_atomic": 9000000,
                                                        "terms": terms})
        self.assertEqual(invalid, "METRON_EMAIL_OFFER_OUT_OF_POLICY")
        counteroffer_price = service["minimum_acceptable_price_atomic"] + 1000000
        recorded = self.call("email-state", data={"action": "offer-record", "account_email": account,
                                                   "owner_token": owner, "conversation_id": conversation["conversation_id"],
                                                   "service_id": service["service_id"], "direction": "OUTBOUND",
                                                   "action_key": action_key, "unit_price_atomic": counteroffer_price,
                                                   "terms": terms})
        self.call("email-state", data={"action": "send-start", "account_email": account,
                                       "owner_token": owner, "action_key": action_key})
        self.call("email-state", data={"action": "send-confirm", "account_email": account,
                                       "owner_token": owner, "action_key": action_key,
                                       "gmail_message_id": "offer-outbound", "gmail_thread_id": "offers-thread",
                                       "confirmation_source": "send_response"})
        state = self.call("email-state", data={"action": "state-list", "account_email": account})
        outbound = [item for item in state["commercial_offers"] if item["gmail_message_id"] == "offer-outbound"]
        self.assertEqual(len(outbound), 1)
        self.assertEqual(outbound[0]["status"], "CONFIRMED")
        duplicate = self.call("email-state", data={"action": "offer-record", "account_email": account,
                                                   "owner_token": owner, "conversation_id": conversation["conversation_id"],
                                                   "service_id": service["service_id"], "direction": "OUTBOUND",
                                                   "action_key": action_key, "unit_price_atomic": counteroffer_price,
                                                   "terms": terms})
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(recorded["offer_id"], duplicate["offer_id"])

    def test_email_deal_terms_must_match_current_service_price_and_scope(self) -> None:
        account = "operator@example.invalid"
        owner = self.call("email-state", data={"action": "run-acquire", "account_email": account})["owner_token"]
        service = self.set_service_policy(account, owner)["service"]
        conversation = self.call("email-state", data={"action": "conversation-upsert", "account_email": account,
                                                        "owner_token": owner, "conversation_key": "bound-deal",
                                                        "gmail_thread_id": "bound-deal-thread", "customer_email": "billing@example.invalid",
                                                        "state": "NEGOTIATING", "service_id": service["service_id"]})
        terms = {"payer_wallet": WALLET, "service_description": service["service_scope"],
                 "line_items": [{"description": service["service_name"], "quantity": 1,
                                 "unit_price_atomic": service["initial_asking_price_atomic"]}],
                 "commercial_service": service,
                 "email_conversation_id": conversation["conversation_id"],
                 "quantity": 1, "deliverables": service["deliverables"],
                 "delivery_days": service["delivery_days"], "capacity_unit": service["capacity_unit"]}
        too_cheap = self.call_error("deal-create", data={"goal_id": self.goal_id, "customer": "Bound Customer",
                                                          "external_ref": "billing@example.invalid",
                                                          "amount": "9", "terms": terms})
        self.assertEqual(too_cheap, "METRON_EMAIL_OFFER_OUT_OF_POLICY")
        accepted_offer = self.call("deal-create", data={"goal_id": self.goal_id, "customer": "Bound Customer",
                                                          "external_ref": "billing@example.invalid",
                                                          "amount": "15", "terms": terms})
        self.call("deal-update", identifier=accepted_offer["id"], status="NEGOTIATING")
        below_service_minimum = json.loads(json.dumps(terms))
        below_service_minimum["line_items"][0]["unit_price_atomic"] = 9000000
        with sqlite3.connect(self.home / "metron.sqlite") as db:
            db.execute("UPDATE deals SET amount_atomic=?,terms_json=? WHERE id=?",
                       (9000000, json.dumps(below_service_minimum), accepted_offer["id"]))
        self.assertEqual(
            self.call_error("deal-accept", identifier=accepted_offer["id"]),
            "METRON_EMAIL_OFFER_OUT_OF_POLICY",
        )
        with sqlite3.connect(self.home / "metron.sqlite") as db:
            db.execute("UPDATE deals SET amount_atomic=?,terms_json=? WHERE id=?",
                       (15000000, json.dumps(terms), accepted_offer["id"]))
        changed_policy = self.set_service_policy(account, owner, service_id=service["service_id"], active=False)["service"]
        self.assertNotEqual(changed_policy["policy_fingerprint"], service["policy_fingerprint"])
        invalidated = self.call_error("deal-accept", identifier=accepted_offer["id"])
        self.assertEqual(invalidated, "METRON_EMAIL_SERVICE_UNAVAILABLE")
        self.set_service_policy(account, owner, service_id=service["service_id"], active=True)
        self.assertEqual(self.call("deal-accept", identifier=accepted_offer["id"])["status"], "PENDING_HUMAN")

        second_conversation = self.call("email-state", data={"action": "conversation-upsert", "account_email": account,
                                                                 "owner_token": owner, "conversation_key": "stripped-service",
                                                                 "gmail_thread_id": "stripped-service-thread",
                                                                 "customer_email": "stripped@example.invalid",
                                                                 "state": "NEGOTIATING", "service_id": service["service_id"]})
        second_terms = json.loads(json.dumps(terms))
        second_terms["email_conversation_id"] = second_conversation["conversation_id"]
        stripped = self.call("deal-create", data={"goal_id": self.goal_id, "customer": "Stripped Service",
                                                   "external_ref": "stripped@example.invalid", "amount": "15",
                                                   "terms": second_terms})
        self.call("deal-update", identifier=stripped["id"], status="NEGOTIATING")
        database = self.home / "metron.sqlite"
        with sqlite3.connect(database) as db:
            current_terms = json.loads(db.execute("SELECT terms_json FROM deals WHERE id=?", (stripped["id"],)).fetchone()[0])
            current_terms.pop("commercial_service")
            current_terms.pop("email_conversation_id")
            db.execute("UPDATE deals SET terms_json=? WHERE id=?", (json.dumps(current_terms), stripped["id"]))
        self.assertEqual(self.call_error("deal-accept", identifier=stripped["id"]),
                         "METRON_EMAIL_SERVICE_POLICY_STALE")

        self.set_service_policy(account, owner, service_id=service["service_id"], delivery_days=5)
        stale_approval = self.call_error("deal-approve", identifier=accepted_offer["id"],
                                         data={"payer_wallet": WALLET})
        self.assertEqual(stale_approval, "METRON_EMAIL_SERVICE_POLICY_STALE")

    def test_service_capacity_is_reserved_by_open_deals_and_released_on_rejection(self) -> None:
        account = "capacity@example.invalid"
        owner = self.call("email-state", data={"action": "run-acquire", "account_email": account})["owner_token"]
        service = self.set_service_policy(account, owner, available_capacity_units=1)["service"]

        def bound_conversation(key: str, thread: str) -> tuple[dict, dict]:
            conversation = self.call("email-state", data={"action": "conversation-upsert", "account_email": account,
                                                              "owner_token": owner, "conversation_key": key,
                                                              "gmail_thread_id": thread, "customer_email": f"{key}@example.invalid",
                                                              "state": "NEGOTIATING", "service_id": service["service_id"]})
            terms = {"payer_wallet": WALLET, "service_description": service["service_scope"],
                     "line_items": [{"description": service["service_name"], "quantity": 1,
                                     "unit_price_atomic": service["initial_asking_price_atomic"]}],
                     "commercial_service": service, "email_conversation_id": conversation["conversation_id"],
                     "quantity": 1, "deliverables": service["deliverables"],
                     "delivery_days": service["delivery_days"], "capacity_unit": service["capacity_unit"]}
            return conversation, terms

        def create_bound_deal(key: str, thread: str) -> str:
            _, terms = bound_conversation(key, thread)
            deal = self.call("deal-create", data={"goal_id": self.goal_id, "customer": key,
                                                   "external_ref": f"{key}@example.invalid",
                                                   "amount": "15", "terms": terms})
            self.call("deal-update", identifier=deal["id"], status="NEGOTIATING")
            return deal["id"]

        second_conversation, second_terms = bound_conversation("second", "capacity-thread-2")
        inbound_id = "capacity-message"
        self.call("email-state", data={"action": "message-claim", "account_email": account, "owner_token": owner,
                                       "gmail_message_id": inbound_id, "gmail_thread_id": "capacity-thread-2",
                                       "customer_email": "second@example.invalid"})
        action_key = f"reply:{inbound_id}"
        self.call("email-state", data={"action": "send-prepare", "account_email": account, "owner_token": owner,
                                       "conversation_id": second_conversation["conversation_id"],
                                       "action_key": action_key, "action_kind": "REPLY",
                                       "source_message_id": inbound_id, "recipient_email": "second@example.invalid",
                                       "content_sha256": "f" * 64})
        quote_terms = {"quantity": 1, "service_scope": service["service_scope"],
                       "deliverables": service["deliverables"], "delivery_days": service["delivery_days"]}
        self.call("email-state", data={"action": "offer-record", "account_email": account, "owner_token": owner,
                                       "conversation_id": second_conversation["conversation_id"],
                                       "service_id": service["service_id"], "direction": "OUTBOUND",
                                       "action_key": action_key, "unit_price_atomic": service["initial_asking_price_atomic"],
                                       "terms": quote_terms})

        first_deal = create_bound_deal("first-capacity-customer", "capacity-thread-1")
        listed = self.call("email-state", data={"action": "service-list", "account_email": account})["services"]
        self.assertEqual(listed[0]["remaining_capacity_units"], 0)
        send_blocked = self.call_error("email-state", data={"action": "send-start", "account_email": account,
                                                              "owner_token": owner, "action_key": action_key})
        self.assertEqual(send_blocked, "METRON_EMAIL_SERVICE_UNAVAILABLE")
        second = self.call_error("deal-create", data={"goal_id": self.goal_id, "customer": "Second capacity customer",
                                                       "external_ref": "second@example.invalid", "amount": "15",
                                                       "terms": second_terms})
        self.assertEqual(second, "METRON_EMAIL_SERVICE_UNAVAILABLE")

        self.call("deal-accept", identifier=first_deal)
        self.call("deal-reject", identifier=first_deal)
        listed = self.call("email-state", data={"action": "service-list", "account_email": account})["services"]
        self.assertEqual(listed[0]["remaining_capacity_units"], 1)
        self.assertEqual(self.call("email-state", data={"action": "send-start", "account_email": account,
                                                          "owner_token": owner, "action_key": action_key})["status"],
                         "SUBMITTING")

    def test_catalog_migration_preserves_existing_deals_and_legacy_policy_rows(self) -> None:
        legacy_home = self.home / "legacy"
        legacy_home.mkdir()
        legacy_env = {**self.env, "METRON_HOME": str(legacy_home)}
        database = legacy_home / "metron.sqlite"
        with sqlite3.connect(database) as db:
            db.executescript("""
                CREATE TABLE goals (id TEXT PRIMARY KEY, revenue_target_atomic INTEGER, currency TEXT,
                    status TEXT, created_at TEXT, completed_at TEXT);
                CREATE TABLE counterparties (id TEXT PRIMARY KEY, kind TEXT, name TEXT, external_ref TEXT, created_at TEXT);
                CREATE TABLE deals (id TEXT PRIMARY KEY, counterparty_id TEXT NOT NULL, goal_id TEXT NOT NULL,
                    amount_atomic INTEGER NOT NULL, currency TEXT NOT NULL, terms_json TEXT NOT NULL,
                    minimum_deal_approved INTEGER NOT NULL DEFAULT 0, custom_or_legal_terms INTEGER NOT NULL DEFAULT 0,
                    custom_terms_approved INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL, accepted_at TEXT,
                    approved_at TEXT, created_at TEXT NOT NULL, originating_spend_intent_id TEXT);
                CREATE TABLE email_commercial_policies (account_email TEXT PRIMARY KEY, service_scope TEXT,
                    price_atomic INTEGER, available_capacity_units INTEGER, capacity_unit TEXT, delivery_days INTEGER,
                    updated_at TEXT);
                CREATE TABLE journal_entries (id TEXT PRIMARY KEY, source_type TEXT NOT NULL, source_id TEXT NOT NULL,
                    description TEXT NOT NULL, status TEXT NOT NULL, posted_at TEXT NOT NULL,
                    UNIQUE(source_type,source_id));
                CREATE TABLE journal_lines (id INTEGER PRIMARY KEY, journal_entry_id TEXT NOT NULL,
                    account_code TEXT NOT NULL, debit_atomic INTEGER NOT NULL, credit_atomic INTEGER NOT NULL,
                    currency TEXT NOT NULL);
                INSERT INTO goals VALUES ('GOAL-OLD',1000000,'USDC','ACTIVE','2026-01-01',NULL);
                INSERT INTO counterparties VALUES ('CP-OLD','CUSTOMER','Historical Customer','old@example.invalid','2026-01-01');
                INSERT INTO deals VALUES ('DEAL-OLD','CP-OLD','GOAL-OLD',1234567,'USDC','{\"service_description\":\"Historical\"}',
                    0,0,0,'HUMAN_APPROVED',NULL,'2026-01-02','2026-01-01',NULL);
                INSERT INTO email_commercial_policies VALUES ('old@example.invalid','Historical policy',123,2,'projects',30,'2026-01-01');
                INSERT INTO journal_entries VALUES ('JE-OLD','SALES_INVOICE','INV-OLD','Historical invoice','POSTED','2026-01-02');
                INSERT INTO journal_lines VALUES (1,'JE-OLD','1100',1234567,0,'USDC');
                INSERT INTO journal_lines VALUES (2,'JE-OLD','4000',0,1234567,'USDC');
            """)
        result = subprocess.run([sys.executable, "-B", str(CLI), "init"], env=legacy_env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        with sqlite3.connect(database) as db:
            deal = db.execute("SELECT id,amount_atomic,terms_json,status FROM deals WHERE id='DEAL-OLD'").fetchone()
            policy = db.execute("SELECT service_scope,price_atomic,available_capacity_units FROM email_commercial_policies "
                                "WHERE account_email='old@example.invalid'").fetchone()
            journal = db.execute("SELECT id,source_type,source_id,status FROM journal_entries WHERE id='JE-OLD'").fetchone()
            lines = db.execute("SELECT account_code,debit_atomic,credit_atomic FROM journal_lines WHERE journal_entry_id='JE-OLD' "
                               "ORDER BY id").fetchall()
            columns = {row[1] for row in db.execute("PRAGMA table_info(deals)")}
            integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        self.assertEqual(deal, ("DEAL-OLD", 1234567, '{"service_description":"Historical"}', "HUMAN_APPROVED"))
        self.assertEqual(policy, ("Historical policy", 123, 2))
        self.assertEqual(journal, ("JE-OLD", "SALES_INVOICE", "INV-OLD", "POSTED"))
        self.assertEqual(lines, [("1100", 1234567, 0), ("4000", 0, 1234567)])
        self.assertTrue({"commercial_service_id", "commercial_capacity_units"}.issubset(columns))
        self.assertEqual(integrity, "ok")

    def test_recovery_is_single_under_concurrency_and_terminal_no_action_stays_terminal(self) -> None:
        account = "operator@example.invalid"
        owner = self.call("email-state", data={"action": "run-acquire", "account_email": account})["owner_token"]
        self.call("email-state", data={"action": "conversation-upsert", "account_email": account,
                                       "owner_token": owner, "conversation_key": "concurrent",
                                       "gmail_thread_id": "concurrent-thread", "customer_email": "billing@example.invalid",
                                       "state": "NEGOTIATING"})
        message_id = "concurrent-message"
        self.call("email-state", data={"action": "message-claim", "account_email": account, "owner_token": owner,
                                       "gmail_message_id": message_id, "gmail_thread_id": "concurrent-thread",
                                       "customer_email": "billing@example.invalid"})
        self.call("email-state", data={"action": "blocker-record", "account_email": account, "owner_token": owner,
                                       "gmail_message_id": message_id, "blocker_code": "COMMERCIAL_POLICY_UNAVAILABLE",
                                       "details": {"missing": ["service scope"],
                                                   "next_action": "Configure the commercial policy."}})
        service = self.set_service_policy(account, owner)["service"]
        self.call("email-state", data={"action": "blocker-resolve", "account_email": account,
                                       "owner_token": owner, "gmail_message_id": message_id,
                                       "service_id": service["service_id"]})
        self.assertEqual(self.call("email-state", data={"action": "run-acquire", "account_email": account})["status"], "BUSY")

        paths = []
        for index in range(4):
            path = self.home / f"parallel-claim-{index}.json"
            path.write_text(json.dumps({"action": "message-claim", "account_email": account, "owner_token": owner,
                                        "gmail_message_id": message_id, "gmail_thread_id": "concurrent-thread",
                                        "customer_email": "billing@example.invalid"}), encoding="utf-8")
            paths.append(path)

        def claim(path: Path) -> str:
            result = subprocess.run([sys.executable, "-B", str(CLI), "email-state", "--input", str(path)],
                                    env=self.env, capture_output=True, text=True)
            payload = json.loads(result.stdout)
            if result.returncode:
                raise AssertionError(payload.get("error", {}).get("code", result.stderr))
            return payload["data"]["status"]

        with ThreadPoolExecutor(max_workers=4) as pool:
            statuses = list(pool.map(claim, paths))
        self.assertEqual(statuses.count("RECOVERED"), 1)
        self.assertEqual(statuses.count("ALREADY_CLAIMED"), 3)
        self.call("email-state", data={"action": "message-complete", "account_email": account,
                                       "owner_token": owner, "gmail_message_id": message_id,
                                       "no_action_code": "OUT_OF_SCOPE"})
        self.call("email-state", data={"action": "run-release", "account_email": account, "owner_token": owner})
        restarted_owner = self.call("email-state", data={"action": "run-acquire", "account_email": account})["owner_token"]
        terminal = self.call("email-state", data={"action": "message-claim", "account_email": account,
                                                   "owner_token": restarted_owner, "gmail_message_id": message_id,
                                                   "gmail_thread_id": "concurrent-thread",
                                                   "customer_email": "billing@example.invalid"})
        self.assertEqual(terminal["status"], "DUPLICATE")
        reopened = subprocess.run([sys.executable, "-B", str(CLI), "email-state", "--input",
                                   str(self.write_request({"action": "blocker-record", "account_email": account,
                                                           "owner_token": restarted_owner, "gmail_message_id": message_id,
                                                           "blocker_code": "COMMERCIAL_POLICY_UNAVAILABLE",
                                                           "details": {"missing": ["service scope"],
                                                                       "next_action": "Configure the commercial policy."}}))],
                                  env=self.env, capture_output=True, text=True)
        self.assertEqual(json.loads(reopened.stdout)["error"]["code"], "METRON_EMAIL_MESSAGE_ALREADY_FINALIZED")
        events = self.call("email-state", data={"action": "state-list", "account_email": account})["message_events"]
        self.assertEqual(len([event for event in events if event["gmail_message_id"] == message_id]), 2)

    def test_email_event_ack_migration_keeps_legacy_reported_event_pending(self) -> None:
        account = "operator@example.invalid"
        owner = self.call("email-state", data={"action": "run-acquire", "account_email": account})["owner_token"]
        self.call("email-state", data={"action": "conversation-upsert", "account_email": account,
                                       "owner_token": owner, "conversation_key": "old-event",
                                       "gmail_thread_id": "old-event-thread", "customer_email": "billing@example.invalid",
                                       "state": "NEGOTIATING"})
        self.call("email-state", data={"action": "message-claim", "account_email": account, "owner_token": owner,
                                       "gmail_message_id": "old-event-message", "gmail_thread_id": "old-event-thread",
                                       "customer_email": "billing@example.invalid"})
        blocker = self.call("email-state", data={"action": "blocker-record", "account_email": account,
                                                  "owner_token": owner, "gmail_message_id": "old-event-message",
                                                  "blocker_code": "COMMERCIAL_POLICY_UNAVAILABLE",
                                                  "details": {"missing": ["scope"],
                                                              "next_action": "Configure the commercial policy."}})
        database = self.home / "metron.sqlite"
        with sqlite3.connect(database) as db:
            db.execute("UPDATE email_message_events SET reported_at='2026-10-13T00:00:00Z' WHERE id=?",
                       (blocker["blocker_id"],))
            db.execute("DROP INDEX IF EXISTS idx_email_blocker_pending_delivery")
            db.execute("ALTER TABLE email_message_events DROP COLUMN delivery_acknowledged_at")
            db.execute("ALTER TABLE email_message_events DROP COLUMN delivery_attempted_at")
            db.execute("ALTER TABLE email_message_events DROP COLUMN delivery_reference")
        self.call("init")
        with sqlite3.connect(database) as db:
            columns = {row[1] for row in db.execute("PRAGMA table_info(email_message_events)")}
            reported_at, attempted_at, acknowledged_at = db.execute(
                "SELECT reported_at,delivery_attempted_at,delivery_acknowledged_at FROM email_message_events WHERE id=?",
                (blocker["blocker_id"],)).fetchone()
            integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        self.assertIn("delivery_acknowledged_at", columns)
        self.assertIn("delivery_attempted_at", columns)
        self.assertIn("delivery_reference", columns)
        self.assertEqual(reported_at, "2026-10-13T00:00:00Z")
        self.assertIsNone(attempted_at)
        self.assertIsNone(acknowledged_at)
        self.assertEqual(integrity, "ok")
        report = self.call("email-state", data={"action": "blocker-report", "account_email": account,
                                                 "owner_token": owner})
        self.assertEqual([item["id"] for item in report["blockers"]], [blocker["blocker_id"]])

    def test_non_actionable_message_requires_explicit_durable_reason(self) -> None:
        account = "operator@example.invalid"
        owner = self.call("email-state", data={"action": "run-acquire", "account_email": account})["owner_token"]
        conversation = self.call("email-state", data={"action": "conversation-upsert", "account_email": account,
                                                       "owner_token": owner, "conversation_key": "opt-out",
                                                       "gmail_thread_id": "opt-out-thread",
                                                       "customer_email": "billing@example.invalid", "state": "ACTIVE"})
        message_id = "opt-out-message"
        self.call("email-state", data={"action": "message-claim", "account_email": account, "owner_token": owner,
                                       "gmail_message_id": message_id, "gmail_thread_id": "opt-out-thread",
                                       "customer_email": "billing@example.invalid"})
        self.call("email-state", data={"action": "conversation-update", "account_email": account,
                                       "owner_token": owner, "conversation_id": conversation["conversation_id"],
                                       "state": "OPTED_OUT"})
        completed = self.call("email-state", data={"action": "message-complete", "account_email": account,
                                                    "owner_token": owner, "gmail_message_id": message_id,
                                                    "no_action_code": "OPT_OUT"})
        self.assertEqual(completed["status"], "PROCESSED")
        events = self.call("email-state", data={"action": "state-list", "account_email": account})["message_events"]
        self.assertEqual([(event["event_type"], event["reason_code"]) for event in events], [("NO_ACTION", "OPT_OUT")])

    def test_processed_blocker_recovers_once_after_policy_resolution_and_restart(self) -> None:
        account = "operator@example.invalid"
        first_owner = self.call("email-state", data={"action": "run-acquire", "account_email": account})["owner_token"]
        conversation = self.call(
            "email-state",
            data={"action": "conversation-upsert", "account_email": account, "owner_token": first_owner,
                  "conversation_key": "legacy-processed", "gmail_thread_id": "legacy-thread",
                  "customer_email": "billing@example.invalid", "state": "NEGOTIATING"},
        )
        message_id = "legacy-processed-message"
        self.call("email-state", data={"action": "message-claim", "account_email": account,
                                       "owner_token": first_owner, "gmail_message_id": message_id,
                                       "gmail_thread_id": "legacy-thread", "customer_email": "billing@example.invalid"})

        with sqlite3.connect(self.home / "metron.sqlite") as db:
            db.execute("UPDATE email_messages SET status='PROCESSED',processed_at=datetime('now'),claimed_by=NULL,lease_until=NULL "
                       "WHERE account_email=? AND gmail_message_id=?", (account, message_id))

        blocked = self.call("email-state", data={"action": "message-claim", "account_email": account,
                                                  "owner_token": first_owner, "gmail_message_id": message_id,
                                                  "gmail_thread_id": "legacy-thread", "customer_email": "billing@example.invalid"})
        self.assertEqual(blocked["status"], "DUPLICATE")
        blocker = self.call("email-state", data={"action": "blocker-record", "account_email": account,
                                                  "owner_token": first_owner, "gmail_message_id": message_id,
                                                  "blocker_code": "COMMERCIAL_POLICY_UNAVAILABLE",
                                                  "details": {"missing": ["verified quote"],
                                                              "next_action": "Configure the commercial policy."}})
        self.assertEqual(blocker["status"], "RECORDED")
        self.assertEqual(self.call("email-state", data={"action": "run-release", "account_email": account,
                                                         "owner_token": first_owner})["status"], "RELEASED")

        second_owner = self.call("email-state", data={"action": "run-acquire", "account_email": account})["owner_token"]
        still_blocked = self.call("email-state", data={"action": "message-claim", "account_email": account,
                                                        "owner_token": second_owner, "gmail_message_id": message_id,
                                                        "gmail_thread_id": "legacy-thread", "customer_email": "billing@example.invalid"})
        self.assertEqual(still_blocked["status"], "BLOCKED_COMMERCIAL_POLICY")
        service = self.set_service_policy(account, second_owner)["service"]
        self.call("email-state", data={"action": "blocker-resolve", "account_email": account,
                                       "owner_token": second_owner, "gmail_message_id": message_id,
                                       "service_id": service["service_id"]})
        recovered = self.call("email-state", data={"action": "message-claim", "account_email": account,
                                                    "owner_token": second_owner, "gmail_message_id": message_id,
                                                    "gmail_thread_id": "legacy-thread", "customer_email": "billing@example.invalid"})
        self.assertEqual(recovered["status"], "RECOVERED")

        self.call("email-state", data={"action": "run-release", "account_email": account, "owner_token": second_owner})
        third_owner = self.call("email-state", data={"action": "run-acquire", "account_email": account})["owner_token"]
        restarted = self.call("email-state", data={"action": "message-claim", "account_email": account,
                                                    "owner_token": third_owner, "gmail_message_id": message_id,
                                                    "gmail_thread_id": "legacy-thread", "customer_email": "billing@example.invalid"})
        self.assertEqual(restarted["status"], "RECLAIMED")

        prepared = self.call("email-state", data={"action": "send-prepare", "account_email": account,
                                                  "owner_token": third_owner, "conversation_id": conversation["conversation_id"],
                                                  "action_key": f"reply:{message_id}", "action_kind": "REPLY",
                                                  "source_message_id": message_id, "recipient_email": "billing@example.invalid",
                                                  "content_sha256": "d" * 64})
        self.assertEqual(prepared["status"], "PREPARED")
        started = self.call("email-state", data={"action": "send-start", "account_email": account,
                                                  "owner_token": third_owner, "action_key": f"reply:{message_id}"})
        self.assertEqual(started["status"], "SUBMITTING")
        self.call("email-state", data={"action": "send-confirm", "account_email": account,
                                       "owner_token": third_owner, "action_key": f"reply:{message_id}",
                                       "gmail_message_id": "recovered-reply-id", "gmail_thread_id": "legacy-thread",
                                       "confirmation_source": "send_response"})
        self.assertEqual(self.call("email-state", data={"action": "message-complete", "account_email": account,
                                                         "owner_token": third_owner, "gmail_message_id": message_id})["status"], "PROCESSED")
        duplicate = self.call("email-state", data={"action": "message-claim", "account_email": account,
                                                    "owner_token": third_owner, "gmail_message_id": message_id,
                                                    "gmail_thread_id": "legacy-thread", "customer_email": "billing@example.invalid"})
        self.assertEqual(duplicate["status"], "DUPLICATE_ACTION_EXISTS")
        attempts = self.call("email-state", data={"action": "state-list", "account_email": account})["send_attempts"]
        self.assertEqual(len([item for item in attempts if item["source_message_id"] == message_id]), 1)

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

    def service_policy_input(self, account: str, owner: str, **overrides: object) -> dict:
        data = {"action": "service-set", "account_email": account, "owner_token": owner,
                "service_name": "Service Alpha", "service_scope": "A defined service scope",
                "deliverables": ["Deliverable one", "Deliverable two"],
                "initial_asking_price_atomic": 15000000, "minimum_acceptable_price_atomic": 10000000,
                "available_capacity_units": 3, "capacity_unit": "projects per month",
                "delivery_days": 4, "active": True}
        data.update(overrides)
        return data

    def set_service_policy(self, account: str, owner: str, **overrides: object) -> dict:
        return self.call("email-state", data=self.service_policy_input(account, owner, **overrides))

    def call_error(self, operation: str, *, identifier: str | None = None, data: dict | None = None) -> str:
        command = [sys.executable, "-B", str(CLI), operation]
        if identifier:
            command.extend(["--id", identifier])
        if data is not None:
            input_path = self.home / f"request-error-{len(list(self.home.glob('request-error-*.json')))}.json"
            input_path.write_text(json.dumps(data), encoding="utf-8")
            command.extend(["--input", str(input_path)])
        result = subprocess.run(command, env=self.env, capture_output=True, text=True)
        payload = json.loads(result.stdout)
        self.assertNotEqual(result.returncode, 0)
        return payload["error"]["code"]


if __name__ == "__main__":
    unittest.main()
