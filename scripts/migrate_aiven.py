"""Copy the existing SQLite documents to Aiven without overwriting cloud data.

Run inside the release container with AIVEN_DATABASE_URL and its public CA path.
First stop old writers, then run --apply and switch to the new container. The
SQLite source remains intact for rollback. Output never includes account data.
"""
import argparse
import os
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from chefagent.aiven_store import AivenDocuments

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    source = Path(os.environ.get("AURORA_LOCAL_DB", "/data/accounts.sqlite"))
    with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as db:
        rows = db.execute("SELECT key,body,version FROM docs ORDER BY key").fetchall()
    if not args.apply:
        print(f"Dry run: {len(rows)} documents available. No writes performed.")
    else:
        backend = AivenDocuments(os.environ["AIVEN_DATABASE_URL"])
        inserted = backend.import_documents(rows)
        # Compare source and cloud documents without exposing either in logs.
        matching = backend.verify_import(rows)
        print(f"Imported or safely advanced {inserted}; exact source matches {matching}/{len(rows)}.")
        if matching != len(rows):
            raise SystemExit("Cloud documents differ. Keep the previous runtime and reconcile before switching.")
