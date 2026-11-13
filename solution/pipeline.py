"""Command line entry point.  Usage:
    python solution/pipeline.py ingest data/drop_1
    python solution/pipeline.py report --out reports
"""
import argparse
import sys
from pathlib import Path

from ledger.db import connect
from ledger.events import ingest_event_file
from ledger.leads import ingest_lead_file
from ledger.reports import build_reports
from ledger.schemas import DEFAULT_SCHEMAS_DIR, load_dispositions, load_schemas


def cmd_ingest(args):
    drop = Path(args.drop)
    if not drop.is_dir():
        sys.exit(f"Not a folder: {drop}")
    schemas = load_schemas(args.schemas)
    conn = connect(args.db)

    for path in sorted(drop.glob("leads/*/*.csv")):
        workflow = path.parent.name
        if workflow not in schemas:
            print(f"skip (unknown workflow): {path}")
            continue
        key = f"{drop.name}/leads/{workflow}/{path.name}"
        done = ingest_lead_file(conn, schemas[workflow], path, key)
        print(("ingested " if done else "already done ") + key)

    for path in sorted(drop.glob("events/*.jsonl")):
        key = f"{drop.name}/events/{path.name}"
        done = ingest_event_file(conn, path, key)
        print(("ingested " if done else "already done ") + key)


def cmd_report(args):
    conn = connect(args.db)
    build_reports(conn, args.out, load_schemas(args.schemas), load_dispositions(args.schemas))
    print(f"reports written to {args.out}")


def main():
    parser = argparse.ArgumentParser(prog="pipeline")
    parser.add_argument("--db", default="ledger.db")
    parser.add_argument("--schemas", default=str(DEFAULT_SCHEMAS_DIR))
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("ingest")
    p.add_argument("drop")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("report")
    p.add_argument("--out", default="reports")
    p.set_defaults(func=cmd_report)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()