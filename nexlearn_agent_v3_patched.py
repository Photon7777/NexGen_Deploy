"""NexLearn AI: Streamlit entry point.

Streamlit Cloud runs this file by name, so it keeps its original filename. The logic
lives in the nexlearn package; this file is only the interface.
"""
from __future__ import annotations

import html
import time
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

from nexlearn import ai, config, data, gcal, ics, planner

load_dotenv()
ROOT = Path(__file__).parent
GOLD, RED, GREEN = "#FFD200", "#E21833", "#00C853"
UMD_COLORS = [GOLD, RED, "#B80C09", "#8B0000", "#F7B801", "#C8102E", "#FFE680", "#7A0019"]
SUGGESTIONS = ["Plan my study week", "What should I work on first?", "Quiz me on regression basics"]

st.set_page_config(
    page_title="NexLearn AI - University of Maryland",
    page_icon="🐢",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(
    f"""
<style>
    h1, h2, h3 {{ color: {GOLD}; }}
    .main-header {{
        background: linear-gradient(90deg, {RED}, {GOLD});
        padding: 1.1rem; border-radius: 12px; color: white; text-align: center;
        font-size: 1.7rem; font-weight: 700; box-shadow: 0 3px 8px rgba(0,0,0,0.3);
    }}
    .deadline {{
        background: #2C2C2C; padding: 10px 12px; border-radius: 10px; margin-bottom: 8px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.4); line-height: 1.5;
    }}
</style>
""",
    unsafe_allow_html=True,
)

# ------------------------------------------------------------------ session state

NOW = config.now()
ss = st.session_state
ss.setdefault("assignments", data.sample_assignments(NOW.date()))
ss.setdefault("source", "Sample assignments")
ss.setdefault("load_messages", [])
ss.setdefault("progress", {})
ss.setdefault("chat", [])
ss.setdefault("plan", None)
ss.setdefault("shortfalls", {})
ss.setdefault("busy", [])
ss.setdefault("checkins", [])
ss.setdefault("pomodoro", None)  # (end_timestamp, total_seconds) while running

# Progress changed by the agent last run. Applied before any slider exists this run.
for name, pct in ss.pop("pending_progress", {}).items():
    ss.progress[name] = pct
    ss[f"prog_{name}"] = pct


def set_assignments(df: pd.DataFrame, source: str) -> None:
    ss.assignments, ss.source, ss.plan, ss.shortfalls = df, source, None, {}
    ss.progress = {k: v for k, v in ss.progress.items() if k in set(df["Assignment"])}


# ------------------------------------------------------------------ sidebar

with st.sidebar:
    st.header("📂 Your assignments")
    upload = st.file_uploader(
        "Upload syllabus CSV", type="csv", help="Columns: Course, Assignment, Due_Date, Hours_Required"
    )
    if upload is not None and ss.get("loaded_file") != upload.file_id:
        ss.loaded_file = upload.file_id
        df, ss.load_messages = data.load_syllabus_csv(upload)
        if df is not None:
            set_assignments(df, upload.name)
    for msg in ss.load_messages:
        st.warning(msg)
    st.caption(f"Showing: **{html.escape(ss.source)}** ({len(ss.assignments)} assignments)")
    if st.button("🎓 Use sample assignments", width="stretch"):
        set_assignments(data.sample_assignments(NOW.date()), "Sample assignments")
        ss.load_messages = []
        st.rerun()
    st.download_button("⬇️ Download CSV template", data.template_csv(), "nexlearn_template.csv", "text/csv", width="stretch")

    st.header("⚙️ Planner")
    daily_cap = st.slider("Max study hours per day", 1, 8, 4)
    start_hour, end_hour = st.slider("Study window", 6, 23, (9, 22), format="%d:00")
    use_gcal = gcal.available() and st.toggle(
        "Plan around my Google Calendar", help="Local runs only: needs credentials.json from Google Cloud."
    )

    st.header("🤖 AI")
    api_key = config.openai_api_key()
    usage_slot = st.empty()  # filled at the end of the run, after this run's AI calls
    if not api_key:
        st.warning("AI features are off: no OPENAI_API_KEY is set.")

# ------------------------------------------------------------------ header and summary

logo, title = st.columns([0.1, 0.9], vertical_alignment="center")
logo.image(str(ROOT / "assets" / "umd_smith_logo.jpg"), width=90)
title.markdown('<div class="main-header">🐢 NexLearn AI · University of Maryland, College Park</div>', unsafe_allow_html=True)
st.caption("An agentic study planner: it reads your assignments, finds free time, and builds a week you can actually follow.")

table = planner.assignment_table(ss.assignments, ss.progress, NOW)
active = table[table["Remaining_Hours"] > 0]
total_hours = table["Hours_Required"].sum()
done_hours = total_hours - table["Remaining_Hours"].sum()
top = active.sort_values("Priority", ascending=False).iloc[0] if not active.empty else None

m1, m2, m3, m4 = st.columns(4)
m1.metric("Due in the next 7 days", int(((~table["Overdue"]) & (table["Days_Left"] <= 7)).sum()))
m2.metric("Study hours left", f"{table['Remaining_Hours'].sum():g}")
m3.metric("Overall progress", f"{done_hours / total_hours:.0%}" if total_hours else "n/a", help="Weighted by hours")
m4.metric("Most urgent", top["Assignment"] if top is not None else "All done", help="Most hours per day needed to finish on time")

tab_chat, tab_plan, tab_progress, tab_tools = st.tabs(["💬 Assistant", "📅 Plan", "📊 Progress", "🧠 Study tools"])

# ------------------------------------------------------------------ assistant


def ask_agent(question: str) -> str:
    blocked = ai.take_ai_call(ss, NOW.date())
    if blocked:
        return blocked
    ctx = ai.AgentContext(
        assignments=ss.assignments, progress=dict(ss.progress), now=NOW, busy=ss.busy,
        daily_cap_hours=daily_cap, start_hour=start_hour, end_hour=end_hour,
    )
    try:
        answer = ai.run_agent(question, ss.chat, ctx, ai.make_llm(api_key, config.openai_model()))
    except Exception as e:
        return f"⚠️ {ai.friendly_error(e)}"
    changed = {k: v for k, v in ctx.progress.items() if ss.progress.get(k) != v}
    if changed:
        ss.pending_progress = changed
    if ctx.plan is not None:
        ss.plan, ss.shortfalls = ctx.plan, ctx.shortfalls
    return answer


with tab_chat:
    if not api_key:
        st.info("Chat needs an OpenAI API key. Add OPENAI_API_KEY to the app's secrets (or a local .env file).")
    history = st.container(height=430)
    with history:
        if not ss.chat:
            st.chat_message("assistant", avatar="🐢").markdown(
                "Hi! I can see your assignments. I can plan your week, tell you what to tackle first, "
                "update your progress, or quiz you on a topic."
            )
        for role, text in ss.chat:
            st.chat_message(role, avatar="🧑‍🎓" if role == "user" else "🐢").markdown(text)

    picked = None
    for col, suggestion in zip(st.columns(len(SUGGESTIONS)), SUGGESTIONS):
        if col.button(suggestion, width="stretch", disabled=not api_key):
            picked = suggestion
    typed = st.chat_input("Ask NexLearn anything", disabled=not api_key)
    if ss.chat and st.button("🧹 Clear chat"):
        ss.chat = []
        st.rerun()

    question = typed or picked
    if question:
        with history:
            st.chat_message("user", avatar="🧑‍🎓").markdown(question)
            with st.chat_message("assistant", avatar="🐢"), st.spinner("Thinking..."):
                answer = ask_agent(question)
        ss.chat += [("user", question), ("assistant", answer)]
        st.rerun()

# ------------------------------------------------------------------ plan

with tab_plan:
    left, right = st.columns([0.56, 0.44], gap="large")
    with left:
        st.subheader("🧠 Adaptive weekly planner")
        st.caption(
            f"Spreads each assignment's remaining hours across free time between {start_hour}:00 and "
            f"{end_hour}:00, earliest deadline first, with at most {daily_cap} hours a day."
        )
        if st.button("📆 Plan the next 7 days", type="primary"):
            if use_gcal:
                try:
                    ss.busy = gcal.busy_intervals(NOW)
                except Exception as e:
                    st.warning(f"Could not read Google Calendar, planning without it: {e}")
            ss.plan, ss.shortfalls = planner.allocate(
                table, NOW, ss.busy, daily_cap_hours=daily_cap, start_hour=start_hour, end_hour=end_hour
            )

        if ss.plan:
            # st.table, not st.dataframe: a grid first drawn in a hidden tab renders squashed.
            st.table(planner.blocks_frame(ss.plan).set_index("Day"))
            st.download_button(
                "⬇️ Download plan for your calendar (.ics)",
                ics.to_ics(ss.plan),
                file_name="nexlearn_study_plan.ics",
                mime="text/calendar",
            )
            st.caption("Import the file in Google Calendar (Settings, then Import), Outlook, or Apple Calendar.")
            if use_gcal and st.button("Add these blocks to Google Calendar"):
                try:
                    st.success(f"Added {gcal.add_blocks(ss.plan)} study blocks to Google Calendar.")
                except Exception as e:
                    st.error(f"Google Calendar sync failed: {e}")
        elif ss.plan is not None:
            if active[~active["Overdue"]].empty:
                st.info("Nothing left to schedule: every assignment is finished or past due.")
            else:
                st.info("No free time found in the next 7 days. Raise the daily cap or widen the study window.")
        for name, short in ss.shortfalls.items():
            st.warning(f"**{name}**: {short} h will not fit before it is due. Raise the daily cap or widen the study window.")

    with right:
        st.subheader("📅 Deadlines this week")
        soon = table[(table["Days_Left"] <= 7) & (table["Remaining_Hours"] > 0)]
        if soon.empty:
            st.info("Nothing due in the next 7 days. 🐢")
        for _, r in soon.iterrows():
            if r["Overdue"]:
                color, when = RED, "Past due"
            else:
                color = RED if r["Days_Left"] <= 1 else GOLD if r["Days_Left"] <= 3 else GREEN
                when = f"{r['Days_Left']:g} days left"
            st.markdown(
                f"""<div class="deadline">
                <b style="color:{color};font-size:16px;">{html.escape(r['Assignment'])}</b>
                <span style="color:#BBBBBB;"> · {html.escape(r['Course'])}</span><br>
                🗓️ Due {r['Due_Date']:%a %b %d, %I:%M %p} · ⏳ {when}<br>
                💪 {r['Completion_%']}% done · 📘 {r['Remaining_Hours']:g} h left
                </div>""",
                unsafe_allow_html=True,
            )
        if not active.empty:
            pie = px.pie(active, names="Assignment", values="Remaining_Hours", color_discrete_sequence=UMD_COLORS,
                         title="Where your remaining hours go")
            pie.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", margin=dict(t=50, b=0, l=0, r=0),
                legend=dict(orientation="h", yanchor="top", y=-0.05, title_text=""),
            )
            st.plotly_chart(pie)

