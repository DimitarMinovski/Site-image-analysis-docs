"""Storage port.

One protocol, two adapters. The laptop writes to the filesystem; AWS writes to
S3. Keys are content-addressed (sha256-derived), so storage is naturally
deduplicated and a key can always be recomputed from the bytes.

Moving to AWS is STORAGE_BACKEND=s3 plus a bucket name. No call site changes.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Protocol

from ..config import settings


def key_for(sha: str, prefix: str = "") -> str:
    """Content-addressed key, fanned out two hex chars deep.

    The fan-out keeps directory listings usable on a filesystem and keeps S3
    prefixes from becoming a single hot partition.
    """
    return f"{prefix}{sha[:2]}/{sha}"


class Storage(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...
    def describe(self) -> str: ...


class LocalStorage:
    """Filesystem adapter for local development."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _p(self, key: str) -> Path:
        p = (self.root / key).resolve()
        # containment check: a crafted key must not escape the root
        if not str(p).startswith(str(self.root.resolve())):
            raise ValueError("key escapes storage root")
        return p

    def put(self, key: str, data: bytes, content_type: str) -> None:
        p = self._p(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def get(self, key: str) -> bytes:
        return self._p(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._p(key).is_file()

    def describe(self) -> str:
        return f"local:{self.root}"


class S3Storage:
    """S3 adapter. boto3 is imported lazily so local runs need no AWS packages.

    Before production use, confirm on the bucket: default encryption enabled,
    public access blocked, region pinned to whatever the data approval
    specified, and a retention policy. Site photographs are customer
    infrastructure imagery.
    """

    def __init__(self, bucket: str, prefix: str = "", region: Optional[str] = None) -> None:
        if not bucket:
            raise ValueError("S3_BUCKET is required when STORAGE_BACKEND=s3")
        import boto3  # noqa: PLC0415

        self.bucket = bucket
        self.prefix = prefix
        self._s3 = boto3.client("s3", region_name=region or settings.aws_region)

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self._s3.put_object(
            Bucket=self.bucket, Key=key, Body=data,
            ContentType=content_type, ServerSideEncryption="AES256",
        )

    def get(self, key: str) -> bytes:
        return self._s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError  # noqa: PLC0415

        try:
            self._s3.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False

    def presign_get(self, key: str, expires_s: int = 300) -> str:
        """Later: hand this to the browser instead of proxying bytes through the API."""
        return self._s3.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=expires_s
        )

    def describe(self) -> str:
        return f"s3:{self.bucket}/{self.prefix}"


def get_storage() -> Storage:
    if settings.storage_backend == "s3":
        return S3Storage(settings.s3_bucket, settings.s3_prefix, settings.aws_region)
    return LocalStorage(settings.storage_root)
