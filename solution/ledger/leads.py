"""Reads one lead CSV file: validate, clean, reject bad rows, merge duplicates."""
import csv
import hashlib
import json
from pathlib import Path

from .cleaning import (normalise_header, normalise_phone, parse_date,
                       parse_decimal, parse_enum)
from .security import phone_token, pii_token


def _parse_value(field, raw):
    kind = field["type"]
    if kind == "string":
        return raw
    if kind == "phone":
        return normalise_phone(raw)
    if kind == "date":
        d = parse_date(raw)
        return d.isoformat() if d is not None else None
    if kind == "decimal":
        d = parse_decimal(raw)
        return str(d) if d is not None else None
    if kind == "enum":
        return parse_enum(raw, field["values"])
    raise ValueError(f"unknown field type: {kind}")


def validate_row(schema, raw):
    """Walk fields in schema order. Returns (values, warnings, reject_reason)."""
    values, warnings = {}, 0
    for field in schema.fields:
        name = field["name"]
        text = raw.get(name, "")
        if text == "":
            if field.get("required"):
                return None, 0, f"missing_required:{name}"
            values[name] = None
            continue
        value = _parse_value(field, text)
        if value is None:
            if field["type"] == "phone":
                return None, 0, "invalid_phone"
            if field.get("required"):  # my call: required but unreadable = missing
                return None, 0, f"missing_required:{name}"
            warnings += 1
        values[name] = value
    return values, warnings, None


def ingest_lead_file(conn, schema, path, file_key) -> bool:
    """Returns True if ingested, False if this file was already done."""
    path = Path(path)
    if conn.execute("SELECT 1 FROM ingested_files WHERE file_key=?", (file_key,)).fetchone():
        return False

    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    batch_id = path.stem
    total = rejected = merged = warnings_total = 0

    with conn:  # everything below is saved together, or not at all
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            header = next(reader, [])
            col = {}
            for i, h in enumerate(header):
                name = schema.header_map.get(normalise_header(h))
                if name and name not in col:
                    col[name] = i

            row_number = 0
            for row in reader:
                if not any(c.strip() for c in row):
                    continue  # blank row: skipped, not counted
                row_number += 1
                total += 1
                raw = {n: (row[i].strip() if i < len(row) else "") for n, i in col.items()}
                values, warns, reason = validate_row(schema, raw)

                if reason:
                    rejected += 1
                    conn.execute(
                        "INSERT OR IGNORE INTO lead_rejections VALUES (?,?,?,?)",
                        (schema.workflow_id, batch_id, row_number, reason))
                    continue

                warnings_total += warns
                phone = values.pop(schema.phone_field)
                ph = phone_token(phone)
                new = {k: (pii_token(v) if k in schema.pii_fields and v is not None else v)
                       for k, v in values.items()}

                existing = conn.execute(
                    "SELECT data_json FROM leads WHERE workflow_id=? AND phone_hash=?",
                    (schema.workflow_id, ph)).fetchone()
                if existing is None:
                    data = new
                else:
                    merged += 1
                    data = json.loads(existing["data_json"])
                    for k, v in new.items():
                        if v is not None:      # last write wins, only non-empty values
                            data[k] = v
                for k, default in schema.defaults.items():
                    if data.get(k) is None:    # defaults come after merging
                        data[k] = default

                ref = data[schema.reference_field]
                if existing is None:
                    conn.execute("INSERT INTO leads VALUES (?,?,?,?,?,?)",
                                 (schema.workflow_id, ph, phone[-4:], batch_id, ref,
                                  json.dumps(data, sort_keys=True)))
                else:
                    conn.execute(
                        "UPDATE leads SET external_ref=?, data_json=? "
                        "WHERE workflow_id=? AND phone_hash=?",
                        (ref, json.dumps(data, sort_keys=True), schema.workflow_id, ph))

        conn.execute(
            "INSERT INTO ingested_files (file_key, kind, sha256, rows_total, rows_rejected, "
            "rows_merged, field_warnings) VALUES (?,?,?,?,?,?,?)",
            (file_key, "leads", digest, total, rejected, merged, warnings_total))
    return True