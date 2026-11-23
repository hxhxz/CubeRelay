from __future__ import annotations

import math

import pytest

mujoco = pytest.importorskip("mujoco")

from cube_relay.embodied.mujoco_v2 import MuJoCoEmbodiedBackend  # noqa: E402
from cube_relay.embodied.physical_cube_26 import move_to_top_fixture_angle_rad  # noqa: E402
from cube_relay.execution.action_chunk import (  # noqa: E402
    ActionChunk,
    ActionChunkExecutor,
    CancellationToken,
    ChunkStatus,
    InterruptMode,
)


def test_action_chunk_approach_preempts_under_100ms() -> None:
    backend = MuJoCoEmbodiedBackend(full_26_cubie=True, width=240, height=180)
    backend.reset_random(seed=0, scramble_steps=2)
    exec_inst = backend._action_chunk_executor()

    # Move safely clear above table first
    prep = ActionChunk.linear_ramp(
        chunk_id="prep_z",
        start={"robot_z_ctrl": 0.0},
        goal={"robot_z_ctrl": -0.145},
        steps=220,
        settle_steps=40,
        dt=float(backend.model.opt.timestep),
    )
    assert exec_inst.execute(prep).status == ChunkStatus.COMPLETED

    approach = ActionChunk.trapezoidal_xy(
        chunk_id="approach_xy_010",
        start_xy=(0.0, 0.0),
        goal_xy=(0.14, 0.04),
        dt=float(backend.model.opt.timestep),
        v_max=0.28,
        a_max=1.2,
    )
    token = CancellationToken()

    def monitor(step_idx: int, sim_time_s: float) -> None:
        if step_idx == 140 and not token.is_cancelled():
            token.cancel(
                "DYNAMIC_HUMAN_PROXIMITY",
                mode=InterruptMode.IMMEDIATE_HOLD,
                sim_time_s=sim_time_s,
            )

    res = exec_inst.execute(approach, token=token, async_monitor_fn=monitor)
    assert res.status == ChunkStatus.PREEMPTED_SAFE_HOLD
    assert res.interrupt_to_hold_sim_ms is not None
    assert res.interrupt_to_hold_sim_ms < 100.0
    assert res.final_ee_vel_norm < 0.025
    assert res.cancel_reason == "DYNAMIC_HUMAN_PROXIMITY"
    backend.renderer.close()


def test_action_chunk_held_cube_preemption_preserves_grip_zero_drop() -> None:
    backend = MuJoCoEmbodiedBackend(full_26_cubie=True, width=240, height=180)
    backend.reset_with_perturbation(seed=0, scramble_steps=2, dx_m=0.0, dy_m=0.0)
    ff = backend.flip_controller
    assert ff is not None

    cube_body = backend._id(mujoco.mjtObj.mjOBJ_BODY, "cube")
    cube_xy = (float(backend.data.xpos[cube_body][0]), float(backend.data.xpos[cube_body][1]))

    # Grasp and lift cube off the table
    ok, st, reason = ff._pick_up_cube(cube_xy, 0.0, z_grasp=-0.272, is_station=False)
    assert ok, f"pickup failed: {st} {reason}"
    ok, st, reason = ff._ramp("lift_held", {"robot_z_ctrl": -0.145}, 0.35, settle_s=0.10, hold_grip=True)
    assert ok, f"lift failed: {st} {reason}"
    assert ff.has_bilateral_finger_contact()
    assert float(backend.data.xpos[cube_body][2]) > 0.70

    transport = ActionChunk.trapezoidal_xy(
        chunk_id="held_transport",
        start_xy=cube_xy,
        goal_xy=(cube_xy[0] + 0.16, cube_xy[1] - 0.14),
        dt=float(backend.model.opt.timestep),
        v_max=0.25,
        a_max=1.1,
        hold_grip_on_interrupt=True,
        held_grip_ctrl=0.070,
    )
    token = CancellationToken()

    def monitor(step_idx: int, sim_time_s: float) -> None:
        if step_idx == 120 and not token.is_cancelled():
            token.cancel(
                "HUMAN_HANDOFF_PAUSE",
                mode=InterruptMode.IMMEDIATE_HOLD,
                sim_time_s=sim_time_s,
            )

    exec_inst = backend._action_chunk_executor()
    res = exec_inst.execute(transport, token=token, async_monitor_fn=monitor)
    assert res.status == ChunkStatus.PREEMPTED_SAFE_HOLD
    assert res.interrupt_to_hold_sim_ms is not None and res.interrupt_to_hold_sim_ms < 100.0
    assert res.hold_grip_preserved is True
    assert res.object_drop_detected is False
    assert ff.has_bilateral_finger_contact()
    assert float(backend.data.xpos[cube_body][2]) > 0.70

    # Hold 200 more physics steps after preempt to prove zero-drop suspension stability
    for _ in range(200):
        mujoco.mj_step(backend.model, backend.data)
    assert ff.has_bilateral_finger_contact()
    assert float(backend.data.xpos[cube_body][2]) > 0.70
    backend.renderer.close()


