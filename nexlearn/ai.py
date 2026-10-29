"""The NexLearn agent, flashcards, and the usage caps that protect the owner's API key."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import date, datetime

import openai
import pandas as pd
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from . import planner
from .config import AI_CALLS_PER_DAY, AI_CALLS_PER_SESSION

# Older turns beyond this are dropped from the prompt to keep requests small.
MAX_HISTORY_MESSAGES = 12

SYSTEM_PROMPT = """You are NexLearn AI, an academic planning assistant for University of Maryland students.

You can see the student's assignments and manage their study time with tools:
- get_assignments: the current list with due dates, hours left, completion, and priority.
- plan_study_week: build a study schedule for the next 7 days around their commitments.
- update_progress: record how far along the student is on an assignment.

Call a tool whenever the answer depends on the student's actual assignments. Never guess
due dates or hours. Whenever the student says how far along they are on an assignment
("halfway", "finished", "about a third"), call update_progress with a percent before you
reply, and confirm what you recorded. Without tools you can explain topics, write practice quiz questions,
and give honest encouragement. Today is {today}. Keep answers short and use Markdown."""


def make_llm(api_key: str, model: str, temperature: float = 0.4) -> ChatOpenAI:
    return ChatOpenAI(api_key=api_key, model=model, temperature=temperature, timeout=60, max_retries=1)


# ------------------------------------------------------------------ agent


@dataclass
class AgentContext:
    """What the agent's tools can see and change during one chat turn."""

    assignments: pd.DataFrame
    progress: dict[str, int]
    now: datetime
    busy: list[planner.Interval] = field(default_factory=list)
    daily_cap_hours: float = 4
    start_hour: int = 9
    end_hour: int = 22
    plan: list[planner.StudyBlock] | None = None
    shortfalls: dict[str, float] = field(default_factory=dict)

    def table(self) -> pd.DataFrame:
        return planner.assignment_table(self.assignments, self.progress, self.now)


def _describe_assignments(t: pd.DataFrame) -> str:
    lines = []
    for _, r in t.iterrows():
        when = "OVERDUE" if r["Overdue"] else f"in {r['Days_Left']} days"
        lines.append(
            f"- {r['Assignment']} ({r['Course']}): due {r['Due_Date']:%a %b %d %I:%M %p} ({when}); "
            f"{r['Hours_Required']:g} h total, {r['Remaining_Hours']:g} h left, "
            f"{r['Completion_%']}% done; priority {r['Priority']} h/day"
        )
    return "\n".join(lines) or "No assignments loaded."


def _describe_plan(blocks: list[planner.StudyBlock], shortfalls: dict[str, float]) -> str:
    if not blocks:
        text = "No study blocks could be scheduled in the next 7 days."
    else:
        days: dict[str, list[str]] = {}
        for b in blocks:
            days.setdefault(f"{b.start:%a %b %d}", []).append(f"{b.start:%I:%M %p}-{b.end:%I:%M %p} {b.assignment}")
        text = "\n".join(f"- {d}: " + "; ".join(items) for d, items in days.items())
    if shortfalls:
        text += "\nWill not fit before the deadline: " + ", ".join(f"{a} ({h} h short)" for a, h in shortfalls.items())
    return text


def build_tools(ctx: AgentContext) -> list:
    @tool
    def get_assignments() -> str:
        """List the student's assignments: course, due date, days left, total and remaining
        hours, percent complete, and priority (hours per day needed to finish on time)."""
        return _describe_assignments(ctx.table())

    @tool
    def plan_study_week(daily_cap_hours: float | None = None) -> str:
        """Schedule study blocks for the next 7 days around the student's calendar.
        Pass daily_cap_hours (1 to 8) only if the student asks for a different daily limit."""
        if daily_cap_hours is not None:
            ctx.daily_cap_hours = max(1.0, min(8.0, float(daily_cap_hours)))
        ctx.plan, ctx.shortfalls = planner.allocate(
            ctx.table(), ctx.now, ctx.busy, daily_cap_hours=ctx.daily_cap_hours,
            start_hour=ctx.start_hour, end_hour=ctx.end_hour,
        )
        return _describe_plan(ctx.plan, ctx.shortfalls)

    @tool
    def update_progress(assignment: str, percent_complete: int) -> str:
        """Record how complete an assignment is, from 0 to 100 percent. Use the name as
        get_assignments lists it; a unique partial name also works."""
        names = list(ctx.assignments["Assignment"])
        exact = [n for n in names if n.lower() == assignment.lower()]
        matches = exact or [n for n in names if assignment.lower() in n.lower()]
        if len(matches) != 1:
            return f"Could not match '{assignment}' to one assignment. Options: {', '.join(names)}"
        pct = max(0, min(100, int(percent_complete)))
        ctx.progress[matches[0]] = pct
        return f"Set {matches[0]} to {pct}% complete."

    return [get_assignments, plan_study_week, update_progress]


def run_agent(question: str, history: list[tuple[str, str]], ctx: AgentContext, llm: BaseChatModel) -> str:
    """One chat turn. `history` is [(role, text)] with role "user" or "assistant"."""
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ]
    )
    tools = build_tools(ctx)
    executor = AgentExecutor(agent=create_tool_calling_agent(llm, tools, prompt), tools=tools, max_iterations=6)
    past = [HumanMessage(t) if role == "user" else AIMessage(t) for role, t in history[-MAX_HISTORY_MESSAGES:]]
    result = executor.invoke({"input": question, "chat_history": past, "today": f"{ctx.now:%A, %B %d, %Y}"})
    return result["output"]


# ------------------------------------------------------------------ flashcards


class Flashcard(BaseModel):
    question: str = Field(description="A short, specific question")
    answer: str = Field(description="A concise answer, one to three sentences")


class FlashcardDeck(BaseModel):
    cards: list[Flashcard]


def make_flashcards(topic: str, n: int, llm: BaseChatModel) -> list[Flashcard]:
    deck = llm.with_structured_output(FlashcardDeck).invoke(
        f"Write {n} flashcards for a university student studying: {topic}. "
        "Mix definitions, reasoning questions, and one applied example."
    )
    return deck.cards[:n]


# ------------------------------------------------------------------ usage caps and errors

_lock = threading.Lock()
_daily = {"day": None, "count": 0}  # module state is shared by every session in the process


def take_ai_call(session_state, today: date) -> str | None:
    """Count one AI request. Returns None if allowed, otherwise a message to show."""
    if session_state.get("ai_calls", 0) >= AI_CALLS_PER_SESSION:
        return f"This session has reached the demo limit of {AI_CALLS_PER_SESSION} AI requests."
    with _lock:
        if _daily["day"] != today:
            _daily.update(day=today, count=0)
        if _daily["count"] >= AI_CALLS_PER_DAY:
            return "The demo has reached its AI request limit for today. Please try again tomorrow."
        _daily["count"] += 1
    session_state["ai_calls"] = session_state.get("ai_calls", 0) + 1
    return None


def friendly_error(e: Exception) -> str:
    if isinstance(e, openai.AuthenticationError):
        return "The OpenAI API key was rejected. The app owner needs to update OPENAI_API_KEY in the app's secrets."
    if isinstance(e, openai.RateLimitError):
        return "OpenAI is rate limiting this app, or the account is out of credit. Try again later."
    if isinstance(e, openai.NotFoundError):
        return "The configured model is not available. Set OPENAI_MODEL in the app's secrets."
    if isinstance(e, (openai.APIConnectionError, openai.APITimeoutError)):
        return "Could not reach OpenAI. Try again in a moment."
    return f"Something went wrong talking to the AI model ({type(e).__name__})."
