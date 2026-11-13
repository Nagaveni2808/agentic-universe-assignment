"""Generates data with a seed we did not develop on, ingests it twice,
and checks that the five reports are identical both times."""
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

import pytest

from ledger.schemas import DEFAULT_SCHEMAS_DIR
from pipeline import cmd_ingest, cmd_report

REPO = Path(__file__).resolve().parents[2]
GEN = REPO / "assignment-a-data" / "tools" / "generate_data.py"
FILES = ["batch_summary.csv", "daily_overview.csv", "lead_report.csv",
         "rejections.csv", "data_quality.json"]


@pytest.mark.skipif(not GEN.exists(), reason="generator not found")
def test_rerun_changes_nothing(tmp_path):
    data = tmp_path / "data"
    subprocess.run([sys.executable, str(GEN), "--seed", "7", "--scale", "small",
                    "--out", str(data)], check=True, capture_output=True)
    db, schemas = str(tmp_path / "t.db"), str(DEFAULT_SCHEMAS_DIR)

    def ingest(drop):
        cmd_ingest(Namespace(drop=str(data / drop), db=db, schemas=schemas))

    def report(name):
        out = tmp_path / name
        cmd_report(Namespace(db=db, out=str(out), schemas=schemas))
        return {n: (out / n).read_bytes() for n in FILES}

    ingest("drop_1")
    ingest("drop_2")
    first = report("r1")

    ingest("drop_1")   # same files again: must change nothing
    ingest("drop_2")
    second = report("r2")

    assert first == second