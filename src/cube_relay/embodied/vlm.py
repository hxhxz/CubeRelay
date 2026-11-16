"""Replaceable coarse scene-understanding interfaces.

VLM output is advisory only. Precise pose, sticker colors and cube legality are
computed by deterministic modules elsewhere.
"""

from __future__ import annotations

import base64
import json
import urllib.request
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from .v2_types import SceneSemantics


class SceneVLM(Protocol):
    def understand(self, rgb: np.ndarray) -> SceneSemantics: ...


class HeuristicSceneVLM:
    """SIMPLIFIED local fallback; detects saturated sticker-like pixels."""

    def understand(self, rgb: np.ndarray) -> SceneSemantics:
        values = rgb.astype(np.int16)
        chroma = values.max(axis=2) - values.min(axis=2)
        visible = int(np.count_nonzero(chroma > 70)) > 40
        return SceneSemantics(
            visible,
            0.65 if visible else 0.2,
            "cube-like colored sticker cluster visible" if visible else "no cube-like cluster",
            "heuristic_local",
        )


@dataclass(slots=True)
class OpenAICompatibleSceneVLM:
    """Cloud or vLLM adapter for OpenAI-compatible chat-completions APIs."""

    endpoint: str
    model: str
    api_key: str = ""
    timeout_seconds: float = 30.0

    def understand(self, rgb: np.ndarray) -> SceneSemantics:
        try:
            from PIL import Image
            import io
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("Pillow is required by the HTTP VLM adapter") from exc
        buffer = io.BytesIO()
        Image.fromarray(rgb).save(buffer, format="JPEG", quality=88)
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        prompt = (
            "Return JSON only with cube_visible (boolean), confidence (0..1), and "
            "description. Do not estimate precise pose or sticker state."
        )
        payload = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {
                    "url": f"data:image/jpeg;base64,{encoded}"}},
            ]}],
        }
        request = urllib.request.Request(
            self.endpoint.rstrip("/") + "/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            result = json.loads(response.read())
        content = json.loads(result["choices"][0]["message"]["content"])
        return SceneSemantics(
            bool(content["cube_visible"]), float(content["confidence"]),
            str(content["description"]), f"openai_compatible:{self.model}",
        )

