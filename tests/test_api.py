from fastapi.testclient import TestClient

from cube_relay.api.main import app, sessions


client = TestClient(app)


def test_api_session_human_robot_and_events() -> None:
    sessions.clear()
    response = client.post("/session", json={
        "scramble": "R U R' F2 D", "robot_mode": "sim",
        "collaboration_mode": "free_collaboration",
    })
    assert response.status_code == 200
    state = response.json()
    assert state["control_mode"] == "hierarchical"
    assert state["policy_backend"] == "kociemba_baseline"
    assert state["machine_status"] == "idle"
    session_id = state["session_id"]
    response = client.post(f"/session/{session_id}/human-move", json={"move": "F"})
    assert response.status_code == 200
    state = response.json()
    response = client.post(f"/session/{session_id}/robot-turn",
                           json={"plan_version": state["plan_version"]})
    assert response.status_code == 200
    events = client.get(f"/session/{session_id}/events").json()
    assert any(event["kind"] == "PLAN_REPAIRED" for event in events)
    assert any(event["kind"] == "ROBOT_MOVE" for event in events)


def test_real_mode_is_default_denied() -> None:
    response = client.post("/session", json={"scramble": "R", "robot_mode": "real"})
    assert response.status_code == 503
    assert "real mode disabled" in response.text


def test_web_index_is_served() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "CubeRelay" in response.text
    assert "顺时针一格" in response.text
    assert "重放上一步机器动作" in response.text
    assert 'href="./style.css"' in response.text
    assert client.get("/style.css").headers["content-type"].startswith("text/css")
    assert client.get("/app.js").status_code == 200
    script = client.get("/app.js").text
    assert 'function selectFace(face)' in script
    assert 'updateSteps();updateControls()' in script
    assert 'playMoveAnimation(lastRobotMove,1200)' in script
    assert client.get("/health").json() == {"status": "ok", "service": "cube-relay"}


def test_uninstalled_vla_backend_is_explicitly_rejected() -> None:
    response = client.post("/session", json={
        "scramble": "R", "robot_mode": "sim", "control_mode": "vla_discrete",
        "policy_backend": "future-vla",
    })
    assert response.status_code == 503
    assert "not installed" in response.text


def test_static_preview_can_call_backend_through_cors() -> None:
    response = client.options("/session", headers={
        "Origin": "null",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"


def test_guided_undo_conflict_requires_api_confirmation() -> None:
    sessions.clear()
    response = client.post("/session", json={
        "facelets": "UDDDUUDUUBLLLRRRFFRRRBFFBBFUUDDDUDDURLBRLLFFLBBFBBFLRL",
        "robot_mode": "sim", "collaboration_mode": "guided_shared_plan",
    })
    state = response.json()
    session_id = state["session_id"]
    state = client.post(f"/session/{session_id}/human-move", json={"move": "U'"}).json()
    state = client.post(f"/session/{session_id}/robot-turn",
                        json={"plan_version": state["plan_version"]}).json()
    assert state["confirmation_required"]
    assert state["confirmation_reason"] == "UNDO_CONFLICT"
    assert state["pending_robot_move"] == "U"
    state = client.post(f"/session/{session_id}/confirm",
                        json={"decision": "keep_human_move"}).json()
    assert not state["confirmation_required"]
    assert state["planned_moves"][0] != "U"
