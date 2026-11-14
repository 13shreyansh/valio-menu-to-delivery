"""Private, durable account documents. Conditional writes prevent lost updates.
Local unit tests use an isolated SQLite database; Vercel always requires Blob.
"""

import json, os, sqlite3, time
from pathlib import Path
from urllib.parse import quote
import httpx
from .kitchen import KitchenError
from .account_scope import storage_namespace


class Conflict(KitchenError):
    pass


class Store:
    def __init__(self, namespace=None):
        self.namespace=namespace or storage_namespace()
        self.token = os.environ.get("BLOB_READ_WRITE_TOKEN")
        if not self.token and os.environ.get("VERCEL"):
            raise KitchenError("Account storage is unavailable. Please try again.")
        self.local = Path(os.environ.get("AURORA_LOCAL_DB", "/tmp/valio-aurora.sqlite"))

    def headers(self):
        return {"Authorization": "Bearer " + self.token, "x-api-version": "13"}

    def url(self, key):
        sid = self.token.split("_")[3]
        return f"https://{sid}.private.blob.vercel-storage.com/{self.namespace}/{key}.json"

    def get(self, key):
        if self.token:
            r = httpx.get(
                self.url(key),
                headers={
                    **self.headers(),
                    "Cache-Control": "no-cache",
                    "Accept-Encoding": "identity",
                },
                params={"cache": "0"},
                timeout=30,
            )
            if r.status_code == 404:
                return None, None
            r.raise_for_status()
            return r.json(), r.headers.get("etag")
        key=self.namespace+"/"+key
        with sqlite3.connect(self.local) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS docs (key TEXT PRIMARY KEY, body TEXT, version INTEGER)"
            )
            row = db.execute(
                "SELECT body,version FROM docs WHERE key=?", (key,)
            ).fetchone()
            return (json.loads(row[0]), str(row[1])) if row else (None, None)

    def put(self, key, value, version=None):
        if self.token:
            h = {
                **self.headers(),
                "x-vercel-blob-access": "private",
                "x-add-random-suffix": "0",
                "x-allow-overwrite": "1" if version else "0",
                "x-content-type": "application/json",
                "x-cache-control-max-age": "0",
            }
            if version:
                h["x-if-match"] = version
            r = httpx.put(
                "https://vercel.com/api/blob/",
                params={"pathname": self.namespace+"/" + key + ".json"},
                headers=h,
                content=json.dumps(value),
                timeout=30,
            )
            if r.status_code in (409, 412) or (
                r.status_code == 400 and "already exists" in r.text.lower()
            ):
                raise Conflict(
                    "This order changed in another window. Reload before trying again."
                )
            if not r.is_success:
                raise KitchenError(
                    "Storage rejected write: "
                    + str(r.json().get("error", {}).get("message", r.status_code))
                )
            return r.json().get("etag")
        key=self.namespace+"/"+key
        with sqlite3.connect(self.local) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS docs (key TEXT PRIMARY KEY, body TEXT, version INTEGER)"
            )
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT version FROM docs WHERE key=?", (key,)).fetchone()
            if (str(old[0]) if old else None) != version:
                raise Conflict(
                    "This order changed in another window. Reload before trying again."
                )
            n = int(version or 0) + 1
            db.execute(
                "INSERT OR REPLACE INTO docs VALUES (?,?,?)",
                (key, json.dumps(value), n),
            )
            return str(n)
