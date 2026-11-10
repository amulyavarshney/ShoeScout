import json
import uuid

import pytest
from starlette.testclient import TestClient


@pytest.fixture
def ws_client(seeded):
    from app.main import app
    with TestClient(app) as c:
        yield c


def _session(c: TestClient) -> str:
    return c.post("/api/v1/sessions", json={}).json()["session_id"]


def _drain_until(ws, wanted: set[str], limit: int = 40) -> list[dict]:
    events = []
    for _ in range(limit):
        msg = ws.receive()
        if "text" in msg and msg["text"]:
            ev = json.loads(msg["text"])
            events.append(ev)
            if ev.get("type") in wanted:
                break
    return events


def test_ws_rejects_unknown_session_with_app_close_code(ws_client):
    from starlette.websockets import WebSocketDisconnect
    with ws_client.websocket_connect("/ws/voice?session_id=nope") as ws:
        ev = json.loads(ws.receive_text())
        assert ev["type"] == "error" and ev["code"] == "SESSION_NOT_FOUND"
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_text()
        assert exc.value.code == 4401


def test_ws_text_turn_streams_results_once(ws_client):
    sid = _session(ws_client)
    with ws_client.websocket_connect(f"/ws/voice?session_id={sid}") as ws:
        ws.send_text(json.dumps({"type": "session.start", "session_id": sid, "audio_format": "pcm_s16le", "sample_rate": 16000}))
        ready = json.loads(ws.receive_text())
        assert ready["type"] == "session.ready" and ready["mode"] == "mock" and ready["server_stt"] is False
        turn = str(uuid.uuid4())
        ws.send_text(json.dumps({"type": "text.turn", "turn_id": turn, "text": "red Nike shoes", "speak": True}))
        events = _drain_until(ws, {"turn.complete"})
        types = [e["type"] for e in events]
        assert types.count("search.results") == 1 and types.count("agent.message") == 1 and types[-1] == "turn.complete"
        assert all(e.get("turn_id") == turn for e in events if "turn_id" in e)
        assert "tts.unavailable" in types  # mock TTS: browser speaks
        results = next(e for e in events if e["type"] == "search.results")
        assert 3 <= len(results["products"]) <= 5
        # Duplicate turn id is ignored (no second answer).
        ws.send_text(json.dumps({"type": "text.turn", "turn_id": turn, "text": "red Nike shoes"}))
        ws.send_text(json.dumps({"type": "ping"}))
        events = _drain_until(ws, {"pong"})
        assert all(e["type"] != "agent.message" for e in events)


def test_ws_audio_without_server_stt_gives_clear_error(ws_client):
    sid = _session(ws_client)
    with ws_client.websocket_connect(f"/ws/voice?session_id={sid}") as ws:
        ws.send_text(json.dumps({"type": "session.start", "session_id": sid, "audio_format": "pcm_s16le", "sample_rate": 16000}))
        ws.receive_text()
        ws.send_text(json.dumps({"type": "audio.start", "turn_id": "t1"}))
        ws.send_bytes(b"\x00" * 640)
        ev = json.loads(ws.receive_text())
        assert ev["type"] == "error" and ev["code"] == "STT_UNAVAILABLE"
        ws.send_text(json.dumps({"type": "turn.cancel", "turn_id": "t1"}))
        events = _drain_until(ws, {"agent.state"})
        assert events[-1]["state"] == "listening"
