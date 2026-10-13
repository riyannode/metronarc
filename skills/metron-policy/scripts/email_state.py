from __future__ import annotations

import json
import re
import secrets
import sqlite3
import uuid
from datetime import datetime, timezone

import finance
import store


EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+\Z")
STATES = {
    "PROSPECTING", "ACTIVE", "NEGOTIATING", "CUSTOMER_ACCEPTED", "PENDING_HUMAN",
    "HUMAN_APPROVED", "HUMAN_REJECTED", "INVOICED", "CLOSED_WON", "CLOSED_LOST", "OPTED_OUT",
}
DEFAULT_OUTBOUND_PER_24H = 10
NO_ACTION_CODES = {"AUTOMATED_MESSAGE", "DUPLICATE_CONTEXT", "OPT_OUT", "OUT_OF_SCOPE"}


def _input(data: dict, allowed: set[str], required: set[str] = frozenset()) -> None:
    if set(data) - allowed or not required.issubset(data):
        raise finance.DomainError("METRON_INVALID_INPUT")


def _text(data: dict, key: str, maximum: int = 512) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise finance.DomainError("METRON_INVALID_INPUT")
    return value.strip()


def _email(data: dict, key: str) -> str:
    value = _text(data, key, 320).lower()
    if not EMAIL.fullmatch(value):
        raise finance.DomainError("METRON_INVALID_INPUT")
    return value


def _json_object(value: object, maximum: int = 16000) -> str:
    if not isinstance(value, dict):
        raise finance.DomainError("METRON_INVALID_INPUT")
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if len(encoded.encode("utf-8")) > maximum:
        raise finance.DomainError("METRON_INVALID_INPUT")
    return encoded


def _blocker_details(value: object) -> str:
    if not isinstance(value, dict) or set(value) != {"missing", "next_action"}:
        raise finance.DomainError("METRON_INVALID_INPUT")
    missing = value["missing"]
    if not isinstance(missing, list) or not 1 <= len(missing) <= 8:
        raise finance.DomainError("METRON_INVALID_INPUT")
    normalized = []
    for item in missing:
        if not isinstance(item, str) or not item.strip() or len(item.strip()) > 128:
            raise finance.DomainError("METRON_INVALID_INPUT")
        normalized.append(item.strip())
    if len(set(normalized)) != len(normalized):
        raise finance.DomainError("METRON_INVALID_INPUT")
    next_action = value["next_action"]
    if not isinstance(next_action, str) or not next_action.strip() or len(next_action.strip()) > 512:
        raise finance.DomainError("METRON_INVALID_INPUT")
    return _json_object({"missing": normalized, "next_action": next_action.strip()}, 2048)


def _timestamp(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise finance.DomainError("METRON_INVALID_INPUT")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise finance.DomainError("METRON_INVALID_INPUT") from None
    if parsed.tzinfo is None:
        raise finance.DomainError("METRON_INVALID_INPUT")
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _lock(db: sqlite3.Connection, account: str, owner: str) -> sqlite3.Row:
    row = db.execute(
        "SELECT * FROM email_run_locks WHERE account_email=? AND owner_token=? AND julianday(expires_at)>julianday('now')",
        (account, owner),
    ).fetchone()
    if row is None:
        raise finance.DomainError("METRON_EMAIL_RUN_LOCK_LOST")
    return row


def _conversation(db: sqlite3.Connection, account: str, conversation_id: str) -> sqlite3.Row:
    row = db.execute(
        "SELECT * FROM email_conversations WHERE account_email=? AND id=?", (account, conversation_id)
    ).fetchone()
    if row is None:
        raise finance.DomainError("METRON_EMAIL_CONVERSATION_NOT_FOUND")
    return row


def _invoice_for_delivery(db: sqlite3.Connection, invoice_id: str, conversation: sqlite3.Row, recipient: str) -> sqlite3.Row:
    row = db.execute(
        "SELECT i.id,i.deal_id,i.status,d.status AS deal_status,c.external_ref "
        "FROM sales_invoices i JOIN deals d ON d.id=i.deal_id JOIN counterparties c ON c.id=i.counterparty_id WHERE i.id=?",
        (invoice_id,),
    ).fetchone()
    if row is None:
        raise finance.DomainError("METRON_INVOICE_NOT_FOUND")
    if row["status"] != "OPEN" or row["deal_status"] != "INVOICED":
        raise finance.DomainError("METRON_INVOICE_NOT_POSTED")
    if conversation["deal_id"] != row["deal_id"]:
        raise finance.DomainError("METRON_EMAIL_IDENTITY_MISMATCH")
    try:
        verified_recipient = _email({"recipient_email": row["external_ref"]}, "recipient_email")
    except finance.DomainError:
        raise finance.DomainError("METRON_EMAIL_IDENTITY_MISMATCH") from None
    if recipient != verified_recipient:
        raise finance.DomainError("METRON_EMAIL_IDENTITY_MISMATCH")
    return row


def _is_suppressed(db: sqlite3.Connection, account: str, recipient: str) -> bool:
    return db.execute(
        "SELECT 1 FROM email_contact_suppressions WHERE account_email=? AND recipient_email=?",
        (account, recipient),
    ).fetchone() is not None


def _record_opt_out(db: sqlite3.Connection, account: str, recipient: str, thread: str | None) -> None:
    db.execute(
        "INSERT OR IGNORE INTO email_contact_suppressions(account_email,recipient_email,source_thread_id,opted_out_at) "
        "VALUES (?,?,?,datetime('now'))",
        (account, recipient, thread),
    )


def _conversation_for_thread(
    db: sqlite3.Connection, account: str, thread: str, customer: str
) -> sqlite3.Row:
    row = db.execute(
        "SELECT * FROM email_conversations WHERE account_email=? AND gmail_thread_id=?", (account, thread)
    ).fetchone()
    if row:
        if row["customer_email"] != customer:
            raise finance.DomainError("METRON_EMAIL_IDENTITY_MISMATCH")
        return row
    conversation_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO email_conversations(id,account_email,conversation_key,gmail_thread_id,customer_email,state,created_at,updated_at) "
        "VALUES (?,?,?,?,?,'ACTIVE',datetime('now'),datetime('now'))",
        (conversation_id, account, f"thread:{thread}", thread, customer),
    )
    return _conversation(db, account, conversation_id)


