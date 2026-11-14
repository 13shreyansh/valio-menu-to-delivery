"""Regression: concurrent cold requests read a partially overwritten catalogue."""
import json,time
from concurrent.futures import ThreadPoolExecutor
from chefagent import catalog as c,build_catalog as b


def test_cold_catalog_is_initialized_once_for_concurrent_requests(monkeypatch,tmp_path):
    monkeypatch.setattr(c,'ROOT',tmp_path/'bundle')
    monkeypatch.setattr(c,'TEMP',tmp_path/'runtime')
    calls=[]
    def download(raw):
        calls.append('download')
        raw.mkdir(parents=True)
        (raw/'products.json').write_text('[{"id":')
        time.sleep(.04)
        (raw/'products.json').write_text('[{"id":"123"}]')
    def build(raw,out):
        assert json.loads((raw/'products.json').read_text())==[{'id':'123'}]
        out.write_text('[{"id":"123"}]')
    class Catalog:
        def __init__(self,path):self.items=json.loads(path.read_text())
    monkeypatch.setattr(b,'download_raw',download)
    monkeypatch.setattr(b,'main',build)
    monkeypatch.setattr(c,'Catalog',Catalog)
    c._load.cache_clear()
    try:
        with ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(lambda _:c.load(),range(6)))
        assert calls==['download']
        assert all(r is results[0] for r in results)
    finally:c._load.cache_clear()


def test_raw_download_is_published_only_after_complete_response(monkeypatch,tmp_path):
    import httpx
    monkeypatch.setenv('VALIO_API_KEY','isolated-unit-test-key')
    target=tmp_path/'products.json'
    target.write_text('[{"id":"previous"}]')
    class Response:
        status_code=200
        def __init__(self,url):self.url=url
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def raise_for_status(self):pass
        def iter_bytes(self,*args):
            yield b'[{"id":'
            if self.url.endswith('/products/download'):assert json.loads(target.read_text())==[{'id':'previous'}]
            yield b'"new"}]'
    monkeypatch.setattr(httpx,'stream',lambda method,url,**kw:Response(url))
    before=len(b.DOWNLOAD_AUDIT)
    try:
        b.download_raw(tmp_path)
        assert json.loads(target.read_text())==[{'id':'new'}]
        call=b.DOWNLOAD_AUDIT[before]
        assert call['product_count']==1 and call['at']>0 and call['duration_ms']>=0
    finally:del b.DOWNLOAD_AUDIT[before:]
