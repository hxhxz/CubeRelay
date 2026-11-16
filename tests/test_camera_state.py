from threading import RLock

from cube_relay.mission.session import SimulationSession


def test_camera_preset_updates_cached_snapshot_while_mission_is_running() -> None:
    session = SimulationSession.__new__(SimulationSession)
    session._lock = RLock()
    session._running = True
    session._latest_snapshot = {
        "active_camera": "gripper_closeup",
        "camera_azimuth_deg": 148.0,
        "camera_elevation_deg": -20.0,
        "camera_distance_m": 0.48,
        "main_frame_url": "data:image/jpeg;base64,old-frame",
    }

    snapshot = session.set_camera_preset("overview")

    assert snapshot["active_camera"] == "overview"
    assert snapshot["camera_azimuth_deg"] == 135.0
    assert snapshot["camera_elevation_deg"] == -28.0
    assert snapshot["camera_distance_m"] == 1.15
    assert snapshot["main_frame_url"] == "data:image/jpeg;base64,old-frame"
    assert session.get_snapshot()["active_camera"] == "overview"
