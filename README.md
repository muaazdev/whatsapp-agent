# Your own AI assistant inside WhatsApp

WhatsApp now lets you add your **own AI agent** as a chat. This project is that agent.
Send it a photo of a bill, a menu, a medicine box or homework and it explains it.
Ask *"remind me to call mom at 6"* and it messages you at 6.
Change one file and it becomes your study tutor, fitness coach or shop helper.

You only touch **two files**: `prompt.md` (who your assistant is) and `.env` (your keys).
No server, no domain, no coding.

---

## What you need (10 minutes)

1. **WhatsApp with the "Agents" option.** Settings → **Agents**. Meta is rolling it out slowly, so it may not be on your phone yet.
2. **A computer** (Windows or Mac) with **Python** installed: [python.org/downloads](https://www.python.org/downloads/). On Windows, tick **"Add Python to PATH"** during install.
3. **One AI key**, any of these:

| Brain | Cost | Get a key |
|---|---|---|
| **Gemini** (Google) | Free tier | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |
| Claude (Anthropic) | Pay as you go | [platform.claude.com](https://platform.claude.com/settings/keys) |
| OpenAI | Pay as you go | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |

No key yet? Use **Gemini**. It's free and it also understands voice notes.

---

## Setup

### 1. Create the agent in WhatsApp
WhatsApp → **Settings → Agents → Create an agent**. Give it a name and a photo.
WhatsApp opens a chat with it. Tap **View API key** and copy the key.
Keep this key private: anyone who has it controls your agent.

### 2. Download this project
Click the green **Code** button on this page → **Download ZIP** → unzip it anywhere.

### 3. Add your keys
- **Windows:** double-click `start.bat`. Notepad opens a file called `.env`.
- **Mac:** open Terminal in the folder, run `sh start.sh`, then open `.env` in TextEdit.

Paste your WhatsApp agent key and your AI key, and set your time zone. Example:

```
WHATSAPP_AGENT_KEY=the-key-you-copied-from-whatsapp
AI_PROVIDER=gemini
GEMINI_API_KEY=your-free-gemini-key
UTC_OFFSET_HOURS=3
```

Save and close.

### 4. Start it
Double-click `start.bat` again (Mac: `sh start.sh`). You'll see:

```
Your WhatsApp agent is running with the gemini brain. Send it a message!
```

Now say hi to your agent in WhatsApp. That's it.

---

## Make it yours: edit `prompt.md`

`prompt.md` is plain English. Whatever you write there is who your assistant is.
Change it, save, and the next reply already follows it (no restart needed). Some ideas:

- *"You are a patient maths tutor for my 12-year-old. Never give the answer straight away; give hints."*
- *"You are my fitness coach. I train 3 days a week. Ask how today's workout went."*
- *"You help me run Ali's Bakery. Our prices are: ..."*

## Things you can say to it

- Send a **photo** + "what does this say?" (bills, forms, menus, signs in another language)
- Send a **PDF** + "summarise this" (Gemini and Claude)
- Send a **voice note** (Gemini only)
- "Remind me to pay rent tomorrow at 9am"
- `/reset` to make it forget the conversation and start fresh

## Good to know

- **Only you** can chat with your agent. It can't message anyone else or join groups.
- It answers while this program is running, so keep the computer on. Close the window to stop it.
- Chats with agents are **not end-to-end encrypted** like your normal chats: messages pass through Meta and go to the AI company you picked. Don't send passwords or very private documents.
- You can have up to **5 agents**. Each one needs its own copy of this folder and its own key.
- Your chat memory and reminders are saved in the `data` folder on your computer.

## If something goes wrong

| You see | Fix |
|---|---|
| "agent key is wrong" | Copy the key again from the agent's chat (View API key). Reinstalling WhatsApp makes a new key. |
| "Another copy ... is already running" | Close the other window that's running the agent. |
| `python` is not recognized | Reinstall Python and tick "Add Python to PATH". |
| "my brain had a hiccup" | Check your AI key, or your free Gemini limit for the day. |
| No reply at all | Make sure the window is open and says it's running. |

---

Built by [Muaaz Ahmad](https://muaazdev.com), Forward Deployed AI Engineer.
Uses Meta's [WhatsApp Agent Platform](https://www.whatsapp.com/developer/WhatsApp-Agent-Platform-Developer-Manual.pdf) (v1). Not affiliated with Meta or WhatsApp. MIT licence.

<details>
<summary>For developers</summary>

- One file, `agent.py`, about 300 lines. Only dependency: `requests`.
- Inbound is a long poll (`GET /updates`, 25 s), so no webhook or public URL. One poller per key (a second one gets HTTP 409).
- Outbound: `POST /messages`; blue ticks + typing via `POST /statuses`; media via `GET /media/{id}`.
- Meta limits: 12 sends, 12 status updates and 15 polls per minute; text up to 4,096 characters.
- Reminders: the model appends a hidden `REMIND: YYYY-MM-DD HH:MM | text` line; the loop checks due reminders every poll.
- Tests (no network, fake Meta API + fake brains): `python tests/test_agent.py`
</details>
