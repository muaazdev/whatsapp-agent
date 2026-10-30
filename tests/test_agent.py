"""
End-to-end test with no network: a fake Meta Agent Platform + fake AI brains.
Run:  python tests/test_agent.py
"""
import importlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class Resp:
    def __init__(self, code=200, body=None, content=b""):
        self.status_code, self._body = code, body
        self.content = content or (json.dumps(body).encode() if body is not None else b"")
        self.text = self.content.decode(errors="ignore")

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(response=self)


def update(*messages, offset):
    return {"object": "whatsapp_agent_platform",
            "entry": [{"id": "1", "changes": [{"field": "messages", "value": {
                "messaging_product": "whatsapp",
                "contacts": [{"wa_id": "user:5", "profile": {"name": "Sara"}}],
                "messages": list(messages), "statuses": []}}]}],
            "next_offset": offset}


def text(mid, body):
    return {"from": "user:5", "id": mid, "timestamp": "1761800000", "type": "text", "text": {"body": body}}


def run(provider):
    tmp = Path(tempfile.mkdtemp())
    for f in ("agent.py", "prompt.md"):
        shutil.copy(ROOT / f, tmp / f)
    os.environ.update({"WHATSAPP_AGENT_KEY": "test", "AI_PROVIDER": provider,
                       "GEMINI_API_KEY": "g", "ANTHROPIC_API_KEY": "a", "OPENAI_API_KEY": "o",
                       "UTC_OFFSET_HOURS": "3"})
    sys.path.insert(0, str(tmp))
    sys.modules.pop("agent", None)
    agent = importlib.import_module("agent")
    sys.path.pop(0)

    polls = [
        Resp(200, update(text("wamid.1", "remind me to call mom at 18:00"), offset=2)),
        Resp(204),
        Resp(200, update({"from": "user:5", "id": "wamid.2", "timestamp": "1761800001", "type": "image",
                          "image": {"id": "m1", "mime_type": "image/jpeg", "caption": "what is this bill?"}},
                         offset=3)),
        Resp(200, update(text("wamid.3", "/reset"), offset=4)),
        KeyboardInterrupt(),
    ]
    wa_log, ai_log = [], []

    def wa_request(method, url, **kw):
        wa_log.append((method, url.split("/agent/v1")[-1], kw.get("json"), kw.get("params")))
        if url.endswith("/updates"):
            nxt = polls.pop(0)
            if isinstance(nxt, BaseException):
                raise nxt
            return nxt
        if "/media/" in url:
            return Resp(200, {"url": "https://lookaside.fbsbx.com/agent/v1/media/m1/content",
                              "mime_type": "image/jpeg"})
        if url.endswith("/messages"):
            return Resp(200, {"messages": [{"id": "wamid.OUT"}]})
        return Resp(200, {"success": True})

    def wa_get(url, **kw):
        wa_log.append(("GET", url, None, None))
        return Resp(200, content=b"\xff\xd8fakejpeg")

    def ai_post(url, headers=None, json=None, timeout=None):
        ai_log.append((url, json))
        if len(ai_log) == 1:  # first AI call is the reminder request
            reply = "Sure, I'll remind you at 6 pm.\nREMIND: 2000-01-01 18:00 | Call mom"
        else:
            reply = "That's your *electricity bill*: 245 SAR, due Nov 5."
        body = {"gemini": {"candidates": [{"content": {"parts": [{"text": reply}]}}]},
                "claude": {"content": [{"type": "text", "text": reply}]},
                "openai": {"choices": [{"message": {"content": reply}}]}}[provider]
        return Resp(200, body)

    with mock.patch.object(agent.wa, "request", side_effect=wa_request), \
         mock.patch.object(agent.wa, "get", side_effect=wa_get), \
         mock.patch.object(agent.requests, "post", side_effect=ai_post):
        agent.main()

    sends = [j for m, p, j, _ in wa_log if p == "/messages"]
    statuses = [j for m, p, j, _ in wa_log if p == "/statuses"]
    bodies = [s["text"]["body"] for s in sends]

    # first poll has no offset (skip old backlog), later polls carry next_offset
    poll_params = [q for m, p, j, q in wa_log if p == "/updates"]
    assert "offset" not in poll_params[0], poll_params[0]
    assert poll_params[1]["offset"] == 2 and poll_params[2]["offset"] == 2 and poll_params[3]["offset"] == 3

    assert all(s["messaging_product"] == "whatsapp" and s["to"] == "user:5" for s in sends)
    assert statuses[0] == {"messaging_product": "whatsapp", "status": "read", "message_id": "wamid.1",
                           "typing_indicator": {"type": "text"}}
    assert bodies[0] == "Sure, I'll remind you at 6 pm.", bodies[0]          # REMIND line hidden
    assert sends[0]["context"] == {"message_id": "wamid.1"}                   # quotes the user
    assert any(b.startswith("⏰ *Reminder:* Call mom") for b in bodies), bodies  # past-due reminder fired
    assert any("electricity bill" in b for b in bodies)
    assert any("Fresh start" in b for b in bodies)
    assert len(ai_log) == 2                                                    # /reset never hits the AI
    image_call = json.dumps(ai_log[1][1])
    import base64
    assert base64.b64encode(b"\xff\xd8fakejpeg").decode() in image_call   # the photo reached the AI
    state = json.loads((tmp / "data" / "state.json").read_text())
    assert state == {"offset": 4, "me": "user:5"}, state
    assert json.loads((tmp / "data" / "history.json").read_text()) == []      # cleared by /reset
    print(f"  {provider}: OK ({len(sends)} sends, {len(statuses)} read receipts)")


if __name__ == "__main__":
    for p in ("gemini", "claude", "openai"):
        run(p)
    print("All good.")
