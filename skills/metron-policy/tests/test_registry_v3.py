from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import circle
import finance
import registry
import registry_receipts
import registry_deployment
import registry_evidence
import store
from registry_hashing import RegistryError, canonical, digest, label, dispatch_key
import test_payment_evidence as fixtures
from test_payment_evidence import PAYER, PAYEE, MERCHANT, incoming_circle_record, arc_receipt

CONTRACT = '0x4444444444444444444444444444444444444444'


class RegistryV3Test(unittest.TestCase):
    setUp = fixtures.PaymentEvidenceTest.setUp
    tearDown = fixtures.PaymentEvidenceTest.tearDown
    create_intent = fixtures.PaymentEvidenceTest.create_intent
    add_invoice = fixtures.PaymentEvidenceTest.add_invoice

    def activate(self, wallet=PAYEE):
        store.write_config({'chain': 'ARC-TESTNET', 'operating_wallet': wallet,
                            'registry_v3_address': CONTRACT, 'registry_v3_enabled': True,
                            'registry_v3_verification': registry_deployment.binding(CONTRACT, wallet)})

    def revenue(self, suffix='1', prepare=True):
        self.activate()
        invoice = self.add_invoice(suffix)
        record = incoming_circle_record()
        record['id'] = 'circle-in-' + suffix
        receipt = arc_receipt(PAYER, PAYEE)
        record['txHash'] = '0x' + suffix.zfill(64)
        receipt['transactionHash'] = record['txHash']
        receipt['transaction']['hash'] = record['txHash']
        receipt['logs'][0]['transactionHash'] = record['txHash']
        finance.reconcile_invoice(self.db, invoice, circle.normalize_transaction(record, receipt))
        return registry.record_revenue(self.db, invoice, 100000) if prepare else invoice

    def spend(self, suffix='1', wallet=PAYER, prepare=True):
        self.activate(wallet)
        intent = self.create_intent()
        record = incoming_circle_record()
        record.update(id='circle-out-' + suffix, transactionType='OUTBOUND', sourceAddress=wallet, destinationAddress=MERCHANT)
        record['txHash']='0x'+hashlib.sha256(('spend-'+suffix).encode()).hexdigest()
        receipt=arc_receipt(wallet,MERCHANT)
        receipt['transactionHash']=record['txHash'];receipt['transaction']['hash']=record['txHash'];receipt['logs'][0]['transactionHash']=record['txHash']
        evidence = circle.normalize_transaction(record, receipt)
        evidence['direction'] = 'OUT'
        finance.record_spend_result(self.db, intent, evidence)
        return registry.record_spend(self.db, intent) if prepare else intent

    def chain(self):
        state = {}
        writes = []
        def query(signature, params, contract, chain):
            if signature == 'VERSION()':
                values = ['0x' + format(3, '064x')]
            elif signature == 'evidenceFacts(address,bytes32)':
                values = [next((v[0] for (kind, _), v in state.items() if kind == 'FACT' and v[3] == params[1]), '0x' + '0' * 64)]
            else:
                kind = 'FACT' if signature.startswith('facts(') else 'RELATIONSHIP'
                item = state.get((kind, params[1]))
                values = item[1:] + ['0x' + format(1, '064x')] if item else ['0x' + '0' * 64] * (5 if kind == 'FACT' else 6)
            return {'data': {'outputData': '0x' + ''.join(v[2:] for v in values)}}
        def execute(kind, params, contract, wallet, chain, key):
            row = self.db.execute('SELECT status FROM registry_v3_records WHERE record_hash=?', (params[0],)).fetchone()
            self.assertEqual(row[0], 'SUBMITTED')
            writes.append((kind, params, key))
            state[kind, params[0]] = params
            return {'data': {'id': 'registry-operation-' + str(len(writes)), 'txHash': '0x' + 'f' * 64}}
        return state, writes, query, execute

    def test_standalone_revenue_with_no_spend_and_no_financial_rewrite(self):
        row = self.revenue()
        self.assertEqual(row['status'], 'PENDING')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM spend_intents').fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM registry_v3_records WHERE kind='FACT'").fetchone()[0], 3)
        before = self.financial_snapshot()
        again = registry.record_revenue(self.db, 'INV-1', 100000)
        self.assertEqual(row['id'], again['id'])
        self.assertEqual(before, self.financial_snapshot())
        self.assertNotIn('INV-1', row['payload_json'])
        self.assertNotIn('payer_wallet', row['payload_json'])

    def financial_snapshot(self):
        return {table: [tuple(row) for row in self.db.execute('SELECT * FROM ' + table)] for table in
                ['goals','policies','spend_intents','deals','sales_invoices','payment_entries','payment_evidence','journal_entries','journal_lines','events','registry_records']}

    def test_spend_independent_and_confirmed_once(self):
        row = self.spend()
        state, writes, query, execute = self.chain()
        with patch.object(circle, 'registry_v3_query', side_effect=query), patch.object(circle, 'registry_v3_execute', side_effect=execute):
            self.assertEqual(registry.sync(self.db, row['id'])['records'][0]['status'], 'CONFIRMED')
            registry.sync(self.db, row['id'])
        self.assertEqual(len(writes), 1)
        receipt = registry.receipts(self.db, row['id'])[-1]
        self.assertTrue(registry_receipts.verify(receipt)['bindings_valid'])
        self.assertFalse(registry_receipts.verify(receipt)['independent_attribution_verified'])

    def test_revenue_bundle_readback_and_receipt_tampering(self):
        row = self.revenue()
        state, writes, query, execute = self.chain()
        with patch.object(circle, 'registry_v3_query', side_effect=query), patch.object(circle, 'registry_v3_execute', side_effect=execute):
            registry.sync(self.db)
        self.assertEqual(len(writes), 5)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM registry_v3_records WHERE status='CONFIRMED'").fetchone()[0], 5)
        receipt = registry.receipts(self.db, row['id'])[-1]
        for key in ['record_hash', 'content_hash', 'idempotency_key', 'payload', 'readback']:
            tampered = copy.deepcopy(receipt)
            if key in {'payload', 'readback'}:
                tampered['binding'][key] = {}
            else:
                tampered['binding'][key] = '0x' + 'b' * 64
            tampered['receipt_hash'] = digest('METRON_RECEIPT_V3', tampered['binding'])
            with self.assertRaises(RegistryError): registry_receipts.verify(tampered)

    def test_unknown_never_resubmits_after_timeout(self):
        row = self.revenue()
        _, _, query, _ = self.chain()
        with patch.object(circle,'registry_v3_query',side_effect=query), patch.object(circle,'registry_v3_execute',side_effect=circle.CircleError('METRON_CIRCLE_TIMEOUT')) as send:
            self.assertEqual(registry.sync(self.db,row['id'])['records'][0]['status'],'UNKNOWN')
            registry.sync(self.db,row['id'])
        self.assertEqual(send.call_count,1)

    def test_crash_after_claim_never_resubmits_and_readback_recovers(self):
        row = self.revenue()
        state, _, query, execute = self.chain()
        def crash(*args):
            execute(*args)
            raise KeyboardInterrupt
        with patch.object(circle,'registry_v3_query',side_effect=query), patch.object(circle,'registry_v3_execute',side_effect=crash):
            with self.assertRaises(KeyboardInterrupt): registry.sync(self.db,row['id'])
        self.assertEqual(self.db.execute('SELECT status FROM registry_v3_records WHERE id=?',(row['id'],)).fetchone()[0],'SUBMITTED')
        with patch.object(circle,'registry_v3_query',side_effect=query), patch.object(circle,'registry_v3_execute') as send:
            self.assertEqual(registry.sync(self.db,row['id'])['records'][0]['status'],'CONFIRMED')
            send.assert_not_called()

    def test_crash_before_send_sacrifices_liveness(self):
        row=self.revenue()
        self.db.execute("UPDATE registry_v3_records SET status='SUBMITTED' WHERE id=?",(row['id'],))
        _,_,query,_=self.chain()
        with patch.object(circle,'registry_v3_query',side_effect=query), patch.object(circle,'registry_v3_execute') as send:
            self.assertEqual(registry.sync(self.db,row['id'])['records'][0]['status'],'UNKNOWN')
            send.assert_not_called()

    def test_missing_malformed_or_conflicting_readback_is_fail_closed(self):
        row=self.revenue()
        _,_,query,execute=self.chain()
        with patch.object(circle,'registry_v3_query',return_value={'data':{'outputData':'0xBAD'}}),patch.object(circle,'registry_v3_execute') as send:
            self.assertEqual(registry.sync(self.db,row['id'])['records'][0]['status'],'PENDING')
            send.assert_not_called()
        with patch.object(circle,'registry_v3_query',side_effect=query),patch.object(circle,'registry_v3_execute',side_effect=execute) as send:
            self.assertEqual(registry.sync(self.db,row['id'])['records'][0]['status'],'CONFIRMED')
            self.assertEqual(send.call_count,1)

    def test_sealed_records_sources_and_receipts_cannot_be_changed_or_deleted(self):
        row=self.revenue()
        for sql in ["UPDATE registry_v3_records SET payload_json='{}'", 'DELETE FROM registry_v3_records',
                    "UPDATE registry_v3_sources SET alias_hash='x'",'DELETE FROM registry_v3_sources',
                    "UPDATE registry_v3_receipts SET receipt_json='{}'",'DELETE FROM registry_v3_receipts']:
            with self.assertRaises(sqlite3.IntegrityError):self.db.execute(sql)

    def test_duplicate_direct_settlement_alias_rejected(self):
        first=self.revenue('1');self.revenue('2',prepare=False)
        # Simulate inconsistent legacy evidence; provenance must reject the same chain tx under another provider ref.
        self.db.execute("UPDATE payment_evidence SET tx_hash=? WHERE payment_entry_id=(SELECT id FROM payment_entries WHERE source_id='INV-2')",('0x'+'1'.zfill(64),))
        # A new deployment representation has its own namespace; within one deployment the conflict is terminal.
        self.assertEqual(registry.record_revenue(self.db,'INV-2',100000)['error_code'],'METRON_REGISTRY_DUPLICATE_SETTLEMENT')
        self.assertEqual(first['status'],'PENDING')

    def test_wrong_wallet_and_wrong_earned_allocation_rejected(self):
        self.revenue()
        self.assertEqual(registry.record_revenue(self.db,'INV-1',1)['status'],'FAILED')
        self.activate(MERCHANT)
        self.assertEqual(registry.record_revenue(self.db,'INV-1',100000)['status'],'FAILED')

    def test_no_deployment_no_submission_and_history_requires_approval(self):
        self.assertEqual(registry.record_revenue(self.db,'INV-missing')['error_code'],'METRON_REGISTRY_EVIDENCE_INVALID')
        with self.assertRaises(RegistryError):registry.recover_revenue(self.db,'INV-1')
        self.revenue()
        # Reusing the same settlement with a different historical label is a conflict, never a rewrite.
        self.assertEqual(registry.record_revenue(self.db,'INV-1',100000,historical=True)['status'],'FAILED')

    def test_additive_initialization_preserves_financial_and_v2_rows(self):
        self.revenue()
        before=self.financial_snapshot()
        # Remove only this fixture's empty/new provenance; reproduce a V2-only database.
        for table in ['registry_v3_backlog', 'registry_v3_receipts', 'registry_v3_sources', 'registry_v3_records']:
            for trigger in self.db.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name=?", (table,)).fetchall():
                self.db.execute('DROP TRIGGER ' + trigger[0])
            self.db.execute('DROP TABLE ' + table)
        store.initialize()
        self.assertEqual(before,self.financial_snapshot())
        self.assertEqual(self.db.execute('PRAGMA integrity_check').fetchone()[0],'ok')

    def test_circle_calls_allow_only_v3_abi_and_explicit_target(self):
        row=self.revenue()
        params=[row[k] for k in ['record_hash','type_hash','schema_hash','evidence_id','content_hash']]
        with patch.object(circle,'call',return_value={}) as call:
            circle.registry_v3_execute('FACT',params,CONTRACT,PAYEE,'ARC-TESTNET',row['idempotency_key'])
            args=call.call_args.args[0]
            self.assertEqual(args[:3],['wallet','execute','recordFact(bytes32,bytes32,bytes32,bytes32,bytes32)'])
            self.assertIn('--idempotency-key',args);self.assertEqual(args[args.index('--amount')+1],'0')
            for kind,contract,wallet,chain in [('EXECUTE',CONTRACT,PAYEE,'ARC-TESTNET'),('FACT',registry.V2_ADDRESS,PAYEE,'ARC-TESTNET'),('FACT',CONTRACT,PAYER,'ARC-TESTNET'),('FACT',CONTRACT,PAYEE,'ARC')]:
                with self.assertRaises(circle.CircleError):circle.registry_v3_execute(kind,params,contract,wallet,chain,row['idempotency_key'])
            with self.assertRaises(circle.CircleError):circle.registry_v3_query('approve(address,uint256)',[],CONTRACT,'ARC-TESTNET')

    def test_canonical_rejects_float_integer_and_non_ascii(self):
        self.assertEqual(canonical({'z':'1','a':False}),' {"a":false,"z":"1"}'.strip())
        for value in [1,1.0,float('nan'),{'amount':1},{'customer':'\u00e9'}]:
            with self.assertRaises(RegistryError):canonical(value)

    def test_relationships_require_existing_confirmed_facts_and_are_claims(self):
        row=self.revenue()
        with self.assertRaises(RegistryError):registry.link(self.db,row['id'],row['id'],label('basis'))
        revenues=[row,self.revenue('2')]
        rows=[self.spend('a',wallet=PAYEE),self.spend('b',wallet=PAYEE)]
        _,_,query,execute=self.chain()
        with patch.object(circle,'registry_v3_query',side_effect=query),patch.object(circle,'registry_v3_execute',side_effect=execute):
            registry.sync(self.db)
        before=self.financial_snapshot()
        customer_path = store.STATE_HOME / 'synthetic-customer-work.txt'
        customer_path.write_bytes(b'synthetic customer deliverable')
        for fact in rows:
            fulfillment = registry_evidence.capture(self.db, fact['source_entity_id'], {'output': 'synthetic paid service output'})
            for revenue in revenues:
                evidence = {'fulfillment_id': fulfillment['id'], 'customer_artifact_path': str(customer_path)}
                relationship=registry.link(self.db,fact['id'],revenue['id'],evidence)
                self.assertIn('OPERATOR_ASSERTED',relationship['payload_json'])
                self.assertEqual(registry.link(self.db,fact['id'],revenue['id'],evidence)['id'],relationship['id'])
        self.assertEqual(before,self.financial_snapshot())
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM registry_v3_records WHERE type_hash=?",(label('SUPPORTS'),)).fetchone()[0],4)

    def test_approved_historical_revenue_does_not_repeat_accounting(self):
        invoice=self.revenue(prepare=False)
        before=self.financial_snapshot()
        _,writes,query,execute=self.chain()
        with patch.object(circle,'registry_v3_query',side_effect=query),patch.object(circle,'registry_v3_execute',side_effect=execute):
            result=registry.recover_revenue(self.db,invoice,operator_confirmed=True)
        self.assertTrue(all(row['status']=='CONFIRMED' for row in result['records']))
        self.assertEqual(len(writes),5)
        self.assertEqual(before,self.financial_snapshot())
        self.assertEqual(self.db.execute('SELECT SUM(historical),COUNT(*) FROM registry_v3_records').fetchone()[0],5)

    def test_v2_history_stays_intact_and_is_readback_only(self):
        h=label('legacy')
        self.db.execute("INSERT INTO registry_records(id,record_type,source_entity_id,operating_wallet,contract_address,chain,spend_id,goal_hash,spend_intent_hash,payment_evidence_hash,amount_atomic,status,idempotency_key,created_at) VALUES ('REG-OLD','SPEND','SI-OLD',?,?,'ARC-TESTNET',?,?,?,?,500000,'UNKNOWN','old-key','2026-01-01')",(PAYEE,registry.V2_ADDRESS,h,h,h,h))
        before=self.financial_snapshot();store.initialize();self.assertEqual(before,self.financial_snapshot())
        words=[PAYEE[2:].rjust(64,'0'),h[2:],h[2:],h[2:],format(500000,'064x'),format(1,'064x'),format(0,'064x')]
        with patch.object(circle,'registry_query',return_value={'data':{'outputData':'0x'+''.join(words)}}),patch.object(circle,'registry_v3_execute') as send:
            result=registry.sync(self.db,'REG-OLD')['records'][0]
            self.assertTrue(result['readback_matches']);self.assertFalse(result['submission_allowed']);send.assert_not_called()
        self.assertEqual(before,self.financial_snapshot())


    def test_concurrent_sync_submits_only_once(self):
        row=self.revenue()
        state,writes,query,execute=self.chain()
        barrier=threading.Barrier(2)
        def concurrent_query(signature,params,contract,chain):
            result=query(signature,params,contract,chain)
            if signature=='facts(address,bytes32)' and not state:
                barrier.wait(timeout=5)
            return result
        def worker():
            with store.connect() as db:
                return registry.sync(db,row['id'])
        with patch.object(circle,'registry_v3_query',side_effect=concurrent_query),patch.object(circle,'registry_v3_execute',side_effect=execute):
            # Each thread owns its connection; execute's assertion uses a separate read connection.
            def threaded_execute(kind,params,contract,wallet,chain,key):
                with store.connect() as db:
                    self.assertEqual(db.execute('SELECT status FROM registry_v3_records WHERE record_hash=?',(params[0],)).fetchone()[0],'SUBMITTED')
                writes.append((kind,params,key));state[kind,params[0]]=params
                return {'data':{'id':'concurrent-operation','txHash':'0x'+'f'*64}}
            with patch.object(circle,'registry_v3_execute',side_effect=threaded_execute):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    list(pool.map(lambda _:worker(),range(2)))
        self.assertEqual(len(writes),1)
        self.assertEqual(self.db.execute('SELECT status FROM registry_v3_records WHERE id=?',(row['id'],)).fetchone()[0],'CONFIRMED')

    def test_conflicting_chain_record_does_not_dispatch(self):
        row=self.revenue()
        state,_,query,_=self.chain()
        state['FACT',row['record_hash']]=[row['record_hash'],row['type_hash'],row['schema_hash'],row['evidence_id'],label('conflict')]
        with patch.object(circle,'registry_v3_query',side_effect=query),patch.object(circle,'registry_v3_execute') as send:
            result=registry.sync(self.db,row['id'])['records'][0]
            self.assertEqual(result['status'],'PENDING');self.assertEqual(result['error_code'],'METRON_REGISTRY_RECONCILIATION_MISMATCH');send.assert_not_called()

    def test_gateway_batch_references_are_per_transfer(self):
        from registry_hashing import settlement_aliases,settlement_identity
        a={'provider':'CIRCLE','chain_id':'5042002','provider_ref':'00000000-0000-4000-8000-0000000000AB',
           'evidence_type':'CIRCLE_GATEWAY_X402_TRANSFER','tx_hash':'0x'+'a'*64}
        b=dict(a,provider_ref=a['provider_ref'].lower())
        self.assertEqual(settlement_identity(a),settlement_identity(b))
        b['provider_ref']='00000000-0000-4000-8000-000000000002'
        self.assertNotEqual(settlement_aliases(a),settlement_aliases(b))
        self.assertEqual(len(settlement_aliases(a)),1)

    def test_published_python_solidity_golden_vector_and_abi(self):
        root = Path(__file__).resolve().parents[3]
        vector = json.loads((root / 'docs/registry-v3-vectors.json').read_text())
        self.assertIs(vector['synthetic_only'], True)
        self.assertEqual(canonical(vector['payload']), vector['canonical_json'])
        self.assertEqual(dispatch_key(vector['payload']['context'], vector['record_hash']), vector['dispatch_key'])
        self.assertEqual(registry_receipts.seal(vector['payload']), (vector['record_hash'], vector['content_hash']))
        from registry_hashing import settlement_aliases
        self.assertEqual(settlement_aliases(vector['payload']['data']['source']), vector['source_aliases'])
        abi = json.loads((root / 'contracts/abi/EconomicRegistryV3.json').read_text())
        functions = [entry for entry in abi if entry['type'] == 'function']
        writes = [entry for entry in functions if entry['stateMutability'] != 'view']
        self.assertEqual({entry['name']: len(entry['inputs']) for entry in writes}, {'recordFact': 5, 'recordRelationship': 6})
        self.assertEqual(len(functions), 6)
        self.assertTrue(all(entry['stateMutability'] != 'payable' for entry in functions))

    def test_offline_cli_receipt_verification_never_opens_database(self):
        import run
        row = self.revenue()
        receipt = registry.receipts(self.db, row['id'])[0]
        path = store.STATE_HOME / 'receipt.json'
        path.write_text(json.dumps(receipt))
        args = run.parser().parse_args(['registry-verify-receipt', '--input', str(path)])
        with patch.object(store, 'initialize', side_effect=AssertionError('must stay offline')), patch.object(store, 'connect', side_effect=AssertionError('must stay offline')):
            result = run.execute(args)
        self.assertTrue(result['bindings_valid'])
        self.assertFalse(result['independent_settlement_verified'])
        self.assertFalse(result['independent_attribution_verified'])

    def test_derived_receipt_rejects_changed_parent_content_even_with_rehashed_envelope(self):
        self.revenue()
        row = self.db.execute("SELECT * FROM registry_v3_records WHERE schema_hash=?", (registry.schema_hash('metron.invoice-settlement/1'),)).fetchone()
        receipt = registry.receipts(self.db, row['id'])[0]
        changed = copy.deepcopy(receipt)
        fact = changed['binding']['facts'][0]
        fact['payload']['data']['source']['amount_atomic'] = '600000'
        fact['record_hash'], fact['content_hash'] = registry_receipts.seal(fact['payload'])
        changed['receipt_hash'] = digest('METRON_RECEIPT_V3', changed['binding'])
        with self.assertRaisesRegex(RegistryError, 'METRON_REGISTRY_RECEIPT_INVALID'):
            registry_receipts.verify(changed)

    def test_historical_recovery_does_not_submit_unrelated_pending_bundle(self):
        unrelated = self.revenue('1')
        invoice = self.revenue('2', prepare=False)
        before = self.financial_snapshot()
        _, writes, query, execute = self.chain()
        with patch.object(circle, 'registry_v3_query', side_effect=query), patch.object(circle, 'registry_v3_execute', side_effect=execute):
            registry.recover_revenue(self.db, invoice, operator_confirmed=True)
        self.assertEqual(len(writes), 5)
        self.assertNotIn(unrelated['record_hash'], [call[1][0] for call in writes])
        self.assertEqual(self.financial_snapshot(), before)

    def test_malformed_registry_tx_hash_preserves_provider_reference_and_never_resubmits(self):
        row = self.revenue()
        _, _, query, _ = self.chain()
        response = {'data': {'id': 'synthetic-known-operation', 'txHash': 'not-a-transaction-hash'}}
        with patch.object(circle, 'registry_v3_query', side_effect=query), patch.object(circle, 'registry_v3_execute', return_value=response) as send:
            registry.sync(self.db, row['id'])
            result = registry.sync(self.db, row['id'])['records'][0]
        self.assertEqual(send.call_count, 1)
        self.assertEqual(result['status'], 'UNKNOWN')
        self.assertEqual(result['provider_tx_ref'], 'synthetic-known-operation')
        self.assertIsNone(result['tx_hash'])

    def test_relationship_receipt_rejects_wrong_endpoint_types(self):
        revenues = [self.revenue('1'), self.revenue('2')]
        _, _, query, execute = self.chain()
        with patch.object(circle, 'registry_v3_query', side_effect=query), patch.object(circle, 'registry_v3_execute', side_effect=execute):
            registry.sync(self.db)
        first, second = [registry.receipts(self.db, row['id'])[-1]['binding'] for row in revenues]
        data = {'from_fact': first['record_hash'], 'to_fact': second['record_hash'],
                'from_content_hash': first['content_hash'], 'to_content_hash': second['content_hash'],
                'basis': {'evidence_hash': label('synthetic-basis')}, 'verification_scope': 'OPERATOR_ASSERTED'}
        schema = 'metron.attribution/1'
        payload = {'kind': 'RELATIONSHIP', 'context': first['payload']['context'], 'data': data,
                   'schema': schema, 'schema_hash': registry.schema_hash(schema), 'type_hash': label('SUPPORTS'), 'historical': False}
        attribution = {'schema': 'metron.attribution-evidence/1', 'from_fact': data['from_fact'], 'to_fact': data['to_fact'],
                       'fulfillment': {'schema': 'metron.x402-fulfillment/1',
                                       'provider_ref': first['payload']['data']['source']['provider_ref'],
                                       'request_hash': label('synthetic-request'), 'service_url_hash': label('synthetic-url'),
                                       'method': 'GET', 'response_sha256': label('synthetic-response'), 'response_bytes': '10',
                                       'capture_source': 'CIRCLE_CLI_RESPONSE'},
                       'customer_artifact_sha256': label('synthetic-work'), 'customer_artifact_bytes': '10',
                       'context_commitment': label('synthetic-context')}
        data['basis']['evidence_hash'] = digest('METRON_ATTRIBUTION_EVIDENCE_V3', attribution)
        record_hash, content_hash = registry_receipts.seal(payload)
        binding = {'payload': payload, 'record_hash': record_hash, 'content_hash': content_hash,
                   'idempotency_key': dispatch_key(payload['context'], record_hash),
                   'status': 'PENDING', 'provider_tx_ref': None, 'tx_hash': None, 'readback': None, 'attribution': attribution,
                   'facts': [{key: item[key] for key in ['record_hash', 'content_hash', 'payload']} for item in [first, second]]}
        receipt = {'schema': 'metron.provenance-receipt/3', 'binding': binding, 'receipt_hash': digest('METRON_RECEIPT_V3', binding)}
        with self.assertRaisesRegex(RegistryError, 'METRON_REGISTRY_RECEIPT_INVALID'):
            registry_receipts.verify(receipt)

    def test_dispatch_key_is_deterministic_uuid_and_raw_digest_is_rejected(self):
        from uuid import UUID
        row = self.revenue()
        payload = json.loads(row['payload_json'])
        self.assertEqual(UUID(row['idempotency_key']).version, 5)
        self.assertEqual(dispatch_key(payload['context'], row['record_hash']), row['idempotency_key'])
        other = dict(payload['context'], registry='0x5555555555555555555555555555555555555555')
        self.assertNotEqual(dispatch_key(other, row['record_hash']), row['idempotency_key'])
        params = [row[key] for key in ['record_hash', 'type_hash', 'schema_hash', 'evidence_id', 'content_hash']]
        with patch.object(circle, 'call') as call:
            with self.assertRaises(circle.CircleError):
                circle.registry_v3_execute('FACT', params, CONTRACT, PAYEE, 'ARC-TESTNET', label('raw-digest'))
            call.assert_not_called()

    def test_receipt_rejects_malformed_registry_references_even_when_rehashed(self):
        row = self.revenue()
        for field, value in [('tx_hash', 'fake-hash'), ('tx_hash', '0x' + '0' * 64), ('provider_tx_ref', {'id': 'nested'})]:
            receipt = registry.receipts(self.db, row['id'])[0]
            receipt['binding'][field] = value
            receipt['receipt_hash'] = digest('METRON_RECEIPT_V3', receipt['binding'])
            with self.assertRaisesRegex(RegistryError, 'METRON_REGISTRY_RECEIPT_INVALID'):
                registry_receipts.verify(receipt)

    def test_confirmed_concurrent_readback_keeps_later_known_transaction_reference(self):
        row = self.revenue()
        state, _, query, _ = self.chain()
        def execute(kind, params, contract, wallet, chain, key):
            state[kind, params[0]] = params
            with store.connect() as another:
                self.assertEqual(registry.sync(another, row['id'])['records'][0]['status'], 'CONFIRMED')
            return {'data': {'id': 'synthetic-late-reference', 'txHash': '0x' + 'f' * 64}}
        with patch.object(circle, 'registry_v3_query', side_effect=query), patch.object(circle, 'registry_v3_execute', side_effect=execute) as send:
            result = registry.sync(self.db, row['id'])['records'][0]
        self.assertEqual(send.call_count, 1)
        self.assertEqual(result['status'], 'CONFIRMED')
        self.assertEqual(result['provider_tx_ref'], 'synthetic-late-reference')
        self.assertEqual(result['tx_hash'], '0x' + 'f' * 64)
        self.assertEqual(registry.receipts(self.db, row['id'])[-1]['binding']['tx_hash'], result['tx_hash'])

    def test_legacy_reads_reject_non_abi_parameters_without_dispatch(self):
        with patch.object(circle, 'call') as call:
            for params in [[PAYEE, '--rpc-url'], ['--chain', label('legacy')]]:
                with self.assertRaises(circle.CircleError):
                    circle.registry_query('spendRecords(address,bytes32)', params, registry.V2_ADDRESS, 'ARC-TESTNET')
            call.assert_not_called()

    def test_status_scopes_namespace_and_normalizes_configured_target(self):
        target = '0xabcdefabcdefabcdefabcdefabcdefabcdefabcd'
        with patch(__name__ + '.CONTRACT', target):
            self.revenue()
        self.assertEqual(registry.status(self.db)['counts'], {'PENDING': 5})
        config = {'chain': 'ARC-TESTNET', 'operating_wallet': PAYEE,
                  'registry_v3_address': '0x' + target[2:].upper(), 'registry_v3_enabled': True}
        store.write_config(config)
        self.assertEqual(len(registry.status(self.db)['latest_records']), 5)
        store.write_config(dict(config, operating_wallet=MERCHANT))
        status = registry.status(self.db)
        self.assertEqual(status['counts'], {})
        self.assertEqual(status['latest_records'], [])


if __name__ == '__main__':
    unittest.main()
