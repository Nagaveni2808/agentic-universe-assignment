"""Reads the workflow schema JSON files and the disposition catalogue."""
import csv
import json
from dataclasses import dataclass
from pathlib import Path

from .cleaning import normalise_header

# solution/ledger/schemas.py -> parents[2] is the repo root
DEFAULT_SCHEMAS_DIR = Path(__file__).resolve().parents[2] / "assignment-a-data" / "schemas"


@dataclass
class Schema:
    workflow_id: str
    fields: list
    header_map: dict      # normalised header text -> field name
    phone_field: str
    reference_field: str
    pii_fields: set
    defaults: dict


def load_schemas(schemas_dir=DEFAULT_SCHEMAS_DIR) -> dict:
    result = {}
    for path in sorted(Path(schemas_dir).glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        header_map = {}
        for f in raw["fields"]:
            for alias in [f["name"], *f.get("aliases", [])]:
                header_map.setdefault(normalise_header(alias), f["name"])
        result[raw["workflow_id"]] = Schema(
            workflow_id=raw["workflow_id"],
            fields=raw["fields"],
            header_map=header_map,
            phone_field=next(f["name"] for f in raw["fields"] if f["type"] == "phone"),
            reference_field=next(f["name"] for f in raw["fields"] if f.get("reference")),
            pii_fields={f["name"] for f in raw["fields"] if f.get("pii")},
            defaults={f["name"]: f["default"] for f in raw["fields"] if "default" in f},
        )
    return result


def load_dispositions(schemas_dir=DEFAULT_SCHEMAS_DIR) -> dict:
    """Returns {(workflow_id, code): {'is_terminal': bool, 'is_success': bool}}."""
    result = {}
    with open(Path(schemas_dir) / "dispositions.csv", newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            result[(row["workflow_id"], row["code"])] = {
                "is_terminal": row["is_terminal"].strip().lower() == "true",
                "is_success": row["is_success"].strip().lower() == "true",
            }
    return result