def test_action_chunk_vla_uniform_interface_and_stale_revision_abort() -> None:
    backend = MuJoCoEmbodiedBackend(full_26_cubie=True, width=240, height=180)
    backend.reset_random(seed=0, scramble_steps=2)
    rev_state = {"world": 2, "goal": 1}
    exec_inst = ActionChunkExecutor(
        backend.model,
        backend.data,
        revision_provider_fn=lambda: (rev_state["world"], rev_state["goal"]),
    )

    vla_chunk = ActionChunk.trapezoidal_xy(
        chunk_id="vla_chunk_01",
        start_xy=(0.0, 0.0),
        goal_xy=(0.04, 0.02),
        dt=float(backend.model.opt.timestep),
        extra_ctrls={"robot_z_ctrl": -0.145},
        world_revision=2,
        goal_revision=1,
        pose_estimate_id="pose-vla-1",
    )
    # Create explicit VLA_POLICY tagged variant
    vla_chunk = ActionChunk(
        chunk_id=vla_chunk.chunk_id,
        targets=vla_chunk.targets,
        source_type="VLA_POLICY",
        dt=vla_chunk.dt,
        world_revision=2,
        goal_revision=1,
        pose_estimate_id="pose-vla-1",
    )
    tok_ok = CancellationToken(expected_world_revision=2, expected_goal_revision=1)
    res_ok = exec_inst.execute(vla_chunk, token=tok_ok)
    assert res_ok.source_type == "VLA_POLICY"
    assert res_ok.status == ChunkStatus.COMPLETED

    # Bump world revision mid-chunk -> must SAFETY_ABORT cleanly
    vla_chunk2 = ActionChunk(
        chunk_id="vla_chunk_stale",
        targets=[{"robot_x_ctrl": 0.04 + 0.0005 * i, "robot_y_ctrl": 0.02} for i in range(120)],
        source_type="VLA_POLICY",
        dt=float(backend.model.opt.timestep),
        world_revision=2,
        goal_revision=1,
    )

    def bump_rev(step_idx: int, _sim_t: float) -> None:
        if step_idx == 30:
            rev_state["world"] = 3

    res_abort = exec_inst.execute(
        vla_chunk2,
        token=CancellationToken(expected_world_revision=2, expected_goal_revision=1),
        async_monitor_fn=bump_rev,
    )
    assert res_abort.status == ChunkStatus.SAFETY_ABORTED
    assert res_abort.safety_violation is not None
    assert "world_revision" in res_abort.safety_violation or "WORLD_REVISION" in res_abort.safety_violation
    backend.renderer.close()


def test_action_chunk_preempts_physical_top_fixture_turn_safely() -> None:
    backend = MuJoCoEmbodiedBackend(full_26_cubie=True, width=240, height=180)
    backend.reset_random(seed=1, scramble_steps=2)
    cube_jnt = backend._joint("cube_free")
    qadr = int(backend.model.jnt_qposadr[cube_jnt])
    backend.data.qpos[qadr : qadr + 3] = [0.35, -0.32, 0.660]
    backend.data.qpos[qadr + 3 : qadr + 7] = [1.0, 0.0, 0.0, 0.0]
    mujoco.mj_forward(backend.model, backend.data)

    token = CancellationToken()
    rj = backend._joint("turn_rotor_joint")
    rj_qadr = int(backend.model.jnt_qposadr[rj])

    def _cancel_mid_turn(_step_idx: int = 0) -> None:
        if abs(float(backend.data.qpos[rj_qadr])) > math.radians(20.0) and not token.is_cancelled():
            token.cancel("SAFETY_PAUSE_MID_SLICE", mode=InterruptMode.IMMEDIATE_HOLD, sim_time_s=float(backend.data.time))

    turner = backend.cube_26_turner
    assert turner is not None
    old_post = turner.post_step_fn
    turner.post_step_fn = lambda _step_idx=0: (_cancel_mid_turn(), old_post() if old_post else None)
    res = turner.execute_top_face_turn(
        move_to_top_fixture_angle_rad("U"),
        token=token,
        release_base_after=True,
    )
    assert res.preempted is True
    assert res.chunk_status == ChunkStatus.PREEMPTED_SAFE_HOLD.value
    # Ensure carrier welds were unlocked cleanly back onto cube_core with zero residual carrier active
    active_names = [
        str(mujoco.mj_id2name(backend.model, mujoco.mjtObj.mjOBJ_EQUALITY, int(idx)) or "")
        for idx in range(backend.model.neq)
        if backend.data.eq_active[idx]
    ]
    assert not any(n.startswith("w_car_") for n in active_names)
    backend.renderer.close()


