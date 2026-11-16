import pytest

from cube_relay.adapters.real_robot import DisabledRealRobotAdapter, RealRobotUnavailableError


@pytest.mark.parametrize("kwargs", [
    {},
    {"driver_configured": True},
    {"driver_configured": True, "human_enabled": True,
     "emergency_stop_ready": True, "workspace_clear": False},
])
def test_real_mode_cannot_initialize_without_all_safety_conditions(kwargs) -> None:
    with pytest.raises(RealRobotUnavailableError):
        DisabledRealRobotAdapter(**kwargs)

