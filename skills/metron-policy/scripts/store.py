from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from registry_schema import REGISTRY_V3_SCHEMA


STATE_HOME = Path(os.environ.get("METRON_HOME", Path.home() / ".metron")).expanduser()
DATABASE = STATE_HOME / "metron.sqlite"
CONFIG = STATE_HOME / "config.json"

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS goals (
  id TEXT PRIMARY KEY, revenue_target_atomic INTEGER NOT NULL CHECK (revenue_target_atomic > 0),
  currency TEXT NOT NULL, status TEXT NOT NULL CHECK (status IN ('ACTIVE','COMPLETED','PAUSED')),
  created_at TEXT NOT NULL, completed_at TEXT
);
CREATE TABLE IF NOT EXISTS policies (
  id TEXT PRIMARY KEY, goal_id TEXT NOT NULL UNIQUE REFERENCES goals(id),
  operating_budget_atomic INTEGER NOT NULL CHECK (operating_budget_atomic >= 0),
  max_spend_per_action_atomic INTEGER NOT NULL CHECK (max_spend_per_action_atomic >= 0),
  max_daily_spend_atomic INTEGER NOT NULL CHECK (max_daily_spend_atomic >= 0),
  minimum_wallet_balance_atomic INTEGER NOT NULL CHECK (minimum_wallet_balance_atomic >= 0),
  minimum_expected_roi_bps INTEGER NOT NULL CHECK (minimum_expected_roi_bps >= 0),
  reinvestment_bps INTEGER NOT NULL CHECK (reinvestment_bps BETWEEN 0 AND 10000),
  minimum_deal_atomic INTEGER NOT NULL CHECK (minimum_deal_atomic >= 0),
  reinvested_operating_capital_atomic INTEGER NOT NULL DEFAULT 0 CHECK (reinvested_operating_capital_atomic >= 0),
  require_human_on_customer_acceptance INTEGER NOT NULL CHECK (require_human_on_customer_acceptance IN (0,1)),
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS counterparties (
  id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK (kind IN ('PROSPECT','CUSTOMER','PROVIDER')),
  name TEXT NOT NULL, external_ref TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS spend_intents (
  id TEXT PRIMARY KEY, goal_id TEXT NOT NULL REFERENCES goals(id), counterparty_id TEXT REFERENCES counterparties(id),
  provider TEXT NOT NULL, service_url TEXT NOT NULL, http_method TEXT NOT NULL, payment_scheme TEXT NOT NULL,
  payee_address TEXT NOT NULL, request_body_hash TEXT NOT NULL, provider_payment_id TEXT UNIQUE,
  provider_amount_atomic INTEGER CHECK (provider_amount_atomic IS NULL OR provider_amount_atomic >= 0),
  purpose TEXT NOT NULL, reason TEXT NOT NULL,
  expected_output TEXT NOT NULL, quoted_cost_atomic INTEGER NOT NULL CHECK (quoted_cost_atomic >= 0),
  max_cost_atomic INTEGER NOT NULL CHECK (max_cost_atomic >= quoted_cost_atomic),
  expected_value_atomic INTEGER NOT NULL CHECK (expected_value_atomic >= 0), expected_roi_bps INTEGER NOT NULL,
  policy_result TEXT NOT NULL CHECK (policy_result IN ('ALLOW','DENY','ESCALATE')),
  status TEXT NOT NULL CHECK (status IN ('PROPOSED','APPROVED','DENIED','ESCALATED','SUBMITTED','EXECUTED','FAILED','UNKNOWN')),
  reason_hash TEXT NOT NULL, created_at TEXT NOT NULL, executed_at TEXT, executed_payment_scheme TEXT
);
CREATE TABLE IF NOT EXISTS deals (
  id TEXT PRIMARY KEY, counterparty_id TEXT NOT NULL REFERENCES counterparties(id), goal_id TEXT NOT NULL REFERENCES goals(id),
  amount_atomic INTEGER NOT NULL CHECK (amount_atomic > 0), currency TEXT NOT NULL, terms_json TEXT NOT NULL,
  commercial_service_id TEXT REFERENCES email_services(id), commercial_capacity_units INTEGER NOT NULL DEFAULT 0 CHECK (commercial_capacity_units >= 0),
  minimum_deal_approved INTEGER NOT NULL DEFAULT 0 CHECK (minimum_deal_approved IN (0,1)),
  custom_or_legal_terms INTEGER NOT NULL DEFAULT 0 CHECK (custom_or_legal_terms IN (0,1)),
  custom_terms_approved INTEGER NOT NULL DEFAULT 0 CHECK (custom_terms_approved IN (0,1)),
  status TEXT NOT NULL CHECK (status IN ('PROSPECTING','NEGOTIATING','CUSTOMER_ACCEPTED','PENDING_HUMAN','HUMAN_APPROVED','HUMAN_REJECTED','INVOICED','CLOSED_WON','CLOSED_LOST')),
  accepted_at TEXT, approved_at TEXT, created_at TEXT NOT NULL,
  originating_spend_intent_id TEXT REFERENCES spend_intents(id)
);
CREATE TABLE IF NOT EXISTS sales_invoices (
  id TEXT PRIMARY KEY, deal_id TEXT NOT NULL UNIQUE REFERENCES deals(id), counterparty_id TEXT NOT NULL REFERENCES counterparties(id),
  amount_atomic INTEGER NOT NULL CHECK (amount_atomic > 0), currency TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('DRAFT','POSTED','OPEN','PAID','VOID')),
  issued_at TEXT, due_at TEXT, paid_at TEXT
);
CREATE TABLE IF NOT EXISTS payment_entries (
  id TEXT PRIMARY KEY, source_type TEXT NOT NULL, source_id TEXT NOT NULL,
  direction TEXT NOT NULL CHECK (direction IN ('IN','OUT','INTERNAL')), counterparty_id TEXT REFERENCES counterparties(id),
  amount_atomic INTEGER NOT NULL CHECK (amount_atomic >= 0), currency TEXT NOT NULL, provider TEXT NOT NULL,
  provider_payment_id TEXT UNIQUE, status TEXT NOT NULL CHECK (status IN ('CREATED','SUBMITTED','CONFIRMED','RECONCILED','FAILED','UNKNOWN')),
  created_at TEXT NOT NULL, confirmed_at TEXT, reconciled_at TEXT
);
CREATE TABLE IF NOT EXISTS payment_evidence (
  id TEXT PRIMARY KEY, payment_entry_id TEXT NOT NULL REFERENCES payment_entries(id), provider TEXT NOT NULL,
  evidence_type TEXT NOT NULL, provider_ref TEXT NOT NULL UNIQUE, chain TEXT, tx_hash TEXT,
  from_address TEXT, to_address TEXT, amount_atomic INTEGER NOT NULL CHECK (amount_atomic >= 0),
  currency TEXT NOT NULL, raw_evidence_hash TEXT NOT NULL, observed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS journal_entries (
  id TEXT PRIMARY KEY, source_type TEXT NOT NULL, source_id TEXT NOT NULL, description TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('POSTED','REVERSED')), posted_at TEXT NOT NULL,
  UNIQUE(source_type, source_id)
);
CREATE TABLE IF NOT EXISTS journal_lines (
  id INTEGER PRIMARY KEY, journal_entry_id TEXT NOT NULL REFERENCES journal_entries(id),
  account_code TEXT NOT NULL CHECK (account_code IN ('1000','1010','1100','4000','5000')),
  debit_atomic INTEGER NOT NULL CHECK (debit_atomic >= 0), credit_atomic INTEGER NOT NULL CHECK (credit_atomic >= 0),
  currency TEXT NOT NULL, CHECK ((debit_atomic = 0) != (credit_atomic = 0))
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY, event_type TEXT NOT NULL, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
  summary TEXT NOT NULL, data_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS registry_records (
  id TEXT PRIMARY KEY, record_type TEXT NOT NULL CHECK (record_type IN ('SPEND','REVENUE')),
  source_entity_id TEXT NOT NULL, operating_wallet TEXT NOT NULL, contract_address TEXT NOT NULL,
  chain TEXT NOT NULL CHECK (chain='ARC-TESTNET'), spend_id TEXT NOT NULL,
  goal_hash TEXT, spend_intent_hash TEXT, payment_evidence_hash TEXT, revenue_evidence_hash TEXT,
  amount_atomic INTEGER NOT NULL CHECK (amount_atomic > 0), earned_capital_atomic INTEGER,
  status TEXT NOT NULL CHECK (status IN ('PENDING','SUBMITTED','CONFIRMED','UNKNOWN','FAILED')),
  idempotency_key TEXT NOT NULL, provider_tx_ref TEXT, tx_hash TEXT, error_code TEXT,
  created_at TEXT NOT NULL, submitted_at TEXT, confirmed_at TEXT
);
CREATE TABLE IF NOT EXISTS email_conversations (
  id TEXT PRIMARY KEY, account_email TEXT NOT NULL, conversation_key TEXT NOT NULL,
  gmail_thread_id TEXT, customer_email TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('PROSPECTING','ACTIVE','NEGOTIATING','CUSTOMER_ACCEPTED','PENDING_HUMAN','HUMAN_APPROVED','HUMAN_REJECTED','INVOICED','CLOSED_WON','CLOSED_LOST','OPTED_OUT')),
  deal_id TEXT REFERENCES deals(id), commercial_service_id TEXT REFERENCES email_services(id), context_json TEXT NOT NULL DEFAULT '{}',
  last_confirmed_action TEXT, next_follow_up_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(account_email,conversation_key), UNIQUE(account_email,gmail_thread_id)
);
CREATE TABLE IF NOT EXISTS email_contact_suppressions (
  account_email TEXT NOT NULL, recipient_email TEXT NOT NULL, source_thread_id TEXT,
  opted_out_at TEXT NOT NULL, PRIMARY KEY(account_email,recipient_email)
);
CREATE TABLE IF NOT EXISTS email_account_limits (
  account_email TEXT PRIMARY KEY,
  max_outbound_per_24h INTEGER NOT NULL CHECK (max_outbound_per_24h >= 0),
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS email_messages (
  id INTEGER PRIMARY KEY, account_email TEXT NOT NULL, gmail_message_id TEXT NOT NULL,
  gmail_thread_id TEXT NOT NULL, conversation_id TEXT NOT NULL REFERENCES email_conversations(id),
  direction TEXT NOT NULL CHECK (direction IN ('INBOUND','OUTBOUND')),
  status TEXT NOT NULL CHECK (status IN ('PROCESSING','PROCESSED','FAILED')),
  claimed_by TEXT, lease_until TEXT, received_at TEXT NOT NULL, processed_at TEXT, error_code TEXT,
  UNIQUE(account_email,gmail_message_id)
);
CREATE TABLE IF NOT EXISTS email_message_events (
  id TEXT PRIMARY KEY, account_email TEXT NOT NULL, gmail_message_id TEXT NOT NULL,
  conversation_id TEXT NOT NULL REFERENCES email_conversations(id),
  event_type TEXT NOT NULL CHECK (event_type IN ('BLOCKER','NO_ACTION','REPLY_CONFIRMED')),
  reason_code TEXT NOT NULL, details_json TEXT NOT NULL DEFAULT '{}',
  status TEXT CHECK (status IN ('OPEN','RESOLVED')),
  policy_fingerprint TEXT, reported_at TEXT, delivery_attempted_at TEXT,
  delivery_acknowledged_at TEXT, delivery_reference TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  CHECK ((event_type='BLOCKER' AND status IS NOT NULL) OR (event_type!='BLOCKER' AND status IS NULL)),
  UNIQUE(account_email,gmail_message_id,event_type),
  FOREIGN KEY(account_email,gmail_message_id) REFERENCES email_messages(account_email,gmail_message_id)
);
CREATE TABLE IF NOT EXISTS email_send_attempts (
  id TEXT PRIMARY KEY, account_email TEXT NOT NULL, action_key TEXT NOT NULL,
  conversation_id TEXT NOT NULL REFERENCES email_conversations(id), action_kind TEXT NOT NULL CHECK (action_kind IN ('OUTREACH','REPLY','FOLLOW_UP','INVOICE','DELIVERABLE')),
  invoice_id TEXT REFERENCES sales_invoices(id),
  source_message_id TEXT, recipient_email TEXT NOT NULL, content_sha256 TEXT NOT NULL CHECK (length(content_sha256)=64),
  status TEXT NOT NULL CHECK (status IN ('PREPARED','SUBMITTING','CONFIRMED','UNKNOWN','FAILED')),
  gmail_message_id TEXT, gmail_thread_id TEXT, error_code TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, confirmed_at TEXT,
  CHECK ((action_kind='INVOICE' AND invoice_id IS NOT NULL AND source_message_id IS NULL) OR
         (action_kind='DELIVERABLE' AND invoice_id IS NULL AND source_message_id IS NOT NULL) OR
         (action_kind NOT IN ('INVOICE','DELIVERABLE') AND invoice_id IS NULL)),
  UNIQUE(account_email,action_key), UNIQUE(account_email,gmail_message_id)
);
CREATE TABLE IF NOT EXISTS email_run_locks (
  account_email TEXT PRIMARY KEY, owner_token TEXT NOT NULL, expires_at TEXT NOT NULL, acquired_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS email_services (
  id TEXT PRIMARY KEY, account_email TEXT NOT NULL,
  service_name TEXT NOT NULL CHECK (length(trim(service_name)) > 0),
  service_scope TEXT NOT NULL CHECK (length(trim(service_scope)) > 0),
  deliverables_json TEXT NOT NULL,
  initial_asking_price_atomic INTEGER NOT NULL CHECK (initial_asking_price_atomic > 0),
  minimum_acceptable_price_atomic INTEGER NOT NULL CHECK (minimum_acceptable_price_atomic > 0),
  available_capacity_units INTEGER NOT NULL CHECK (available_capacity_units >= 0),
  capacity_unit TEXT NOT NULL CHECK (length(trim(capacity_unit)) > 0),
  delivery_days INTEGER NOT NULL CHECK (delivery_days > 0),
  active INTEGER NOT NULL CHECK (active IN (0,1)), updated_at TEXT NOT NULL,
  UNIQUE(account_email,service_name),
  CHECK (initial_asking_price_atomic >= minimum_acceptable_price_atomic)
);
CREATE TABLE IF NOT EXISTS email_offers (
  id TEXT PRIMARY KEY, account_email TEXT NOT NULL,
  conversation_id TEXT NOT NULL REFERENCES email_conversations(id),
  service_id TEXT NOT NULL REFERENCES email_services(id),
  direction TEXT NOT NULL CHECK (direction IN ('INBOUND','OUTBOUND')),
  action_key TEXT, gmail_message_id TEXT,
  unit_price_atomic INTEGER NOT NULL CHECK (unit_price_atomic > 0),
  terms_json TEXT NOT NULL, policy_fingerprint TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('RECEIVED','PREPARED','CONFIRMED','UNKNOWN','FAILED')),
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  CHECK ((direction='INBOUND' AND action_key IS NULL AND gmail_message_id IS NOT NULL AND status='RECEIVED') OR
         (direction='OUTBOUND' AND action_key IS NOT NULL)),
  UNIQUE(account_email,action_key), UNIQUE(account_email,gmail_message_id)
);
CREATE INDEX IF NOT EXISTS idx_spend_intents_goal_status ON spend_intents(goal_id,status);
CREATE INDEX IF NOT EXISTS idx_events_created_at ON events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_type_entity_id ON events(event_type,entity_id);
CREATE INDEX IF NOT EXISTS idx_email_messages_thread ON email_messages(account_email,gmail_thread_id,received_at);
CREATE INDEX IF NOT EXISTS idx_email_messages_processing ON email_messages(account_email,status,lease_until);
CREATE INDEX IF NOT EXISTS idx_email_message_events_pending ON email_message_events(account_email,event_type,status,reported_at);
CREATE INDEX IF NOT EXISTS idx_email_send_unresolved ON email_send_attempts(account_email,status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_email_one_outreach_per_recipient
  ON email_send_attempts(account_email,recipient_email) WHERE action_kind='OUTREACH';
CREATE UNIQUE INDEX IF NOT EXISTS idx_email_one_reply_per_message
  ON email_send_attempts(account_email,source_message_id) WHERE action_kind='REPLY';
CREATE UNIQUE INDEX IF NOT EXISTS idx_email_one_followup_per_message
  ON email_send_attempts(account_email,source_message_id) WHERE action_kind='FOLLOW_UP';
CREATE UNIQUE INDEX IF NOT EXISTS idx_email_one_deliverable_per_deal
  ON email_send_attempts(action_key) WHERE action_kind='DELIVERABLE';
"""

EMAIL_SEND_ATTEMPTS_SQL = """
CREATE TABLE email_send_attempts (
  id TEXT PRIMARY KEY, account_email TEXT NOT NULL, action_key TEXT NOT NULL,
  conversation_id TEXT NOT NULL REFERENCES email_conversations(id),
  action_kind TEXT NOT NULL CHECK (action_kind IN ('OUTREACH','REPLY','FOLLOW_UP','INVOICE','DELIVERABLE')),
  invoice_id TEXT REFERENCES sales_invoices(id), source_message_id TEXT, recipient_email TEXT NOT NULL,
  content_sha256 TEXT NOT NULL CHECK (length(content_sha256)=64),
  status TEXT NOT NULL CHECK (status IN ('PREPARED','SUBMITTING','CONFIRMED','UNKNOWN','FAILED')),
  gmail_message_id TEXT, gmail_thread_id TEXT, error_code TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, confirmed_at TEXT,
  CHECK ((action_kind='INVOICE' AND invoice_id IS NOT NULL AND source_message_id IS NULL) OR
         (action_kind='DELIVERABLE' AND invoice_id IS NULL AND source_message_id IS NOT NULL) OR
         (action_kind NOT IN ('INVOICE','DELIVERABLE') AND invoice_id IS NULL)),
  UNIQUE(account_email,action_key), UNIQUE(account_email,gmail_message_id)
)
"""

REGISTRY_TABLE_SQL = """
CREATE TABLE registry_records (
  id TEXT PRIMARY KEY, record_type TEXT NOT NULL CHECK (record_type IN ('SPEND','REVENUE')),
  source_entity_id TEXT NOT NULL, operating_wallet TEXT NOT NULL, contract_address TEXT NOT NULL,
  chain TEXT NOT NULL CHECK (chain='ARC-TESTNET'), spend_id TEXT NOT NULL,
  goal_hash TEXT, spend_intent_hash TEXT, payment_evidence_hash TEXT, revenue_evidence_hash TEXT,
  amount_atomic INTEGER NOT NULL CHECK (amount_atomic > 0), earned_capital_atomic INTEGER,
  status TEXT NOT NULL CHECK (status IN ('PENDING','SUBMITTED','CONFIRMED','UNKNOWN','FAILED')),
  idempotency_key TEXT NOT NULL, provider_tx_ref TEXT, tx_hash TEXT, error_code TEXT,
  created_at TEXT NOT NULL, submitted_at TEXT, confirmed_at TEXT
)
"""

REGISTRY_COLUMNS = (
    "id", "record_type", "source_entity_id", "operating_wallet", "contract_address", "chain", "spend_id",
    "goal_hash", "spend_intent_hash", "payment_evidence_hash", "revenue_evidence_hash", "amount_atomic",
    "earned_capital_atomic", "status", "idempotency_key", "provider_tx_ref", "tx_hash", "error_code",
    "created_at", "submitted_at", "confirmed_at",
)


def connect() -> sqlite3.Connection:
    STATE_HOME.mkdir(mode=0o700, parents=True, exist_ok=True)
    STATE_HOME.chmod(0o700)
    connection = sqlite3.connect(DATABASE, timeout=10, isolation_level=None)
    DATABASE.chmod(0o600)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    return connection


def initialize() -> dict[str, str]:
    with connect() as db:
        db.executescript(SCHEMA)
        db.executescript(REGISTRY_V3_SCHEMA)
        _migrate_email_message_events(db)
        _migrate_email_conversations(db)
        _migrate_commercial_deals(db)
        _migrate_email_send_attempts(db)
        db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_email_one_invoice_per_invoice "
            "ON email_send_attempts(invoice_id) WHERE action_kind='INVOICE'"
        )
        db.execute(
            "INSERT OR IGNORE INTO email_contact_suppressions(account_email,recipient_email,source_thread_id,opted_out_at) "
            "SELECT lower(account_email),lower(customer_email),min(gmail_thread_id),min(updated_at) "
            "FROM email_conversations WHERE state='OPTED_OUT' GROUP BY lower(account_email),lower(customer_email)"
        )
        _migrate_registry_schema(db)
        db.executescript("""
            CREATE INDEX IF NOT EXISTS idx_registry_records_status ON registry_records(status,record_type,created_at);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_registry_current_revenue
              ON registry_records(chain,operating_wallet,revenue_evidence_hash) WHERE record_type='REVENUE';
            CREATE UNIQUE INDEX IF NOT EXISTS idx_registry_current_source
              ON registry_records(record_type,source_entity_id);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_registry_current_spend
              ON registry_records(chain,operating_wallet,spend_id)
              WHERE record_type='SPEND';
            CREATE UNIQUE INDEX IF NOT EXISTS idx_registry_current_idempotency
              ON registry_records(idempotency_key);
        """)
        columns={row[1] for row in db.execute("PRAGMA table_info(spend_intents)")}
        additions=(
            ("http_method","TEXT NOT NULL DEFAULT 'GET'"),
            ("payment_scheme","TEXT NOT NULL DEFAULT 'exact'"),
            ("payee_address","TEXT NOT NULL DEFAULT ''"),
            ("request_body_hash","TEXT NOT NULL DEFAULT '74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b'"),
            ("provider_payment_id","TEXT"),
            ("provider_amount_atomic","INTEGER"),
            ("executed_payment_scheme","TEXT"),
        )
        for name,definition in additions:
            if name not in columns:
                db.execute(f"ALTER TABLE spend_intents ADD COLUMN {name} {definition}")
        policy_columns={row[1] for row in db.execute("PRAGMA table_info(policies)")}
        if "minimum_wallet_balance_atomic" not in policy_columns:
            with transaction(db):
                db.execute("ALTER TABLE policies ADD COLUMN minimum_wallet_balance_atomic INTEGER NOT NULL DEFAULT 0 CHECK (minimum_wallet_balance_atomic >= 0)")
                if "reserve_floor_atomic" in policy_columns:
                    db.execute("UPDATE policies SET minimum_wallet_balance_atomic=reserve_floor_atomic")
        if "reinvested_operating_capital_atomic" not in policy_columns:
            db.execute("ALTER TABLE policies ADD COLUMN reinvested_operating_capital_atomic INTEGER NOT NULL DEFAULT 0 CHECK (reinvested_operating_capital_atomic >= 0)")
        deal_columns={row[1] for row in db.execute("PRAGMA table_info(deals)")}
        if "minimum_deal_approved" not in deal_columns:
            db.execute("ALTER TABLE deals ADD COLUMN minimum_deal_approved INTEGER NOT NULL DEFAULT 0 CHECK (minimum_deal_approved IN (0,1))")
        if "custom_or_legal_terms" not in deal_columns:
            db.execute("ALTER TABLE deals ADD COLUMN custom_or_legal_terms INTEGER NOT NULL DEFAULT 0 CHECK (custom_or_legal_terms IN (0,1))")
        if "custom_terms_approved" not in deal_columns:
            db.execute("ALTER TABLE deals ADD COLUMN custom_terms_approved INTEGER NOT NULL DEFAULT 0 CHECK (custom_terms_approved IN (0,1))")
        if "originating_spend_intent_id" not in deal_columns:
            db.execute("ALTER TABLE deals ADD COLUMN originating_spend_intent_id TEXT REFERENCES spend_intents(id)")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_spend_provider_payment_id ON spend_intents(provider_payment_id)")
    if not CONFIG.exists():
        write_config({"chain": "ARC-TESTNET", "operating_wallet": None})
    else:
        config=read_config()
        if "vault_address" in config:
            config.pop("vault_address")
            write_config(config)
    return {"database": str(DATABASE), "config": str(CONFIG)}


def _migrate_email_message_events(db: sqlite3.Connection) -> None:
    columns = {row[1] for row in db.execute("PRAGMA table_info(email_message_events)")}
    with transaction(db):
        if "delivery_acknowledged_at" not in columns:
            db.execute("ALTER TABLE email_message_events ADD COLUMN delivery_acknowledged_at TEXT")
        if "delivery_attempted_at" not in columns:
            db.execute("ALTER TABLE email_message_events ADD COLUMN delivery_attempted_at TEXT")
        if "delivery_reference" not in columns:
            db.execute("ALTER TABLE email_message_events ADD COLUMN delivery_reference TEXT")
        if "service_id" not in columns:
            db.execute("ALTER TABLE email_message_events ADD COLUMN service_id TEXT")
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_email_blocker_pending_delivery "
            "ON email_message_events(account_email,event_type,status,delivery_acknowledged_at)"
        )


def _migrate_email_conversations(db: sqlite3.Connection) -> None:
    columns = {row[1] for row in db.execute("PRAGMA table_info(email_conversations)")}
    if "commercial_service_id" not in columns:
        db.execute("ALTER TABLE email_conversations ADD COLUMN commercial_service_id TEXT REFERENCES email_services(id)")


def _migrate_commercial_deals(db: sqlite3.Connection) -> None:
    columns = {row[1] for row in db.execute("PRAGMA table_info(deals)")}
    with transaction(db):
        if "commercial_service_id" not in columns:
            db.execute("ALTER TABLE deals ADD COLUMN commercial_service_id TEXT REFERENCES email_services(id)")
        if "commercial_capacity_units" not in columns:
            db.execute("ALTER TABLE deals ADD COLUMN commercial_capacity_units INTEGER NOT NULL DEFAULT 0 CHECK (commercial_capacity_units >= 0)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_deals_commercial_capacity ON deals(commercial_service_id,status)")


def _migrate_email_send_attempts(db: sqlite3.Connection) -> None:
    columns = {row[1] for row in db.execute("PRAGMA table_info(email_send_attempts)")}
    table_sql = db.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='email_send_attempts'"
    ).fetchone()[0]
    if "invoice_id" in columns and "DELIVERABLE" in table_sql:
        return
    with transaction(db):
        db.execute("ALTER TABLE email_send_attempts RENAME TO email_send_attempts_before_invoice")
        db.execute(EMAIL_SEND_ATTEMPTS_SQL)
        invoice_id = "invoice_id" if "invoice_id" in columns else "NULL"
        db.execute(
            "INSERT INTO email_send_attempts "
            "(id,account_email,action_key,conversation_id,action_kind,invoice_id,source_message_id,recipient_email,content_sha256,status,"
            "gmail_message_id,gmail_thread_id,error_code,created_at,updated_at,confirmed_at) "
            f"SELECT id,account_email,action_key,conversation_id,action_kind,{invoice_id},source_message_id,recipient_email,content_sha256,status,"
            "gmail_message_id,gmail_thread_id,error_code,created_at,updated_at,confirmed_at "
            "FROM email_send_attempts_before_invoice"
        )
        db.execute("DROP TABLE email_send_attempts_before_invoice")
        db.execute("CREATE INDEX IF NOT EXISTS idx_email_send_unresolved ON email_send_attempts(account_email,status)")
        db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_email_one_outreach_per_recipient "
            "ON email_send_attempts(account_email,recipient_email) WHERE action_kind='OUTREACH'"
        )
        db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_email_one_reply_per_message "
            "ON email_send_attempts(account_email,source_message_id) WHERE action_kind='REPLY'"
        )
        db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_email_one_followup_per_message "
            "ON email_send_attempts(account_email,source_message_id) WHERE action_kind='FOLLOW_UP'"
        )
        db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_email_one_invoice_per_invoice "
            "ON email_send_attempts(invoice_id) WHERE action_kind='INVOICE'"
        )
        db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_email_one_deliverable_per_deal "
            "ON email_send_attempts(action_key) WHERE action_kind='DELIVERABLE'"
        )


def _migrate_registry_schema(db: sqlite3.Connection) -> None:
    columns = tuple(row[1] for row in db.execute("PRAGMA table_info(registry_records)"))
    indexes = {row[1] for row in db.execute("PRAGMA index_list(registry_records)")}
    required_indexes = {"idx_registry_current_revenue", "idx_registry_current_spend", "idx_registry_current_idempotency"}
    if columns == REGISTRY_COLUMNS and required_indexes.issubset(indexes):
        return
    with transaction(db):
        old_columns = {row[1] for row in db.execute("PRAGMA table_info(registry_records)")}
        if not set(REGISTRY_COLUMNS).issubset(old_columns):
            raise sqlite3.DatabaseError("METRON_REGISTRY_SCHEMA_CHANGED")
        db.execute("ALTER TABLE registry_records RENAME TO registry_records_before_schema_update")
        for index in db.execute("PRAGMA index_list(registry_records_before_schema_update)").fetchall():
            if index[3] == "c":
                name = index[1].replace('"', '""')
                db.execute(f'DROP INDEX "{name}"')
        db.execute(REGISTRY_TABLE_SQL)
        columns_sql = ",".join(REGISTRY_COLUMNS)
        db.execute(
            f"INSERT INTO registry_records ({columns_sql}) SELECT {columns_sql} "
            "FROM registry_records_before_schema_update"
        )
        db.execute("DROP TABLE registry_records_before_schema_update")


def read_config() -> dict:
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        raise ValueError("METRON_CONFIG_INVALID") from exc


def email_service_policy(db: sqlite3.Connection, account_email: str, service_id: str) -> tuple[dict, str] | None:
    row = db.execute(
        "SELECT * FROM email_services WHERE account_email=? AND id=?", (account_email, service_id)
    ).fetchone()
    if row is None:
        return None
    try:
        deliverables = json.loads(row["deliverables_json"])
        asking = row["initial_asking_price_atomic"]
        minimum = row["minimum_acceptable_price_atomic"]
        capacity = row["available_capacity_units"]
        delivery_days = row["delivery_days"]
        active = row["active"]
        text_fields = (row["service_name"], row["service_scope"], row["capacity_unit"])
        if (
            any(not isinstance(value, str) or not value.strip() for value in text_fields)
            or not isinstance(deliverables, list) or not deliverables
            or any(not isinstance(value, str) or not value.strip() or len(value) > 512 for value in deliverables)
            or len(set(deliverables)) != len(deliverables)
            or isinstance(asking, bool) or not isinstance(asking, int) or asking <= 0
            or isinstance(minimum, bool) or not isinstance(minimum, int) or minimum <= 0 or minimum > asking
            or isinstance(capacity, bool) or not isinstance(capacity, int) or capacity < 0
            or isinstance(delivery_days, bool) or not isinstance(delivery_days, int) or delivery_days <= 0
            or isinstance(active, bool) or not isinstance(active, int) or active not in (0, 1)
        ):
            return None
        chain = read_config().get("chain", "ARC-TESTNET")
        if chain != "ARC-TESTNET":
            return None
        policy = {
            "service_id": row["id"],
            "account_email": account_email,
            "service_name": row["service_name"].strip(),
            "service_scope": row["service_scope"].strip(),
            "deliverables": deliverables,
            "initial_asking_price_atomic": asking,
            "minimum_acceptable_price_atomic": minimum,
            "available_capacity_units": capacity,
            "capacity_unit": row["capacity_unit"].strip(),
            "delivery_days": delivery_days,
            "active": bool(active),
            "currency": "USDC",
            "chain": chain,
        }
        encoded = json.dumps(policy, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return policy, hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def email_service_remaining_capacity(
    db: sqlite3.Connection, service_id: str, configured_capacity: int, exclude_deal_id: str | None = None
) -> int:
    sql = (
        "SELECT COALESCE(SUM(commercial_capacity_units),0) FROM deals WHERE commercial_service_id=? "
        "AND status NOT IN ('CLOSED_LOST','CLOSED_WON','HUMAN_REJECTED')"
    )
    parameters: tuple[object, ...] = (service_id,)
    if exclude_deal_id is not None:
        sql += " AND id!=?"
        parameters += (exclude_deal_id,)
    committed = db.execute(sql, parameters).fetchone()[0]
    return max(0, configured_capacity - committed)


def write_config(data: dict) -> None:
    STATE_HOME.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = CONFIG.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(CONFIG)


@contextmanager
def transaction(db: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    db.execute("BEGIN IMMEDIATE")
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise


def next_id(db: sqlite3.Connection, table: str, prefix: str) -> str:
    if table not in {"goals", "counterparties", "spend_intents", "deals", "sales_invoices", "payment_entries", "payment_evidence", "journal_entries", "registry_records"}:
        raise ValueError("METRON_INVALID_ID_TABLE")
    number = db.execute(f"SELECT COUNT(*) + 1 FROM {table}").fetchone()[0]
    return f"{prefix}-{number:06d}"


def event(db: sqlite3.Connection, event_type: str, entity_type: str, entity_id: str, summary: str, data: dict, now: str) -> None:
    db.execute(
        "INSERT INTO events(event_type,entity_type,entity_id,summary,data_json,created_at) VALUES (?,?,?,?,?,?)",
        (event_type, entity_type, entity_id, summary, json.dumps(data, sort_keys=True), now),
    )
