from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "skills/metron-policy/scripts"))

import email_state
import finance
import store


class EmailDeliverableTest(unittest.TestCase):
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
        store.write_config({"chain": "ARC-TESTNET", "operating_wallet": None})
        self.db = store.connect()
        self.account = "seller@example.com"
        self.customer = "buyer@example.com"
        self.thread = "thread-1"
        self.conversation = "conversation-1"
        self.deal = "deal-1"
        self.owner = "test-owner"
        self.goal = finance.create_goal(self.db, {
            "revenue_target": "50",
            "policy": {
                "operating_budget": "10",
                "max_spend_per_action": "2",
                "max_daily_spend": "8",
                "minimum_wallet_balance": "0",
                "minimum_deal": "1",
                "reinvestment_bps": 1000,
            },
        })["id"]
        now = finance.now()
        self.db.execute(
            "INSERT INTO counterparties(id,kind,name,external_ref,created_at) VALUES (?,?,?,?,?)",
            ("customer-1", "CUSTOMER", "Fixture customer", self.customer, now),
        )
        self.db.execute(
            "INSERT INTO deals(id,counterparty_id,goal_id,amount_atomic,currency,terms_json,status,accepted_at,approved_at,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (self.deal, "customer-1", self.goal, 1_000_000, "USDC",
             json.dumps({"email_conversation_id": self.conversation, "scope": "verified scope"}),
             "CLOSED_WON", "2026-10-01T00:00:00Z", "2026-10-02T00:00:00Z", now),
        )
        # PENDING_HUMAN is intentionally stale here; the deal row is authoritative.
        self.db.execute(
            "INSERT INTO email_conversations(id,account_email,conversation_key,gmail_thread_id,customer_email,state,deal_id,context_json,created_at,updated_at) "
            "VALUES (?,?,?,?,?,'PENDING_HUMAN',?,'{}',?,?)",
            (self.conversation, self.account, "fixture", self.thread, self.customer, self.deal, now, now),
        )
        self.db.executemany(
            "INSERT INTO email_messages(account_email,gmail_message_id,gmail_thread_id,conversation_id,direction,status,received_at,processed_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            [
                (self.account, "invoice-message", self.thread, self.conversation, "OUTBOUND", "PROCESSED", now, now),
                (self.account, "acceptance-message", self.thread, self.conversation, "INBOUND", "PROCESSING", now, None),
            ],
        )
        self.db.execute(
            "INSERT INTO email_run_locks(account_email,owner_token,expires_at,acquired_at) "
            "VALUES (?,?,datetime('now','+600 seconds'),datetime('now'))",
            (self.account, self.owner),
        )
        self.db.execute(
            "INSERT INTO email_send_attempts(id,account_email,action_key,conversation_id,action_kind,source_message_id,recipient_email,content_sha256,status,error_code,created_at,updated_at) "
            "VALUES ('old-unknown',?,'reply:acceptance-message',?,'REPLY','acceptance-message',?,?,'UNKNOWN','METRON_EMAIL_SEND_AMBIGUOUS',datetime('now','-2 days'),datetime('now','-2 days'))",
            (self.account, self.conversation, self.customer, "a" * 64),
        )

    def tearDown(self) -> None:
        self.db.close()
        self.store_paths.stop()
        self.temporary.cleanup()

    def send_data(self, action: str, *, content_hash: str | None = None) -> dict:
        data = {
            "action": action,
            "account_email": self.account,
            "owner_token": self.owner,
            "conversation_id": self.conversation,
            "action_key": f"deliverable:{self.deal}",
            "action_kind": "DELIVERABLE",
            "source_message_id": "invoice-message",
            "recipient_email": self.customer,
            "content_sha256": content_hash or hashlib.sha256(b"body plus pdf bytes").hexdigest(),
        }
        if action != "send-prepare":
            data.pop("conversation_id", None)
            data.pop("action_kind", None)
            data.pop("source_message_id", None)
            data.pop("recipient_email", None)
            data.pop("content_sha256", None)
        return data

    def test_prepare_is_idempotent_and_conflicting_content_fails_closed(self) -> None:
        prepared = email_state.execute(self.db, self.send_data("send-prepare"))
        self.assertEqual(prepared["status"], "PREPARED")
        duplicate = email_state.execute(self.db, self.send_data("send-prepare"))
        self.assertTrue(duplicate["duplicate"])
        with self.assertRaises(finance.DomainError) as conflict:
            email_state.execute(self.db, self.send_data("send-prepare", content_hash="b" * 64))
        self.assertEqual(conflict.exception.code, "METRON_EMAIL_ACTION_CONFLICT")

    def test_prepare_requires_closed_email_deal_and_verified_thread_source(self) -> None:
        self.db.execute("UPDATE deals SET status='INVOICED' WHERE id=?", (self.deal,))
        with self.assertRaises(finance.DomainError) as not_closed:
            email_state.execute(self.db, self.send_data("send-prepare"))
        self.assertEqual(not_closed.exception.code, "METRON_EMAIL_DELIVERABLE_NOT_ELIGIBLE")
        self.db.execute("UPDATE deals SET status='CLOSED_WON' WHERE id=?", (self.deal,))
        data = self.send_data("send-prepare")
        data["source_message_id"] = "acceptance-message"
        with self.assertRaises(finance.DomainError) as bad_source:
            email_state.execute(self.db, data)
        self.assertEqual(bad_source.exception.code, "METRON_EMAIL_MESSAGE_NOT_FOUND")

    def test_prepare_rechecks_customer_identity_and_suppression(self) -> None:
        self.db.execute("UPDATE counterparties SET external_ref='other@example.com' WHERE id='customer-1'")
        with self.assertRaises(finance.DomainError) as mismatch:
            email_state.execute(self.db, self.send_data("send-prepare"))
        self.assertEqual(mismatch.exception.code, "METRON_EMAIL_IDENTITY_MISMATCH")
        self.db.execute("UPDATE counterparties SET external_ref=? WHERE id='customer-1'", (self.customer,))
        self.db.execute(
            "INSERT INTO email_contact_suppressions(account_email,recipient_email,source_thread_id,opted_out_at) VALUES (?,?,?,datetime('now'))",
            (self.account, self.customer, self.thread),
        )
        with self.assertRaises(finance.DomainError) as suppressed:
            email_state.execute(self.db, self.send_data("send-prepare"))
        self.assertEqual(suppressed.exception.code, "METRON_EMAIL_OPTED_OUT")

    def test_prepare_requires_terms_and_source_to_match_saved_conversation_thread(self) -> None:
        self.db.execute("UPDATE deals SET terms_json=? WHERE id=?", (json.dumps({"email_conversation_id": "other"}), self.deal))
        with self.assertRaises(finance.DomainError) as mismatched_terms:
            email_state.execute(self.db, self.send_data("send-prepare"))
        self.assertEqual(mismatched_terms.exception.code, "METRON_EMAIL_DELIVERABLE_NOT_ELIGIBLE")
        self.db.execute(
            "UPDATE deals SET terms_json=? WHERE id=?",
            (json.dumps({"email_conversation_id": self.conversation, "scope": "verified scope"}), self.deal),
        )
        self.db.execute(
            "UPDATE email_messages SET gmail_thread_id='other-thread' WHERE account_email=? AND gmail_message_id='invoice-message'",
            (self.account,),
        )
        with self.assertRaises(finance.DomainError) as mismatched_thread:
            email_state.execute(self.db, self.send_data("send-prepare"))
        self.assertEqual(mismatched_thread.exception.code, "METRON_EMAIL_MESSAGE_NOT_FOUND")

    def test_send_start_revalidates_deal_and_account_limit(self) -> None:
        email_state.execute(self.db, self.send_data("send-prepare"))
        self.db.execute("UPDATE deals SET status='INVOICED' WHERE id=?", (self.deal,))
        with self.assertRaises(finance.DomainError) as not_closed:
            email_state.execute(self.db, self.send_data("send-start"))
        self.assertEqual(not_closed.exception.code, "METRON_EMAIL_DELIVERABLE_NOT_ELIGIBLE")
        self.db.execute("UPDATE deals SET status='CLOSED_WON' WHERE id=?", (self.deal,))
        self.db.execute(
            "INSERT INTO email_account_limits(account_email,max_outbound_per_24h,updated_at) VALUES (?,1,datetime('now'))",
            (self.account,),
        )
        self.db.execute("UPDATE email_send_attempts SET status='CONFIRMED',confirmed_at=datetime('now') WHERE id='old-unknown'")
        limited = email_state.execute(self.db, self.send_data("send-start"))
        self.assertEqual(limited["error_code"], "METRON_EMAIL_SEND_LIMIT_REACHED")
        self.assertEqual(self.db.execute("SELECT status FROM email_send_attempts WHERE action_key=?", (f"deliverable:{self.deal}",)).fetchone()[0], "PREPARED")

    def test_confirmation_records_delivery_without_mutating_deal_or_unknown_send(self) -> None:
        before = tuple(self.db.execute("SELECT status,accepted_at,approved_at,terms_json FROM deals WHERE id=?", (self.deal,)).fetchone())
        prepared = email_state.execute(self.db, self.send_data("send-prepare"))
        started = email_state.execute(self.db, self.send_data("send-start"))
        self.assertEqual(started["status"], "SUBMITTING")
        confirm = email_state.execute(self.db, {
            "action": "send-confirm", "account_email": self.account, "owner_token": self.owner,
            "action_key": f"deliverable:{self.deal}", "gmail_message_id": "sent-report-message",
            "gmail_thread_id": self.thread, "confirmation_source": "send_response",
        })
        self.assertEqual(confirm["status"], "CONFIRMED")
        repeat = email_state.execute(self.db, {
            "action": "send-confirm", "account_email": self.account, "owner_token": self.owner,
            "action_key": f"deliverable:{self.deal}", "gmail_message_id": "sent-report-message",
            "gmail_thread_id": self.thread, "confirmation_source": "send_response",
        })
        self.assertTrue(repeat["duplicate"])
        after = tuple(self.db.execute("SELECT status,accepted_at,approved_at,terms_json FROM deals WHERE id=?", (self.deal,)).fetchone())
        self.assertEqual(before, after)
        self.assertEqual(self.db.execute("SELECT status FROM email_send_attempts WHERE id='old-unknown'").fetchone()[0], "UNKNOWN")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM email_messages WHERE gmail_message_id='sent-report-message'").fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT last_confirmed_action FROM email_conversations WHERE id=?", (self.conversation,)).fetchone()[0], "DELIVERABLE")
        self.assertIsNotNone(prepared["attempt_id"])


