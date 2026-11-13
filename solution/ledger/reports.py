"""Builds the five report files. Everything is calculated here, from the database."""
import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from .cleaning import IST

EPOCH = datetime(1970, 1, 1, tzinfo=IST)


def _key(e):
    """Sort events by time, with event_id as a tie-breaker."""
    return (e["ts"] or EPOCH, e["event_id"])


def _write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def _effective(call):
    """Latest override wins; otherwise the latest disposition.set; otherwise None."""
    pool = call["overrides"] or call["sets"]
    return max(pool, key=_key) if pool else None


def build_reports(conn, out_dir, schemas, dispositions):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    leads = {(r["workflow_id"], r["phone_hash"]): dict(r)
             for r in conn.execute("SELECT * FROM leads")}

    events = [dict(r) for r in conn.execute("SELECT * FROM events")]
    for e in events:
        e["ts"] = datetime.fromisoformat(e["occurred_at"]) if e["occurred_at"] else None
        e["lead"] = None

    # --- Link events to leads (workflow + phone hash) ---
    for e in events:
        if e["event_type"] == "disposition.override":
            continue
        key = (e["workflow_id"], e["phone_hash"])
        if e["phone_hash"] and key in leads:
            e["lead"] = key

    # --- Which lead does each call belong to? ---
    call_lead = {}
    for e in sorted((x for x in events if x["lead"] and x["call_id"]), key=_key):
        call_lead.setdefault(e["call_id"], e["lead"])

    # --- Overrides have no phone: link through call_id ---
    for e in events:
        if e["event_type"] == "disposition.override" and e["call_id"]:
            e["lead"] = call_lead.get(e["call_id"])

    # --- Orphans and unknown dispositions ---
    orphans = unknown = 0
    valid = []
    for e in events:
        if e["lead"] is None:
            orphans += 1
            continue
        if e["event_type"].startswith("disposition."):
            code = json.loads(e["payload_json"]).get("disposition_code")
            info = dispositions.get((e["lead"][0], code))
            if info is None:
                unknown += 1
                continue
            e["code"], e["info"] = code, info
        valid.append(e)

    # --- Group into calls ---
    calls = {}
    for e in valid:
        cid = e["call_id"]
        if not cid:
            continue
        c = calls.setdefault(cid, {"init": None, "connected": False, "failed": False,
                                   "sets": [], "overrides": []})
        t = e["event_type"]
        if t == "call.initiated":
            if c["init"] is None or _key(e) < _key(c["init"]):
                c["init"] = e
        elif t == "call.connected":
            c["connected"] = True
        elif t == "call.telephony_failed":
            c["failed"] = True
        elif t == "disposition.set":
            c["sets"].append(e)
        elif t == "disposition.override":
            c["overrides"].append(e)

    by_lead = defaultdict(list)
    for cid, c in calls.items():
        if c["init"] is None or c["init"]["ts"] is None:
            continue  # a call only counts if its call.initiated is present
        c["id"] = cid
        c["init_ts"] = c["init"]["ts"]
        c["eff"] = _effective(c)
        by_lead[call_lead[cid]].append(c)

    # --- lead_report.csv + batch_summary.csv ---
    lead_rows, batch = [], defaultdict(lambda: defaultdict(int))
    for key, lead in leads.items():
        cs = sorted(by_lead.get(key, []), key=lambda c: (c["init_ts"], c["id"]))
        if not cs:
            bucket = "yet_to_reach_out"
        elif any(c["eff"] and c["eff"]["info"]["is_terminal"] for c in cs):
            bucket = "completed"
        elif all(c["failed"] for c in cs):
            bucket = "in_progress_telephony_failed"
        else:
            bucket = "in_progress_dialed"

        with_disp = [c for c in cs if c["eff"]]
        lead_rows.append((
            key[0], lead["external_ref"], lead["batch_id"],
            "+91******" + lead["phone_last4"], bucket,
            len(cs), sum(c["connected"] for c in cs),
            cs[-1]["init_ts"].astimezone(IST).isoformat(timespec="seconds") if cs else "",
            with_disp[-1]["eff"]["code"] if with_disp else "",
            str(any(c["eff"] and c["eff"]["info"]["is_success"] for c in cs)).lower(),
        ))
        b = batch[(key[0], lead["batch_id"])]
        b["total_leads"] += 1
        b[bucket] += 1

    lead_rows.sort(key=lambda r: (r[0], r[1]))
    _write_csv(out / "lead_report.csv",
               ["workflow_id", "external_ref", "batch_id", "phone_masked", "bucket",
                "total_calls", "connected_calls", "last_call_at", "current_disposition",
                "ever_success"], lead_rows)

    _write_csv(out / "batch_summary.csv",
               ["workflow_id", "batch_id", "total_leads", "yet_to_reach_out",
                "in_progress_telephony_failed", "in_progress_dialed", "completed"],
               [(w, b_id, v["total_leads"], v["yet_to_reach_out"],
                 v["in_progress_telephony_failed"], v["in_progress_dialed"], v["completed"])
                for (w, b_id), v in sorted(batch.items())])

    # --- daily_overview.csv ---
    daily = defaultdict(lambda: {"total": 0, "connected": 0, "success": set()})
    for key, cs in by_lead.items():
        for c in cs:
            d = daily[(key[0], c["init_ts"].astimezone(IST).date().isoformat())]
            d["total"] += 1
            d["connected"] += int(c["connected"])
            if c["eff"] and c["eff"]["info"]["is_success"]:
                d["success"].add(key)
    _write_csv(out / "daily_overview.csv",
               ["workflow_id", "date", "total_calls", "connected_calls",
                "connectivity_rate", "success_leads"],
               [(w, d, v["total"], v["connected"], f"{v['connected'] / v['total']:.4f}",
                 len(v["success"])) for (w, d), v in sorted(daily.items())])

    # --- rejections.csv ---
    _write_csv(out / "rejections.csv", ["workflow_id", "batch_id", "row_number", "reason"],
               [tuple(r) for r in conn.execute(
                   "SELECT workflow_id, batch_id, row_number, reason FROM lead_rejections "
                   "ORDER BY workflow_id, batch_id, row_number")])

    # --- data_quality.json ---
    lead_sum = conn.execute(
        "SELECT COALESCE(SUM(rows_total),0) t, COALESCE(SUM(rows_rejected),0) r, "
        "COALESCE(SUM(rows_merged),0) m, COALESCE(SUM(field_warnings),0) w "
        "FROM ingested_files WHERE kind='leads'").fetchone()
    ev_sum = conn.execute(
        "SELECT COALESCE(SUM(events_total),0) t, COALESCE(SUM(events_malformed),0) m, "
        "COALESCE(SUM(events_duplicate),0) d FROM ingested_files WHERE kind='events'").fetchone()

    reasons = {"invalid_phone": 0}
    for s in schemas.values():
        for f in s.fields:
            if f.get("required"):
                reasons.setdefault(f"missing_required:{f['name']}", 0)
    for r in conn.execute("SELECT reason, COUNT(*) n FROM lead_rejections GROUP BY reason"):
        reasons[r["reason"]] = r["n"]

    quality = {
        "lead_rows_total": lead_sum["t"],
        "lead_rows_rejected": lead_sum["r"],
        "rejections_by_reason": dict(sorted(reasons.items())),
        "duplicate_lead_rows_merged": lead_sum["m"],
        "field_warnings": lead_sum["w"],
        "events_total": ev_sum["t"],
        "malformed_events": ev_sum["m"],
        "duplicate_events_dropped": ev_sum["d"],
        "orphan_events": orphans,
        "unknown_disposition_events": unknown,
    }
    (out / "data_quality.json").write_text(json.dumps(quality, indent=2) + "\n", encoding="utf-8")