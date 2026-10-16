from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import test_registry_v3 as fixtures
import circle
import registry
import registry_deployment
import registry_evidence
import registry_receipts
from registry_hashing import RegistryError, canonical, digest
import run
import store


class RegistryHardeningTest(unittest.TestCase):
    setUp = fixtures.RegistryV3Test.setUp
    tearDown = fixtures.RegistryV3Test.tearDown
    create_intent = fixtures.RegistryV3Test.create_intent
    add_invoice = fixtures.RegistryV3Test.add_invoice
    activate = fixtures.RegistryV3Test.activate
    revenue = fixtures.RegistryV3Test.revenue
    spend = fixtures.RegistryV3Test.spend
    chain = fixtures.RegistryV3Test.chain
    financial_snapshot = fixtures.RegistryV3Test.financial_snapshot

    def test_preclaim_transient_read_failure_remains_pending_and_can_retry(self):
        row = self.revenue()
        with patch.object(circle, 'registry_v3_query', side_effect=circle.CircleError('METRON_CIRCLE_TIMEOUT')), patch.object(circle, 'registry_v3_execute') as send:
            result = registry.sync(self.db, row['id'])['records'][0]
            self.assertEqual(result['status'], 'PENDING')
            send.assert_not_called()
        _, writes, query, execute = self.chain()
        with patch.object(circle, 'registry_v3_query', side_effect=query), patch.object(circle, 'registry_v3_execute', side_effect=execute):
            self.assertEqual(registry.sync(self.db, row['id'])['records'][0]['status'], 'CONFIRMED')
        self.assertEqual(len(writes), 1)

    def test_revenue_hook_dispatches_only_selected_five_record_bundle(self):
        unrelated = self.revenue('1')
        self.revenue('2')
        _, writes, query, execute = self.chain()
        with patch.object(circle, 'registry_v3_query', side_effect=query), patch.object(circle, 'registry_v3_execute', side_effect=execute):
            result = run.registry_after_revenue(self.db, 'INV-2', 100000)
        self.assertEqual(len(writes), 5)
        self.assertNotIn(unrelated['record_hash'], [item[1][0] for item in writes])
        self.assertTrue(all(item['status'] == 'CONFIRMED' for item in result['records']))

    def test_disabled_v3_captures_visible_durable_backlog_without_dispatch(self):
        invoice = self.revenue(prepare=False)
        config = store.read_config(); config['registry_v3_enabled'] = False; store.write_config(config)
        before = self.financial_snapshot()
        with patch.object(circle, 'registry_v3_execute') as send:
            result = run.registry_after_revenue(self.db, invoice, 100000)
            self.assertEqual(result['status'], 'DEFERRED')
            self.assertGreater(registry.status(self.db)['deferred_count'], 0)
            send.assert_not_called()
        self.assertEqual(self.financial_snapshot(), before)
        with store.connect() as fresh:
            self.assertEqual(fresh.execute("SELECT COUNT(*) FROM registry_v3_backlog WHERE status='DEFERRED'").fetchone()[0], 1)

    def test_atomic_capture_survives_missing_hook_and_resumes_only_with_approval(self):
        invoice = self.revenue(prepare=False)
        row = self.db.execute("SELECT * FROM registry_v3_backlog WHERE source_entity_id=?", (invoice,)).fetchone()
        before = self.financial_snapshot()
        with self.assertRaises(RegistryError): registry.resume(self.db, row['id'])
        _, writes, query, execute = self.chain()
        with patch.object(circle, 'registry_v3_query', side_effect=query), patch.object(circle, 'registry_v3_execute', side_effect=execute):
            result = registry.resume(self.db, row['id'], operator_confirmed=True)
        self.assertEqual(len(writes), 5)
        self.assertTrue(all(item['status'] == 'CONFIRMED' for item in result['records']))
        self.assertEqual(self.financial_snapshot(), before)

    def test_initialization_does_not_auto_import_old_financial_history(self):
        self.db.execute('DROP TRIGGER registry_v3_capture')
        invoice = self.revenue(prepare=False)
        before = self.financial_snapshot()
        store.initialize()
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM registry_v3_backlog').fetchone()[0], 0)
        self.assertEqual(self.financial_snapshot(), before)
        with self.assertRaises(RegistryError): registry.recover_revenue(self.db, invoice)

    def test_backlog_capture_rolls_back_with_failed_financial_transaction(self):
        before = self.db.execute('SELECT COUNT(*) FROM registry_v3_backlog').fetchone()[0]
        # Real reconciliation must roll back its evidence-trigger side effects as well.
        import finance
        original = store.event
        captured = []
        def event(db, event_type, *args):
            if event_type == 'INVOICE_RECONCILED':
                captured.append(db.execute('SELECT COUNT(*) FROM registry_v3_backlog').fetchone()[0])
                raise finance.DomainError('SYNTHETIC_ROLLBACK')
            return original(db, event_type, *args)
        with patch.object(store, 'event', side_effect=event):
            with self.assertRaises(finance.DomainError): self.revenue(prepare=False)
        self.assertEqual(captured, [before + 1])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM registry_v3_backlog').fetchone()[0], before)

    def test_postclaim_query_failure_never_returns_pending(self):
        row = self.revenue()
        self.db.execute("UPDATE registry_v3_records SET status='SUBMITTED' WHERE id=?", (row['id'],))
        with patch.object(circle, 'registry_v3_query', side_effect=circle.CircleError('METRON_CIRCLE_TIMEOUT')), patch.object(circle, 'registry_v3_execute') as send:
            self.assertEqual(registry.sync(self.db, row['id'])['records'][0]['status'], 'UNKNOWN')
            send.assert_not_called()

    def test_failed_claim_receipt_rolls_back_and_remains_retryable(self):
        row = self.revenue()
        _, _, query, _ = self.chain()
        with patch.object(circle, 'registry_v3_query', side_effect=query), patch.object(registry_receipts, 'save', side_effect=RegistryError('METRON_REGISTRY_RECEIPT_INVALID')), patch.object(circle, 'registry_v3_execute') as send:
            self.assertEqual(registry.sync(self.db, row['id'])['records'][0]['status'], 'PENDING')
            send.assert_not_called()

    def test_stale_preclaim_error_does_not_reset_another_claim(self):
        row = self.revenue()
        def error(*args):
            with store.connect() as fresh:
                fresh.execute("UPDATE registry_v3_records SET status='SUBMITTED' WHERE id=?", (row['id'],))
            raise circle.CircleError('METRON_CIRCLE_TIMEOUT')
        with patch.object(circle, 'registry_v3_query', side_effect=error), patch.object(circle, 'registry_v3_execute') as send:
            result = registry.sync(self.db, row['id'])['records'][0]
            self.assertEqual(result['status'], 'UNKNOWN')
            send.assert_not_called()

    def test_activation_checks_code_and_never_dispatches_backlog(self):
        self.revenue(prepare=False)
        original = store.read_config()
        verification = registry_deployment.binding(fixtures.CONTRACT, fixtures.PAYEE)
        inspected = {'chain_id': '5042002', 'runtime_sha256': verification['runtime_sha256'], 'version': '3'}
        with patch.object(circle, 'registry_v3_inspect', return_value=dict(inspected, runtime_sha256='wrong')):
            with self.assertRaises(RegistryError): registry_deployment.activate(fixtures.CONTRACT, operator_confirmed=True)
        self.assertEqual(store.read_config(), original)
        with patch.object(circle, 'registry_v3_inspect', return_value=inspected), patch.object(circle, 'registry_v3_execute') as send:
            with self.assertRaises(RegistryError): registry_deployment.activate(fixtures.CONTRACT)
            result = registry_deployment.activate(fixtures.CONTRACT, operator_confirmed=True)
            self.assertEqual(result['status'], 'ACTIVE')
            self.assertFalse(result['backlog_dispatch'])
            send.assert_not_called()
        self.assertTrue(registry_deployment.approved(store.read_config()))

    def test_boolean_config_flag_cannot_bypass_activation(self):
        self.activate()
        config = store.read_config(); config.pop('registry_v3_verification'); store.write_config(config)
        with self.assertRaisesRegex(RegistryError, 'METRON_REGISTRY_ACTIVATION_REQUIRED'): registry.context()
        path = store.STATE_HOME / 'activation.json'; path.write_text(json.dumps({'registry_v3_enabled': True}))
        with self.assertRaises(RegistryError): run.execute(run.parser().parse_args(['config-set', '--input', str(path)]))

    def test_deployment_inspection_rejects_wrong_chain_missing_code_or_version(self):
        for chain_id, code, version in [('0x1', '0x1234', 3), (hex(5042002), '0x', 3), (hex(5042002), '0x1234', 2)]:
            with patch.object(circle, '_arc_rpc', side_effect=[chain_id, code]), patch.object(circle, 'call', return_value={'data': {'outputData': '0x' + format(version, '064x')}}):
                with self.assertRaises(circle.CircleError): circle.registry_v3_inspect(fixtures.CONTRACT)
        for malformed in [{}, {'data': None}, []]:
            with patch.object(circle, '_arc_rpc', side_effect=[hex(5042002), '0x1234']), patch.object(circle, 'call', return_value=malformed):
                with self.assertRaises(circle.CircleError): circle.registry_v3_inspect(fixtures.CONTRACT)
        artifact = registry_deployment.release()
        with patch.object(circle, '_arc_rpc', side_effect=[hex(5042002), artifact['runtime_bytecode']]), patch.object(circle, 'call', return_value={'data': {'outputData': '0x' + format(3, '064x')}}):
            self.assertEqual(circle.registry_v3_inspect(fixtures.CONTRACT)['runtime_sha256'], artifact['runtime_sha256'])

    def test_pinned_release_matches_source_and_abi(self):
        from pathlib import Path
        import hashlib
        root = Path(__file__).resolve().parents[3]
        artifact = registry_deployment.release()
        self.assertEqual(artifact['abi'], json.loads((root/'contracts/abi/EconomicRegistryV3.json').read_text()))
        self.assertEqual(artifact['source_sha256'], hashlib.sha256((root/'contracts/src/EconomicRegistry.sol').read_bytes()).hexdigest())

    def test_relationships_wait_when_revenue_submission_is_ambiguous(self):
        row = self.revenue()
        state, writes, query, execute = self.chain()
        def submit(kind, params, *args):
            if params[0] == row['record_hash']: raise circle.CircleError('METRON_CIRCLE_TIMEOUT')
            return execute(kind, params, *args)
        with patch.object(circle, 'registry_v3_query', side_effect=query), patch.object(circle, 'registry_v3_execute', side_effect=submit):
            result = registry.sync_revenue(self.db, 'INV-1')
        self.assertEqual(len(writes), 2)
        self.assertTrue(all(item[0] == 'FACT' for item in writes))
        self.assertEqual([item['status'] for item in result['records'] if item['kind'] == 'RELATIONSHIP'], ['PENDING', 'PENDING'])

    def test_attribution_requires_real_sources_and_preserves_operator_claim_scope(self):
        revenue = self.revenue()
        spend = self.spend(wallet=fixtures.PAYEE)
        _, _, query, execute = self.chain()
        with patch.object(circle, 'registry_v3_query', side_effect=query), patch.object(circle, 'registry_v3_execute', side_effect=execute): registry.sync(self.db)
        before = self.financial_snapshot()
        with self.assertRaises(RegistryError): registry.link(self.db, spend['id'], revenue['id'], '0x' + 'a' * 64)
        fulfillment = registry_evidence.capture(self.db, spend['source_entity_id'], {'output': 'SYNTHETIC private vendor output'})
        with self.assertRaises(RegistryError): registry.link(self.db, spend['id'], revenue['id'], {'fulfillment_id': fulfillment['id'], 'customer_artifact_path': 'missing-file'})
        path = store.STATE_HOME / 'customer-work.txt'; path.write_bytes(b'SYNTHETIC private customer work')
        relationship = registry.link(self.db, spend['id'], revenue['id'], {'fulfillment_id': fulfillment['id'], 'customer_artifact_path': str(path)})
        payload = json.loads(relationship['payload_json']); commitment = payload['data']['basis']['evidence_hash']
        audit = registry_evidence.audit(self.db, commitment)
        self.assertTrue(audit['source_artifacts_verified'])
        self.assertEqual(audit['invoice_id'], 'INV-1')
        self.assertFalse(audit['independent_attribution_verified'])
        receipt = registry.receipts(self.db, relationship['id'])[0]
        self.assertTrue(registry_receipts.verify(receipt)['bindings_valid'])
        self.assertNotIn('SYNTHETIC private', canonical(receipt))
        self.assertNotIn('customer-work.txt', canonical(receipt))
        missing = json.loads(json.dumps(receipt)); missing['binding'].pop('attribution')
        missing['receipt_hash'] = digest('METRON_RECEIPT_V3', missing['binding'])
        with self.assertRaises(RegistryError): registry_receipts.verify(missing)
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("UPDATE registry_v3_attributions SET customer_artifact=? WHERE commitment=?", (b'changed', commitment))
        self.assertEqual(self.financial_snapshot(), before)
        changed = json.loads(json.dumps(receipt)); changed['binding']['attribution']['customer_artifact_sha256'] = '0x' + 'a' * 64
        changed['receipt_hash'] = digest('METRON_RECEIPT_V3', changed['binding'])
        with self.assertRaises(RegistryError): registry_receipts.verify(changed)
        path.write_bytes(b'changed work')
        self.assertTrue(registry_evidence.audit(self.db, commitment)['source_artifacts_verified'])
        with self.assertRaises(RegistryError): registry.link(self.db, spend['id'], revenue['id'], {'fulfillment_id': fulfillment['id'], 'customer_artifact_path': str(path)})

    def test_service_hook_captures_output_even_while_registry_is_disabled(self):
        spend = self.spend()
        config = store.read_config(); config['registry_v3_enabled'] = False; store.write_config(config)
        before = self.financial_snapshot()
        run.registry_after_spend(self.db, spend['source_entity_id'], {'body': 'synthetic paid response'})
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM registry_v3_fulfillments').fetchone()[0], 1)
        self.assertEqual(self.financial_snapshot(), before)

    def test_failed_output_capture_does_not_repeat_or_reclassify_payment(self):
        spend = self.spend()
        before = self.financial_snapshot()
        with patch.object(registry_evidence, 'capture', side_effect=OSError('synthetic artifact error')), patch.object(circle, 'service_pay') as pay:
            result = run.registry_after_spend(self.db, spend['source_entity_id'], {'body': 'synthetic'})
            self.assertEqual(result['records'][0]['status'], 'UNKNOWN')
            pay.assert_not_called()
        self.assertEqual(self.financial_snapshot(), before)

    def test_verified_activation_is_bound_to_wallet_and_release_integrity(self):
        self.activate()
        config = store.read_config(); config['operating_wallet'] = fixtures.MERCHANT; store.write_config(config)
        with self.assertRaises(RegistryError): registry.context()
        path = store.STATE_HOME / 'invalid-release.json'
        artifact = registry_deployment.release(); artifact['runtime_bytecode'] = '0x1234'; path.write_text(json.dumps(artifact))
        with patch.object(registry_deployment, 'RELEASE', path):
            with self.assertRaisesRegex(RegistryError, 'METRON_REGISTRY_RELEASE_INVALID'): registry_deployment.release()


if __name__ == '__main__':
    unittest.main()
