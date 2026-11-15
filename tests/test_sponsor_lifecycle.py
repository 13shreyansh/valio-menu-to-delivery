import asyncio
from contextlib import asynccontextmanager

import pytest


@pytest.mark.parametrize("provider_fails", [False, True])
def test_provider_verifier_closes_pools_on_success_and_failure(monkeypatch, capsys, provider_fails):
    from scripts import verify_sponsors
    closed = []
    monkeypatch.setattr(verify_sponsors, "close_pools", lambda: closed.append(True))
    def probe(identity):
        if provider_fails:
            raise RuntimeError("Provider unavailable")
        return {"provider": "isolated test provider"}
    monkeypatch.setattr(verify_sponsors, "database_probe", probe)
    if provider_fails:
        with pytest.raises(SystemExit):
            verify_sponsors.main(["--database"])
    else:
        verify_sponsors.main(["--database"])
    assert closed == [True]


def test_application_shutdown_closes_pool_workers(monkeypatch):
    from api import index
    from chefagent import aiven_store
    closed = []
    @asynccontextmanager
    async def session():
        yield
    monkeypatch.setattr(index.mcp.session_manager, "run", session)
    monkeypatch.setattr(aiven_store, "close_pools", lambda: closed.append(True))
    async def scenario():
        async with index.lifespan(index.app):
            assert not closed
    asyncio.run(scenario())
    assert closed == [True]


def test_unchanged_sqlite_catch_up_does_not_repeat_per_row_writes(monkeypatch, tmp_path, capsys):
    import json
    import runpy
    import sqlite3
    import sys
    from pathlib import Path
    from chefagent import aiven_store
    path = tmp_path / "source.sqlite"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE docs (key TEXT PRIMARY KEY, body TEXT, version INTEGER)")
        db.execute("INSERT INTO docs VALUES (?,?,?)", ("accounts/test/ledger", json.dumps({"orders": []}), 1))
    monkeypatch.setenv("AURORA_LOCAL_DB", str(path))
    monkeypatch.setenv("AIVEN_DATABASE_URL", "test-only")
    monkeypatch.setattr(sys, "argv", ["migrate_aiven.py", "--apply"])
    closed = []
    monkeypatch.setattr(aiven_store, "close_pools", lambda: closed.append(True))
    class Backend:
        def __init__(self, url):
            pass
        def pending_import(self, rows):
            assert len(rows) == 1
            return []
        def import_documents(self, rows):
            raise AssertionError("Unchanged rows should not be rewritten")
        def verify_import(self, rows):
            return len(rows)
    monkeypatch.setattr(aiven_store, "AivenDocuments", Backend)
    runpy.run_path(str(Path(__file__).parents[1] / "scripts/migrate_aiven.py"), run_name="__main__")
    assert "exact source matches 1/1" in capsys.readouterr().out
    assert closed == [True]
