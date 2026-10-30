"""
Your own AI assistant inside WhatsApp.

Uses Meta's WhatsApp Agent Platform (https://api.whatsapp.com/agent/v1)
and one AI brain of your choice: Claude, OpenAI, or Google Gemini (free tier).

You only edit two files:
  prompt.md  -> who your assistant is and how it talks
  .env       -> your keys

Then run:  python agent.py
"""

import base64
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
DATA.mkdir(exist_ok=True)


# ---------------------------------------------------------------- settings --

def load_env(path=HERE / ".env"):
    """Tiny .env reader, so there is nothing extra to install."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env()

WHATSAPP_KEY = os.getenv("WHATSAPP_AGENT_KEY", "")
BRAIN = os.getenv("AI_PROVIDER", "gemini").lower()          # gemini | claude | openai
MODELS = {
    "gemini": os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
    "claude": os.getenv("CLAUDE_MODEL", "claude-haiku-5-5"),
    "openai": os.getenv("OPENAI_MODEL", "gpt-6-luna"),
}
KEYS = {
    "gemini": os.getenv("GEMINI_API_KEY", ""),
    "claude": os.getenv("ANTHROPIC_API_KEY", ""),
    "openai": os.getenv("OPENAI_API_KEY", ""),
}
TZ_OFFSET = float(os.getenv("UTC_OFFSET_HOURS", "0"))         # e.g. 3 for Riyadh, 5 for Karachi
HISTORY_TURNS = int(os.getenv("HISTORY_TURNS", "20"))
WA = os.getenv("WHATSAPP_BASE_URL", "https://api.whatsapp.com/agent/v1")


def now_local():
    return datetime.utcnow() + timedelta(hours=TZ_OFFSET)


# ------------------------------------------------------------ small storage --

def load(name, default):
    f = DATA / name
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return default


def save(name, value):
    (DATA / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


state = load("state.json", {"offset": None, "me": None})
history = load("history.json", [])
reminders = load("reminders.json", [])


# --------------------------------------------------------------- WhatsApp --

wa = requests.Session()
wa.headers["Authorization"] = f"Bearer {WHATSAPP_KEY}"
_sent = []  # timestamps of recent sends (Meta allows 12 a minute)


def wa_call(method, path, **kw):
    r = wa.request(method, WA + path, timeout=kw.pop("timeout", 30), **kw)
    if r.status_code == 401:
        sys.exit("WhatsApp said your agent key is wrong. Copy it again from the agent's chat (View API key).")
    if r.status_code == 409:
        sys.exit("Another copy of this agent is already running with the same key. Close it and try again.")
    return r


def get_updates():
    params = {"timeout": 25, "limit": 50}
    if state["offset"] is not None:
        params["offset"] = state["offset"]
    r = wa_call("GET", "/updates", params=params, timeout=60)
    if r.status_code == 204:          # nothing new in 25 seconds
        return None
    if r.status_code == 429:          # polled too fast
        time.sleep(10)
        return None
    r.raise_for_status()
    return r.json()


def mark_read(message_id, typing=True):
    body = {"messaging_product": "whatsapp", "status": "read", "message_id": message_id}
    if typing:
        body["typing_indicator"] = {"type": "text"}
    try:
        wa_call("POST", "/statuses", json=body)
    except requests.RequestException:
        pass  # a missed blue tick is not worth crashing over


def send_text(text, reply_to=None):
    if not state.get("me"):
        print("  (can't send yet: message your agent once so it learns who you are)")
        return
    for chunk in split(text, 4000):
        while len([t for t in _sent if time.time() - t < 60]) >= 12:
            time.sleep(2)
        body = {"messaging_product": "whatsapp", "to": state["me"], "type": "text",
                "text": {"body": chunk}}
        if reply_to:
            body["context"] = {"message_id": reply_to}
            reply_to = None
        r = wa_call("POST", "/messages", json=body)
        _sent.append(time.time())
        if r.status_code == 429:
            time.sleep(10)
            wa_call("POST", "/messages", json=body)
        elif r.status_code >= 400:
            print("  send failed:", r.status_code, r.text[:200])


def download_media(media_id):
    meta = wa_call("GET", f"/media/{media_id}").json()
    data = wa.get(meta["url"], timeout=90).content
    return data, meta.get("mime_type", "application/octet-stream")


def split(text, size):
    parts = []
    while len(text) > size:
        cut = text.rfind("\n", 0, size)
        cut = cut if cut > size // 2 else size
        parts.append(text[:cut])
        text = text[cut:].lstrip()
    return parts + [text] if text else parts


# ------------------------------------------------------------------- brain --

def system_prompt():
    persona = (HERE / "prompt.md").read_text(encoding="utf-8")
    return f"""{persona}

