# NexLearn AI

An agentic study planner for University of Maryland students, built with Streamlit, LangChain, and the OpenAI API.

**Live app:** https://nexgen-ai.streamlit.app

NexLearn reads a student's assignments, scores each one by how many hours a day it needs before its deadline, and builds a week of study sessions around their free time. A LangChain tool-calling agent sits on top: students can ask it to plan the week, say what to tackle first, record progress in plain English ("I'm halfway through the midterm prep"), or quiz them on a topic.

Originally built for the 2025 Agentic AI Case Competition (Honorable Mention).

## Features

| Area | What it does |
| --- | --- |
| **Assistant** | Tool-calling agent with three tools: `get_assignments`, `plan_study_week`, `update_progress`. Chat history and the system prompt go to the model on every turn, so it remembers the conversation. |
| **Adaptive planner** | Spreads each assignment's remaining hours across free slots before its deadline, earliest deadline first, under a daily cap and inside a study window you choose. Two assignments never share a slot. Reports work that will not fit in time. |
| **Calendar export** | Download the plan as an `.ics` file for Google Calendar, Outlook, or Apple Calendar. Running locally, it can also read busy times from and write blocks to Google Calendar. |
| **Progress** | Per-assignment sliders, a done-vs-remaining hours chart, and an hours-weighted overall progress figure. |
| **Study tools** | AI flashcards (structured output, so cards always parse), a Pomodoro timer that counts down live, and a daily mood, energy, and confidence check-in. |

Priority is `remaining hours / days left`: the hours per day an assignment needs from now until it is due.

## Run it locally

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
echo 'OPENAI_API_KEY=sk-...' > .env
streamlit run nexlearn_agent_v3_patched.py
```

Without a key, everything except the assistant and flashcards still works.

**Optional Google Calendar sync (local only).** Create an OAuth client of type *Desktop app* in Google Cloud, enable the Calendar API, and save the client file as `credentials.json` in the project folder. A "Plan around my Google Calendar" toggle then appears in the sidebar. Google's desktop sign-in opens a browser on the machine running the app, which is why the hosted version offers the `.ics` download instead.

## Upload your own assignments

Upload a CSV with these columns (the sidebar has a template):

| Column | Example | Notes |
| --- | --- | --- |
| `Course` | BUDT 704 | |
| `Assignment` | Problem Set 3 | Repeated names get the course added. |
| `Due_Date` | 2026-11-04 or 2026-11-04 17:00 | A date alone means 11:59 PM. Times are US Eastern. |
| `Hours_Required` | 4 | Decimals are fine. |

Rows with an unreadable date or hours value are dropped, and the app says how many.

## Deploying on Streamlit Community Cloud

- Main file: `nexlearn_agent_v3_patched.py` (the name the existing deployment uses).
- Secrets (**Manage app**, then **Settings**, then **Secrets**):
  ```toml
  OPENAI_API_KEY = "sk-..."
  # OPENAI_MODEL = "gpt-4o-mini"   # optional override
  ```
- The public app runs on the owner's key, so each session is capped at 20 AI requests and the whole app at 300 a day (`nexlearn/config.py`). Set a monthly budget in the OpenAI dashboard as well.

## Project layout

```
nexlearn_agent_v3_patched.py   Streamlit interface (entry point)
nexlearn/
    config.py      time zone, model, API key lookup, usage caps
    data.py        sample assignments and CSV loading
    planner.py     priority scoring and the weekly planner (pure functions)
    ai.py          agent, tools, flashcards, usage caps, error messages
    ics.py         calendar file export
    gcal.py        optional Google Calendar sync for local runs
tests/             pytest suite, including an offline agent test with a scripted model
```

```bash
pip install -r requirements-dev.txt
pytest
```

The agent test replays scripted model replies, so it needs no API key.

## Changelog

**October 2026: fixes and rebuild.**

The deployed app had stopped working. Fixed:

- Every AI feature failed because the deployed OpenAI key was rejected. The app now reads the key from Streamlit secrets and shows a clear message instead of a stack trace.
- The Pomodoro button crashed: `st.experimental_rerun` was removed from Streamlit.
- The sample assignments were hard-coded to November 2025, so the deadlines and planner showed nothing. Sample dates are now relative to today.
- Google Calendar could not sign in on a hosted server. The hosted app now offers an `.ics` download.
- Conversation memory was rebuilt on every rerun, and the agent's prompt never included it.
- Flashcards often fell back to placeholder text when the model wrapped its JSON in code fences.
- Daily check-ins, including notes, were written to one shared file on the server that every visitor could see. They now stay in each visitor's session.
- Completion started at random percentages.
- Times used the server clock (UTC) instead of Eastern time.
- The planner could book two assignments into the same hour, and could schedule time earlier in the day than the current time.
- CSV uploads that mixed date-only and date-and-time values silently dropped rows.

Also new: the tool-calling agent with progress updates, the module split and tests, the tabbed layout, and usage caps.
