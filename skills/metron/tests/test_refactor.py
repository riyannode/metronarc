from __future__ import annotations

import argparse
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import finance
import run
import store


class MetronRefactorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.paths = patch.multiple(store, STATE_HOME=root, DATABASE=root / "metron.sqlite", CONFIG=root / "config.json")
        self.paths.start()
        self.addCleanup(self.paths.stop)
        self.addCleanup(self.temp.cleanup)

    def test_legacy_policy_migrates_once_and_preserves_history(self):
        legacy_schema = store.SCHEMA.replace(
            "minimum_wallet_balance_atomic INTEGER NOT NULL CHECK (minimum_wallet_balance_atomic >= 0)",
            "reserve_floor_atomic INTEGER NOT NULL CHECK (reserve_floor_atomic >= 0)",
        )
        with sqlite3.connect(store.DATABASE) as db:
            db.executescript(legacy_schema)
            db.execute("INSERT INTO goals VALUES ('GOAL-000001',1000000,'USDC','ACTIVE','2026-01-01T00:00:00+00:00',NULL)")
            db.execute("INSERT INTO policies VALUES ('POL-000001','GOAL-000001',20000000,100000,2000000,7000000,50000,1000,0,0,1,'2026-01-01','2026-01-01')")
            db.execute("INSERT INTO journal_entries VALUES ('JE-OLD','PAYMENT_ENTRY','PE-OLD','legacy','POSTED','2026-01-01')")
            db.execute("INSERT INTO journal_lines(journal_entry_id,account_code,debit_atomic,credit_atomic,currency) VALUES ('JE-OLD','1010',1,0,'USDC')")
        store.CONFIG.write_text(json.dumps({"chain": "ARC-TESTNET", "operating_wallet": None, "vault_address": "0x" + "1" * 40}))

        store.initialize()
        with store.connect() as db:
            self.assertEqual(db.execute("SELECT minimum_wallet_balance_atomic FROM policies").fetchone()[0], 7_000_000)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM journal_lines WHERE account_code='1010'").fetchone()[0], 1)
            db.execute("UPDATE policies SET reserve_floor_atomic=9000000")
        detail = run.execute(argparse.Namespace(operation="goal-get", input=None, id="GOAL-000001"))
        self.assertIn("minimum_wallet_balance_atomic", detail["policy"])
        self.assertNotIn("reserve_floor_atomic", detail["policy"])
        self.assertNotIn("vault_address", store.read_config())
        store.initialize()
        with store.connect() as db:
            self.assertEqual(db.execute("SELECT minimum_wallet_balance_atomic FROM policies").fetchone()[0], 7_000_000)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0], 1)

    def test_minimum_wallet_balance_is_checked_after_estimate_before_dispatch(self):
        store.initialize()
        with store.connect() as db:
            goal = finance.create_goal(db, {"revenue_target": "100", "policy": {
                "operating_budget": "20", "max_spend_per_action": "1", "max_daily_spend": "2",
                "minimum_wallet_balance": "10", "minimum_expected_roi_bps": 0,
            }})
            intent = finance.propose_spend(db, {
                "goal_id": goal["id"], "service_url": "https://api.example.com/data", "http_method": "GET",
                "payment_scheme": "exact", "accepted_chains": ["ARC-TESTNET"],
                "payee_address": "0x" + "2" * 40, "purpose": "research", "reason": "research",
                "expected_output": "data", "quoted_cost": "1", "max_cost": "1", "expected_value": "1",
            })
        store.write_config({"chain": "ARC-TESTNET", "operating_wallet": "0x" + "3" * 40})
        calls = []

        def estimate(*args):
            calls.append("estimate")
            return {}

        def balance(*args):
            calls.append("balance")
            return {"balances": [{"symbol": "USDC", "balance": "10.999999"}]}

        args = argparse.Namespace(operation="spend-execute", input=None, id=intent["id"])
        with patch.object(run.circle, "service_estimate", side_effect=estimate), \
             patch.object(run.circle, "validate_service_estimate"), \
             patch.object(run.circle, "wallet_balance", side_effect=balance), \
             patch.object(run.circle, "service_pay") as pay:
            with self.assertRaises(finance.DomainError) as raised:
                run.execute(args)
        self.assertEqual(raised.exception.code, "METRON_MINIMUM_WALLET_BALANCE_VIOLATION")
        self.assertEqual(calls, ["estimate", "balance"])
        pay.assert_not_called()
        with store.connect() as db:
            self.assertEqual(db.execute("SELECT status FROM spend_intents WHERE id=?", (intent["id"],)).fetchone()[0], "APPROVED")

    def test_approved_payment_uses_circle_wallet_and_posts_balanced_expense(self):
        store.initialize()
        wallet = "0x" + "3" * 40
        payee = "0x" + "2" * 40
        with store.connect() as db:
            goal = finance.create_goal(db, {"revenue_target": "100", "policy": {
                "operating_budget": "20", "max_spend_per_action": "1", "max_daily_spend": "2",
                "minimum_wallet_balance": "10", "minimum_expected_roi_bps": 0,
            }})
            intent = finance.propose_spend(db, {
                "goal_id": goal["id"], "service_url": "https://api.example.com/data", "http_method": "GET",
                "payment_scheme": "exact", "accepted_chains": ["ARC-TESTNET"], "payee_address": payee,
                "purpose": "research", "reason": "research", "expected_output": "data",
                "quoted_cost": "1", "max_cost": "1", "expected_value": "1",
            })
        store.write_config({"chain": "ARC-TESTNET", "operating_wallet": wallet})
        args = argparse.Namespace(operation="spend-execute", input=None, id=intent["id"])
        evidence = {"provider_ref": "0x" + "a" * 64, "status": "confirmed", "direction": "OUT",
                    "amount_atomic": 1_000_000, "currency": "USDC", "from_address": wallet,
                    "to_address": payee, "chain": "ARC-TESTNET", "tx_hash": "0x" + "a" * 64}
        with patch.object(run.circle, "service_estimate", return_value={}), \
             patch.object(run.circle, "validate_service_estimate"), \
             patch.object(run.circle, "wallet_balance", return_value={"balances": [{"symbol": "USDC", "balance": "11"}]}), \
             patch.object(run.circle, "service_pay", return_value={}) as pay, \
             patch.object(run.circle, "service_payment_reference", return_value=evidence["provider_ref"]), \
             patch.object(run.circle, "service_payment_metadata", return_value={
                 "amount_atomic": evidence["amount_atomic"], "seller": payee, "chain": "ARC-TESTNET",
                 "scheme": "exact", "response": {"ok": True},
             }), \
             patch.object(run.circle, "transactions", return_value={}), \
             patch.object(run.circle, "find_transaction", return_value=evidence):
            result = run.execute(args)
        pay.assert_called_once_with("https://api.example.com/data", wallet, "ARC-TESTNET", "1", "GET", None)
        self.assertEqual(result["record"]["status"], "CONFIRMED")
        with store.connect() as db:
            lines = db.execute("SELECT account_code,debit_atomic,credit_atomic FROM journal_lines ORDER BY account_code").fetchall()
            self.assertEqual({row["account_code"] for row in lines}, {"1000", "5000"})
            self.assertEqual(sum(row["debit_atomic"] for row in lines), sum(row["credit_atomic"] for row in lines))

    def test_confirmed_invoice_payment_alone_increases_earned_capital(self):
        store.initialize()
        wallet = "0x" + "3" * 40
        payer = "0x" + "4" * 40
        store.write_config({"chain": "ARC-TESTNET", "operating_wallet": wallet})
        with store.connect() as db:
            goal = finance.create_goal(db, {"revenue_target": "100", "policy": {
                "operating_budget": "20", "max_spend_per_action": "1", "max_daily_spend": "2",
                "reinvestment_bps": 1000, "minimum_expected_roi_bps": 0,
            }})
            deal = finance.create_deal(db, {"goal_id": goal["id"], "customer": "Customer", "amount": "5", "terms": {"payer_wallet": payer}})
            finance.accept_deal(db, deal["id"])
            finance.approve_deal(db, deal["id"], True, payer)
            invoice = finance.create_invoice(db, deal["id"], None)
            finance.post_invoice(db, invoice["id"])
            self.assertEqual(db.execute("SELECT reinvested_operating_capital_atomic FROM policies").fetchone()[0], 0)
            payment = {"status": "confirmed", "direction": "IN", "currency": "USDC", "amount_atomic": 5_000_000,
                       "provider_ref": "0x" + "b" * 64, "from_address": payer, "to_address": wallet, "chain": "ARC-TESTNET"}
            finance.reconcile_invoice(db, invoice["id"], payment)
            self.assertEqual(db.execute("SELECT reinvested_operating_capital_atomic FROM policies").fetchone()[0], 500_000)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM payment_entries WHERE direction='IN' AND status='RECONCILED'").fetchone()[0], 1)
            journals = db.execute("SELECT journal_entry_id,account_code,debit_atomic,credit_atomic FROM journal_lines ORDER BY journal_entry_id,account_code").fetchall()
            self.assertEqual({row["account_code"] for row in journals}, {"1000", "1100", "4000"})
            self.assertEqual(sum(row["debit_atomic"] for row in journals), sum(row["credit_atomic"] for row in journals))

    def test_budget_daily_action_roi_and_human_gates_remain_enforced(self):
        store.initialize()
        with store.connect() as db:
            def create_goal(budget, daily, per_action, roi=0):
                return finance.create_goal(db, {"revenue_target": "100", "policy": {
                    "operating_budget": budget, "max_spend_per_action": per_action,
                    "max_daily_spend": daily, "minimum_expected_roi_bps": roi,
                }})["id"]

            def propose(goal_id, cost, expected):
                return finance.propose_spend(db, {
                    "goal_id": goal_id, "service_url": "https://api.example.com/data", "http_method": "GET",
                    "payment_scheme": "exact", "accepted_chains": ["ARC-TESTNET"],
                    "payee_address": "0x" + "2" * 40, "purpose": "research", "reason": "research",
                    "expected_output": "data", "quoted_cost": cost, "max_cost": cost,
                    "expected_value": expected,
                })

            limited = create_goal("0.20", "0.15", "0.10")
            escalated = propose(limited, "0.11", "1")
            self.assertEqual(escalated["policy_result"], "ESCALATE")
            finance.approve_spend(db, escalated["id"])
            self.assertEqual(propose(limited, "0.05", "1")["policy_result"], "DENY")

            budget_limited = create_goal("0.05", "0.05", "0.05")
            self.assertEqual(propose(budget_limited, "0.05", "1")["policy_result"], "ALLOW")
            self.assertEqual(propose(budget_limited, "0.01", "1")["policy_result"], "DENY")

            roi_limited = create_goal("0.20", "0.20", "0.10", roi=20_000)
            self.assertEqual(propose(roi_limited, "0.05", "0.01")["policy_result"], "DENY")

    def test_unknown_spend_does_not_retry_circle_dispatch(self):
        store.initialize()
        with store.connect() as db:
            goal = finance.create_goal(db, {"revenue_target": "100", "policy": {
                "operating_budget": "20", "max_spend_per_action": "1", "max_daily_spend": "2",
                "minimum_expected_roi_bps": 0,
            }})
            intent = finance.propose_spend(db, {
                "goal_id": goal["id"], "service_url": "https://api.example.com/data", "http_method": "GET",
                "payment_scheme": "exact", "accepted_chains": ["ARC-TESTNET"],
                "payee_address": "0x" + "2" * 40, "purpose": "research", "reason": "research",
                "expected_output": "data", "quoted_cost": "1", "expected_value": "1",
            })
            db.execute("UPDATE spend_intents SET status='UNKNOWN' WHERE id=?", (intent["id"],))
        args = argparse.Namespace(operation="spend-execute", input=None, id=intent["id"])
        with patch.object(run.circle, "service_estimate") as estimate, \
             patch.object(run.circle, "wallet_balance") as balance, \
             patch.object(run.circle, "service_pay") as pay:
            with self.assertRaises(finance.DomainError) as raised:
                run.execute(args)
        self.assertEqual(raised.exception.code, "METRON_SPEND_DENIED")
        estimate.assert_not_called()
        balance.assert_not_called()
        pay.assert_not_called()


if __name__ == "__main__":
    unittest.main()
