"""Menu photos and speech providers. Credentials stay in the server environment.

Provider failures never place an order or alter the kitchen ledger.
"""
import base64
import hashlib
import io
import os
import uuid

import httpx
from PIL import Image, UnidentifiedImageError

from .account_scope import account_id
from .account_store import Store
from .kitchen import KitchenError

PHOTO_MIMES = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}
AUDIO_MIMES = {"audio/webm", "audio/ogg", "audio/mp4", "audio/wav", "audio/x-wav"}
MAX_BYTES = 6_000_000


def capabilities():
    return {
        "menuPhotos": all(os.environ.get(k) for k in ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET")),
        "spokenConfirmation": bool(os.environ.get("ELEVENLABS_API_KEY")),
    }


def decode_media(media, allowed):
    if not isinstance(media, dict) or media.get("mime") not in allowed:
        raise KitchenError("Choose a supported photo or recording.")
    data = media.get("data")
    if not isinstance(data, str) or len(data) > 8_000_000:
        raise KitchenError("Choose a photo or recording smaller than 6 MB.")
    try:
        binary = base64.b64decode(data, validate=True)
    except (ValueError, TypeError):
        raise KitchenError("This file could not be read. Choose another file.") from None
    if not binary or len(binary) > MAX_BYTES:
        raise KitchenError("Choose a photo or recording smaller than 6 MB.")
    return binary, media["mime"]


def upload_menu(media):
    binary, mime = decode_media(media, PHOTO_MIMES)
    try:
        with Image.open(io.BytesIO(binary)) as photo:
            if photo.format != PHOTO_MIMES[mime] or photo.width * photo.height > 40_000_000:
                raise KitchenError("Choose a JPEG, PNG or WebP menu photo under 40 megapixels.")
            photo.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise KitchenError("This photo could not be read. Choose another photo.") from None
    if not capabilities()["menuPhotos"]:
        raise KitchenError("Photo storage is temporarily unavailable. You can still type your menu.")
    import cloudinary
    import cloudinary.uploader
    from cloudinary.utils import cloudinary_url

    config = dict(
        cloud_name=os.environ["CLOUDINARY_CLOUD_NAME"],
        api_key=os.environ["CLOUDINARY_API_KEY"],
        api_secret=os.environ["CLOUDINARY_API_SECRET"],
        secure=True,
    )
    media_id = uuid.uuid4().hex
    public_id = "valio/" + hashlib.sha256(account_id().encode()).hexdigest()[:20] + "/" + media_id
    transform = {"width": 960, "height": 960, "crop": "limit", "quality": "auto", "fetch_format": "webp"}
    try:
        uploaded = cloudinary.uploader.upload(
            io.BytesIO(binary), public_id=public_id, type="authenticated",
            resource_type="image", overwrite=False, eager=[transform],
            timeout=45, **config,
        )
        if uploaded.get("public_id") != public_id or uploaded.get("type") != "authenticated":
            raise ValueError("Unexpected photo receipt")
        preview, _ = cloudinary_url(
            public_id, version=uploaded["version"], format=uploaded["format"],
            type="authenticated", sign_url=True, transformation=[transform], **config,
        )
        receipt = {"id": media_id, "provider": "Cloudinary", "public_id": public_id,
                   "preview_url": preview, "width": uploaded["width"], "height": uploaded["height"],
                   "bytes": uploaded["bytes"], "type": "authenticated"}
        Store().put("media/" + media_id, receipt)
        return receipt
    except KitchenError:
        raise
    except Exception:
        raise KitchenError("Your photo could not be saved. Try again, or type the menu. Your order has not changed.") from None


def transcribe(media):
    binary, mime = decode_media(media, AUDIO_MIMES)
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        # Preserve the existing working input path where speech access is not configured.
        from .kitchen_intake import understand
        return {"transcript": understand(media=media, source="audio")["transcript"], "provider": "Gemini"}
    try:
        response = httpx.post(
            "https://api.elevenlabs.io/v1/speech-to-text",
            headers={"xi-api-key": key},
            data={"model_id": os.environ.get("ELEVENLABS_STT_MODEL", "scribe_v2"),
                  "tag_audio_events": "false", "diarize": "false"},
            files={"file": ("recording." + mime.split("/")[-1].replace("x-", ""), binary, mime)},
            timeout=90,
        )
        response.raise_for_status()
        text = response.json().get("text", "").strip()
        if not text or len(text) > 4000:
            raise ValueError("No usable speech")
        return {"transcript": text, "provider": "ElevenLabs"}
    except (httpx.HTTPError, ValueError, TypeError):
        raise KitchenError("The recording could not be transcribed. Try again, or type it. Your order has not changed.") from None


def confirmation_audio(order):
    if order.get("status") != "placed" or not order.get("order_number"):
        raise KitchenError("Place and review the order before reading its confirmation.")
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise KitchenError("Spoken confirmations are temporarily unavailable. Your written confirmation is unchanged.")
    # Only server-recorded facts are spoken. User text never becomes an instruction or an order action.
    text = (f"Order {order['order_number']} is recorded. Total {float(order['total']):.2f} euros. "
            "This is a test account. Nothing will be shipped.")
    voice = os.environ.get("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")
    try:
        response = httpx.post(
            "https://api.elevenlabs.io/v1/text-to-speech/" + voice,
            headers={"xi-api-key": key, "Accept": "audio/mpeg"},
            params={"output_format": "mp3_44100_128"},
            json={"text": text, "model_id": os.environ.get("ELEVENLABS_TTS_MODEL", "eleven_multilingual_v2")},
            timeout=60,
        )
        response.raise_for_status()
        if not response.content or "audio" not in response.headers.get("content-type", ""):
            raise ValueError("No audio returned")
        return response.content
    except (httpx.HTTPError, ValueError):
        raise KitchenError("The confirmation could not be read aloud. Your recorded order is unchanged.") from None
