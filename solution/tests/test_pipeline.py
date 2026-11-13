import csv
import json

from ledger.db import connect
from ledger.events import ingest_event_file
from ledger.leads import ingest_lead_file
from ledger.reports import build_reports
from ledger.schemas import DEFAULT_SCHEMAS_DIR, load_dispositions, load_schemas


def ev(i, typ, **kw):
    d = {"event_id": f"e{i}", "event_type": typ, "workflow_id": "motor_renewal",
         "call_id": "call_1", "occurred_at": "2026-10-05T13:20:21Z",
         "phone": "98765-43210", "payload": {}}
    d.update(kw)
    return d


def test_end_to_end(tmp_path):
    schemas = load_schemas(DEFAULT_SCHEMAS_DIR)
    disp = load_dispositions(DEFAULT_SCHEMAS_DIR)
    conn = connect(tmp_path / "t.db")

    # Events arrive FIRST (an earlier drop), the lead arrives later.
    lines = [
        json.dumps(ev(1, "call.initiated")),
        json.dumps(ev(2, "call.connected", occurred_at="2026-10-05T13:21:00Z")),
        json.dumps(ev(3, "disposition.set", occurred_at="2026-10-05T13:25:00Z",
                      payload={"disposition_code": "payment_link_sent"})),
        json.dumps(ev(4, "disposition.override", phone=None, occurred_at="2026-10-05T13:30:00Z",
                      payload={"disposition_code": "renewed"})),
        json.dumps(ev(1, "call.initiated")),                         # duplicate
        "this is not json",                                          # malformed
        json.dumps(ev(7, "call.initiated", call_id="call_9", phone="9000000001")),  # orphan
        json.dumps(ev(8, "disposition.set", payload={"disposition_code": "banana"})),  # unknown
    ]
    efile = tmp_path / "events_0001.jsonl"
    efile.write_text("\n".join(lines) + "\n", encoding="utf-8")
    lfile = tmp_path / "batch_001.csv"
    lfile.write_text("customer_name,phone,policy_number\nAsha,9876543210,P1\n", encoding="utf-8")

    assert ingest_event_file(conn, efile, "d1/events/events_0001.jsonl") is True
    assert ingest_lead_file(conn, schemas["motor_renewal"], lfile, "d2/leads/motor_renewal/batch_001.csv")
    assert ingest_event_file(conn, efile, "d1/events/events_0001.jsonl") is False  # re-run: nothing

    out = tmp_path / "reports"
    build_reports(conn, out, schemas, disp)

    lead = list(csv.DictReader(open(out / "lead_report.csv", encoding="utf-8")))
    assert len(lead) == 1
    row = lead[0]
    assert row["bucket"] == "completed"
    assert row["total_calls"] == "1" and row["connected_calls"] == "1"
    assert row["last_call_at"] == "2026-10-05T18:50:21+05:30"
    assert row["current_disposition"] == "renewed"      # the override beat the original
    assert row["ever_success"] == "true"
    assert row["phone_masked"] == "+91******3210"

    daily = list(csv.DictReader(open(out / "daily_overview.csv", encoding="utf-8")))
    assert daily == [{"workflow_id": "motor_renewal", "date": "2026-10-05", "total_calls": "1",
                      "connected_calls": "1", "connectivity_rate": "1.0000", "success_leads": "1"}]

    q = json.loads((out / "data_quality.json").read_text(encoding="utf-8"))
    assert q["events_total"] == 8
    assert q["malformed_events"] == 1
    assert q["duplicate_events_dropped"] == 1
    assert q["orphan_events"] == 1
    assert q["unknown_disposition_events"] == 1