"""One-step visual/hinge experiment, not a contact-driven cubie simulation.

No simulator truth is accepted by planning or comparison. Post-turn evidence
must be fresh: never carry the pre-turn fusion into the new epoch.
"""
from dataclasses import asdict

from cube_relay.cube import CubeEngine, CubeSolver, SOLVED_FACELETS, validate_facelets
from .perception_v2 import StickerStateFusion


def plan_visual_state(facelets: str) -> dict:
    # v8 canonical row-major faces already use Kociemba's URFDLB convention.
    # Do NOT sort colors, transpose faces or apply a world-frame rotation.
    validate_facelets(facelets)
    moves = CubeSolver().solve(facelets)
    engine = CubeEngine()
    final = engine.apply_moves(facelets, moves)
    if final != SOLVED_FACELETS:
        raise ValueError("SYMBOLIC_SOLUTION_INVALID")
    return {"input_source": "v8_camera_fusion", "face_order": "URFDLB",
            "input_state": facelets, "solution": moves,
            "symbolic_final": final, "solution_verified": True,
            "predicted_next": engine.apply_move(facelets, moves[0]) if moves else facelets}


def compare_observations(predicted: str, observations: list) -> dict:
    fusion = StickerStateFusion()
    for observation in observations:
        fusion.add(observation)
    evidence = fusion.fused_evidence()
    differences = []
    for item in fusion.evidence:
        index = "URFDLB".index(item.face) * 9 + item.index
        if item.color is not None and item.color != predicted[index]:
            differences.append({"index": index, "facelet": f"{item.face}{item.index}",
                                "predicted": predicted[index], "observed": item.color,
                                "source_view": item.source_view})
    status = ("UNVERIFIED_CONFLICT" if fusion.conflict_count else
              "VISUAL_MISMATCH" if differences else
              "UNVERIFIED_INSUFFICIENT_EVIDENCE" if fusion.unknown_count else
              "VISUALLY_VERIFIED")
    legal = False
    if fusion.unknown_count == 0 and fusion.conflict_count == 0:
        try:
            validate_facelets(fusion.facelets())
            legal = True
        except ValueError:
            if status == "VISUALLY_VERIFIED":
                status = "OBSERVED_STATE_ILLEGAL"
    return {"status": status, "unknown": fusion.unknown_count,
            "observed_legal": legal,
            "conflicts": list(fusion.conflicting_indices), "differences": differences,
            "observed_state": "".join(item.color or "?" for item in evidence),
            "evidence": [asdict(item) for item in fusion.evidence]}
