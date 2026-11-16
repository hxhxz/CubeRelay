"""Independent cube validation contract and Kociemba solvability checker."""

from collections import Counter
from dataclasses import dataclass
from typing import Protocol

from .state import FACE_ORDER


class InvalidCubeState(ValueError):
    """Raised when facelets do not describe a physically solvable 3x3 cube."""


class SolvabilityChecker(Protocol):
    def check(self, facelets: str) -> None: ...


class KociembaSolvabilityChecker:
    """Physical cubie parity/orientation check, separate from CubeSolver planning."""

    def check(self, facelets: str) -> None:
        try:
            import kociemba
            kociemba.solve(facelets)
        except (ValueError, RuntimeError) as exc:
            raise InvalidCubeState(f"cube is not physically solvable: {exc}") from exc


@dataclass(frozen=True, slots=True)
class ValidationReport:
    valid: bool
    facelets: str
    physical_solvability_checked: bool
    error: str | None = None


class StateValidator:
    """Standalone validator; it neither plans nor mutates cube states."""

    def __init__(self, checker: SolvabilityChecker | None = None) -> None:
        self.checker = checker or KociembaSolvabilityChecker()

    def validate(self, facelets: str, *, check_solvable: bool = True) -> ValidationReport:
        try:
            self._validate_format(facelets)
            if check_solvable:
                self.checker.check(facelets)
            return ValidationReport(True, facelets, check_solvable)
        except InvalidCubeState as exc:
            return ValidationReport(False, facelets, check_solvable, str(exc))

    def require_valid(self, facelets: str, *, check_solvable: bool = True) -> str:
        report = self.validate(facelets, check_solvable=check_solvable)
        if not report.valid:
            raise InvalidCubeState(report.error or "invalid cube state")
        return facelets

    @staticmethod
    def _validate_format(facelets: str) -> None:
        if not isinstance(facelets, str):
            raise InvalidCubeState("facelets must be a string")
        if len(facelets) != 54:
            raise InvalidCubeState(f"facelets must contain 54 characters, got {len(facelets)}")
        invalid = set(facelets) - set(FACE_ORDER)
        if invalid:
            raise InvalidCubeState(f"unknown facelet symbols: {''.join(sorted(invalid))}")
        counts = Counter(facelets)
        wrong = {face: counts[face] for face in FACE_ORDER if counts[face] != 9}
        if wrong:
            raise InvalidCubeState(f"each face symbol must occur 9 times: {wrong}")
        centers = "".join(facelets[index * 9 + 4] for index in range(6))
        if centers != FACE_ORDER:
            raise InvalidCubeState(f"centers must be {FACE_ORDER}, got {centers}")


DEFAULT_VALIDATOR = StateValidator()


def validate_facelets(facelets: str, *, check_solvable: bool = True) -> str:
    """Backward-compatible entry point backed by the independent validator."""
    return DEFAULT_VALIDATOR.require_valid(facelets, check_solvable=check_solvable)
