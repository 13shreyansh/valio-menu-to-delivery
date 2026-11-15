"""TLS-verified PostgreSQL document storage for Valio's private kitchens.

The ledger is one versioned row per account. Its compare-and-swap update is the
order commitment point, so concurrent browser/MCP writers cannot lose orders.
"""
import json
import hashlib
import os
import threading
from contextlib import contextmanager

from .kitchen import KitchenError

_schema_lock = threading.Lock()
_initialized = set()
_pools = {}


class AivenDocuments:
    def __init__(self, url):
        self.url = url

    @contextmanager
    def connect(self):
        import psycopg
        from psycopg_pool import ConnectionPool, PoolTimeout
        kwargs = {"sslmode": "verify-full", "connect_timeout": 10,
                  "application_name": "valio-menu-to-delivery"}
        if os.environ.get("AIVEN_CA_CERT_PATH"):
            kwargs["sslrootcert"] = os.environ["AIVEN_CA_CERT_PATH"]
        try:
            with _schema_lock:
                pool = _pools.get(self.url)
                if pool is None or pool.closed:
                    pool = _pools[self.url] = ConnectionPool(
                        self.url, kwargs=kwargs, min_size=1, max_size=5, timeout=15,
                        open=True, name="valio-aiven", max_idle=60,
                    )
            with pool.connection() as db:
                with _schema_lock:
                    if self.url not in _initialized:
                        with db.transaction():
                            db.execute("SELECT pg_advisory_xact_lock(821614706)")
                            db.execute("""CREATE TABLE IF NOT EXISTS valio_docs (
                                key TEXT PRIMARY KEY,
                                body JSONB NOT NULL,
                                version BIGINT NOT NULL CHECK (version > 0),
                                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                            )""")
                        _initialized.add(self.url)
                yield db
        except (psycopg.Error, PoolTimeout):
            raise KitchenError("Account storage is unavailable. Your order has not changed. Please try again.") from None

    def get(self, full_key):
        import psycopg
        try:
            with self.connect() as db:
                row = db.execute("SELECT body, version FROM valio_docs WHERE key=%s", (full_key,)).fetchone()
                return (row[0], str(row[1])) if row else (None, None)
        except psycopg.Error:
            raise KitchenError("Account storage is unavailable. Please try again.") from None

    def put(self, full_key, value, version):
        import psycopg
        from psycopg.types.json import Jsonb
        from .account_store import Conflict
        try:
            with self.connect() as db:
                if version is None:
                    row = db.execute(
                        "INSERT INTO valio_docs (key,body,version) VALUES (%s,%s,1) ON CONFLICT DO NOTHING RETURNING version",
                        (full_key, Jsonb(value)),
                    ).fetchone()
                else:
                    row = db.execute(
                        "UPDATE valio_docs SET body=%s,version=version+1,updated_at=now() WHERE key=%s AND version=%s RETURNING version",
                        (Jsonb(value), full_key, int(version)),
                    ).fetchone()
                if row is None:
                    raise Conflict("This order changed in another window. Reload before trying again.")
                return str(row[0])
        except psycopg.Error:
            raise KitchenError("Account storage is unavailable. Your order has not changed. Please try again.") from None

    def clone_account(self, src, dst, replace=False):
        """Clone a seed in one transaction, excluding its MCP token and old drafts."""
        import psycopg
        from psycopg.types.json import Jsonb
        try:
            with self.connect() as db:
                prefix = src + "/"
                rows = db.execute("SELECT key,body FROM valio_docs WHERE left(key,%s)=%s", (len(prefix), prefix)).fetchall()
                docs = {key[len(prefix):]: body for key, body in rows}
                if "ledger" not in docs:
                    return False
                # Work on a detached copy; the source kitchen is never mutated.
                book = json.loads(json.dumps(docs["ledger"]))
                book.pop("archive", None)
                keep = {o.get("draft_id") for o in book.get("orders", [])}
                keep |= {d.get("draft_id") or d.get("id") for d in book.get("drafts", []) if isinstance(d, dict)}
                keep |= {d for d in book.get("drafts", []) if isinstance(d, str)}
                docs["ledger"] = book
                if replace:
                    target = dst + "/"
                    db.execute("DELETE FROM valio_docs WHERE left(key,%s)=%s", (len(target), target))
                for name, body in docs.items():
                    if name == "mcp" or name.startswith("media/") or (name.startswith("drafts/") and name[7:] not in keep):
                        continue
                    db.execute("INSERT INTO valio_docs (key,body,version) VALUES (%s,%s,1) ON CONFLICT DO NOTHING", (dst + "/" + name, Jsonb(body)))
            return True
        except psycopg.Error:
            raise KitchenError("A private kitchen could not be prepared. Please try again.") from None

    def import_documents(self, rows):
        """Import SQLite, or catch up only rows unchanged since our last import.

        A canary can use private clones while the old runtime still writes SQLite.
        At cutover, changed source rows may advance only when their cloud version
        and body still equal our previous receipt. Cloud writes are never lost.
        """
        from psycopg.types.json import Jsonb
        from .account_store import Conflict
        digest = lambda value: hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        count = 0
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS valio_imports (
                source TEXT NOT NULL, key TEXT NOT NULL, version BIGINT NOT NULL,
                body_hash TEXT NOT NULL, PRIMARY KEY(source,key)
            )""")
            for key, body, version in rows:
                value = json.loads(body)
                wanted_hash = digest(value)
                inserted = db.execute(
                    "INSERT INTO valio_docs (key,body,version) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                    (key, Jsonb(value), version),
                )
                if inserted.rowcount:
                    count += 1
                else:
                    current = db.execute("SELECT body,version FROM valio_docs WHERE key=%s FOR UPDATE", (key,)).fetchone()
                    previous = db.execute("SELECT version,body_hash FROM valio_imports WHERE source=%s AND key=%s", ("aurora-sqlite-v1", key)).fetchone()
                    same = current[1] == version and digest(current[0]) == wanted_hash
                    if not same:
                        if not previous or current[1] != previous[0] or digest(current[0]) != previous[1] or version < previous[0]:
                            raise Conflict("Cloud account data changed after import. Keep the current runtime and reconcile before switching.")
                        db.execute("UPDATE valio_docs SET body=%s,version=%s,updated_at=now() WHERE key=%s", (Jsonb(value), version, key))
                        count += 1
                db.execute("""INSERT INTO valio_imports (source,key,version,body_hash) VALUES (%s,%s,%s,%s)
                    ON CONFLICT(source,key) DO UPDATE SET version=excluded.version,body_hash=excluded.body_hash""",
                    ("aurora-sqlite-v1", key, version, wanted_hash))
        return count

    def verify_import(self, rows):
        """Compare in one connection, without exposing account values in output."""
        expected = {key: (json.loads(body), int(version)) for key, body, version in rows}
        with self.connect() as db:
            actual = db.execute("SELECT key,body,version FROM valio_docs WHERE key=ANY(%s)", (list(expected),)).fetchall()
        return sum(expected[key] == (body, version) for key, body, version in actual)
