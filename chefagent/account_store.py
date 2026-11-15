"""Private, durable account documents. Conditional writes prevent lost updates.
Local unit tests use an isolated SQLite database; Vercel always requires Blob.
"""

import json, os, sqlite3, time
from pathlib import Path
from urllib.parse import quote
import httpx
from .kitchen import KitchenError
from .account_scope import storage_namespace


CLIENT = httpx.Client(timeout=20)  # one pooled connection per warm instance


class Conflict(KitchenError):
    pass


class Store:
    def __init__(self, namespace=None):
        self.namespace=namespace or storage_namespace()
        self.token = None
        self.pg = os.environ.get("STORE_URL")
        self.pg_key = os.environ.get("STORE_KEY")
        if not self.pg and os.environ.get("VERCEL"):
            raise KitchenError("Account storage is unavailable. Please try again.")
        self.local = Path(os.environ.get("AURORA_LOCAL_DB", "/tmp/valio-aurora.sqlite"))

    def headers(self):
        return {"Authorization": "Bearer " + self.token, "x-api-version": "13"}

    def url(self, key):
        sid = self.token.split("_")[3]
        return f"https://{sid}.private.blob.vercel-storage.com/{self.namespace}/{key}.json"

    def pg_headers(self):
        return {
            "apikey": self.pg_key,
            "Authorization": "Bearer " + self.pg_key,
            "x-store-secret": os.environ.get("STORE_SECRET", ""),
            "Content-Type": "application/json",
        }

    def pg_get(self, key):
        r = CLIENT.get(
            self.pg + "/rest/v1/valio_docs",
            params={"key": "eq." + self.namespace + "/" + key, "select": "body,version"},
            headers=self.pg_headers(),
        )
        r.raise_for_status()
        rows = r.json()
        return (rows[0]["body"], str(rows[0]["version"])) if rows else (None, None)

    def pg_put(self, key, value, version):
        full = self.namespace + "/" + key
        if version:
            r = CLIENT.patch(
                self.pg + "/rest/v1/valio_docs",
                params={"key": "eq." + full, "version": "eq." + str(version)},
                headers={**self.pg_headers(), "Prefer": "return=representation"},
                content=json.dumps({"body": value, "version": int(version) + 1}),
            )
            if r.is_success and not r.json():
                raise Conflict("This order changed in another window. Reload before trying again.")
        else:
            r = CLIENT.post(
                self.pg + "/rest/v1/valio_docs",
                headers={**self.pg_headers(), "Prefer": "return=minimal"},
                content=json.dumps({"key": full, "body": value, "version": 1}),
            )
            if r.status_code == 409:
                raise Conflict("This order changed in another window. Reload before trying again.")
        if not r.is_success:
            raise KitchenError("Account storage is unavailable. Please try again.")
        return str(int(version or 0) + 1)

    def get(self, key):
        if self.pg:
            return self.pg_get(key)
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
        if self.pg:
            return self.pg_put(key, value, version)
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
