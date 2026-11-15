"""Request-local kitchens: public Hotel Aurora and isolated automated test kitchens."""
from contextlib import contextmanager
from contextvars import ContextVar
import re

CURRENT_ACCOUNT = ContextVar('valio_account', default='aurora')
TEST_RUN = re.compile(r'^[a-f0-9]{32}$')
# Every "Try the demo account" visit gets its own private copy of Hotel Aurora (demo-...).
PRIVATE = re.compile(r'(?:test|repair|demo)-[a-f0-9]{32}')


def account_id():
    return CURRENT_ACCOUNT.get()


def account_name():
    return 'Aurora Test Kitchen' if account_id().startswith(('test-', 'repair-')) else 'Hotel Aurora'


def storage_namespace():
    return 'accounts/aurora-v3' if account_id() == 'aurora' else 'accounts/' + account_id()


@contextmanager
def kitchen_scope(value):
    if value != 'aurora' and not PRIVATE.fullmatch(value):
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
        if scope['path'].startswith('/mcp'):
            # Outside agents carry a per-account bearer token. No token, no door.
            if req.method == 'OPTIONS':
                return await self.app(scope, receive, send)
            from . import portal
            auth = req.headers.get('authorization', '')
            token = auth[7:].strip() if auth.lower().startswith('bearer ') else req.query_params.get('token', '')
            account = portal.token_account(token)
            ok = False
            if account:
                with kitchen_scope(account):
                    try:
                        ok = portal.token_valid(token)
                    except Exception:
                        return await JSONResponse({'error': 'Valio is unavailable. Please try again.'}, status_code=503)(scope, receive, send)
            if not ok:
                return await JSONResponse(
                    {'error': 'unauthorized', 'error_description': 'Send your account token as "Authorization: Bearer <token>". Find it in the Valio Aimo portal under Settings, Connected assistants.'},
                    status_code=401, headers={'WWW-Authenticate': 'Bearer realm="Valio Aimo MCP"'},
                )(scope, receive, send)
            identity = account
        elif not run:
            try:
                cookie = unseal(req.cookies.get('aurora_account', ''))
                candidate = cookie.get('account_id', 'aurora')
                if candidate == 'aurora' or re.fullmatch(r'(?:test|demo)-[a-f0-9]{32}', candidate):
                    identity = candidate
            except (KitchenError, ValueError):
                pass
        with kitchen_scope(identity):
            await self.app(scope, receive, send)
