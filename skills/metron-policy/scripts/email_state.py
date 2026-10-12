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
                if row["state"] == "OPTED_OUT" and state != "OPTED_OUT":
                    raise finance.DomainError("METRON_EMAIL_OPTED_OUT")
                db.execute(
                    "UPDATE email_conversations SET gmail_thread_id=?,state=?,deal_id=?,context_json=CASE WHEN ? THEN ? ELSE context_json END,next_follow_up_at=CASE WHEN ? THEN ? ELSE next_follow_up_at END,updated_at=datetime('now') WHERE id=?",
                    (next_thread, state, deal_id, has_context, context, has_next_follow_up, next_follow_up, row["id"]),
                )
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
            if row["state"] == "OPTED_OUT" and state != "OPTED_OUT":
                raise finance.DomainError("METRON_EMAIL_OPTED_OUT")
            deal_id = data.get("deal_id", row["deal_id"])
            if deal_id is not None and not db.execute("SELECT 1 FROM deals WHERE id=?", (deal_id,)).fetchone():
                raise finance.DomainError("METRON_DEAL_NOT_FOUND")
            db.execute(
                "UPDATE email_conversations SET state=COALESCE(?,state),deal_id=?,context_json=COALESCE(?,context_json),next_follow_up_at=CASE WHEN ? THEN ? ELSE next_follow_up_at END,updated_at=datetime('now') WHERE id=?",
                (state, deal_id, context, has_next_follow_up, next_follow_up, conversation_id),
            )
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
                if row["status"] == "PROCESSED":
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
        allowed = {"action", "account_email", "owner_token", "gmail_message_id", "error_code"}
        required = {"action", "account_email", "owner_token", "gmail_message_id"}
        _input(data, allowed, required)
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
                db.execute("UPDATE email_messages SET status='PROCESSED',processed_at=datetime('now'),lease_until=NULL WHERE id=?", (row["id"],))
                return {"status": "PROCESSED"}
            error = _text(data, "error_code", 128) if data.get("error_code") else "METRON_EMAIL_PROCESSING_FAILED"
            db.execute("UPDATE email_messages SET status='FAILED',error_code=?,lease_until=NULL WHERE id=?", (error, row["id"]))
            return {"status": "FAILED", "error_code": error}

    if action == "send-prepare":
        _input(data, {"action", "account_email", "owner_token", "conversation_id", "action_key", "action_kind", "source_message_id", "recipient_email", "content_sha256"},
               {"action", "account_email", "owner_token", "conversation_id", "action_key", "action_kind", "recipient_email", "content_sha256"})
        account = _email(data, "account_email")
        owner = _text(data, "owner_token", 128)
        conversation_id = _text(data, "conversation_id", 64)
        key = _text(data, "action_key", 512)
        kind = data.get("action_kind")
        source = _text(data, "source_message_id", 512) if data.get("source_message_id") is not None else None
        recipient = _email(data, "recipient_email")
        content_hash = _text(data, "content_sha256", 64).lower()
        if kind not in {"OUTREACH", "REPLY", "FOLLOW_UP"} or not re.fullmatch(r"[0-9a-f]{64}", content_hash):
            raise finance.DomainError("METRON_INVALID_INPUT")
        if (kind == "OUTREACH" and (source is not None or not key.startswith("outreach:"))) or (kind == "REPLY" and (source is None or key != f"reply:{source}")) or (kind == "FOLLOW_UP" and (source is None or key != f"follow-up:{source}")):
            raise finance.DomainError("METRON_INVALID_INPUT")
        with store.transaction(db):
            _lock(db, account, owner)
            conversation = _conversation(db, account, conversation_id)
            if conversation["state"] == "OPTED_OUT":
                raise finance.DomainError("METRON_EMAIL_OPTED_OUT")
            if recipient != conversation["customer_email"]:
                raise finance.DomainError("METRON_EMAIL_IDENTITY_MISMATCH")
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
                if (existing["conversation_id"], existing["action_kind"], existing["source_message_id"], existing["recipient_email"], existing["content_sha256"]) != (conversation_id, kind, source, recipient, content_hash):
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
                "INSERT INTO email_send_attempts(id,account_email,action_key,conversation_id,action_kind,source_message_id,recipient_email,content_sha256,status,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,'PREPARED',datetime('now'),datetime('now'))",
                (attempt_id, account, key, conversation_id, kind, source, recipient, content_hash),
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
                if conversation["state"] == "OPTED_OUT":
                    db.execute("UPDATE email_send_attempts SET status='FAILED',updated_at=datetime('now'),error_code='METRON_EMAIL_OPTED_OUT' WHERE id=?", (attempt["id"],))
                    return {"status": "FAILED", "attempt_id": attempt["id"], "error_code": "METRON_EMAIL_OPTED_OUT"}
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
        attempts = [dict(row) for row in db.execute(
            "SELECT id,action_key,conversation_id,action_kind,source_message_id,recipient_email,status,gmail_message_id,gmail_thread_id,error_code,updated_at FROM email_send_attempts WHERE account_email=? ORDER BY updated_at DESC LIMIT 200",
            (account,),
        ).fetchall()]
        return {"conversations": conversations, "messages": messages, "send_attempts": attempts}

    raise finance.DomainError("METRON_INVALID_INPUT")
