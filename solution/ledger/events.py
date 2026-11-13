"""Reads one events file (JSON Lines) into the append-only ledger."""
import hashlib
import json
from pathlib import Path

from .cleaning import normalise_phone, parse_timestamp
from .security import phone_token


def ingest_event_file(conn, path, file_key) -> bool:
    """Returns True if ingested, False if this file was already done."""
    path = Path(path)
    if conn.execute("SELECT 1 FROM ingested_files WHERE file_key=?", (file_key,)).fetchone():
        return False

    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    total = malformed = duplicates = 0

    with conn:  # all-or-nothing for the whole file
        with open(path, encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                total += 1

                # Rule 1: malformed = not valid JSON, or no event_id
                try:
                    ev = json.loads(line)
                except ValueError:
                    malformed += 1
                    continue
                eid = ev.get("event_id") if isinstance(ev, dict) else None
                if isinstance(eid, bool) or not isinstance(eid, (str, int)) or str(eid).strip() == "":
                    malformed += 1
                    continue

                raw_phone = ev.get("phone")
                phone = normalise_phone(str(raw_phone)) if raw_phone else None
                ts = parse_timestamp(ev.get("occurred_at"))
                payload = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}

                # Rule 2: duplicate event_id (same file or earlier drop) -> counted, skipped
                cur = conn.execute(
                    "INSERT OR IGNORE INTO events VALUES (?,?,?,?,?,?,?,?)",
                    (str(eid).strip(), str(ev.get("event_type") or ""),
                     ev.get("workflow_id"), ev.get("call_id"),
                     ts.isoformat() if ts else None,
                     phone_token(phone) if phone else None,
                     json.dumps(payload, sort_keys=True), file_key))
                if cur.rowcount == 0:
                    duplicates += 1

        conn.execute(
            "INSERT INTO ingested_files (file_key, kind, sha256, events_total, "
            "events_malformed, events_duplicate) VALUES (?,?,?,?,?,?)",
            (file_key, "events", digest, total, malformed, duplicates))
    return True