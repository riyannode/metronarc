# Durable email state

Email state lives in the existing `email_*` tables in `~/.metron/metron.sqlite`; it is not a second ledger. `email-state` first opens that file read-only and checks SQLite integrity plus core METRON tables. It returns `METRON_NOT_INITIALIZED` or `METRON_STATE_SCHEMA_INVALID` instead of creating a replacement database. A valid existing database receives additive `CREATE TABLE IF NOT EXISTS` email tables through METRON's normal initializer.

Call the installed `skills/metron-policy/scripts/run.py email-state --input <private-json-file>` operation. Keep JSON input in a private temporary file and remove it after use. Each invocation accepts one JSON object. The available actions are:

| Action | Purpose |
|---|---|
| `run-acquire` / `run-renew` / `run-release` | Serialize scheduled work per normalized email account. The default lease is 300 seconds; renew before slow connector calls. `BUSY` means another run owns the lock. |
| `state-list` | Load saved conversations, inbound/outbound message IDs, follow-up times, and send attempts before searching or acting. |
| `conversation-upsert` / `conversation-update` | Persist a verified customer, thread, communication state, METRON deal ID, concise facts/terms, and optional ISO-8601 UTC `next_follow_up_at`. Setting `next_follow_up_at` to JSON `null` clears it. |
| `message-claim` | Atomically associate an inbound Gmail message with its thread and customer, then claim it for this run. `DUPLICATE`, `ALREADY_CLAIMED`, or `BLOCKED_UNRESOLVED_SEND` means do not process or send it again. |
| `message-complete` / `message-fail` | Finish a claimed inbound message. Completion is rejected while a send is only prepared, submitting, or ambiguous. |
| `send-prepare` / `send-start` | Reserve a unique outreach/reply/follow-up action using a stable action key and SHA-256 of the exact outgoing body. Call `send-start` once immediately before the connector send. Only its `SUBMITTING` result permits one send call. |
| `send-confirm` / `send-unknown` / `send-fail` | Persist confirmed Gmail message/thread IDs, preserve an ambiguous send, or mark a provider-confirmed no-send failure. `send-fail` requires `not_sent_confirmed: true`. |

Use action keys consistently: `outreach:<conversation-id>` for initial outreach, `reply:<inbound-message-id>` for a reply, and `follow-up:<prior-outbound-message-id>` for a planned follow-up. A reply must reference an inbound message in the same thread; a follow-up must reference the preceding confirmed outbound message in that conversation. An account/customer can have only one initial outreach, an inbound message can have only one reply, and an outbound message can have only one follow-up. The database's unique constraints and `BEGIN IMMEDIATE` transactions enforce these rules across concurrent scheduler runs.

The sequence for any outbound message is `send-prepare` → `send-start` → exactly one native connector send → `send-confirm`. `send-start` rechecks the persisted opt-out state; a `FAILED` result with `METRON_EMAIL_OPTED_OUT` is a local cancellation and must not call Gmail. If the send result is ambiguous, use `send-unknown`, then read the existing Gmail thread. Confirm with `confirmation_source: "gmail_readback"` only when the exact sent message is present. If it is absent or cannot be checked, preserve `UNKNOWN` and stop; never retry. The per-account run lock fences active schedulers. A claim left by an earlier run can be reassigned under the new lock only when no ambiguous send is linked to that message. `SUBMITTING` and `UNKNOWN` are never sendable states.

Store message IDs, thread IDs, customer address, state, deal reference, last confirmed action, and brief verified context only. Do not store message bodies, credentials, or tokens. `context` is a JSON object replaced as a whole; read the existing state first when updating it.