# ------------------------------------------------------------------ progress


def sync_progress(name: str) -> None:
    ss.progress[name] = ss[f"prog_{name}"]


with tab_progress:
    st.subheader("🎯 Update your progress")
    cols = st.columns(2)
    for i, name in enumerate(table["Assignment"]):
        ss.setdefault(f"prog_{name}", ss.progress.get(name, 0))
        cols[i % 2].slider(name, 0, 100, key=f"prog_{name}", format="%d%%", on_change=sync_progress, args=(name,))

    hours = table.assign(Done=table["Hours_Required"] - table["Remaining_Hours"], Remaining=table["Remaining_Hours"])
    hours = hours.melt(id_vars="Assignment", value_vars=["Done", "Remaining"], var_name="Status", value_name="Hours")
    bar = px.bar(
        hours, y="Assignment", x="Hours", color="Status", orientation="h",
        color_discrete_map={"Done": GOLD, "Remaining": RED}, title="Study hours done and remaining",
    )
    bar.update_layout(
        barmode="stack", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(autorange="reversed", title=""), legend_title_text="",
    )
    st.plotly_chart(bar)

# ------------------------------------------------------------------ study tools


def pomodoro() -> None:
    if ss.pomodoro is None:
        minutes = st.number_input("Minutes", 5, 60, 25, step=5)
        if st.button("▶️ Start focus"):
            ss.pomodoro = (time.time() + minutes * 60, minutes * 60)
            st.toast("Focus session started. You got this, Terp! 🐢", icon="🔥")
            st.rerun()
        return
    end, total = ss.pomodoro
    left = end - time.time()
    if left <= 0:
        ss.pomodoro, ss.pomodoro_done = None, True
        st.rerun()
    st.metric("Time left", f"{int(left // 60):02d}:{int(left % 60):02d}")
    st.progress(min(1.0, 1 - left / total))
    if st.button("⏹ Stop"):
        ss.pomodoro = None
        st.rerun()


