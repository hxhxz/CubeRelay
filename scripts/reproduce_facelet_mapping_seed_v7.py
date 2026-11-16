#!/usr/bin/env python3
"""Minimal one-seed continuous-observation reproduction with per-view attribution."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from cube_relay.embodied.active_inspection_v7 import ContinuousActiveInspector
from cube_relay.embodied.mujoco_v2 import MuJoCoEmbodiedBackend


def _json_default(value: object) -> object:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", type=Path,
                        default=Path("results/facelet_mapping_v7_seed0_trace.json"))
    parser.add_argument("--replay", type=Path,
                        default=Path("results/replays/facelet_mapping_v7_seed0.mp4"))
    args = parser.parse_args()
    backend = MuJoCoEmbodiedBackend(width=320, height=240, video_path=args.replay)
    metadata = backend.reset_random(args.seed, 15)
    truth = str(metadata["truth_for_evaluation_only"])
    result = ContinuousActiveInspector(backend, "sequential").run(
        args.seed, reset_scene=False, max_cycles=6
    )
    mapping_by_source = {
        (item["frame_index"], item["source_view"]): item
        for item in backend.facelet_mapping_diagnostics
    }
    steps = []
    cumulative_correct: set[int] = set()
    for event in result.events:
        raw = asdict(event)
        visual = raw["detail"].pop("visual_evidence", [])
        grouped: dict[tuple[str, str], list[dict[str, object]]] = {}
        for item in visual:
            grouped.setdefault((item["source_view"], item["face"]), []).append(item)
        views = []
        for (source, face), items in grouped.items():
            correct = 0
            errors = []
            canonical_indices = []
            for item in items:
                if item["color"] is None:
                    continue
                canonical_indices.append(item["index"])
                global_index = "URFDLB".index(face) * 9 + item["index"]
                expected = truth[global_index]
                if item["color"] == expected:
                    correct += 1
                    cumulative_correct.add(global_index)
                else:
                    errors.append({
                        "canonical_index": f"{face}{item['index']}",
                        "actual": item["color"], "expected": expected,
                        "attribution": "color_or_index_disambiguated_by_mapping_diagnostic",
                    })
            diagnostics = [value for (frame, view), value in mapping_by_source.items()
                           if view in source or source in view]
            if errors and diagnostics:
                reason = diagnostics[-1].get("reason")
                attribution = "pose_or_face_identity" if reason else "vision_color"
                for error in errors:
                    error["attribution"] = attribution
            views.append({
                "source_view": source, "visible_face_id": face,
                "canonical_indices": sorted(canonical_indices),
                "correct_patch_count": correct,
                "errors": errors, "mapping_diagnostics": diagnostics[-1:] or None,
            })
        raw.update({
            "views": views,
            "cumulative_correct_unique": len(cumulative_correct),
        })
        steps.append(raw)
    report = {
        "seed": args.seed, "success": result.success,
        "first_failure_stage": result.first_failure_stage,
        "steps": steps, "final_unknown": result.events[-1].unknown if result.events else 54,
        "final_conflicts": result.events[-1].conflicts if result.events else 0,
        "final_correct_unique": len(cumulative_correct),
        "mapping_diagnostics": backend.facelet_mapping_diagnostics,
        "truth_usage": "evaluation_and_attribution_only",
        "replay": str(args.replay),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, default=_json_default), encoding="utf-8")
    visualization = args.output.with_suffix(".png")
    canvas = Image.new("RGB", (1100, 120 + 62 * len(steps)), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text((20, 15), f"CubeRelay v7 facelet mapping seed={args.seed}", fill="black")
    draw.text((20, 40), "green=correct unique  gray=unknown  red=conflicts", fill="black")
    for row, step in enumerate(steps):
        y = 78 + row * 62
        correct = step["cumulative_correct_unique"]
        unknown = step["unknown"]
        conflicts = step["conflicts"]
        draw.text((20, y), f"{step['step']:02d} {step['skill']}", fill="black")
        x = 270
        draw.rectangle((x, y, x + correct * 10, y + 16), fill=(35, 160, 75))
        x += correct * 10
        draw.rectangle((x, y, x + unknown * 10, y + 16), fill=(180, 180, 180))
        if conflicts:
            draw.rectangle((270, y + 21, 270 + conflicts * 10, y + 34), fill=(210, 45, 45))
        faces = ", ".join(
            f"{view['visible_face_id']}:{len(view['canonical_indices'])}/9"
            for view in step["views"]
        )
        draw.text((270, y + 38), faces[:115], fill=(60, 60, 60))
    canvas.save(visualization)
    report["visualization"] = str(visualization)
    args.output.write_text(json.dumps(report, indent=2, default=_json_default), encoding="utf-8")
    backend.write_video()
    backend.renderer.close()
    print(json.dumps({key: report[key] for key in (
        "seed", "success", "first_failure_stage", "final_unknown",
        "final_conflicts", "final_correct_unique",
    )}, indent=2))


if __name__ == "__main__":
    main()
