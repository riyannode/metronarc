import json
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest import mock
from uuid import uuid4

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))

import circle
import finance
import store


AGENT_WALLET="0x81bd819b3cc14c233a7368c8d6ccc0197a13dce1"
BACKING_EOA="0x2f33bdb4b941b461dee05d96eeec49c1b94f5fad"
SELLER="0xb52d1d41daf8c87c8709bc79be41c4c424ad36f1"
TX_HASH="0xbd3a8147afc531ee61396cf8354bfbeb270f462565330d6b9c2b651d8ca62011"


def transfer(**changes):
    value={
        "id":"6c78e302-4cfd-4ceb-9606-ab21c90b6d14",
        "status":"completed",
        "token":"USDC",
        "sendingNetwork":"eip155:5042002",
        "recipientNetwork":"eip155:5042002",
        "fromAddress":BACKING_EOA,
        "toAddress":SELLER,
        "amount":"5000",
        "nonce":"0x"+"38"*32,
        "txHash":TX_HASH,
        "createdAt":"2026-10-12T03:03:43.468Z",
        "updatedAt":"2026-10-12T03:12:04.148Z",
    }
    value.update(changes)
    return value


class GatewayReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(":memory:",isolation_level=None)
        self.db.row_factory=sqlite3.Row
        self.db.executescript(store.SCHEMA)
        goal=finance.create_goal(self.db,{"revenue_target":"1","policy":{"operating_budget":"1","max_spend_per_action":"0.01","max_daily_spend":"1","minimum_wallet_balance":"0"}})
        self.intent=finance.propose_spend(self.db,{
            "goal_id":goal["id"],"service_url":"https://api.example.com/resource","http_method":"GET",
            "payment_scheme":"GatewayWalletBatched","accepted_chains":["eip155:5042002"],"payee_address":SELLER,
            "purpose":"test","reason":"fixture","expected_output":"fixture","quoted_cost":"0.005","max_cost":"0.005",
        })["id"]
        self.provider_ref="6c78e302-4cfd-4ceb-9606-ab21c90b6d14"
        self.db.execute("UPDATE spend_intents SET status='UNKNOWN',provider_payment_id=?,provider_amount_atomic=5000,executed_payment_scheme='GatewayWalletBatched' WHERE id=?",(self.provider_ref,self.intent))

    def tearDown(self):
        self.db.close()

    def normalized(self,record=None):
        return circle.normalize_gateway_x402_transfer(record or transfer(),self.provider_ref,"ARC-TESTNET")

    def record_result(self,evidence=None,expected_sender=BACKING_EOA):
        with mock.patch.object(store,"read_config",return_value={"chain":"ARC-TESTNET","operating_wallet":AGENT_WALLET}):
            return finance.record_spend_result(self.db,self.intent,evidence or self.normalized(),expected_sender)

    def test_circle_agent_wallet_resolves_to_backing_eoa(self):
        response={"data":{"address":AGENT_WALLET,"backingEOA":BACKING_EOA}}
        self.assertEqual(circle.gateway_backing_eoa(response,AGENT_WALLET),BACKING_EOA)
        with self.assertRaises(circle.CircleError):
            circle.gateway_backing_eoa(response,SELLER)

    def test_gateway_transfer_checks_identity_and_both_networks(self):
        self.assertEqual(self.normalized()["amount_atomic"],5000)
        for changes in (
            {"id":str(uuid4())},
            {"token":"USDT"},
            {"sendingNetwork":"eip155:5042"},
            {"recipientNetwork":"eip155:5042"},
            {"nonce":"0x1234"},
            {"txHash":"not-a-hash"},
            {"fromAddress":"malformed"},
            {"createdAt":"not-a-date"},
            {"updatedAt":None},
        ):
            with self.subTest(changes=changes), self.assertRaises(circle.CircleError):
                self.normalized(transfer(**changes))

    def test_nullable_and_shared_batch_hash_are_supported(self):
        first=self.normalized(transfer(txHash=None))
        second=circle.normalize_gateway_x402_transfer(transfer(id=str(uuid4())),None,"ARC-TESTNET")
        self.assertIsNone(first["tx_hash"])
        self.assertEqual(second["tx_hash"],TX_HASH)

    def test_pending_states_remain_unknown_and_keep_reference(self):
        for status in ("received","batched"):
            with self.subTest(status=status):
                pending=self.normalized(transfer(status=status,txHash=None))
                self.assertEqual(self.record_result(pending)["status"],"UNKNOWN")
                self.assertEqual(self.db.execute("SELECT status FROM spend_intents WHERE id=?",(self.intent,)).fetchone()[0],"UNKNOWN")
                self.assertEqual(self.db.execute("SELECT count(*) FROM payment_entries").fetchone()[0],0)

    def test_confirmed_reconciles_with_nullable_batch_hash(self):
        evidence=self.normalized(transfer(status="confirmed",txHash=None))
        self.assertEqual(self.record_result(evidence)["status"],"CONFIRMED")
        self.assertIsNone(self.db.execute("SELECT tx_hash FROM payment_evidence").fetchone()[0])
        self.assertEqual(self.db.execute("SELECT evidence_type FROM payment_evidence").fetchone()[0],"CIRCLE_GATEWAY_X402_TRANSFER")
        self.assertEqual(self.db.execute("SELECT count(*) FROM journal_entries").fetchone()[0],1)

    def test_completed_reconciles_with_nullable_batch_hash(self):
        evidence=self.normalized(transfer(status="completed",txHash=None))
        self.assertEqual(self.record_result(evidence)["status"],"CONFIRMED")
        self.assertIsNone(self.db.execute("SELECT tx_hash FROM payment_evidence").fetchone()[0])
        self.assertEqual(self.db.execute("SELECT count(*) FROM journal_entries").fetchone()[0],1)

    def test_sender_seller_amount_and_failed_identity_mismatches_stay_unknown(self):
        cases=(
            (self.normalized(),AGENT_WALLET),
            (self.normalized(transfer(toAddress=AGENT_WALLET)),BACKING_EOA),
            (self.normalized(transfer(amount="5001")),BACKING_EOA),
            (self.normalized(transfer(status="failed",fromAddress=AGENT_WALLET)),BACKING_EOA),
        )
        for evidence,sender in cases:
            with self.subTest(sender=sender,status=evidence["status"]):
                self.assertEqual(self.record_result(evidence,sender)["status"],"UNKNOWN")
                self.assertEqual(self.db.execute("SELECT count(*) FROM payment_entries").fetchone()[0],0)

    def test_transfer_uuid_must_match_existing_intent_reference(self):
        evidence=self.normalized()
        evidence["provider_ref"]=str(uuid4())
        self.assertEqual(self.record_result(evidence)["status"],"UNKNOWN")
        self.assertEqual(self.db.execute("SELECT provider_payment_id FROM spend_intents WHERE id=?",(self.intent,)).fetchone()[0],self.provider_ref)

    def test_matching_failed_transfer_is_terminal_without_journal(self):
        failed=self.normalized(transfer(status="failed"))
        self.assertEqual(self.record_result(failed)["status"],"FAILED")
        self.assertEqual(self.db.execute("SELECT count(*) FROM journal_entries").fetchone()[0],0)

    def test_duplicate_reconciliation_cannot_post_twice(self):
        self.assertEqual(self.record_result()["status"],"CONFIRMED")
        with mock.patch.object(store,"read_config",return_value={"chain":"ARC-TESTNET","operating_wallet":AGENT_WALLET}):
            with self.assertRaises(finance.DomainError):
                finance.record_spend_result(self.db,self.intent,self.normalized(),BACKING_EOA)
        self.assertEqual(self.db.execute("SELECT count(*) FROM payment_entries").fetchone()[0],1)
        self.assertEqual(self.db.execute("SELECT count(*) FROM journal_entries").fetchone()[0],1)

    def test_explicit_curl_transport_does_not_fall_back_or_disable_tls(self):
        raw=json.dumps(transfer()).encode()+b"\n200"
        completed=mock.Mock(returncode=0,stdout=raw)
        with mock.patch.dict("os.environ",{"METRON_GATEWAY_STATUS_CURL_EXE":"curl.exe"}), mock.patch.object(circle.subprocess,"run",return_value=completed) as run, mock.patch.object(circle,"urlopen") as urllib:
            result=circle.gateway_x402_transfer(self.provider_ref,"ARC-TESTNET")
        self.assertEqual(result["provider_ref"],self.provider_ref)
        args=run.call_args.args[0]
        self.assertEqual(args[0],"curl.exe")
        self.assertIn("--no-insecure",args)
        self.assertIn("--no-location",args)
        self.assertIn("--proto",args)
        urllib.assert_not_called()

    def test_explicit_curl_403_stays_unavailable_without_fallback(self):
        response=mock.Mock(returncode=0,stdout=b"<html>Lockout</html>\n403")
        with mock.patch.dict("os.environ",{"METRON_GATEWAY_STATUS_CURL_EXE":"curl.exe"}), mock.patch.object(circle.subprocess,"run",return_value=response), mock.patch.object(circle,"urlopen") as urllib:
            with self.assertRaises(circle.CircleError) as error:
                circle.gateway_x402_transfer(self.provider_ref,"ARC-TESTNET")
        self.assertEqual(error.exception.code,"METRON_GATEWAY_STATUS_UNAVAILABLE")
        urllib.assert_not_called()


if __name__=="__main__":
    unittest.main()
