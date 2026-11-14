"""Request-local kitchens: public Hotel Aurora and isolated automated test kitchens."""
from contextlib import contextmanager
from contextvars import ContextVar
import re

CURRENT_ACCOUNT = ContextVar('valio_account', default='aurora')
TEST_RUN = re.compile(r'^[a-f0-9]{32}$')


def account_id():
    return CURRENT_ACCOUNT.get()


def account_name():
    return 'Hotel Aurora' if account_id() == 'aurora' else 'Aurora Test Kitchen'


def storage_namespace():
    return 'accounts/aurora-v3' if account_id() == 'aurora' else 'accounts/' + account_id()


@contextmanager
def kitchen_scope(value):
    if value != 'aurora' and not re.fullmatch(r'(?:test|repair)-[a-f0-9]{32}', value):
        raise ValueError('Invalid kitchen scope')
    token = CURRENT_ACCOUNT.set(value)
    try:
        yield
    finally:
        CURRENT_ACCOUNT.reset(token)


class KitchenScopeMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        from starlette.requests import Request
        from starlette.responses import JSONResponse
        from .kitchen import unseal, KitchenError

        req = Request(scope)
        run = req.headers.get('x-valio-test-run')
        if run and not TEST_RUN.fullmatch(run):
            return await JSONResponse(
                {'error': 'Use a valid test kitchen run ID.'}, status_code=400
            )(scope, receive, send)
        identity = 'test-' + run if run else 'aurora'
        # Public connectors always default to Aurora; their caller has no browser
        # cookie. Explicit test-run headers isolate automated outside clients too.
        if not run and not scope['path'].startswith('/mcp'):
            try:
                cookie = unseal(req.cookies.get('aurora_account', ''))
                candidate = cookie.get('account_id', 'aurora')
                if candidate == 'aurora' or re.fullmatch(r'test-[a-f0-9]{32}', candidate):
                    identity = candidate
            except (KitchenError, ValueError):
                pass
        with kitchen_scope(identity):
            await self.app(scope, receive, send)