def execute(db: sqlite3.Connection, data: dict) -> dict:
    action = data.get("action")
    if not isinstance(action, str):
        raise finance.DomainError("METRON_INVALID_INPUT")

    if action == "run-acquire":
        _input(data, {"action", "account_email", "lease_seconds"}, {"action", "account_email"})
        account = _email(data, "account_email")
        lease = data.get("lease_seconds", 300)
        if isinstance(lease, bool) or not isinstance(lease, int) or not 30 <= lease <= 3600:
            raise finance.DomainError("METRON_INVALID_INPUT")
        with store.transaction(db):
            current = db.execute(
                "SELECT owner_token,expires_at FROM email_run_locks WHERE account_email=? AND julianday(expires_at)>julianday('now')",
                (account,),
            ).fetchone()
            if current:
                return {"status": "BUSY", "expires_at": current["expires_at"]}
            owner = secrets.token_urlsafe(24)
            db.execute(
                "INSERT INTO email_run_locks(account_email,owner_token,expires_at,acquired_at) VALUES (?,?,datetime('now',?),datetime('now')) "
                "ON CONFLICT(account_email) DO UPDATE SET owner_token=excluded.owner_token,expires_at=excluded.expires_at,acquired_at=excluded.acquired_at",
                (account, owner, f"+{lease} seconds"),
            )
            return {"status": "ACQUIRED", "owner_token": owner, "expires_in_seconds": lease}

    if action in {"run-renew", "run-release"}:
        _input(data, {"action", "account_email", "owner_token", "lease_seconds"}, {"action", "account_email", "owner_token"})
        account = _email(data, "account_email")
        owner = _text(data, "owner_token", 128)
        with store.transaction(db):
            _lock(db, account, owner)
            if action == "run-release":
                db.execute("DELETE FROM email_run_locks WHERE account_email=? AND owner_token=?", (account, owner))
                return {"status": "RELEASED"}
            lease = data.get("lease_seconds", 300)
            if isinstance(lease, bool) or not isinstance(lease, int) or not 30 <= lease <= 3600:
                raise finance.DomainError("METRON_INVALID_INPUT")
            db.execute(
                "UPDATE email_run_locks SET expires_at=datetime('now',?) WHERE account_email=? AND owner_token=?",
                (f"+{lease} seconds", account, owner),
            )
            return {"status": "RENEWED", "expires_in_seconds": lease}

    if action == "send-limit-get":
        _input(data, {"action", "account_email"}, {"action", "account_email"})
        account = _email(data, "account_email")
        row = db.execute(
            "SELECT max_outbound_per_24h FROM email_account_limits WHERE account_email=?", (account,)
        ).fetchone()
        return {
            "account_email": account,
            "max_outbound_per_24h": row["max_outbound_per_24h"] if row else DEFAULT_OUTBOUND_PER_24H,
            "configured": row is not None,
        }

    if action == "send-limit-set":
        _input(data, {"action", "account_email", "max_outbound_per_24h"},
               {"action", "account_email", "max_outbound_per_24h"})
        account = _email(data, "account_email")
        limit = data["max_outbound_per_24h"]
        if isinstance(limit, bool) or not isinstance(limit, int) or not 0 <= limit <= 2147483647:
            raise finance.DomainError("METRON_INVALID_INPUT")
        with store.transaction(db):
            db.execute(
                "INSERT INTO email_account_limits(account_email,max_outbound_per_24h,updated_at) VALUES (?,?,datetime('now')) "
                "ON CONFLICT(account_email) DO UPDATE SET max_outbound_per_24h=excluded.max_outbound_per_24h,updated_at=datetime('now')",
                (account, limit),
            )
        return {"status": "UPDATED", "account_email": account, "max_outbound_per_24h": limit}

    if action == "suppression-clear":
        _input(data, {"action", "account_email", "recipient_email", "user_confirmed"},
               {"action", "account_email", "recipient_email", "user_confirmed"})
        account = _email(data, "account_email")
        recipient = _email(data, "recipient_email")
        if data["user_confirmed"] is not True:
            raise finance.DomainError("METRON_EMAIL_SUPPRESSION_CHANGE_REQUIRES_USER")
        with store.transaction(db):
            result = db.execute(
                "DELETE FROM email_contact_suppressions WHERE account_email=? AND recipient_email=?",
                (account, recipient),
            )
        return {"status": "CLEARED" if result.rowcount else "NOT_SUPPRESSED", "account_email": account, "recipient_email": recipient}

    if action == "conversation-list":
        _input(data, {"action", "account_email"}, {"action", "account_email"})
        account = _email(data, "account_email")
        rows = db.execute(
            "SELECT id,conversation_key,gmail_thread_id,customer_email,state,deal_id,context_json,last_confirmed_action,next_follow_up_at,updated_at "
            "FROM email_conversations WHERE account_email=? ORDER BY updated_at DESC", (account,)
        ).fetchall()
        return [dict(row) for row in rows]

    if action == "conversation-upsert":
        _input(data, {"action", "account_email", "owner_token", "conversation_key", "gmail_thread_id", "customer_email", "state", "deal_id", "context", "next_follow_up_at"},
               {"action", "account_email", "owner_token", "conversation_key", "customer_email"})
        account = _email(data, "account_email")
        owner = _text(data, "owner_token", 128)
        key = _text(data, "conversation_key", 512)
        customer = _email(data, "customer_email")
        thread = _text(data, "gmail_thread_id", 512) if data.get("gmail_thread_id") is not None else None
        requested_state = data.get("state")
        if requested_state is not None and requested_state not in STATES:
            raise finance.DomainError("METRON_INVALID_INPUT")
        has_context = "context" in data
        context = _json_object(data.get("context", {}))
        has_next_follow_up = "next_follow_up_at" in data
        next_follow_up = _timestamp(data.get("next_follow_up_at"))
        if requested_state in {"CUSTOMER_ACCEPTED", "PENDING_HUMAN", "HUMAN_REJECTED", "INVOICED", "CLOSED_WON", "CLOSED_LOST", "OPTED_OUT"}:
            has_next_follow_up = True
            next_follow_up = None
        with store.transaction(db):
            _lock(db, account, owner)
            by_key = db.execute(
                "SELECT * FROM email_conversations WHERE account_email=? AND conversation_key=?", (account, key)
            ).fetchone()
            by_thread = db.execute(
                "SELECT * FROM email_conversations WHERE account_email=? AND gmail_thread_id=?", (account, thread)
            ).fetchone() if thread else None
            if by_key and by_thread and by_key["id"] != by_thread["id"]:
                raise finance.DomainError("METRON_EMAIL_IDENTITY_MISMATCH")
            row = by_key or by_thread
            if row:
                if row["customer_email"] != customer or (row["gmail_thread_id"] and thread and row["gmail_thread_id"] != thread):
                    raise finance.DomainError("METRON_EMAIL_IDENTITY_MISMATCH")
                deal_id = data.get("deal_id", row["deal_id"])
                if deal_id is not None and not db.execute("SELECT 1 FROM deals WHERE id=?", (deal_id,)).fetchone():
                    raise finance.DomainError("METRON_DEAL_NOT_FOUND")
                next_thread = row["gmail_thread_id"] or thread
                state = requested_state or row["state"]
                if row["state"] == "OPTED_OUT" and state != "OPTED_OUT" and _is_suppressed(db, account, customer):
                    raise finance.DomainError("METRON_EMAIL_OPTED_OUT")
                db.execute(
                    "UPDATE email_conversations SET gmail_thread_id=?,state=?,deal_id=?,context_json=CASE WHEN ? THEN ? ELSE context_json END,next_follow_up_at=CASE WHEN ? THEN ? ELSE next_follow_up_at END,updated_at=datetime('now') WHERE id=?",
                    (next_thread, state, deal_id, has_context, context, has_next_follow_up, next_follow_up, row["id"]),
                )
                if requested_state == "OPTED_OUT":
                    _record_opt_out(db, account, customer, next_thread)
                return {"status": "UPDATED", "conversation_id": row["id"], "gmail_thread_id": next_thread, "state": state}
            deal_id = data.get("deal_id")
            if deal_id is not None and not db.execute("SELECT 1 FROM deals WHERE id=?", (deal_id,)).fetchone():
                raise finance.DomainError("METRON_DEAL_NOT_FOUND")
            conversation_id = str(uuid.uuid4())
            state = requested_state or "PROSPECTING"
            db.execute(
                "INSERT INTO email_conversations(id,account_email,conversation_key,gmail_thread_id,customer_email,state,deal_id,context_json,next_follow_up_at,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,datetime('now'),datetime('now'))",
                (conversation_id, account, key, thread, customer, state, deal_id, context, next_follow_up),
            )
            if requested_state == "OPTED_OUT":
                _record_opt_out(db, account, customer, thread)
            return {"status": "CREATED", "conversation_id": conversation_id, "gmail_thread_id": thread, "state": state}

    if action == "conversation-update":
        _input(data, {"action", "account_email", "owner_token", "conversation_id", "state", "deal_id", "context", "next_follow_up_at"},
               {"action", "account_email", "owner_token", "conversation_id"})
        account = _email(data, "account_email")
        owner = _text(data, "owner_token", 128)
        conversation_id = _text(data, "conversation_id", 64)
        state = data.get("state")
        if state is not None and state not in STATES:
            raise finance.DomainError("METRON_INVALID_INPUT")
        context = _json_object(data["context"]) if "context" in data else None
        has_next_follow_up = "next_follow_up_at" in data
        next_follow_up = _timestamp(data["next_follow_up_at"]) if has_next_follow_up else None
        if state in {"CUSTOMER_ACCEPTED", "PENDING_HUMAN", "HUMAN_REJECTED", "INVOICED", "CLOSED_WON", "CLOSED_LOST", "OPTED_OUT"}:
            has_next_follow_up = True
            next_follow_up = None
        with store.transaction(db):
            _lock(db, account, owner)
            row = _conversation(db, account, conversation_id)
            next_state = state or row["state"]
            if row["state"] == "OPTED_OUT" and next_state != "OPTED_OUT" and _is_suppressed(db, account, row["customer_email"]):
                raise finance.DomainError("METRON_EMAIL_OPTED_OUT")
            deal_id = data.get("deal_id", row["deal_id"])
            if deal_id is not None and not db.execute("SELECT 1 FROM deals WHERE id=?", (deal_id,)).fetchone():
                raise finance.DomainError("METRON_DEAL_NOT_FOUND")
            db.execute(
                "UPDATE email_conversations SET state=COALESCE(?,state),deal_id=?,context_json=COALESCE(?,context_json),next_follow_up_at=CASE WHEN ? THEN ? ELSE next_follow_up_at END,updated_at=datetime('now') WHERE id=?",
                (state, deal_id, context, has_next_follow_up, next_follow_up, conversation_id),
            )
            if state == "OPTED_OUT":
                _record_opt_out(db, account, row["customer_email"], row["gmail_thread_id"])
            return {"status": "UPDATED", "conversation_id": conversation_id, "state": state or row["state"]}

    if action == "message-claim":
        _input(data, {"action", "account_email", "owner_token", "gmail_message_id", "gmail_thread_id", "customer_email", "lease_seconds"},
               {"action", "account_email", "owner_token", "gmail_message_id", "gmail_thread_id", "customer_email"})
        account = _email(data, "account_email")
        owner = _text(data, "owner_token", 128)
        message_id = _text(data, "gmail_message_id", 512)
        thread = _text(data, "gmail_thread_id", 512)
        customer = _email(data, "customer_email")
        lease = data.get("lease_seconds", 300)
        if isinstance(lease, bool) or not isinstance(lease, int) or not 30 <= lease <= 3600:
            raise finance.DomainError("METRON_INVALID_INPUT")
        with store.transaction(db):
            _lock(db, account, owner)
            conversation = _conversation_for_thread(db, account, thread, customer)
            row = db.execute(
                "SELECT * FROM email_messages WHERE account_email=? AND gmail_message_id=?", (account, message_id)
            ).fetchone()
            if row:
                if row["gmail_thread_id"] != thread or row["conversation_id"] != conversation["id"] or row["direction"] != "INBOUND":
                    raise finance.DomainError("METRON_EMAIL_IDENTITY_MISMATCH")
                blocker = db.execute(
                    "SELECT status FROM email_message_events WHERE account_email=? AND gmail_message_id=? AND event_type='BLOCKER'",
                    (account, message_id),
                ).fetchone()
                if blocker and blocker["status"] == "OPEN":
                    return {"status": "BLOCKED_COMMERCIAL_POLICY", "conversation_id": conversation["id"]}
                if row["status"] == "PROCESSED":
                    if blocker and blocker["status"] == "RESOLVED":
                        prior_reply = db.execute(
                            "SELECT 1 FROM email_send_attempts WHERE account_email=? AND source_message_id=? AND action_kind='REPLY' LIMIT 1",
                            (account, message_id),
                        ).fetchone()
                        if prior_reply:
                            return {"status": "DUPLICATE_ACTION_EXISTS", "conversation_id": conversation["id"]}
                        db.execute(
                            "UPDATE email_messages SET status='PROCESSING',claimed_by=?,lease_until=datetime('now',?),error_code=NULL WHERE id=?",
                            (owner, f"+{lease} seconds", row["id"]),
                        )
                        return {"status": "RECOVERED", "conversation_id": conversation["id"]}
                    return {"status": "DUPLICATE", "conversation_id": conversation["id"]}
                if row["status"] == "PROCESSING" and row["claimed_by"] == owner:
                    return {"status": "ALREADY_CLAIMED", "conversation_id": conversation["id"]}
                unresolved = db.execute(
                    "SELECT 1 FROM email_send_attempts WHERE account_email=? AND source_message_id=? AND status IN ('SUBMITTING','UNKNOWN') LIMIT 1",
                    (account, message_id),
                ).fetchone()
                if unresolved:
                    return {"status": "BLOCKED_UNRESOLVED_SEND", "conversation_id": conversation["id"]}
                db.execute(
                    "UPDATE email_messages SET status='PROCESSING',claimed_by=?,lease_until=datetime('now',?),error_code=NULL WHERE id=?",
                    (owner, f"+{lease} seconds", row["id"]),
                )
                return {"status": "RECLAIMED", "conversation_id": conversation["id"]}
            db.execute(
                "INSERT INTO email_messages(account_email,gmail_message_id,gmail_thread_id,conversation_id,direction,status,claimed_by,lease_until,received_at) "
                "VALUES (?,?,?,?,'INBOUND','PROCESSING',?,datetime('now',?),datetime('now'))",
                (account, message_id, thread, conversation["id"], owner, f"+{lease} seconds"),
            )
            db.execute("UPDATE email_conversations SET next_follow_up_at=NULL,updated_at=datetime('now') WHERE id=?", (conversation["id"],))
            return {"status": "CLAIMED", "conversation_id": conversation["id"]}

    if action in {"message-complete", "message-fail"}:
        allowed = {"action", "account_email", "owner_token", "gmail_message_id", "error_code", "no_action_code"}
        required = {"action", "account_email", "owner_token", "gmail_message_id"}
        _input(data, allowed, required)
        if action == "message-fail" and "no_action_code" in data:
            raise finance.DomainError("METRON_INVALID_INPUT")
        account = _email(data, "account_email")
        owner = _text(data, "owner_token", 128)
        message_id = _text(data, "gmail_message_id", 512)
        with store.transaction(db):
            _lock(db, account, owner)
            row = db.execute(
                "SELECT * FROM email_messages WHERE account_email=? AND gmail_message_id=?", (account, message_id)
            ).fetchone()
            if row is None or row["direction"] != "INBOUND":
                raise finance.DomainError("METRON_EMAIL_MESSAGE_NOT_FOUND")
            if row["status"] == "PROCESSED" and action == "message-complete":
                return {"status": "ALREADY_PROCESSED"}
            if row["status"] != "PROCESSING" or row["claimed_by"] != owner:
                raise finance.DomainError("METRON_EMAIL_MESSAGE_LOCKED")
            unresolved = db.execute(
                "SELECT 1 FROM email_send_attempts WHERE account_email=? AND source_message_id=? AND status IN ('PREPARED','SUBMITTING','UNKNOWN') LIMIT 1",
                (account, message_id),
            ).fetchone()
            if unresolved:
                raise finance.DomainError("METRON_EMAIL_SEND_UNRESOLVED")
            if action == "message-complete":
                confirmed_reply = db.execute(
                    "SELECT id FROM email_send_attempts WHERE account_email=? AND source_message_id=? AND action_kind='REPLY' AND status='CONFIRMED' LIMIT 1",
                    (account, message_id),
                ).fetchone()
                blocker = db.execute(
                    "SELECT status FROM email_message_events WHERE account_email=? AND gmail_message_id=? AND event_type='BLOCKER'",
                    (account, message_id),
                ).fetchone()
                if confirmed_reply:
                    db.execute(
                        "INSERT OR IGNORE INTO email_message_events(id,account_email,gmail_message_id,conversation_id,event_type,reason_code,details_json,created_at,updated_at) "
                        "VALUES (?,?,?,?,'REPLY_CONFIRMED','GMAIL_REPLY_CONFIRMED',?,datetime('now'),datetime('now'))",
                        (str(uuid.uuid4()), account, message_id, row["conversation_id"], _json_object({"send_attempt_id": confirmed_reply["id"]})),
                    )
                elif blocker and blocker["status"] == "OPEN":
                    pass
                elif "no_action_code" in data:
                    reason = _text(data, "no_action_code", 64)
                    if reason not in NO_ACTION_CODES:
                        raise finance.DomainError("METRON_INVALID_INPUT")
                    details = "{}"
                    db.execute(
                        "INSERT OR IGNORE INTO email_message_events(id,account_email,gmail_message_id,conversation_id,event_type,reason_code,details_json,created_at,updated_at) "
                        "VALUES (?,?,?,?,'NO_ACTION',?,?,datetime('now'),datetime('now'))",
                        (str(uuid.uuid4()), account, message_id, row["conversation_id"], reason, details),
                    )
                else:
                    raise finance.DomainError("METRON_EMAIL_ACTION_REQUIRED")
                db.execute("UPDATE email_messages SET status='PROCESSED',processed_at=datetime('now'),lease_until=NULL WHERE id=?", (row["id"],))
                return {"status": "PROCESSED"}
            error = _text(data, "error_code", 128) if data.get("error_code") else "METRON_EMAIL_PROCESSING_FAILED"
            db.execute("UPDATE email_messages SET status='FAILED',error_code=?,lease_until=NULL WHERE id=?", (error, row["id"]))
            return {"status": "FAILED", "error_code": error}

    if action == "blocker-record":
        _input(data, {"action", "account_email", "owner_token", "gmail_message_id", "blocker_code", "details"},
               {"action", "account_email", "owner_token", "gmail_message_id", "blocker_code", "details"})
        account = _email(data, "account_email")
        owner = _text(data, "owner_token", 128)
        message_id = _text(data, "gmail_message_id", 512)
        code = _text(data, "blocker_code", 64)
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", code):
            raise finance.DomainError("METRON_INVALID_INPUT")
        details = _blocker_details(data["details"])
        with store.transaction(db):
            _lock(db, account, owner)
            message = db.execute(
                "SELECT * FROM email_messages WHERE account_email=? AND gmail_message_id=? AND direction='INBOUND'",
                (account, message_id),
            ).fetchone()
            if message is None:
                raise finance.DomainError("METRON_EMAIL_MESSAGE_NOT_FOUND")
            if message["status"] == "PROCESSING" and message["claimed_by"] != owner:
                raise finance.DomainError("METRON_EMAIL_MESSAGE_LOCKED")
            if message["status"] not in {"PROCESSING", "PROCESSED"}:
                raise finance.DomainError("METRON_EMAIL_MESSAGE_LOCKED")
            prior_attempt = db.execute(
                "SELECT status FROM email_send_attempts WHERE account_email=? AND source_message_id=? AND action_kind='REPLY' LIMIT 1",
                (account, message_id),
            ).fetchone()
            if prior_attempt and prior_attempt["status"] != "FAILED":
                raise finance.DomainError("METRON_EMAIL_REPLY_ALREADY_ATTEMPTED")
            existing = db.execute(
                "SELECT * FROM email_message_events WHERE account_email=? AND gmail_message_id=? AND event_type='BLOCKER'",
                (account, message_id),
            ).fetchone()
            if existing:
                if existing["reason_code"] != code or existing["details_json"] != details:
                    raise finance.DomainError("METRON_EMAIL_BLOCKER_CONFLICT")
                if message["status"] == "PROCESSING":
                    db.execute(
                        "UPDATE email_messages SET status='PROCESSED',processed_at=datetime('now'),lease_until=NULL WHERE id=?",
                        (message["id"],),
                    )
                return {"status": "EXISTS", "blocker_id": existing["id"], "reported": existing["reported_at"] is not None}
            event_id = str(uuid.uuid4())
            db.execute(
                "INSERT INTO email_message_events(id,account_email,gmail_message_id,conversation_id,event_type,reason_code,details_json,status,created_at,updated_at) "
                "VALUES (?,?,?,?,'BLOCKER',?,?, 'OPEN',datetime('now'),datetime('now'))",
                (event_id, account, message_id, message["conversation_id"], code, details),
            )
            if message["status"] == "PROCESSING":
                db.execute(
                    "UPDATE email_messages SET status='PROCESSED',processed_at=datetime('now'),lease_until=NULL WHERE id=?",
                    (message["id"],),
                )
            return {"status": "RECORDED", "blocker_id": event_id, "reported": False}

    if action == "blocker-report":
        _input(data, {"action", "account_email", "owner_token"}, {"action", "account_email", "owner_token"})
        account = _email(data, "account_email")
        owner = _text(data, "owner_token", 128)
        with store.transaction(db):
            _lock(db, account, owner)
            rows = db.execute(
                "SELECT e.id,e.gmail_message_id,e.conversation_id,e.reason_code,e.details_json,e.created_at,c.gmail_thread_id,c.customer_email "
                "FROM email_message_events e JOIN email_conversations c ON c.id=e.conversation_id "
                "WHERE e.account_email=? AND e.event_type='BLOCKER' AND e.status='OPEN' AND e.reported_at IS NULL ORDER BY e.created_at",
                (account,),
            ).fetchall()
            if rows:
                ids = [row["id"] for row in rows]
                db.executemany("UPDATE email_message_events SET reported_at=datetime('now'),updated_at=datetime('now') WHERE id=?", [(item,) for item in ids])
            blockers = [
                {**dict(row), "details": json.loads(row["details_json"])} for row in rows
            ]
            for blocker in blockers:
                blocker.pop("details_json")
            return {"status": "REPORTED" if blockers else "NO_PENDING_BLOCKERS", "blockers": blockers}

    if action == "blocker-resolve":
        _input(data, {"action", "account_email", "owner_token", "gmail_message_id", "policy_fingerprint"},
               {"action", "account_email", "owner_token", "gmail_message_id", "policy_fingerprint"})
        account = _email(data, "account_email")
        owner = _text(data, "owner_token", 128)
        message_id = _text(data, "gmail_message_id", 512)
        fingerprint = _text(data, "policy_fingerprint", 64).lower()
        if not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
            raise finance.DomainError("METRON_INVALID_INPUT")
        with store.transaction(db):
            _lock(db, account, owner)
            blocker = db.execute(
                "SELECT * FROM email_message_events WHERE account_email=? AND gmail_message_id=? AND event_type='BLOCKER'",
                (account, message_id),
            ).fetchone()
            if blocker is None:
                raise finance.DomainError("METRON_EMAIL_BLOCKER_NOT_FOUND")
            if blocker["status"] == "RESOLVED":
                if blocker["policy_fingerprint"] != fingerprint:
                    raise finance.DomainError("METRON_EMAIL_BLOCKER_RESOLUTION_CONFLICT")
                return {"status": "ALREADY_RESOLVED", "blocker_id": blocker["id"]}
            db.execute(
                "UPDATE email_message_events SET status='RESOLVED',policy_fingerprint=?,updated_at=datetime('now') WHERE id=?",
                (fingerprint, blocker["id"]),
            )
            return {"status": "RESOLVED", "blocker_id": blocker["id"], "policy_fingerprint": fingerprint}

    if action == "send-prepare":
        _input(data, {"action", "account_email", "owner_token", "conversation_id", "action_key", "action_kind", "source_message_id", "invoice_id", "recipient_email", "content_sha256"},
               {"action", "account_email", "owner_token", "conversation_id", "action_key", "action_kind", "recipient_email", "content_sha256"})
        account = _email(data, "account_email")
        owner = _text(data, "owner_token", 128)
        conversation_id = _text(data, "conversation_id", 64)
        key = _text(data, "action_key", 512)
        kind = data.get("action_kind")
        source = _text(data, "source_message_id", 512) if data.get("source_message_id") is not None else None
        invoice_id = _text(data, "invoice_id", 64) if data.get("invoice_id") is not None else None
        recipient = _email(data, "recipient_email")
        content_hash = _text(data, "content_sha256", 64).lower()
        if kind not in {"OUTREACH", "REPLY", "FOLLOW_UP", "INVOICE"} or not re.fullmatch(r"[0-9a-f]{64}", content_hash):
            raise finance.DomainError("METRON_INVALID_INPUT")
        if (kind == "OUTREACH" and (source is not None or invoice_id is not None or not key.startswith("outreach:"))) or (kind == "REPLY" and (source is None or invoice_id is not None or key != f"reply:{source}")) or (kind == "FOLLOW_UP" and (source is None or invoice_id is not None or key != f"follow-up:{source}")) or (kind == "INVOICE" and (source is not None or invoice_id is None or key != f"invoice:{invoice_id}")):
            raise finance.DomainError("METRON_INVALID_INPUT")
        with store.transaction(db):
            _lock(db, account, owner)
            conversation = _conversation(db, account, conversation_id)
            if recipient != conversation["customer_email"]:
                raise finance.DomainError("METRON_EMAIL_IDENTITY_MISMATCH")
            if conversation["state"] == "OPTED_OUT" or _is_suppressed(db, account, recipient):
                raise finance.DomainError("METRON_EMAIL_OPTED_OUT")
            if kind == "INVOICE":
                _invoice_for_delivery(db, invoice_id or "", conversation, recipient)
                other_account = db.execute(
                    "SELECT account_email FROM email_send_attempts WHERE invoice_id=? AND action_kind='INVOICE'",
                    (invoice_id,),
                ).fetchone()
                if other_account is not None and other_account["account_email"] != account:
                    raise finance.DomainError("METRON_EMAIL_ACTION_CONFLICT")
            if kind == "REPLY":
                inbound = db.execute(
                    "SELECT 1 FROM email_messages WHERE account_email=? AND gmail_message_id=? AND conversation_id=? AND direction='INBOUND'",
                    (account, source, conversation_id),
                ).fetchone()
                if inbound is None:
                    raise finance.DomainError("METRON_EMAIL_MESSAGE_NOT_FOUND")
            if kind == "FOLLOW_UP":
                prior_outbound = db.execute(
                    "SELECT 1 FROM email_messages WHERE account_email=? AND gmail_message_id=? AND conversation_id=? AND direction='OUTBOUND' AND status='PROCESSED'",
                    (account, source, conversation_id),
                ).fetchone()
                if prior_outbound is None:
                    raise finance.DomainError("METRON_EMAIL_MESSAGE_NOT_FOUND")
            if kind == "REPLY" and db.execute(
                "SELECT 1 FROM email_messages WHERE account_email=? AND gmail_message_id=? AND status='PROCESSING' AND claimed_by=?",
                (account, source, owner),
            ).fetchone() is None:
                raise finance.DomainError("METRON_EMAIL_MESSAGE_LOCKED")
            existing = db.execute(
                "SELECT * FROM email_send_attempts WHERE account_email=? AND action_key=?", (account, key)
            ).fetchone()
            if existing:
                if (existing["conversation_id"], existing["action_kind"], existing["source_message_id"], existing["invoice_id"], existing["recipient_email"], existing["content_sha256"]) != (conversation_id, kind, source, invoice_id, recipient, content_hash):
                    raise finance.DomainError("METRON_EMAIL_ACTION_CONFLICT")
                if existing["status"] in {"SUBMITTING", "UNKNOWN"}:
                    raise finance.DomainError("METRON_EMAIL_SEND_UNRESOLVED")
                if existing["status"] in {"CONFIRMED", "FAILED"}:
                    return {"status": existing["status"], "attempt_id": existing["id"], "duplicate": True}
                return {"status": "PREPARED", "attempt_id": existing["id"], "duplicate": True}
            if kind == "OUTREACH" and db.execute(
                "SELECT 1 FROM email_send_attempts WHERE account_email=? AND recipient_email=? AND action_kind='OUTREACH' LIMIT 1",
                (account, recipient),
            ).fetchone():
                raise finance.DomainError("METRON_EMAIL_ACTION_CONFLICT")
            attempt_id = str(uuid.uuid4())
            db.execute(
                "INSERT INTO email_send_attempts(id,account_email,action_key,conversation_id,action_kind,invoice_id,source_message_id,recipient_email,content_sha256,status,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,'PREPARED',datetime('now'),datetime('now'))",
                (attempt_id, account, key, conversation_id, kind, invoice_id, source, recipient, content_hash),
            )
            return {"status": "PREPARED", "attempt_id": attempt_id, "duplicate": False}

    if action in {"send-start", "send-unknown", "send-fail", "send-confirm"}:
        allowed = {"action", "account_email", "owner_token", "action_key", "gmail_message_id", "gmail_thread_id", "confirmation_source", "error_code", "not_sent_confirmed"}
        required = {"action", "account_email", "owner_token", "action_key"}
        if action == "send-confirm":
            required |= {"gmail_message_id", "gmail_thread_id", "confirmation_source"}
        if action == "send-fail":
            required |= {"not_sent_confirmed"}
        _input(data, allowed, required)
        account = _email(data, "account_email")
        owner = _text(data, "owner_token", 128)
        key = _text(data, "action_key", 512)
        with store.transaction(db):
            _lock(db, account, owner)
            attempt = db.execute(
                "SELECT * FROM email_send_attempts WHERE account_email=? AND action_key=?", (account, key)
            ).fetchone()
            if attempt is None:
                raise finance.DomainError("METRON_EMAIL_ACTION_NOT_FOUND")
            if action == "send-start":
                if attempt["status"] != "PREPARED":
                    raise finance.DomainError("METRON_EMAIL_SEND_UNRESOLVED")
                conversation = _conversation(db, account, attempt["conversation_id"])
                if conversation["state"] == "OPTED_OUT" or _is_suppressed(db, account, attempt["recipient_email"]):
                    db.execute("UPDATE email_send_attempts SET status='FAILED',updated_at=datetime('now'),error_code='METRON_EMAIL_OPTED_OUT' WHERE id=?", (attempt["id"],))
                    return {"status": "FAILED", "attempt_id": attempt["id"], "error_code": "METRON_EMAIL_OPTED_OUT"}
                if attempt["action_kind"] == "INVOICE":
                    _invoice_for_delivery(db, attempt["invoice_id"], conversation, attempt["recipient_email"])
                configured_limit = db.execute(
                    "SELECT max_outbound_per_24h FROM email_account_limits WHERE account_email=?", (account,)
                ).fetchone()
                limit = configured_limit["max_outbound_per_24h"] if configured_limit else DEFAULT_OUTBOUND_PER_24H
                sent_recently = db.execute(
                    "SELECT count(*) FROM email_send_attempts WHERE account_email=? AND "
                    "((status='CONFIRMED' AND confirmed_at>=datetime('now','-24 hours')) OR "
                    "(status IN ('SUBMITTING','UNKNOWN') AND updated_at>=datetime('now','-24 hours'))) ",
                    (account,),
                ).fetchone()[0]
                if sent_recently >= limit:
                    return {"status": "PREPARED", "attempt_id": attempt["id"], "error_code": "METRON_EMAIL_SEND_LIMIT_REACHED", "max_outbound_per_24h": limit}
                db.execute("UPDATE email_send_attempts SET status='SUBMITTING',updated_at=datetime('now') WHERE id=? AND status='PREPARED'", (attempt["id"],))
                return {"status": "SUBMITTING", "attempt_id": attempt["id"]}
            if action == "send-unknown":
                if attempt["status"] == "UNKNOWN":
                    return {"status": "UNKNOWN", "attempt_id": attempt["id"]}
                if attempt["status"] != "SUBMITTING":
                    raise finance.DomainError("METRON_EMAIL_SEND_UNRESOLVED")
                db.execute("UPDATE email_send_attempts SET status='UNKNOWN',updated_at=datetime('now'),error_code='METRON_EMAIL_SEND_AMBIGUOUS' WHERE id=?", (attempt["id"],))
                return {"status": "UNKNOWN", "attempt_id": attempt["id"]}
            if action == "send-fail":
                if data["not_sent_confirmed"] is not True or attempt["status"] != "SUBMITTING":
                    raise finance.DomainError("METRON_EMAIL_SEND_UNRESOLVED")
                error = _text(data, "error_code", 128) if data.get("error_code") else "METRON_EMAIL_SEND_FAILED"
                db.execute("UPDATE email_send_attempts SET status='FAILED',updated_at=datetime('now'),error_code=? WHERE id=?", (error, attempt["id"]))
                return {"status": "FAILED", "attempt_id": attempt["id"], "error_code": error}
            message_id = _text(data, "gmail_message_id", 512)
            thread = _text(data, "gmail_thread_id", 512)
            source = data.get("confirmation_source")
            if source not in {"send_response", "gmail_readback"}:
                raise finance.DomainError("METRON_INVALID_INPUT")
            if attempt["status"] == "CONFIRMED":
                if (attempt["gmail_message_id"], attempt["gmail_thread_id"]) != (message_id, thread):
                    raise finance.DomainError("METRON_EMAIL_ACTION_CONFLICT")
                return {"status": "CONFIRMED", "attempt_id": attempt["id"], "duplicate": True}
            if source == "send_response" and attempt["status"] != "SUBMITTING":
                raise finance.DomainError("METRON_EMAIL_SEND_UNRESOLVED")
            if source == "gmail_readback" and attempt["status"] not in {"SUBMITTING", "UNKNOWN"}:
                raise finance.DomainError("METRON_EMAIL_SEND_UNRESOLVED")
            conversation = _conversation(db, account, attempt["conversation_id"])
            if conversation["gmail_thread_id"] and conversation["gmail_thread_id"] != thread:
                raise finance.DomainError("METRON_EMAIL_IDENTITY_MISMATCH")
            db.execute(
                "UPDATE email_send_attempts SET status='CONFIRMED',gmail_message_id=?,gmail_thread_id=?,updated_at=datetime('now'),confirmed_at=datetime('now'),error_code=NULL WHERE id=?",
                (message_id, thread, attempt["id"]),
            )
            db.execute(
                "UPDATE email_conversations SET gmail_thread_id=?,last_confirmed_action=?,updated_at=datetime('now') WHERE id=?",
                (thread, attempt["action_kind"], conversation["id"]),
            )
            db.execute(
                "INSERT INTO email_messages(account_email,gmail_message_id,gmail_thread_id,conversation_id,direction,status,received_at,processed_at) "
                "VALUES (?,?,?,?,'OUTBOUND','PROCESSED',datetime('now'),datetime('now'))",
                (account, message_id, thread, conversation["id"]),
            )
            return {"status": "CONFIRMED", "attempt_id": attempt["id"], "gmail_message_id": message_id, "gmail_thread_id": thread, "duplicate": False}

    if action == "state-list":
        _input(data, {"action", "account_email"}, {"action", "account_email"})
        account = _email(data, "account_email")
        conversations = [dict(row) for row in db.execute(
            "SELECT id,conversation_key,gmail_thread_id,customer_email,state,deal_id,context_json,last_confirmed_action,next_follow_up_at,updated_at FROM email_conversations WHERE account_email=? ORDER BY updated_at DESC",
            (account,),
        ).fetchall()]
        messages = [dict(row) for row in db.execute(
            "SELECT gmail_message_id,gmail_thread_id,conversation_id,direction,status,received_at,processed_at,error_code FROM email_messages WHERE account_email=? ORDER BY received_at DESC LIMIT 200",
            (account,),
        ).fetchall()]
        message_events = [
            {**dict(row), "details": json.loads(row["details_json"])}
            for row in db.execute(
                "SELECT id,gmail_message_id,conversation_id,event_type,reason_code,details_json,status,policy_fingerprint,reported_at,created_at,updated_at "
                "FROM email_message_events WHERE account_email=? ORDER BY created_at DESC LIMIT 200",
                (account,),
            ).fetchall()
        ]
        for event in message_events:
            event.pop("details_json")
        attempts = [dict(row) for row in db.execute(
            "SELECT id,action_key,conversation_id,action_kind,invoice_id,source_message_id,recipient_email,status,gmail_message_id,gmail_thread_id,error_code,updated_at FROM email_send_attempts WHERE account_email=? ORDER BY updated_at DESC LIMIT 200",
            (account,),
        ).fetchall()]
        suppressed = [dict(row) for row in db.execute(
            "SELECT recipient_email,source_thread_id,opted_out_at FROM email_contact_suppressions WHERE account_email=? ORDER BY opted_out_at DESC",
            (account,),
        ).fetchall()]
        configured_limit = db.execute(
            "SELECT max_outbound_per_24h FROM email_account_limits WHERE account_email=?", (account,)
        ).fetchone()
        return {
            "conversations": conversations,
            "messages": messages,
            "message_events": message_events,
            "send_attempts": attempts,
            "suppressed_contacts": suppressed,
            "max_outbound_per_24h": configured_limit["max_outbound_per_24h"] if configured_limit else DEFAULT_OUTBOUND_PER_24H,
            "send_limit_configured": configured_limit is not None,
        }

    raise finance.DomainError("METRON_INVALID_INPUT")