@pytest.mark.parametrize("interrupt", [False, True])
def test_chat_micro_hold_during_motion(interrupt):
    import threading
    import time
    from cube_relay.mission.dual_model import FakeStructuredModelClient
    from cube_relay.mission.relay_cognition import HRIDialogueInterpreter
    from cube_relay.mission.session import SimulationSession

    backend = MuJoCoEmbodiedBackend(full_26_cubie=True, width=240, height=180)
    backend.reset_with_perturbation(seed=0, scramble_steps=2, dx_m=0.0, dy_m=0.0)
    controller = backend.flip_controller
    cube_body = backend._id(mujoco.mjtObj.mjOBJ_BODY, "cube")
    start_xy = tuple(backend.data.xpos[cube_body][:2])
    assert controller._pick_up_cube(start_xy, 0.0, z_grasp=-0.272, is_station=False)[0]
    assert controller._ramp("lift_held", {"robot_z_ctrl": -0.145}, 0.35, settle_s=0.10, hold_grip=True)[0]
    token = CancellationToken()
    stopped = threading.Event()
    injected = threading.Event()
    stamps = {}
    positions = []
    errors = []

    def route(prompt, image):
        stamps["routing"] = time.perf_counter()
        assert token.speculative_pause
        assert stopped.wait(1)
        time.sleep(0.03)
        return dict(speech_act="PAUSE_AND_HANDOVER" if interrupt else "UPDATE_PREFERENCE_ONLY",
                    requires_immediate_motion_interrupt=interrupt, should_wake_robot_from_human_turn=False)

    session = SimulationSession(hri_interpreter=HRIDialogueInterpreter(FakeStructuredModelClient("hri", route)))
    session._active_cancellation_token = token
    session._running = True

    def chat():
        try:
            assert injected.wait(2)
            stamps["arrival"] = time.perf_counter()
            session.human_send_chat("停一下，后面底面 D 全归你拧" if interrupt else "干得漂亮，待会儿底面留给我")
        except BaseException as exc:
            errors.append(exc)

    executor = backend._action_chunk_executor()
    original_step = executor._step_fn

    def step():
        original_step()
        if token.speculative_pause and executor._ee_vel_norm() < 0.001:
            stamps.setdefault("stopped", time.perf_counter())
            assert backend.data.ctrl[executor._actuator_ids["left_finger_ctrl"]] >= 0.070
            assert controller.has_bilateral_finger_contact()
            stopped.set()

    executor._step_fn = step
    chunk = ActionChunk.trapezoidal_xy(chunk_id="chat_hold", start_xy=start_xy,
                                        goal_xy=(start_xy[0] + 0.16, start_xy[1] - 0.14),
                                        dt=float(backend.model.opt.timestep), hold_grip_on_interrupt=True)

    def monitor(idx, sim_time):
        positions.append(idx)
        if idx == 140:
            assert executor._ee_vel_norm() > 0.02
            injected.set()

    thread = threading.Thread(target=chat, daemon=True)
    thread.start()
    try:
        result = executor.execute(chunk, token=token, async_monitor_fn=monitor)
        thread.join(2)
        assert not thread.is_alive() and not errors, errors
        print(f"interrupt={interrupt} route={(stamps['routing'] - stamps['arrival']) * 1000:.3f}ms "
              f"hold={(stamps['stopped'] - stamps['arrival']) * 1000:.3f}ms")
        assert stamps["routing"] - stamps["arrival"] < 0.010
        assert stamps["stopped"] - stamps["arrival"] < 0.020
        assert result.status == (ChunkStatus.PREEMPTED_SAFE_HOLD if interrupt else ChunkStatus.COMPLETED)
        assert controller.has_bilateral_finger_contact()
        if not interrupt:
            assert positions == list(range(len(chunk.targets)))
    finally:
        backend.renderer.close()
