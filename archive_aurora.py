"""Aurora-backed archive -- the same interface as dejasolve.Archive, backed by
Aurora PostgreSQL + pgvector instead of archive/cases.jsonl.

Additive, not a replacement. Every benchmarked number on the deck --
run_all.py, bench.py, surrogate.py, fold.py -- goes through dejasolve.Archive
reading the local file exactly as before; nothing here is imported by any of
them. This module exists only so app.py can optionally point the *live demo's*
retrieval at the "at scale" backend docs/architecture.md describes, gated
behind the RETRIEVAL_BACKEND=aurora environment variable. Unset, this file is
never imported and nothing about the benchmarked pipeline changes.

Populate the table first with sync_archive_to_aurora.py.
"""

from __future__ import annotations

import json
import os

import numpy as np

import casecard
import dejasolve
import model
import verifier


def _connect():
    """A fresh connection per call, not a pooled one -- this backend serves a
    ten-minute demo's request volume, not production traffic, and a pool would
    be complexity this doesn't need yet."""
    import boto3
    import psycopg2

    endpoint = os.environ["AURORA_ENDPOINT"]
    secret_arn = os.environ["AURORA_SECRET_ARN"]
    user = os.environ.get("AURORA_DB_USER", "dejasolve_admin")
    dbname = os.environ.get("AURORA_DB_NAME", "dejasolve")

    secret = boto3.client("secretsmanager").get_secret_value(SecretId=secret_arn)
    password = json.loads(secret["SecretString"])["password"]

    return psycopg2.connect(host=endpoint, port=5432, dbname=dbname,
                             user=user, password=password, sslmode="require")


def _vector_literal(params: dict) -> str:
    """pgvector's text input format for a `vector(7)` value: '[v1,v2,...,v7]'."""
    q = model.normalise(model.param_vector(params))[0]
    return "[" + ",".join(f"{v:.10g}" for v in q) + "]"


class AuroraArchive(dejasolve.Archive):
    """Overrides __init__ (loads from Aurora, not a file) and nearest()
    (queries pgvector, not numpy). nearest_failure() and nearest_on() are
    inherited unchanged from dejasolve.Archive -- both operate on in-memory
    arrays built below, identically shaped to the file-backed path, so there is
    exactly one place a bug in that logic could live."""

    def __init__(self):  # noqa: super().__init__ deliberately not called -- it reads a file
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT record FROM cases WHERE status = 'solved'")
                self.records = [row[0] for row in cur.fetchall()]
                cur.execute("SELECT record FROM cases WHERE status != 'solved'")
                self.failures = [row[0] for row in cur.fetchall()]
        finally:
            conn.close()

        if not self.records:
            raise RuntimeError(
                "cases table is empty -- run `python sync_archive_to_aurora.py` first")

        self.failure_modes: dict[str, int] = {}
        for f in self.failures:
            self.failure_modes[f["status"]] = self.failure_modes.get(f["status"], 0) + 1
        self.failure_norm = (model.normalise(
            np.array([[f["params"][k] for k in model.PARAM_NAMES]
                      for f in self.failures])) if self.failures else None)

        params = np.array([[r["params"][k] for k in model.PARAM_NAMES]
                           for r in self.records])
        self.norm = model.normalise(params)
        self.states = np.array([[r["solution"][k] for k in model.STATE_NAMES]
                                for r in self.records])
        self.verifier = verifier.Verifier(self.records)
        self.domain = casecard.DOMAIN

    def nearest(self, params: dict) -> tuple[int, float]:
        """The one query that actually goes through pgvector rather than numpy.

        Mathematically identical to dejasolve.Archive.nearest(): both normalise
        against the same fixed PARAM_BOUNDS and both compute a Euclidean
        distance, so this returns the same case for the same query. No ANN
        index on purpose -- pgvector's `<->` here is an exact sequential scan
        over ~400 rows, and phase-1c's own finding (an approximate index can
        fail silently once the distance metric itself has degraded) is a good
        reason not to trade exactness for speed this archive doesn't need.
        """
        literal = _vector_literal(params)
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT case_id, setup_vector <-> %s::vector AS d FROM cases "
                    "WHERE status = 'solved' ORDER BY d ASC LIMIT 1",
                    (literal,))
                case_id, distance = cur.fetchone()
        finally:
            conn.close()
        j = next(i for i, r in enumerate(self.records) if r["case_id"] == case_id)
        return j, float(distance)
