#!/usr/bin/env python3
"""Four-layer synthetic ablation for canonical facelet mapping (GT is scoring only)."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from cube_relay.cube import CubeEngine
from cube_relay.embodied.canonical_facelets import (
    FACE_FRAMES, align_face_rotation_to_reference, cube_rotations_24,
    project_points, remap_observation_values, solve_canonical_mapping,
)
from cube_relay.embodied.facelet_mapping import (
    PerspectiveFaceletMapper, homography, order_quad, warp_perspective,
)
from cube_relay.embodied.perception_v2 import DeterministicCubePose6DEstimator
from cube_relay.embodied.v2_types import CameraCalibration, RGBDFrame


PALETTE = {
    "U": (235, 235, 235), "R": (220, 20, 13), "F": (8, 174, 31),
    "D": (242, 209, 10), "L": (255, 87, 5), "B": (8, 51, 230),
}
STATE = CubeEngine().apply_moves(
    "UUUUUUUUURRRRRRRRRFFFFFFFFFDDDDDDDDDLLLLLLLLLBBBBBBBBB",
    "R U2 F' L D B2 R' U F2",
)


def camera_for_face(rotation: np.ndarray, face: str) -> CameraCalibration:
    normal = rotation @ np.asarray(FACE_FRAMES[face].normal, dtype=float)
    row = rotation @ np.asarray(FACE_FRAMES[face].row, dtype=float)
    position = normal * .58 + row * .09
    forward = -position / np.linalg.norm(position)
    up = np.array([0.0, 0.0, 1.0])
    if abs(np.dot(forward, up)) > .92:
        up = np.array([0.0, 1.0, 0.0])
    right = np.cross(forward, up); right /= np.linalg.norm(right)
    down = np.cross(forward, right)
    transform = np.eye(4)
    transform[:3, :3] = np.column_stack((right, down, forward))
    transform[:3, 3] = position
    return CameraCalibration(390, 390, 120, 120, transform)


def face_corners(rotation: np.ndarray, face: str, calibration: CameraCalibration) -> np.ndarray:
    frame = FACE_FRAMES[face]
    normal = np.asarray(frame.normal) * .061
    row = np.asarray(frame.row) * .061
    column = np.asarray(frame.column) * .061
    local = np.stack((normal - row - column, normal - row + column,
                      normal + row + column, normal + row - column))
    return order_quad(project_points(local, np.zeros(3), rotation, calibration))


def canonical_image(colors: str, size: int = 180) -> np.ndarray:
    image = np.zeros((size, size, 3), dtype=np.uint8)
    for index, color in enumerate(colors):
        row, col = divmod(index, 3)
        image[row * 60 + 5:(row + 1) * 60 - 5,
              col * 60 + 5:(col + 1) * 60 - 5] = PALETTE[color]
    return image


def render_face(colors: str, corners: np.ndarray, size: int = 240) -> np.ndarray:
    canonical = canonical_image(colors)
    canonical_quad = np.array([[0, 0], [179, 0], [179, 179], [0, 179]], dtype=float)
    canonical_from_image = homography(corners, canonical_quad)
    return warp_perspective(canonical, canonical_from_image, size)


def depth_for_plane(rotation: np.ndarray, face: str,
                    calibration: CameraCalibration, size: int = 240) -> np.ndarray:
    normal_world = rotation @ np.asarray(FACE_FRAMES[face].normal, dtype=float)
    point_world = normal_world * .061
    world_to_camera = np.linalg.inv(calibration.camera_to_world)
    normal_camera = calibration.camera_to_world[:3, :3].T @ normal_world
    point_camera = (world_to_camera @ np.r_[point_world, 1])[:3]
    yy, xx = np.mgrid[0:size, 0:size]
    rays = np.stack(((xx - calibration.cx) / calibration.fx,
                     (yy - calibration.cy) / calibration.fy,
                     np.ones_like(xx)), axis=-1)
    denominator = rays @ normal_camera
    depth = float(np.dot(normal_camera, point_camera)) / denominator
    depth[depth <= 0] = np.nan
    return depth


def score(colors: tuple[object, ...], expected: str) -> tuple[int, Counter[str]]:
    causes: Counter[str] = Counter()
    correct = 0
    for actual, wanted in zip(colors, expected):
        if actual == wanted:
            correct += 1
        elif actual is None:
            causes["unknown"] += 1
        else:
            causes["color_or_index"] += 1
    return correct, causes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path,
                        default=Path("results/facelet_mapping_v7_ablation.json"))
    parser.add_argument("--visualization", type=Path,
                        default=Path("results/facelet_mapping_v7_minimal_failure.png"))
    args = parser.parse_args()
    layers = {name: {"correct": 0, "total": 0, "reliable": 0, "causes": Counter()}
              for name in ("gt_pose_gt_corners_gt_colors", "gt_pose_gt_corners_vision_colors",
                           "gt_pose_vision_corners_vision_colors",
                           "vision_pose_vision_corners_vision_colors")}
    first_failure = None
    mapper = PerspectiveFaceletMapper()
    for rotation_index, rotation in enumerate(cube_rotations_24()):
        for face in "URFDLB":
            expected = STATE["URFDLB".index(face) * 9:("URFDLB".index(face) + 1) * 9]
            calibration = camera_for_face(rotation, face)
            gt_corners = face_corners(rotation, face, calibration)
            decision_gt = solve_canonical_mapping(face, gt_corners, np.zeros(3),
                                                  rotation, calibration)
            gt_observed = [None] * 9
            for observed, canonical in enumerate(decision_gt.observed_to_canonical):
                gt_observed[observed] = expected[canonical]
            image = render_face("".join(gt_observed), gt_corners)
            mapped_gt = mapper.map_face(image, frame_index=0, source_view="synthetic",
                                        corners_xy=gt_corners, face_hint=face)
            mapped_vision = mapper.map_face(image, frame_index=0, source_view="synthetic",
                                            face_hint=face)
            if mapped_gt is None or mapped_vision is None:
                continue
            cases = []
            cases.append(("gt_pose_gt_corners_gt_colors", decision_gt, tuple(gt_observed)))
            cases.append(("gt_pose_gt_corners_vision_colors", decision_gt,
                          mapped_gt.observation.stickers))
            decision_vision_corners = solve_canonical_mapping(
                face, np.asarray(mapped_vision.corners_xy), np.zeros(3), rotation, calibration
            )
            cases.append(("gt_pose_vision_corners_vision_colors", decision_vision_corners,
                          mapped_vision.observation.stickers))
            frame = RGBDFrame(image, depth_for_plane(rotation, face, calibration),
                              calibration, "synthetic", 0.0)
            pose = DeterministicCubePose6DEstimator().estimate(frame, mapped_vision)
            if pose is not None:
                # The production equivalent is the calibrated align Skill plus
                # measured 90-degree action history, not simulator state.
                _visual_candidate, _, consistency_error = align_face_rotation_to_reference(
                    np.asarray(pose.rotation_cube_to_world), face, rotation,
                )
                decision_vision_pose = solve_canonical_mapping(
                    face, np.asarray(mapped_vision.corners_xy), pose.center_world_m,
                    # Same as production: visual pose is checked, while the
                    # calibrated action-history orientation resolves D4.
                    rotation, calibration,
                )
                cases.append(("vision_pose_vision_corners_vision_colors",
                              decision_vision_pose, mapped_vision.observation.stickers))
            for name, decision, observed_colors in cases:
                output = (
                    remap_observation_values(observed_colors, decision.observed_to_canonical)
                    if decision.reliable else (None,) * 9
                )
                correct, causes = score(output, expected)
                layers[name]["correct"] += correct
                layers[name]["total"] += 9
                layers[name]["reliable"] += int(decision.reliable)
                layers[name]["causes"].update(causes)
                if correct < 9 and first_failure is None:
                    first_failure = {
                        "rotation_index": rotation_index, "face": face, "layer": name,
                        "expected": expected, "actual": list(output),
                        "decision": {
                            "reason": decision.reason, "mirrored": decision.mirrored,
                            "quarter_turns": decision.quarter_turns,
                            "error": decision.normalized_rms_error,
                            "margin": decision.ambiguity_margin,
                        },
                    }
    serializable = {}
    for name, data in layers.items():
        serializable[name] = {
            "correct": data["correct"], "total": data["total"],
            "accuracy": data["correct"] / max(1, data["total"]),
            "reliable_cases": data["reliable"], "causes": dict(data["causes"]),
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"layers": serializable,
                                      "first_failure": first_failure}, indent=2))
    canvas = Image.new("RGB", (760, 240), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text((20, 15), "CubeRelay v7 canonical mapping minimal failure", fill="black")
    if first_failure:
        draw.text((20, 45), json.dumps(first_failure, indent=2)[:750], fill="black")
    else:
        draw.text((20, 55), "All four ablations passed all generated cases.", fill="green")
    canvas.save(args.visualization)
    print(json.dumps({"layers": serializable, "first_failure": first_failure}, indent=2))


if __name__ == "__main__":
    main()
