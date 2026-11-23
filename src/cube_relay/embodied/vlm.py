"""Legacy coarse scene-understanding adapters & deterministic pixel presence detectors.

LIVE M4 mainline perception uses `cube_relay.mission.dual_model.VLMPerceptionProvider`
and `cube_relay.perception.evidence.PerceptionEvidenceBundle`. Modules here are either:
- Traditional heuristic vision helpers (`ChromaCubePresenceDetector`, `source_type="HEURISTIC_VISION"`), or
- Legacy experiment interfaces (`SceneVLM`, `HeuristicSceneVLM`, `OpenAICompatibleSceneVLM`).
Neither may be reported or promoted as a `REAL_VLM` call, and precise pose / sticker state
always remains computed by deterministic CV modules elsewhere.
"""

from __future__ import annotations

import base64
import json
import urllib.request
from dataclasses import dataclass
from typing import ClassVar, Protocol

import numpy as np

from .v2_types import SceneSemantics


class SceneVLM(Protocol):
    """LEGACY_EXPERIMENT protocol for early coarse RGB scene detectors."""

    def understand(self, rgb: np.ndarray) -> SceneSemantics: ...


class ChromaCubePresenceDetector:
    """Traditional deterministic chroma-threshold cube presence detector (`HEURISTIC_VISION`).

    NOT a VLM: detects saturated sticker-like pixels via `max(RGB) - min(RGB) > 70`.
    """

    source_type: str = "HEURISTIC_VISION"
    is_real_vlm: bool = False
    architecture_role: str = "ACTIVE_LOW_LEVEL_DEPENDENCY"

    def understand(self, rgb: np.ndarray) -> SceneSemantics:
        values = rgb.astype(np.int16)
        chroma = values.max(axis=2) - values.min(axis=2)
        visible = int(np.count_nonzero(chroma > 70)) > 40
        return SceneSemantics(
            visible,
            0.65 if visible else 0.2,
            "cube-like colored sticker cluster visible (heuristic chroma detector)"
            if visible
            else "no cube-like cluster",
            "heuristic_local",
        )


class HeuristicSceneVLM(ChromaCubePresenceDetector):
    """LEGACY_EXPERIMENT alias for `ChromaCubePresenceDetector` (HEURISTIC_VISION, not a VLM)."""

    architecture_role: str = "LEGACY_EXPERIMENT"


@dataclass(slots=True)
class OpenAICompatibleSceneVLM:
    """LEGACY_EXPERIMENT v2/v5/v6 HTTP adapter for coarse binary visibility checks.

    Not used by LIVE `SimulationSession` mainline (which uses `VLMPerceptionProvider`).
    """

    endpoint: str
    model: str
    api_key: str = ""
    timeout_seconds: float = 30.0
    source_type: ClassVar[str] = "LEGACY_EXPERIMENT_VLM"
    architecture_role: ClassVar[str] = "LEGACY_EXPERIMENT"

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

