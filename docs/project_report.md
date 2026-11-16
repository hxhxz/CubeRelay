# CubeRelay four-week MVP report

## Architecture

The cube engine and solver remain deterministic and Web-independent. The turn
coordinator owns authoritative actual state and plan version. Robot and observation
adapters provide replaceable boundaries. FastAPI exposes the coordinator; the Web UI
is a zero-build client. Telemetry and benchmark code consume structured events.

## Failure handling

Handled failures include malformed/impossible states, low-confidence observations,
missing confirmation, stale plans, no-op/wrong robot moves, dry-run non-execution,
and disabled real hardware. Recoverable valid states are replanned; unconfirmed or
invalid observations pause the session.

## Research limits and next questions

Replanning is a deterministic baseline, not scientific novelty. The next useful work
is calibrated multi-view perception, capability-aware human/robot task allocation,
contact-rich manipulation, failure attribution, and hardware-grounded sim-to-real
evaluation.

## Hardware status

No robot or calibrated camera was supplied. Consequently there is no real-robot
success claim or hardware video. The interface and safety migration checklist are
delivered as the no-hardware Week 4 path.

