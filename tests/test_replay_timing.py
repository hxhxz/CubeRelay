import json
from types import SimpleNamespace
import numpy as np
import pytest
from cube_relay.embodied.replay_timing import TimedFrames, resample_indices


def test_resampling_uses_sim_clock_not_number_of_capture_calls():
    times = np.arange(1,501)*.002
    indices = resample_indices(times,12)
    assert len(indices) <= 14
    assert len(times)/12 > 40  # Legacy encoding expands one second to 41.7 s.
    assert all(0 <= i < len(times) for i in indices)
    assert indices == sorted(indices)


def test_sim_time_recorder_excludes_same_time_perception_snapshots():
    b = SimpleNamespace(video_timing="sim_time", data=SimpleNamespace(time=3.))
    frames = TimedFrames(b)
    for _ in range(5):
        frames.append(np.zeros((2,2,3),dtype=np.uint8))
    assert not frames
    frames.store(np.zeros((2,2,3),dtype=np.uint8))
    assert frames.timestamps == [3.]
    frames.clear()
    assert frames.timestamps == [] and frames.next_capture == 3.


def test_nonmonotonic_timestamps_rejected():
    with pytest.raises(ValueError):
        resample_indices([2.,1.],12)


def test_recording_modes_leave_actual_dynamics_identical(tmp_path):
    pytest.importorskip("mujoco")
    from cube_relay.embodied.mujoco_v2 import MuJoCoEmbodiedBackend
    records = []
    for mode in ("legacy","sim_time"):
        b = MuJoCoEmbodiedBackend(width=160,height=120,video_timing=mode,
                                  video_path=tmp_path/f"{mode}.mp4")
        try:
            b.reset_random(0,15)
            for _ in range(30):
                b._set_controls({"robot_x_ctrl":.1}, .02)
            b.write_video()
            records.append(json.loads((tmp_path/f"{mode}.timing.json").read_text()))
        finally:
            b.renderer.close()
    old,new = records
    assert old["physics_steps"] == new["physics_steps"] == 300
    assert old["physics_digest"] == new["physics_digest"]
    assert len(old["video_frames"]) == 300
    assert len(new["video_frames"]) < 10
    assert max(abs(f["sim_time"]-new["source_sim_times"][0]-f["video_seconds"])
               for f in new["video_frames"]) <= .00201