---
How this chat works (keep following these rules):
- You are chatting on WhatsApp. Keep replies short and friendly. Use WhatsApp formatting:
  *bold*, _italic_, and simple "- " bullets. No tables, no markdown headings.
- Right now it is {now_local():%A %d %B %Y, %H:%M} for the user.
- If the user asks you to remind them of something, confirm it in your reply and add ONE
  extra last line in exactly this form (it is hidden from the user):
  REMIND: YYYY-MM-DD HH:MM | what to remind them about
"""


def ask_ai(user_parts):
    """user_parts: list of {"text": str} or {"mime": str, "data": bytes}."""
    provider = BRAIN if BRAIN in KEYS else "gemini"
    if not KEYS[provider]:
        return f"I'm not connected to a brain yet. Add your {provider} key to the .env file."
    try:
        return {"gemini": gemini, "claude": claude, "openai": openai}[provider](user_parts)
    except requests.HTTPError as e:
        print("  AI error:", e.response.status_code, e.response.text[:300])
        return "Sorry, my brain had a hiccup. Try again in a minute."


def past_turns():
    return history[-HISTORY_TURNS * 2:]


def b64(raw):
    return base64.b64encode(raw).decode()


def gemini(parts):
    contents = [{"role": "user" if h["role"] == "user" else "model", "parts": [{"text": h["text"]}]}
                for h in past_turns()]
    now = [{"text": p["text"]} if "text" in p else
           {"inline_data": {"mime_type": p["mime"], "data": b64(p["data"])}} for p in parts]
    contents.append({"role": "user", "parts": now})
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{MODELS['gemini']}:generateContent",
        headers={"x-goog-api-key": KEYS["gemini"]},
        json={"system_instruction": {"parts": [{"text": system_prompt()}]}, "contents": contents},
        timeout=120)
    r.raise_for_status()
    cand = r.json()["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in cand).strip()


def claude(parts):
    messages = [{"role": h["role"], "content": h["text"]} for h in past_turns()]
    now = []
    for p in parts:
        if "text" in p:
            now.append({"type": "text", "text": p["text"]})
        elif p["mime"].startswith("image/"):
            now.append({"type": "image", "source": {"type": "base64", "media_type": p["mime"],
                                                    "data": b64(p["data"])}})
        elif p["mime"] == "application/pdf":
            now.append({"type": "document", "source": {"type": "base64", "media_type": p["mime"],
                                                       "data": b64(p["data"])}})
    messages.append({"role": "user", "content": now})
    r = requests.post("https://api.anthropic.com/v1/messages",
                      headers={"x-api-key": KEYS["claude"], "anthropic-version": "2023-06-01"},
                      json={"model": MODELS["claude"], "max_tokens": 1500,
                            "system": system_prompt(), "messages": messages},
                      timeout=120)
    r.raise_for_status()
    return "".join(b.get("text", "") for b in r.json()["content"]).strip()


def openai(parts):
    messages = [{"role": "system", "content": system_prompt()}]
    messages += [{"role": h["role"], "content": h["text"]} for h in past_turns()]
    now = []
    for p in parts:
        if "text" in p:
            now.append({"type": "text", "text": p["text"]})
        elif p["mime"].startswith("image/"):
            now.append({"type": "image_url",
                        "image_url": {"url": f"data:{p['mime']};base64,{b64(p['data'])}"}})
    messages.append({"role": "user", "content": now})
    r = requests.post("https://api.openai.com/v1/chat/completions",
                      headers={"Authorization": f"Bearer {KEYS['openai']}"},
                      json={"model": MODELS["openai"], "messages": messages,
                            "max_completion_tokens": 1500},
                      timeout=120)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


# --------------------------------------------------------------- handling --

REMIND = re.compile(r"^\s*REMIND:\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\s*\|\s*(.+)$", re.M)


def handle(msg):
    kind = msg.get("type")
    state["me"] = msg.get("from") or state.get("me")   # the agent's creator: the only person it can talk to
    mark_read(msg["id"], typing=True)

    if kind == "text":
        text = msg["text"]["body"].strip()
        if text.lower() in ("/reset", "/new"):
            history.clear()
            save("history.json", history)
            send_text("Fresh start. I've forgotten our earlier chat.")
            return
        parts, log = [{"text": text}], text
    elif kind in ("image", "audio", "document", "sticker", "video"):
        media = msg[kind]
        caption = media.get("caption", "")
        if kind == "audio" and BRAIN != "gemini":
            send_text("I can't listen to voice notes with this brain yet. Type it to me, "
                      "or switch AI_PROVIDER to gemini.", msg["id"])
            return
        if kind in ("video", "sticker") or (kind == "document" and media.get("mime_type") != "application/pdf"):
            send_text("I can read text, photos and PDFs. Send me one of those.", msg["id"])
            return
        if kind == "document" and BRAIN == "openai":
            send_text("PDFs work with the gemini or claude brain. Send a photo of the page instead.", msg["id"])
            return
        data, mime = download_media(media["id"])
        parts = [{"mime": mime, "data": data}]
        label = {"image": "a photo", "audio": "a voice note", "document": "a PDF"}[kind]
        parts.append({"text": caption or f"(The user sent {label}.)"})
        log = f"[sent {label}] {caption}".strip()
    else:
        return  # reactions and anything new: ignore quietly

    reply = ask_ai(parts)

    for when, what in REMIND.findall(reply):
        reminders.append({"at": when, "text": what.strip()})
        save("reminders.json", reminders)
        print(f"  reminder saved for {when}: {what.strip()}")
    reply = REMIND.sub("", reply).strip()

    history.extend([{"role": "user", "text": log}, {"role": "assistant", "text": reply}])
    del history[:-HISTORY_TURNS * 2]
    save("history.json", history)
    send_text(reply or "Done.", msg["id"])


def send_due_reminders():
    stamp = now_local().strftime("%Y-%m-%d %H:%M")
    due = [r for r in reminders if r["at"] <= stamp]
    for r in due:
        send_text(f"⏰ *Reminder:* {r['text']}")
        reminders.remove(r)
    if due:
        save("reminders.json", reminders)


# --------------------------------------------------------------------- run --

def main():
    if not WHATSAPP_KEY:
        sys.exit("Add WHATSAPP_AGENT_KEY to your .env file first (see README).")
    print(f"Your WhatsApp agent is running with the {BRAIN} brain. Send it a message!")
    print("Press Ctrl+C to stop.\n")
    while True:
        try:
            send_due_reminders()
            update = get_updates()
            if not update:
                continue
            for entry in update.get("entry", []):
                for change in entry.get("changes", []):
                    for msg in change.get("value", {}).get("messages", []):
                        print(f"[{now_local():%H:%M}] got a {msg.get('type')} message")
                        handle(msg)
            if update.get("next_offset") is not None:
                state["offset"] = update["next_offset"]
                save("state.json", state)
        except KeyboardInterrupt:
            print("\nStopped. See you!")
            break
        except requests.RequestException as e:
            print("  network hiccup, retrying in 5s:", type(e).__name__)
            time.sleep(5)


if __name__ == "__main__":
    main()
