"""Launch the CubeRelay FastAPI + WebSocket SimulationSession server."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import uvicorn


def _ensure_websockets_available() -> None:
    try:
        import websockets  # noqa: F401
        return
    except ImportError:
        pass
    fallback = Path("/opt/homebrew/anaconda3/lib/python3.14/site-packages")
    if (fallback / "websockets").exists() and str(fallback) not in sys.path:
        sys.path.append(str(fallback))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="CubeRelay MuJoCo SimulationSession Server")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=440)
    parser.add_argument(
        "--full-26-cubie",
        dest="full_26_cubie",
        action="store_true",
        default=True,
        help="Run the LIVE server with the full 26-cubie physical cube (default).",
    )
    parser.add_argument(
        "--legacy-u-only",
        dest="full_26_cubie",
        action="store_false",
        help="Run with the legacy single-brick U-only scene for M3-D/M4-D compatibility.",
    )
    args = parser.parse_args(argv)

    _ensure_websockets_available()

    from cube_relay.api.main import app, configure_m3d_session
    from cube_relay.mission.models import MissionType
    from cube_relay.mission.session import SimulationSession

    session = SimulationSession(
        seed=args.seed,
        width=args.width,
        height=args.height,
        use_dedicated_thread=True,
        full_26_cubie=args.full_26_cubie,
    )
    if args.full_26_cubie:
        session.select_mission(MissionType.RELAY_SOLVE_CUBE)
    configure_m3d_session(session, default_seed=args.seed, full_26_cubie=args.full_26_cubie)
    try:
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    finally:
        session.close()


if __name__ == "__main__":
    main()
