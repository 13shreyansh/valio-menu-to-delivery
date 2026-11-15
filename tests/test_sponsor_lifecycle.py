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
