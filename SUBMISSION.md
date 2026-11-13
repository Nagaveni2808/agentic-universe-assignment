# Submission

## Candidate
- **Name:** Nagaveni
- **Assignment chosen:** A (Data): Interaction Ledger & Reporting Pipeline
- **Time spent (honest estimate):** [YOU: e.g. 9h]

## How to run
```bash
python -m venv .venv
.venv\Scripts\activate            # Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
python assignment-a-data/tools/generate_data.py --seed 42 --scale small --out data

python solution/pipeline.py ingest data/drop_1
python solution/pipeline.py ingest data/drop_2
python solution/pipeline.py report --out reports

pytest
```
Optional: set `LEDGER_SECRET` (the key used for hashing) before running. Database file: `ledger.db` (SQLite, ignored by git).

## Design
**Idea:** the database stores raw facts. All numbers are calculated when `report` runs. Late-arriving leads and orphan events therefore fix themselves, and the order or grouping of ingest runs cannot change the result.

**Tables (SQLite):**
- `ingested_files`: one row per file already processed, with per-file counters (rows, rejected, merged, warnings, events, malformed, duplicates). A file already listed is skipped, so re-runs change nothing. Each file is saved in one transaction, so a crash leaves nothing half-done.
- `leads`: primary key `(workflow_id, phone_hash)`. Holds `batch_id` (from the first valid row, never changed), `external_ref`, last 4 digits, and the cleaned fields as JSON.
- `lead_rejections`: `(workflow_id, batch_id, row_number, reason)`, with no PII.
- `events`: the append-only ledger. `event_id` is the primary key, and database triggers block UPDATE and DELETE.

**PII:** phone numbers and PII fields (names) are never stored in plain text. They are stored as HMAC-SHA256 tokens, using a secret key with separate sub-keys for phone and other PII. The same phone always gives the same token, so events match leads by token. Only the last 4 digits of the phone are kept (needed for the masked column).

**Report time:** link events to leads by `(workflow_id, phone_token)`, link overrides through their `call_id`, then count orphans, drop unknown dispositions, group events into calls, work out each call's effective disposition, and compute buckets and the five files.

## Decisions & assumptions
| Decision | Why | Alternative considered |
|---|---|---|
| Orphans and unknown dispositions are counted at report time, not ingest time | An event whose lead arrives in a later drop must count; counts reflect the final state | Re-checking orphans after every ingest |
| Skip a file if its file key (drop name + path) was already ingested | Simple, makes re-runs a no-op | Comparing the content hash (stored, but not used for skipping) |
| Names and phones stored as HMAC hashes | Not readable at rest; phone still matches | Encrypting with a reversible key (needed only if we must read names back) |
| A required field that is present but unparseable counts as `missing_required:<field>` | The spec only names invalid_phone for bad values | Adding a new reason code |
| If a header matches two columns, the first column wins | Avoids ambiguity | Rejecting the file |
| Ties on timestamps are broken by `event_id` | Gives a stable, repeatable result | Arrival order |
| An override whose call has no linked event is an orphan | It cannot be tied to a lead | Keeping it aside |
| A call counts only if its `call.initiated` is linked | Spec rule | none |
| Orphan check comes before the unknown-disposition check | Order given in the spec | none |
| Strict date patterns (2-digit day and month) | The spec lists exact formats | Lenient parsing |
| Money rounds half-up | Matches what people expect | Banker's rounding |

## Failure modes considered
- **Re-running a drop:** skipped by file key. Tested (`test_idempotency.py`, seed 7).
- **Crash in the middle of a file:** the file is saved in one transaction, so nothing is half-written.
- **Duplicate events across drops:** the `event_id` primary key plus `INSERT OR IGNORE`.
- **Bad lines and rows:** malformed events are counted, bad leads go to `rejections.csv`, and blank rows are skipped.
- **Edits to the ledger:** blocked by database triggers.
- **Not handled:**
  - A file that is edited but keeps the same name is skipped (it would need hash comparison).
  - The default secret key is for development only. Production needs a secret manager and key rotation.
  - No locking if two ingests run at the same time.
  - Reports are built in Python memory, so very large data may be slow. Not measured.
  - Events for workflows that have no schema are not specially handled.
  - I did not write an explicit test that "drop 1 then drop 2" equals "everything at once".

## Testing
- Cleaning rules: headers, phones (valid and invalid formats), dates, money, enums, timestamps.
- Lead ingest: rejection reasons, merge with last-write-wins, no plain-text names, re-run does nothing.
- End to end: events that arrive before their lead, overrides without phone, duplicate, malformed, orphan and unknown-disposition events, and all report values.
- Idempotency on an unseen seed (7): all five reports are byte-identical after re-ingesting.
- Not tested: large scale, concurrent runs.

## Results
- Seed 42, small: 2057 lead rows (108 rejected, 57 merged), 8745 event lines (8 malformed, 237 duplicates, 462 orphans, 18 unknown dispositions).
- [YOU: add one thing you noticed in the data, and your timing if you measured it]

## If I had another day
1. Compare content hashes and handle changed files.
2. Do report aggregation in SQL and test on `--scale large`.
3. Add a test for "ingest in two drops = ingest all at once".
4. Move the secret to a proper secret manager and plan key rotation.
5. Write a short production note (scheduling, retries, backfills for 100k leads/day).