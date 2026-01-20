import os
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
from langchain_openai import ChatOpenAI
from langchain.agents import initialize_agent, Tool
from langchain.prompts import PromptTemplate
from langchain.memory import ConversationBufferMemory
from langchain.schema import SystemMessage
from dotenv import load_dotenv
import numpy as np

# ------------------------------
#  Load environment
# ------------------------------
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# ------------------------------
#  Page Config
# ------------------------------
st.set_page_config(
    page_title="NexLearn AI - University of Maryland",
    page_icon="🐢",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ------------------------------
#  UMD Branding (Dark Mode)
# ------------------------------
st.markdown("""
<style>
    .stApp {
        background-color: #1E1E1E;
        color: #FFFFFF;
        font-family: 'Inter', sans-serif;
    }
    h1, h2, h3, h4, h5, h6 {
        color: #FFD200;
        font-weight: 700;
    }
    .main-header {
        background: linear-gradient(90deg, #E21833, #FFD200);
        padding: 1.2rem;
        border-radius: 12px;
        color: white;
        text-align: center;
        font-size: 1.8rem;
        font-weight: 700;
        margin-bottom: 20px;
        box-shadow: 0 3px 8px rgba(0,0,0,0.3);
    }
    section[data-testid="stSidebar"] {
        background-color: #2C2C2C;
        color: #FFD200;
    }
    .stButton>button {
        background: linear-gradient(90deg, #E21833, #B80C09);
        color: white;
        border: none;
        border-radius: 10px;
        padding: 0.5rem 1rem;
        transition: 0.2s;
    }
    .stButton>button:hover {
        background: linear-gradient(90deg, #B80C09, #8B0000);
        transform: scale(1.03);
    }
    .slider-card {
        background-color: #2C2C2C;
        padding: 1rem;
        border-radius: 10px;
        margin-bottom: 0.8rem;
        box-shadow: 0 2px 6px rgba(0,0,0,0.4);
    }
</style>
""", unsafe_allow_html=True)

# ------------------------------
#  Header
# ------------------------------
col1, col2 = st.columns([0.12, 0.88])
with col1:
    st.image("data:image/jpeg;base64,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", width=95)
with col2:
    st.markdown('<div class="main-header">🐢 NexLearn AI — University of Maryland, College Park</div>', unsafe_allow_html=True)

st.caption("Empowering UMD students to organize, plan, and achieve academic success 🎓")

# ------------------------------
#  Mock Data or Upload
# ------------------------------
def mock_canvas_assignments():
    return pd.DataFrame({
        "Assignment": [
            "Marketing Reflection",
            "Data Analytics Midterm",
            "Finance Simulation Report",
            "Business Strategy Presentation",
            "Leadership Essay",
            "Global Markets Quiz"
        ],
        "Due_Date": pd.to_datetime([
            "2025-11-07", "2025-11-10", "2025-11-12",
            "2025-11-15", "2025-11-18", "2025-11-21"
        ]),
        "Hours_Required": [3, 5, 6, 4, 3, 2]
    })

st.sidebar.header("📂 Data Input")
uploaded = st.sidebar.file_uploader("Upload syllabus CSV", type="csv")

if "df" not in st.session_state:
    st.session_state.df = None

if uploaded:
    # Robust CSV validation
    try:
        tmpdf = pd.read_csv(uploaded)
        required_cols = {"Course","Assignment","Due_Date","Hours_Required"}
        missing = required_cols - set(tmpdf.columns)
        if missing:
            st.sidebar.error(f"❌ Missing required columns: {', '.join(sorted(missing))}")
        else:
            # Parse dates safely
            tmpdf["Due_Date"] = pd.to_datetime(tmpdf["Due_Date"], errors="coerce")
            if tmpdf["Due_Date"].isna().any():
                st.sidebar.warning("⚠️ Some Due_Date values could not be parsed and were dropped.")
                tmpdf = tmpdf.dropna(subset=["Due_Date"])
            # Coerce hours to numeric
            tmpdf["Hours_Required"] = pd.to_numeric(tmpdf["Hours_Required"], errors="coerce").fillna(0)
            st.session_state.df = tmpdf
            st.sidebar.success("✅ Syllabus data uploaded and validated.")
    except Exception as e:
        st.sidebar.error(f"❌ Failed to read CSV: {e}")
elif st.sidebar.button("🎓 Simulate Canvas Data"):
    st.session_state.df = mock_canvas_assignments()
    st.sidebar.success("✅ Mock Canvas assignments loaded!")
else:
    st.session_state.df = mock_canvas_assignments()

df = st.session_state.df
df["Due_Date"] = pd.to_datetime(df["Due_Date"])

# ------------------------------
#  AI Tools
# ------------------------------
def create_study_schedule(_input=None):
    today = datetime.now()
    df["Days_Left"] = (df["Due_Date"] - today).dt.days.clip(lower=1)
    df["Priority"] = (df["Hours_Required"] / df["Days_Left"]).round(2)
    return df.sort_values("Priority", ascending=False)

def summarize_topic(topic=None):
    llm = ChatOpenAI(openai_api_key=OPENAI_API_KEY, model_name="gpt-4o-mini")
    prompt = PromptTemplate(
        input_variables=["topic"],
        template="Summarize this study topic briefly and give 3 quiz questions: {topic}"
    )
    return (prompt | llm).invoke({"topic": topic or "general study material"}).content

def motivation_boost(_input=None):
    llm = ChatOpenAI(openai_api_key=OPENAI_API_KEY, model_name="gpt-4o-mini")
    return llm.predict("Give a motivational message to a University of Maryland student to stay focused and positive today.")


# ------------------------------
#  Google Calendar Integration
# ------------------------------
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

def get_calendar_service():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    service = build("calendar", "v3", credentials=creds)
    return service


def add_event_to_calendar(assignment, due_date, hours_required):
    try:
        service = get_calendar_service()
        event = {
            "summary": f"{assignment}",
            "description": f"Study for {assignment} ({hours_required} hours estimated)",
            "start": {
                "dateTime": (due_date - timedelta(hours=hours_required)).isoformat(),
                "timeZone": "America/New_York",
            },
            "end": {
                "dateTime": due_date.isoformat(),
                "timeZone": "America/New_York",
            },
        }
        event = service.events().insert(calendarId="primary", body=event).execute()
        st.success(f"✅ Added '{assignment}' to your Google Calendar!")
    except Exception as e:
        st.error(f"⚠️ Google Calendar integration failed: {e}")


# ------------------------------
#  LangChain Agent
# ------------------------------
tools = [
    Tool(name="Create Study Schedule", func=lambda x: create_study_schedule().to_string(index=False),
         description="Generate personalized UMD study schedules."),
    Tool(name="Summarize Topic", func=summarize_topic, description="Summarize topics and quiz."),
    Tool(name="Motivation Boost", func=motivation_boost, description="Provide motivational UMD-centric messages.")
]

if "system_context" not in st.session_state:
    st.session_state.system_context = """
    You are NexLearn AI — a University of Maryland academic assistant.
    You help students manage coursework, plan study time, and stay motivated.
    Always return structured, encouraging, and actionable answers formatted in Markdown.
    """

llm = ChatOpenAI(openai_api_key=OPENAI_API_KEY, temperature=0.6, model_name="gpt-4o-mini")
memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
memory.chat_memory.add_message(SystemMessage(content=st.session_state.system_context))
agent = initialize_agent(tools, llm, agent_type="zero-shot-react-description", memory=memory, verbose=True)

# ------------------------------
#  Chat
# ------------------------------
st.markdown("### 💬 Chat with NexLearn AI")
user_query = st.text_input("Ask something (e.g., 'Plan my study week' or 'Give me motivation for finals')")

if "messages" not in st.session_state:
    st.session_state.messages = []

if st.button("🚀 Send"):
    if not OPENAI_API_KEY:
        st.warning("⚠️ Please set your OpenAI API Key in the .env file")
    elif user_query:
        response = agent.run(user_query)
        st.session_state.messages.append(("🧑‍🎓 You", user_query))
        st.session_state.messages.append(("🤖 NexLearn AI", response))

for sender, msg in st.session_state.messages:
    st.markdown(f"**{sender}:** {msg}")


def get_upcoming_calendar_events():
    """Fetch events from the user's Google Calendar for the next 7 days."""
    try:
        service = get_calendar_service()
        now = datetime.utcnow().isoformat() + "Z"  # current time in UTC
        week_later = (datetime.utcnow() + timedelta(days=7)).isoformat() + "Z"

        events_result = service.events().list(
            calendarId="primary",
            timeMin=now,
            timeMax=week_later,
            maxResults=10,
            singleEvents=True,
            orderBy="startTime"
        ).execute()

        return events_result.get("items", [])
    except Exception as e:
        st.warning(f"⚠️ Could not fetch Google Calendar events: {e}")
        return []
    
# ------------------------------
#  Adaptive Weekly Planner Helpers
# ------------------------------
from datetime import time as dt_time

def _merge_busy_windows(events):
    """Return a dict: date -> list of (start,end) busy intervals (naive)."""
    busy = {}
    for ev in events:
        start_raw = ev["start"].get("dateTime", ev["start"].get("date"))
        end_raw = ev["end"].get("dateTime", ev["end"].get("date"))
        try:
            s = pd.to_datetime(start_raw).to_pydatetime().replace(tzinfo=None)
            e = pd.to_datetime(end_raw).to_pydatetime().replace(tzinfo=None)
        except Exception:
            continue
        day = s.date()
        busy.setdefault(day, []).append((s, e))
    # merge overlaps per day
    for d, intervals in busy.items():
        intervals.sort()
        merged = []
        for s,e in intervals:
            if not merged or s > merged[-1][1]:
                merged.append([s,e])
            else:
                merged[-1][1] = max(merged[-1][1], e)
        busy[d] = [(a,b) for a,b in merged]
    return busy

def _daily_free_blocks(day, work_start=9, work_end=22, busy_intervals=None, chunk_minutes=60):
    """Compute free 1h blocks for a given day inside working window, excluding busy intervals."""
    start = datetime.combine(day, dt_time(hour=work_start))
    end = datetime.combine(day, dt_time(hour=work_end))
    blocks = []
    cur = start
    busy_intervals = busy_intervals or []
    def is_free(slot_start, slot_end):
        for bstart, bend in busy_intervals:
            if not (slot_end <= bstart or slot_start >= bend):
                return False
        return True
    while cur + timedelta(minutes=chunk_minutes) <= end:
        slot_end = cur + timedelta(minutes=chunk_minutes)
        if is_free(cur, slot_end):
            blocks.append((cur, slot_end))
        cur = slot_end
    return blocks

def allocate_adaptive_blocks(schedule_df, events=None, days_ahead=7, daily_cap_hours=4, chunk_minutes=60):
    """
    For assignments due within next `days_ahead` days, split Hours_Required
    across free 1h blocks up to daily_cap_hours per day.
    Returns list of planned blocks dicts.
    """
    today = datetime.now().date()
    future_limit = today + timedelta(days=days_ahead)
    consider = schedule_df.copy()
    consider = consider[(consider["Due_Date"].dt.date >= today) & (consider["Due_Date"].dt.date <= future_limit)]
    consider = consider.sort_values(["Due_Date", "Priority"], ascending=[True, False]) if "Priority" in consider.columns else consider.sort_values("Due_Date")

    busy_map = _merge_busy_windows(events or [])
    plans = []
    # Track per-day assigned hours
    assigned_per_day = {}
    for _, row in consider.iterrows():
        remaining = float(row.get("Hours_Required", 0))
        due_day = row["Due_Date"].date()
        day = today
        while day <= min(due_day, future_limit) and remaining > 0:
            # skip due-day final hour glut; prefer earlier days
            daily_cap = daily_cap_hours
            used = assigned_per_day.get(day, 0.0)
            if used >= daily_cap:
                day += timedelta(days=1); continue
            free_blocks = _daily_free_blocks(day, busy_intervals=busy_map.get(day, []), chunk_minutes=chunk_minutes)
            for s,e in free_blocks:
                if assigned_per_day.get(day, 0.0) >= daily_cap:
                    break
                if remaining <= 0:
                    break
                plans.append({
                    "Assignment": row["Assignment"],
                    "Course": row.get("Course",""),
                    "Start": s,
                    "End": e
                })
                assigned_per_day[day] = assigned_per_day.get(day, 0.0) + (chunk_minutes/60.0)
                remaining -= (chunk_minutes/60.0)
            day += timedelta(days=1)
    return plans

def sync_adaptive_plan_to_calendar(plans):
    try:
        service = get_calendar_service()
        for blk in plans:
            event = {
                "summary": f"Study: {blk['Assignment']}",
                "description": f"Scheduled study block for {blk['Assignment']}",
                "start": {"dateTime": blk["Start"].isoformat(), "timeZone": "America/New_York"},
                "end": {"dateTime": blk["End"].isoformat(), "timeZone": "America/New_York"},
            }
            service.events().insert(calendarId="primary", body=event).execute()
        st.success(f"✅ Synced {len(plans)} adaptive study blocks to Google Calendar.")
    except Exception as e:
        st.error(f"⚠️ Calendar sync failed: {e}")



# ------------------------------
#  Dashboard Overview
# ------------------------------
st.markdown("### 📊 UMD Study Dashboard")

schedule = create_study_schedule().sort_values("Due_Date")

# Sync completion tracking
if "completion" not in st.session_state:
    st.session_state.completion = {}

for assignment in schedule["Assignment"]:
    st.session_state.completion.setdefault(assignment, np.random.randint(10, 80))
for a in [a for a in st.session_state.completion if a not in schedule["Assignment"].values]:
    del st.session_state.completion[a]

schedule["Completion_%"] = schedule["Assignment"].map(st.session_state.completion)

# Summary card: overall completion
overall_progress = int(np.mean(list(st.session_state.completion.values())))
st.markdown(f"""
<div style='background-color:#2C2C2C;padding:15px;border-radius:10px;
            text-align:center;margin-bottom:20px;
            border:1px solid #FFD200;box-shadow:0 2px 6px rgba(0,0,0,0.4);'>
    <h3 style='color:#FFD200;'>📈 Weekly Completion Summary</h3>
    <h1 style='color:#FFFFFF;'>{overall_progress}%</h1>
    <p style='color:#BBBBBB;'>of your total assignments completed this week</p>
</div>
""", unsafe_allow_html=True)

# ------------------------------
#  Upcoming Deadlines + Study Hours + Calendar Sync (Fixed)
# ------------------------------
from datetime import timezone

col1, col2 = st.columns([0.45, 0.55])

with col1:
    st.subheader("📅 Upcoming Deadlines This Week")

    # Sidebar: Calendar toggle
    use_calendar = st.sidebar.checkbox("🔗 Use Google Calendar", value=False)

    today = datetime.now(timezone.utc).replace(tzinfo=None)
    next_week = today + timedelta(days=7)

    # ---- Adaptive weekly planning ----
    st.markdown("#### 🧠 Adaptive Weekly Planner")
    max_hours = st.slider("Max study hours per day", 1, 8, 4)
    if st.button("📆 Plan next 7 days adaptively"):
        cal_events = get_upcoming_calendar_events() if use_calendar else []
        # Ensure schedule has Priority column
        sched = create_study_schedule().copy()
        plans = allocate_adaptive_blocks(sched, cal_events, days_ahead=7, daily_cap_hours=max_hours)
        if plans:
            if use_calendar:
                sync_adaptive_plan_to_calendar(plans)
            # Show preview
            preview = pd.DataFrame(plans)
            st.dataframe(preview)
        else:
            st.info("No free slots found within the next 7 days. Try increasing daily cap or enable calendar.")

    # ---- Calendar sync button ----
    if st.button("🗓 Sync All Deadlines to Google Calendar"):
        try:
            service = get_calendar_service()
            for _, row in schedule.iterrows():
                event = {
                    "summary": f"{row['Assignment']}",
                    "description": f"Study for {row['Assignment']} ({row['Hours_Required']} hrs estimated)",
                    "start": {
                        "dateTime": (row["Due_Date"] - timedelta(hours=row["Hours_Required"])).isoformat(),
                        "timeZone": "America/New_York",
                    },
                    "end": {
                        "dateTime": row["Due_Date"].isoformat(),
                        "timeZone": "America/New_York",
                    },
                }
                service.events().insert(calendarId="primary", body=event).execute()
            st.success("✅ All assignments successfully synced to Google Calendar!")
        except Exception as e:
            st.error(f"⚠️ Failed to sync with Google Calendar: {e}")
            st.info("Make sure your credentials.json and token.json are configured properly.")

    # ---- Upcoming events display ----
    if use_calendar:
        events = get_upcoming_calendar_events()

        if events:
            st.markdown("### 🗓 Google Calendar Events")
            for event in events:
                event_name = event.get("summary", "Untitled Event")

                # Safely parse timezone-aware or date-only events
                start = event["start"].get("dateTime", event["start"].get("date"))
                try:
                    start_dt = pd.to_datetime(start, utc=True).tz_convert(None)
                except Exception:
                    start_dt = pd.to_datetime(start).tz_localize(None)

                days_left = (start_dt - today).days
                urgency_color = "#E21833" if days_left <= 1 else "#FFD200" if days_left <= 3 else "#00C853"

                st.markdown(f"""
                    <div style='background-color:#2C2C2C;padding:12px;
                                border-radius:10px;margin-bottom:8px;
                                box-shadow:0 2px 6px rgba(0,0,0,0.4);'>
                        <b style='color:{urgency_color};font-size:16px;'>{event_name}</b><br>
                        🗓️ <b>When:</b> {start_dt.strftime('%b %d, %Y %I:%M %p')}<br>
                        ⏳ <b>{days_left} days left</b>
                    </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No Google Calendar events found for this week 🐢")

    else:
        # ---- Use local assignment data ----
        upcoming = schedule[(schedule["Due_Date"] >= today) & (schedule["Due_Date"] <= next_week)]

        if not upcoming.empty:
            for _, row in upcoming.iterrows():
                days_left = (row["Due_Date"] - today).days
                urgency_color = "#E21833" if days_left <= 2 else "#FFD200" if days_left <= 5 else "#00C853"
                completion = st.session_state.completion[row["Assignment"]]

                st.markdown(f"""
                    <div style='background-color:#2C2C2C;padding:12px;
                                border-radius:10px;margin-bottom:8px;
                                box-shadow:0 2px 6px rgba(0,0,0,0.4);'>
                        <b style='color:{urgency_color};font-size:16px;'>{row['Assignment']}</b><br>
                        🗓️ <b>Due:</b> {row['Due_Date'].strftime('%b %d, %Y')}<br>
                        ⏳ <b>{days_left} days left</b> | 💪 <b>{completion}% complete</b><br>
                        📘 <b>Est. Study Time:</b> {row['Hours_Required']} hrs
                    </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No upcoming deadlines this week — you’re ahead! 🐢")


with col2:
    st.subheader("⏱️ Study Hours Overview")
    fig2 = px.pie(
        schedule,
        names="Assignment",
        values="Hours_Required",
        color_discrete_sequence=["#FFD200", "#E21833", "#B80C09", "#8B0000", "#F7B801", "#C8102E"],
        title="Study Time Distribution"
    )
    fig2.update_layout(
        font=dict(color="#FFFFFF"),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend_title_text=""
    )
    st.plotly_chart(fig2, use_container_width=True)




# ------------------------------
#  Progress Sliders
# ------------------------------
with st.expander("🎯 Update Your Assignment Progress"):
    for _, row in schedule.iterrows():
        current_value = st.session_state.completion.get(row["Assignment"], 0)
        st.session_state.completion[row["Assignment"]] = st.slider(
            f"{row['Assignment']}",
            min_value=0,
            max_value=100,
            value=int(current_value),
            key=f"slider_{row['Assignment']}"
        )

# ------------------------------
#  Completion Chart
# ------------------------------
schedule["Completion_%"] = schedule["Assignment"].map(st.session_state.completion)

fig = px.bar(
    schedule,
    x="Assignment",
    y="Completion_%",
    color="Priority",
    text="Completion_%",
    color_continuous_scale=["#FFD200", "#E21833"],
    title="📚 Real-Time Progress — University of Maryland"
)
fig.update_layout(
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#FFFFFF", family="Inter"),
    title_font=dict(size=22, color="#FFD200")
)
st.plotly_chart(fig, use_container_width=True)


# ------------------------------
#  Well-Being & Routines
# ------------------------------
st.markdown("### 📝 Daily Check-In & Focus Tools")

with st.container():
    c1, c2, c3 = st.columns(3)
    with c1:
        mood = st.slider("Mood (1–5)", 1, 5, 3)
    with c2:
        energy = st.slider("Energy (1–5)", 1, 5, 3)
    with c3:
        confidence = st.slider("Study Confidence (1–5)", 1, 5, 3)
    note = st.text_input("Optional note")

    if st.button("💾 Save today's check-in"):
        try:
            row = {
                "date": datetime.now().date().isoformat(),
                "mood": mood,
                "energy": energy,
                "confidence": confidence,
                "note": note
            }
            path = "checkins.csv"
            if os.path.exists(path):
                prev = pd.read_csv(path)
                prev = pd.concat([prev, pd.DataFrame([row])], ignore_index=True)
                prev.to_csv(path, index=False)
            else:
                pd.DataFrame([row]).to_csv(path, index=False)
            st.success("Saved! Check the trend below.")
        except Exception as e:
            st.error(f"Failed to save check-in: {e}")

# Show recent trend
if os.path.exists("checkins.csv"):
    cd = pd.read_csv("checkins.csv")
    cd["date"] = pd.to_datetime(cd["date"])
    cd = cd.sort_values("date")
    st.line_chart(cd.set_index("date")[["mood","energy","confidence"]])

# ------------------------------
#  Flashcards
# ------------------------------
st.markdown("### 🧠 Quick Flashcards")
flash_topic = st.text_input("Enter a topic to generate flashcards")
def generate_flashcards(topic):
    llm = ChatOpenAI(openai_api_key=OPENAI_API_KEY, model_name="gpt-4o-mini")
    tmpl = PromptTemplate(
        input_variables=["topic"],
        template=(
            "Generate 6 concise Q/A flashcards for undergraduate study on: {topic}. "
            "Return ONLY JSON list of objects with keys 'q' and 'a'."
        )
    )
    raw = (tmpl | llm).invoke({"topic": topic or "study skills"}).content
    try:
        import json
        data = json.loads(raw)
    except Exception:
        # fallback: naive split
        data = [{"q": f"Question {i+1} about {topic}", "a": "Answer placeholder"} for i in range(6)]
    return data

if st.button("🃏 Generate Flashcards"):
    if not OPENAI_API_KEY:
        st.warning("Set your OpenAI API Key first.")
    else:
        cards = generate_flashcards(flash_topic)
        st.session_state.flashcards = cards

if "flashcards" in st.session_state:
    for i, card in enumerate(st.session_state.flashcards):
        with st.expander(f"Card {i+1}: {card['q']}"):
            st.markdown(f"**Answer:** {card['a']}")

# ------------------------------
#  Pomodoro
# ------------------------------
st.markdown("### ⏳ Pomodoro Focus")
if "pomodoro_start" not in st.session_state:
    st.session_state.pomodoro_start = None
if "pomodoro_len" not in st.session_state:
    st.session_state.pomodoro_len = 25  # minutes

colA, colB = st.columns(2)
with colA:
    st.session_state.pomodoro_len = st.number_input("Minutes", 5, 60, st.session_state.pomodoro_len)
with colB:
    if st.session_state.pomodoro_start is None:
        if st.button("▶️ Start Focus"):
            st.session_state.pomodoro_start = datetime.now()
            st.toast("Focus session started. You got this, Terp! 🐢", icon="🔥")
            st.experimental_rerun()
    else:
        if st.button("⏹ Stop"):
            st.session_state.pomodoro_start = None
            st.toast("Session stopped. Nice work!", icon="✅")
            st.experimental_rerun()

if st.session_state.pomodoro_start:
    elapsed = (datetime.now() - st.session_state.pomodoro_start).total_seconds()
    total = st.session_state.pomodoro_len * 60
    remaining = max(0, total - elapsed)
    mins = int(remaining // 60)
    secs = int(remaining % 60)
    st.info(f"Time left: **{mins:02d}:{secs:02d}**")
    if remaining <= 0:
        st.balloons()
        st.success("Pomodoro complete! Take a 5-minute break. 🌿")
        st.session_state.pomodoro_start = None
# ------------------------------
#  Footer
# ------------------------------
st.markdown("""
<hr style="border: 1px solid #FFD200;">
<div style='text-align:center; color:#FFD200;'>
    🐢 Developed for the University of Maryland | NexLearn AI © 2025
</div>
""", unsafe_allow_html=True)