class EmailSendAttemptMigrationTest(unittest.TestCase):
    def test_legacy_rows_survive_and_deliverable_key_is_global(self) -> None:
        db = sqlite3.connect(":memory:", isolation_level=None)
        db.execute("CREATE TABLE email_conversations(id TEXT PRIMARY KEY)")
        db.execute("CREATE TABLE sales_invoices(id TEXT PRIMARY KEY)")
        db.execute("INSERT INTO email_conversations VALUES ('conversation-1')")
        db.execute("INSERT INTO email_conversations VALUES ('conversation-2')")
        db.execute("INSERT INTO sales_invoices VALUES ('invoice-1')")
        db.executescript("""
            CREATE TABLE email_send_attempts (
              id TEXT PRIMARY KEY, account_email TEXT NOT NULL, action_key TEXT NOT NULL,
              conversation_id TEXT NOT NULL REFERENCES email_conversations(id),
              action_kind TEXT NOT NULL CHECK (action_kind IN ('OUTREACH','REPLY','FOLLOW_UP','INVOICE')),
              invoice_id TEXT REFERENCES sales_invoices(id), source_message_id TEXT, recipient_email TEXT NOT NULL,
              content_sha256 TEXT NOT NULL CHECK (length(content_sha256)=64),
              status TEXT NOT NULL CHECK (status IN ('PREPARED','SUBMITTING','CONFIRMED','UNKNOWN','FAILED')),
              gmail_message_id TEXT, gmail_thread_id TEXT, error_code TEXT,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL, confirmed_at TEXT,
              CHECK ((action_kind='INVOICE' AND invoice_id IS NOT NULL AND source_message_id IS NULL) OR (action_kind!='INVOICE' AND invoice_id IS NULL)),
              UNIQUE(account_email,action_key), UNIQUE(account_email,gmail_message_id)
            );
            CREATE INDEX idx_email_send_unresolved ON email_send_attempts(account_email,status);
            CREATE UNIQUE INDEX idx_email_one_reply_per_message ON email_send_attempts(account_email,source_message_id) WHERE action_kind='REPLY';
            INSERT INTO email_send_attempts VALUES ('unknown','seller@example.com','reply:acceptance','conversation-1','REPLY',NULL,'acceptance','buyer@example.com','aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','UNKNOWN',NULL,NULL,'METRON_EMAIL_SEND_AMBIGUOUS','t0','t1',NULL);
            INSERT INTO email_send_attempts VALUES ('invoice','seller@example.com','invoice:invoice-1','conversation-1','INVOICE','invoice-1',NULL,'buyer@example.com','bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb','CONFIRMED','gmail-1','thread-1',NULL,'t0','t1','t1');
        """)

        store._migrate_email_send_attempts(db)

        rows = {row[0]: row[1:] for row in db.execute(
            "SELECT id,action_key,action_kind,invoice_id,source_message_id,status,gmail_message_id,gmail_thread_id,error_code FROM email_send_attempts"
        )}
        self.assertEqual(rows["unknown"], ("reply:acceptance", "REPLY", None, "acceptance", "UNKNOWN", None, None, "METRON_EMAIL_SEND_AMBIGUOUS"))
        self.assertEqual(rows["invoice"], ("invoice:invoice-1", "INVOICE", "invoice-1", None, "CONFIRMED", "gmail-1", "thread-1", None))
        ddl = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='email_send_attempts'").fetchone()[0]
        self.assertIn("DELIVERABLE", ddl)
        db.execute(
            "INSERT INTO email_send_attempts(id,account_email,action_key,conversation_id,action_kind,source_message_id,recipient_email,content_sha256,status,created_at,updated_at) "
            "VALUES ('delivery-1','seller@example.com','deliverable:deal-1','conversation-1','DELIVERABLE','prior-send','buyer@example.com',?,'PREPARED','t0','t0')",
            ("c" * 64,),
        )
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO email_send_attempts(id,account_email,action_key,conversation_id,action_kind,source_message_id,recipient_email,content_sha256,status,created_at,updated_at) "
                "VALUES ('delivery-2','other-seller@example.com','deliverable:deal-1','conversation-2','DELIVERABLE','prior-send','buyer@example.com',?,'PREPARED','t0','t0')",
                ("d" * 64,),
            )
        db.close()


if __name__ == "__main__":
    unittest.main()
