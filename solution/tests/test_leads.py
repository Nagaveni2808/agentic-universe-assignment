from ledger.db import connect
from ledger.leads import ingest_lead_file
from ledger.schemas import DEFAULT_SCHEMAS_DIR, load_schemas

CSV = """Name,Mobile No,Policy_No,Expiry,Premium,Language
Asha,98765 43210,P1,01/12/2026,"₹1,200",HI
,98765 43211,P2,,,
Ravi,12345,P3,,,
Asha K,+91 98765 43210,P1B,,,
"""


def test_lead_ingest(tmp_path):
    schema = load_schemas(DEFAULT_SCHEMAS_DIR)["motor_renewal"]
    f = tmp_path / "batch_001.csv"
    f.write_text(CSV, encoding="utf-8")
    conn = connect(tmp_path / "t.db")

    assert ingest_lead_file(conn, schema, f, "d1/batch_001") is True

    leads = [tuple(r) for r in conn.execute(
        "SELECT batch_id, external_ref, phone_last4 FROM leads")]
    assert leads == [("batch_001", "P1B", "3210")]  # merged, last write wins

    rej = [tuple(r) for r in conn.execute(
        "SELECT row_number, reason FROM lead_rejections ORDER BY row_number")]
    assert rej == [(2, "missing_required:customer_name"), (3, "invalid_phone")]

    blob = conn.execute("SELECT data_json FROM leads").fetchone()[0]
    assert "Asha" not in blob                       # no plain-text names

    assert ingest_lead_file(conn, schema, f, "d1/batch_001") is False  # re-run: nothing
    assert conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0] == 1