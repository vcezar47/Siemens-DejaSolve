"""One-off: load data/archive/cases.jsonl and data/archive/failures.jsonl into Aurora.

Populates the `cases` table archive_aurora.AuroraArchive reads from. Run once
after the data.yaml stack exists, and again after any `python -m dejasolve.sweep`
re-run -- it upserts, so re-running it is always safe.

Needs network access to the Aurora cluster, which sits in private subnets: run
this inside the VPC (an ECS "run task" using the dejasolve-ui task definition
with the command overridden to `python -m dejasolve.cloud.sync_archive_to_aurora` is the
simplest way from the console -- see docs/aws-deployment-plan.md), not from a
laptop.

    python -m dejasolve.cloud.sync_archive_to_aurora
"""

from __future__ import annotations

import json
from pathlib import Path

from .archive_aurora import _connect, _vector_literal

ROOT = Path(__file__).resolve().parent.parent.parent

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    case_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    record JSONB NOT NULL,
    setup_vector vector(7)
);
"""


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def main() -> None:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(SCHEMA)
        conn.commit()

        solved = _read_jsonl(ROOT / "data" / "archive" / "cases.jsonl")
        failed = _read_jsonl(ROOT / "data" / "archive" / "failures.jsonl")
        if not solved:
            raise SystemExit(f"no records at {ROOT / 'data' / 'archive' / 'cases.jsonl'} "
                              "-- run `python -m dejasolve.sweep` first")

        with conn.cursor() as cur:
            for r in solved:
                cur.execute(
                    "INSERT INTO cases (case_id, status, record, setup_vector) "
                    "VALUES (%s, 'solved', %s, %s::vector) "
                    "ON CONFLICT (case_id) DO UPDATE SET "
                    "record = EXCLUDED.record, setup_vector = EXCLUDED.setup_vector",
                    (r["case_id"], json.dumps(r), _vector_literal(r["params"])))
            for r in failed:
                cur.execute(
                    "INSERT INTO cases (case_id, status, record, setup_vector) "
                    "VALUES (%s, %s, %s, NULL) "
                    "ON CONFLICT (case_id) DO UPDATE SET "
                    "status = EXCLUDED.status, record = EXCLUDED.record",
                    (r["case_id"], r["status"], json.dumps(r)))
        conn.commit()
        print(f"synced {len(solved)} solved, {len(failed)} failed cases to Aurora")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
