"""Manual observation validation and confirmation workflow."""

from cube_relay.cube.validation import StateValidator, ValidationReport
from cube_relay.models import CubeObservation


class ManualObservationAdapter:
    def __init__(self, validator: StateValidator | None = None, min_confidence: float = 0.8) -> None:
        self.validator = validator or StateValidator()
        self.min_confidence = min_confidence

    def validate(self, observation: CubeObservation) -> ValidationReport:
        if observation.source not in ("manual", "camera"):
            return ValidationReport(False, observation.facelets, False,
                                    "manual adapter accepts manual/camera observations only")
        if observation.confidence < self.min_confidence:
            return ValidationReport(False, observation.facelets, False, "LOW_CONFIDENCE")
        if not observation.confirmed:
            return ValidationReport(False, observation.facelets, False, "MANUAL_CONFIRMATION_REQUIRED")
        return self.validator.validate(observation.facelets, check_solvable=True)