with tab_tools:
    st.subheader("🃏 Flashcards")
    f1, f2 = st.columns([0.75, 0.25], vertical_alignment="bottom")
    topic = f1.text_input("Topic", placeholder="e.g. linear regression assumptions")
    count = f2.number_input("Cards", 3, 10, 6)
    if st.button("Generate flashcards", disabled=not api_key):
        if not topic.strip():
            st.warning("Enter a topic first.")
        elif blocked := ai.take_ai_call(ss, NOW.date()):
            st.warning(blocked)
        else:
            try:
                with st.spinner("Writing cards..."):
                    ss.flashcards = ai.make_flashcards(topic, int(count), ai.make_llm(api_key, config.openai_model()))
            except Exception as e:
                st.error(ai.friendly_error(e))
    for i, card in enumerate(ss.get("flashcards", []), 1):
        with st.expander(f"Card {i}: {card.question}"):
            st.markdown(card.answer)

    st.divider()
    p_col, c_col = st.columns(2, gap="large")
    with p_col:
        st.subheader("⏳ Pomodoro")
        if ss.pop("pomodoro_done", False):
            st.balloons()
            st.success("Pomodoro complete! Take a 5-minute break. 🌿")
        # Tick once a second only while a session is running.
        st.fragment(pomodoro, run_every=1 if ss.pomodoro else None)()

    with c_col:
        st.subheader("📝 Daily check-in")
        with st.form("checkin", clear_on_submit=True, border=False):
            a, b, c = st.columns(3)
            mood = a.slider("Mood", 1, 5, 3)
            energy = b.slider("Energy", 1, 5, 3)
            confidence = c.slider("Confidence", 1, 5, 3)
            note = st.text_input("Note (optional)")
            if st.form_submit_button("💾 Save check-in"):
                ss.checkins.append(
                    {"Time": config.now(), "Mood": mood, "Energy": energy, "Confidence": confidence, "Note": note}
                )
        if ss.checkins:
            checkins = pd.DataFrame(ss.checkins)
            trend = checkins.melt(id_vars="Time", value_vars=["Mood", "Energy", "Confidence"], var_name="Measure", value_name="Score")
            line = px.line(trend, x="Time", y="Score", color="Measure", markers=True, range_y=[0.5, 5.5], height=260,
                           color_discrete_sequence=[GOLD, RED, GREEN])
            line.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", legend_title_text="",
                               xaxis_title="", margin=dict(t=10, b=0, l=0, r=0))
            st.plotly_chart(line)
            st.download_button("⬇️ Download check-ins (.csv)", checkins.to_csv(index=False), "nexlearn_checkins.csv", "text/csv")
        st.caption("Check-ins stay in this browser session only. Download them to keep a record.")

if api_key:
    usage_slot.caption(
        f"Model: {config.openai_model()}  \n"
        f"{ss.get('ai_calls', 0)} of {config.AI_CALLS_PER_SESSION} AI requests used this session"
    )

st.markdown(
    f"""<hr style="border: 1px solid {GOLD};">
<div style="text-align:center; color:{GOLD};">🐢 Built for the University of Maryland · NexLearn AI</div>""",
    unsafe_allow_html=True,
)
