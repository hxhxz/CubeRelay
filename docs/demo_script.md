# 90-second demo

0–10s: Start `uvicorn cube_relay.api.main:app --app-dir src --reload`, open
`http://127.0.0.1:8000`, and point out the SIM/DRY RUN truthfulness banner.

10–25s: Keep `sim`, use scramble `R U R' F2 D`, press **Start**, and show the 54
facelets, next actor, recommended move and plan version.

25–40s: On the human turn deliberately press a move different from Recommended.
Show `HUMAN_MOVE` followed by `PLAN_REPAIRED` and the incremented version.

40–65s: Alternate Recommended human moves and **Robot turn**. Explain that robot
feedback updates actual state; the solved check never relies on an exhausted plan.

65–75s: Export JSON and point out actual state, move actor and plan version.

75–90s: Start a `dry_run` session, issue one human and robot turn, and show that it
pauses without changing actual state. Mention that real mode is default-denied.

For a fully automatic terminal version run `python scripts/demo_90s.py`.

