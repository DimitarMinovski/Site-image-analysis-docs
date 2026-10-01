"""Configuration.

Every externally-variable thing is read from the environment, so moving from
a laptop to AWS is configuration rather than a code change. Nothing here has a
secret as a default.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _b(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # --- database -----------------------------------------------------
    database_url: str = os.environ.get(
        "DATABASE_URL", "postgresql://localhost:5432/siteimg"
    )

    # --- storage ------------------------------------------------------
    # local  -> filesystem under storage_root        (laptop)
    # s3     -> S3Storage                            (AWS)
    storage_backend: str = os.environ.get("STORAGE_BACKEND", "local")
    storage_root: Path = Path(os.environ.get("STORAGE_ROOT", str(REPO_ROOT / "var" / "images")))
    s3_bucket: str = os.environ.get("S3_BUCKET", "")
    s3_prefix: str = os.environ.get("S3_PREFIX", "images/")
    aws_region: str = os.environ.get("AWS_REGION", "eu-north-1")

    # --- analyser -----------------------------------------------------
    # stub      -> deterministic fake, schema-valid        (Step 4)
    # pipeline  -> perception + policy engine              (Steps 5-7)
    analyser: str = os.environ.get("ANALYSER", "stub")

    # --- model provider (unused by the stub; wired for Steps 5-7) ----
    # none | bedrock | openai
    model_provider: str = os.environ.get("MODEL_PROVIDER", "none")
    model_id: str = os.environ.get("MODEL_ID", "")
    model_timeout_s: int = int(os.environ.get("MODEL_TIMEOUT_S", "60"))

    # --- api ----------------------------------------------------------
    # Loopback by default. Binding to 0.0.0.0 must be a deliberate act.
    api_host: str = os.environ.get("API_HOST", "127.0.0.1")
    api_port: int = int(os.environ.get("API_PORT", "8000"))
    api_token: str = os.environ.get("API_TOKEN", "dev-token-change-me")
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            o.strip()
            for o in os.environ.get(
                "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
            ).split(",")
            if o.strip()
        )
    )

    # --- upload limits ------------------------------------------------
    max_upload_bytes: int = int(os.environ.get("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
    min_image_px: int = int(os.environ.get("MIN_IMAGE_PX", "800"))
    max_image_pixels: int = int(os.environ.get("MAX_IMAGE_PIXELS", str(80_000_000)))

    # --- worker -------------------------------------------------------
    worker_poll_s: float = float(os.environ.get("WORKER_POLL_S", "1.0"))
    max_attempts: int = int(os.environ.get("MAX_ATTEMPTS", "3"))

    # --- versions stamped onto every row ------------------------------
    perception_version: str = os.environ.get("PERCEPTION_VERSION", "0.1.0-stub")
    policy_engine_version: str = os.environ.get("POLICY_ENGINE_VERSION", "0.1.0-stub")
    rubric_version: str = os.environ.get("RUBRIC_VERSION", "0.1.0")

    debug: bool = _b("DEBUG", False)

    @property
    def schema_dir(self) -> Path:
        return REPO_ROOT / "schema"


settings = Settings()
