"""Aurora-backed archive -- the same interface as pipeline.Archive, backed by
Aurora PostgreSQL + pgvector instead of data/archive/cases.jsonl.

Additive, not a replacement. Every benchmarked number on the deck --
run_all.py, benchmarks/bench.py, benchmarks/surrogate.py, benchmarks/fold.py -- goes through pipeline.Archive
reading the local file exactly as before; nothing here is imported by any of
them. This module exists only so app.py can optionally point the *live demo's*
retrieval at the "at scale" backend docs/architecture.md describes, gated
behind the RETRIEVAL_BACKEND=aurora environment variable. Unset, this file is
never imported and nothing about the benchmarked pipeline changes.

Populate the table first with dejasolve/cloud/sync_archive_to_aurora.py.
"""

from __future__ import annotations

import functools
import json
import os

import numpy as np

from .. import casecard
from .. import pipeline
from .. import model
from .. import verifier


@functools.lru_cache(maxsize=1)
def _password(secret_arn: str) -> str:
    """The Aurora login, fetched from Secrets Manager once per process.

    `_connect()`'s "no pool, this demo doesn't need it" decision is about the
    database *connection* -- Aurora's own request volume for a ten-minute
    demo. It says nothing about a Secrets Manager API call, and every
    `nearest()` was repeating this one regardless: a fresh `get_secret_value`
    round trip before every single analyse, for a secret that does not rotate
    mid-demo. `lru_cache` rather than a bare module global so the cache is
    invalidated the normal way (`_password.cache_clear()`) if this process
    ever needs to pick up a rotated secret without restarting.
    """
    import boto3
    secret = boto3.client("secretsmanager").get_secret_value(SecretId=secret_arn)
    return json.loads(secret["SecretString"])["password"]


def _connect():
    """A fresh connection per call, not a pooled one -- this backend serves a
    ten-minute demo's request volume, not production traffic, and a pool would
    be complexity this doesn't need yet."""
    import psycopg2

    endpoint = os.environ["AURORA_ENDPOINT"]
    secret_arn = os.environ["AURORA_SECRET_ARN"]
    user = os.environ.get("AURORA_DB_USER", "dejasolve_admin")
    dbname = os.environ.get("AURORA_DB_NAME", "dejasolve")

    return psycopg2.connect(host=endpoint, port=5432, dbname=dbname,
                             user=user, password=_password(secret_arn),
                             sslmode="require")


def _vector_literal(params: dict) -> str:
    """pgvector's text input format for a `vector(7)` value: '[v1,v2,...,v7]'."""
    q = model.normalise(model.param_vector(params))[0]
    return "[" + ",".join(f"{v:.10g}" for v in q) + "]"


class AuroraArchive(pipeline.Archive):
    """Overrides __init__ (loads from Aurora, not a file) and nearest()
    (queries pgvector, not numpy). nearest_failure() and nearest_on() are
    inherited unchanged from pipeline.Archive -- both operate on in-memory
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
                "cases table is empty -- run `python -m dejasolve.cloud.sync_archive_to_aurora` first")

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
        #: same rule as pipeline.Archive: `record` is the whole JSON blob
        #: `dejasolve/cloud/sync_archive_to_aurora.py` upserted, so a card synced before
        #: sensitivities existed simply has none, and `warm_start` (inherited
        #: from `pipeline.Archive`, not overridden here) degrades to the
        #: verbatim transfer for it rather than raising.
        self.sensitivity = [
            None if r.get("sensitivity") is None
            else np.asarray(r["sensitivity"], dtype=float) for r in self.records]
        #: same rule again for the curvature tensor -- a card synced before
        #: `dejasolve/sweep.py` recorded one simply has none, and `warm_start` degrades to
        #: the first-order transfer for it.
        self.hessian = [
            None if r.get("hessian") is None
            else np.asarray(r["hessian"], dtype=float) for r in self.records]
        self.verifier = verifier.Verifier(self.records)
        self.domain = casecard.DOMAIN
        #: case_id -> position in `self.records`, built once rather than
        #: linear-scanned per `nearest()` call -- see `nearest()` for why a
        #: bare `next()` over `self.records` was also the wrong tool here,
        #: not just the slow one.
        self._index_by_id = {r["case_id"]: i for i, r in enumerate(self.records)}

    def nearest(self, params: dict) -> tuple[int, float]:
        """The one query that actually goes through pgvector rather than numpy.

        Mathematically identical to pipeline.Archive.nearest(): both normalise
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
        # `self.records` is a snapshot taken at __init__; pgvector queries the
        # live table. A row inserted into `cases` after this process started
        # is a case_id this snapshot does not contain, and a bare
        # `next(i for ... )` over `self.records` raised an unhandled
        # StopIteration for it -- a bare, unhelpful exception rather than the
        # RuntimeError every other refusal in this pipeline is. `_index_by_id`
        # (built once in __init__) turns the lookup into a dict `.get()`, so
        # a miss is a clear, actionable message instead of a crash.
        j = self._index_by_id.get(case_id)
        if j is None:
            raise RuntimeError(
                f"pgvector returned {case_id!r} as the nearest case, but this "
                f"process's snapshot does not have it -- the archive changed "
                f"since this service started; restart it to pick up new rows")
        return j, float(distance)

    def nearest_k(self, params: dict, k: int) -> list[tuple[int, float]]:
        """The ranked-retrieval shortlist, from pgvector rather than numpy.

        The same query as `nearest()` with `LIMIT 1` widened to `LIMIT k`.
        Overridden rather than inherited for one reason: `select()` picks the
        case the solver actually starts from, and if the shortlist it ranks
        came from the in-memory snapshot while `nearest()` came from the live
        table, the demo would be reporting a pgvector retrieval it did not
        perform. One backend, one source of candidates.
        """
        literal = _vector_literal(params)
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT case_id, setup_vector <-> %s::vector AS d FROM cases "
                    "WHERE status = 'solved' ORDER BY d ASC LIMIT %s",
                    (literal, int(k)))
                rows = cur.fetchall()
        finally:
            conn.close()
        out: list[tuple[int, float]] = []
        for case_id, distance in rows:
            # A row inserted after this process started is a case_id the
            # snapshot does not have. `nearest()` raises for it because it has
            # no candidate left to offer; here there are k-1 others, so the
            # unknown one is skipped and retrieval proceeds on a shortlist that
            # is one shorter -- degraded, not broken, and never silently
            # substituting the wrong record for it.
            i = self._index_by_id.get(case_id)
            if i is not None:
                out.append((i, float(distance)))
        if not out:
            raise RuntimeError(
                "pgvector returned no candidate this process's snapshot has -- "
                "the archive changed since this service started; restart it")
        return out
