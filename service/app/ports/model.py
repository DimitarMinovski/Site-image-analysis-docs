"""Vision model port.

Unused by the stub analyser. It exists now so that Step 7 is a configuration
change rather than a refactor, and so the shape of the call is fixed before a
provider is chosen.

The contract is deliberately narrow:

    describe_image(image_bytes, prompt, json_schema) -> dict

One call, bytes in, validated JSON out. Nothing provider-specific leaks past
this boundary, which is what makes the evaluation harness able to benchmark a
new model by changing MODEL_PROVIDER and re-running.

Providers are imported lazily, so a laptop with no cloud SDKs installed runs
the whole skeleton.
"""
from __future__ import annotations

import base64
import json
from typing import Any, Optional, Protocol

from ..config import settings


class ModelUnavailable(RuntimeError):
    """Raised when a provider is selected but not usable, with what to do about it."""


class ModelClient(Protocol):
    def describe_image(self, image: bytes, prompt: str,
                       json_schema: Optional[dict] = None) -> dict: ...
    def describe(self) -> str: ...


class NullModel:
    """Default. Fails loudly rather than silently returning something plausible."""

    def describe_image(self, image: bytes, prompt: str,
                       json_schema: Optional[dict] = None) -> dict:
        raise ModelUnavailable(
            "MODEL_PROVIDER=none. The stub analyser needs no model. "
            "Set MODEL_PROVIDER=bedrock or openai, plus MODEL_ID, before Step 7."
        )

    def describe(self) -> str:
        return "none"


class BedrockModel:
    """Amazon Bedrock. Vision models take an image block plus a text block.

    Kept thin on purpose: retry, backoff and cost accounting belong in the
    worker, not in the adapter.
    """

    def __init__(self, model_id: str, region: str) -> None:
        if not model_id:
            raise ModelUnavailable("MODEL_ID is required when MODEL_PROVIDER=bedrock")
        try:
            import boto3  # noqa: PLC0415
        except ImportError as e:
            raise ModelUnavailable("boto3 not installed. pip install 'boto3'") from e
        self.model_id = model_id
        self._rt = boto3.client("bedrock-runtime", region_name=region)

    def describe_image(self, image: bytes, prompt: str,
                       json_schema: Optional[dict] = None) -> dict:
        instruction = prompt
        if json_schema:
            instruction += (
                "\n\nReply with JSON only, conforming exactly to this schema. "
                "No prose, no code fences.\n" + json.dumps(json_schema)
            )
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
            "temperature": 0,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image", "source": {
                        "type": "base64", "media_type": "image/jpeg",
                        "data": base64.b64encode(image).decode()}},
                    {"type": "text", "text": instruction},
                ],
            }],
        }
        resp = self._rt.invoke_model(modelId=self.model_id, body=json.dumps(body))
        payload = json.loads(resp["body"].read())
        return _extract_json(payload["content"][0]["text"])

    def describe(self) -> str:
        return f"bedrock:{self.model_id}"


class OpenAIModel:
    """OpenAI-compatible chat completions with an image part."""

    def __init__(self, model_id: str, timeout_s: int) -> None:
        if not model_id:
            raise ModelUnavailable("MODEL_ID is required when MODEL_PROVIDER=openai")
        try:
            from openai import OpenAI  # noqa: PLC0415
        except ImportError as e:
            raise ModelUnavailable("openai not installed. pip install 'openai'") from e
        self.model_id = model_id
        self._c = OpenAI(timeout=timeout_s)

    def describe_image(self, image: bytes, prompt: str,
                       json_schema: Optional[dict] = None) -> dict:
        url = "data:image/jpeg;base64," + base64.b64encode(image).decode()
        kwargs: dict[str, Any] = {
            "model": self.model_id,
            "temperature": 0,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": url}},
                ],
            }],
        }
        if json_schema:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "representation", "schema": json_schema, "strict": False},
            }
        resp = self._c.chat.completions.create(**kwargs)
        return _extract_json(resp.choices[0].message.content or "")

    def describe(self) -> str:
        return f"openai:{self.model_id}"


def _extract_json(text: str) -> dict:
    """Tolerate code fences and leading prose; fail loudly if there is no object."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```")[1]
        if t.lstrip().lower().startswith("json"):
            t = t.lstrip()[4:]
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"model returned no JSON object: {text[:200]!r}")
    return json.loads(t[start:end + 1])


def get_model() -> ModelClient:
    p = settings.model_provider
    if p == "bedrock":
        return BedrockModel(settings.model_id, settings.aws_region)
    if p == "openai":
        return OpenAIModel(settings.model_id, settings.model_timeout_s)
    return NullModel()
