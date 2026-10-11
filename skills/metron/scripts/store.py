from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


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
  created_at TEXT NOT NULL, submitted_at TEXT, confirmed_at TEXT,
  UNIQUE(record_type, source_entity_id), UNIQUE(chain, operating_wallet, spend_id, record_type)
);
CREATE INDEX IF NOT EXISTS idx_spend_intents_goal_status ON spend_intents(goal_id,status);
CREATE INDEX IF NOT EXISTS idx_events_created_at ON events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_registry_records_status ON registry_records(status,record_type,created_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_registry_revenue_evidence ON registry_records(chain,operating_wallet,revenue_evidence_hash) WHERE record_type='REVENUE';
"""


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


def read_config() -> dict:
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        raise ValueError("METRON_CONFIG_INVALID") from exc


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
