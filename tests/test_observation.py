import numpy as np

from cube_relay.embodied.observation import CameraFrame, VisionObservationAdapter


def test_camera_without_estimator_never_claims_facelets() -> None:
    frame = CameraFrame(np.zeros((8, 8, 3), dtype=np.uint8), "test", 0.0)
    observation = VisionObservationAdapter().observe(frame)
    assert observation.facelets is None
    assert observation.confidence == 0
    assert "no visual" in observation.error

