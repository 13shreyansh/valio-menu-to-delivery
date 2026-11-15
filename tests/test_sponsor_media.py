import base64
import io
from unittest.mock import Mock

import httpx
import pytest
from PIL import Image

from chefagent import sponsor_media as media
from chefagent.kitchen import KitchenError


def test_missing_seed_never_issues_a_shared_kitchen_cookie(monkeypatch):
    from fastapi.testclient import TestClient
    from api.index import app
    from chefagent import portal_routes
    monkeypatch.setattr(portal_routes, "clone_account", lambda *args: False)
    client = TestClient(app, base_url="https://testserver")
    try:
        response = client.post("/api/login")
        assert response.status_code == 422
        assert "aurora_account" not in response.cookies
        assert "private kitchen" in response.json()["error"]
    finally:
        client.close()


@pytest.mark.parametrize("route_name,provider_name", [("menu_photo", "upload_menu"), ("transcribe", "transcribe")])
def test_provider_work_is_off_event_loop_and_preserves_private_kitchen(monkeypatch, route_name, provider_name):
    import asyncio
    import threading
    from chefagent import portal_routes
    from chefagent.account_scope import kitchen_scope, account_id
    event_loop_thread = threading.get_ident()
    identity = "test-" + "e" * 32
    def provider(value):
        assert threading.get_ident() != event_loop_thread, "Provider work blocks the event loop"
        assert account_id() == identity, "Provider work lost private-account scope"
        return {"ok": True}
    monkeypatch.setattr(media, provider_name, provider)
    class Request:
        async def json(self):
            return {"media": {}}
    with kitchen_scope(identity):
        assert asyncio.run(getattr(portal_routes, route_name)(Request())) == {"ok": True}


def photo():
    out = io.BytesIO()
    Image.new("RGB", (1600, 1200), "white").save(out, format="PNG")
    return {"mime": "image/png", "data": base64.b64encode(out.getvalue()).decode()}


def test_cloudinary_photo_is_authenticated_resized_and_scoped(monkeypatch, tmp_path):
    import cloudinary.uploader
    monkeypatch.setenv("CLOUDINARY_CLOUD_NAME", "test-cloud")
    monkeypatch.setenv("CLOUDINARY_API_KEY", "test-key")
    monkeypatch.setenv("CLOUDINARY_API_SECRET", "test-secret")
    monkeypatch.setenv("AURORA_LOCAL_DB", str(tmp_path / "account.sqlite"))
    def uploaded(file, **options):
        assert options["type"] == "authenticated"
        assert options["eager"] == [{"width": 960, "height": 960, "crop": "limit", "quality": "auto", "fetch_format": "webp"}]
        assert options["overwrite"] is False and options["api_key"] == "test-key"
        assert options["public_id"].startswith("valio/") and "aurora" not in options["public_id"]
        return {"public_id": options["public_id"], "type": "authenticated", "version": 1,
                "format": "png", "width": 1600, "height": 1200, "bytes": 10000}
    monkeypatch.setattr(cloudinary.uploader, "upload", uploaded)
    receipt = media.upload_menu(photo())
    assert "/image/authenticated/s--" in receipt["preview_url"]
    assert "w_960" in receipt["preview_url"] and "test-secret" not in receipt["preview_url"]
    saved = media.Store().get("media/" + receipt["id"])[0]
    assert saved == receipt and "data" not in saved


def test_fake_image_is_rejected_before_any_upload(monkeypatch):
    monkeypatch.setattr(media, "capabilities", lambda: (_ for _ in ()).throw(AssertionError("must validate first")))
    with pytest.raises(KitchenError, match="could not be read"):
        media.upload_menu({"mime": "image/png", "data": base64.b64encode(b"not an image").decode()})


def test_elevenlabs_transcription_returns_reviewable_text(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    def post(url, **kwargs):
        assert url == "https://api.elevenlabs.io/v1/speech-to-text"
        assert kwargs["headers"] == {"xi-api-key": "test-key"}
        assert kwargs["files"]["file"][1] == b"audio"
        assert kwargs["data"]["model_id"] == "scribe_v2"
        return httpx.Response(200, json={"text": "Wedding Saturday, 120 guests"}, request=httpx.Request("POST", url))
    monkeypatch.setattr(media.httpx, "post", post)
    assert media.transcribe({"mime": "audio/webm", "data": base64.b64encode(b"audio").decode()}) == {
        "transcript": "Wedding Saturday, 120 guests", "provider": "ElevenLabs"}


def test_provider_error_is_safe_and_does_not_silently_switch_models(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setattr(media.httpx, "post", lambda url, **kw: httpx.Response(401, text="private provider detail", request=httpx.Request("POST", url)))
    with pytest.raises(KitchenError, match="Your order has not changed") as err:
        media.transcribe({"mime": "audio/webm", "data": base64.b64encode(b"audio").decode()})
    assert "private provider detail" not in str(err.value)


def test_speech_uses_recorded_order_facts_and_requires_placement(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    with pytest.raises(KitchenError, match="Place and review"):
        media.confirmation_audio({"status": "draft"})
    def post(url, **kwargs):
        assert "AU-123" in kwargs["json"]["text"]
        assert "42.50 euros" in kwargs["json"]["text"]
        assert "Nothing will be shipped" in kwargs["json"]["text"]
        return httpx.Response(200, content=b"mp3 bytes", headers={"content-type": "audio/mpeg"}, request=httpx.Request("POST", url))
    monkeypatch.setattr(media.httpx, "post", post)
    assert media.confirmation_audio({"status": "placed", "order_number": "AU-123", "total": 42.5}) == b"mp3 bytes"
