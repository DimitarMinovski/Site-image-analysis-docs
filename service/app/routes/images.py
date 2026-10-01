"""Image ingest.

Idempotency is the important property. The SHA-256 of the bytes is the identity,
so re-uploading the same photograph returns the existing record and its latest
assessment and creates no second job. That makes every retry path - a flaky
mobile connection, a double tap, a replayed queue message - safe by default.
"""
from __future__ import annotations

import hashlib
import io
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile, status

from .. import db
from ..config import settings
from ..ports.storage import get_storage, key_for

router = APIRouter()

# Magic bytes. Never trust the filename or the declared content type.
_MAGIC = [
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"II*\x00", "image/tiff"),
    (b"MM\x00*", "image/tiff"),
]


def _sniff(data: bytes) -> Optional[str]:
    for sig, ct in _MAGIC:
        if data.startswith(sig):
            return ct
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1"):
        return "image/heic"
    return None


def _dimensions(data: bytes) -> tuple[Optional[int], Optional[int]]:
    """Read dimensions without decoding the whole image.

    MAX_IMAGE_PIXELS guards against decompression-bomb images: a small file that
    expands to gigabytes of pixels.
    """
    try:
        from PIL import Image

        Image.MAX_IMAGE_PIXELS = settings.max_image_pixels
        with Image.open(io.BytesIO(data)) as im:
            return im.width, im.height
    except Exception:
        return None, None


@router.post("/images", status_code=status.HTTP_202_ACCEPTED)
async def upload_image(
    response: Response,
    file: UploadFile = File(...),
    site_id: Optional[str] = Form(None),
    cabinet_id: Optional[str] = Form(None),
    cabinet_type: Optional[str] = Form(None),
    captured_at: Optional[str] = Form(None),
) -> dict:
    data = await file.read()

    if not data:
        raise HTTPException(400, "empty upload")
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(413, f"upload exceeds {settings.max_upload_bytes} bytes")

    content_type = _sniff(data)
    if content_type is None:
        raise HTTPException(415, "not a recognised image (checked by magic bytes, not filename)")

    w, h = _dimensions(data)
    if w and h and min(w, h) < settings.min_image_px:
        raise HTTPException(
            422,
            f"image too small: {w}x{h}, shortest side must be >= {settings.min_image_px}px. "
            "A cabinet face below this cannot be measured.",
        )

    sha = hashlib.sha256(data).hexdigest()

    with db.conn() as c:
        existing = db.find_image_by_sha(c, sha)
        if existing:
            # idempotent: no new row, no new job
            latest = db.latest_assessment_for_image(c, existing["id"])
            job = db.job_for_image(c, existing["id"])
            response.status_code = status.HTTP_200_OK
            return {
                "duplicate": True,
                "image_sha256": sha,
                "image_id": existing["id"],
                "job": {"id": job["id"], "status": job["status"]} if job else None,
                "assessment_id": latest["id"] if latest else None,
                "verdict": latest["verdict"] if latest else None,
            }

        key = key_for(sha, settings.s3_prefix if settings.storage_backend == "s3" else "")
        get_storage().put(key, data, content_type)

        ts = None
        if captured_at:
            try:
                ts = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
            except ValueError:
                raise HTTPException(400, "captured_at must be ISO-8601")

        img = db.insert_image(
            c, sha256=sha, storage_key=key, content_type=content_type,
            byte_size=len(data), site_id=site_id, cabinet_id=cabinet_id,
            cabinet_type=cabinet_type, width_px=w, height_px=h, captured_at=ts,
        )
        job = db.enqueue(c, img["id"])
        c.commit()

    return {
        "duplicate": False,
        "image_sha256": sha,
        "image_id": img["id"],
        "job": {"id": job["id"], "status": job["status"]},
    }


@router.get("/images/{sha}")
def get_image_meta(sha: str) -> dict:
    with db.conn() as c:
        img = db.find_image_by_sha(c, sha)
        if not img:
            raise HTTPException(404, "unknown image")
        job = db.job_for_image(c, img["id"])
        latest = db.latest_assessment_for_image(c, img["id"])
    return {
        "image": {k: v for k, v in img.items() if k != "storage_key"},
        "job": {"id": job["id"], "status": job["status"], "error": job["error"]} if job else None,
        "assessment_id": latest["id"] if latest else None,
    }


@router.get("/images/{sha}/bytes")
def get_image_bytes(sha: str) -> Response:
    """Proxied for local development. On AWS this becomes a presigned S3 URL
    so image bytes never traverse the API."""
    with db.conn() as c:
        img = db.find_image_by_sha(c, sha)
    if not img:
        raise HTTPException(404, "unknown image")
    data = get_storage().get(img["storage_key"])
    return Response(content=data, media_type=img["content_type"],
                    headers={"Cache-Control": "private, max-age=3600"})
