from datetime import date, datetime

import httpx
import openai
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import Field

from nexlearn import ai
from nexlearn.data import sample_assignments

NOW = datetime(2026, 10, 28, 8, 0)


class FakeToolModel(GenericFakeChatModel):
    """Replays scripted replies (including tool calls) and records every prompt it sees."""

    seen: list = Field(default_factory=list)
    disable_streaming: bool = True  # the agent streams; tool-call-only replies have no text chunks

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append(messages)
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def _ctx():
    return ai.AgentContext(assignments=sample_assignments(NOW.date()), progress={}, now=NOW)


def test_agent_calls_planner_tool_and_returns_answer():
    llm = FakeToolModel(messages=iter([
        AIMessage(content="", tool_calls=[{"name": "plan_study_week", "args": {"daily_cap_hours": 3}, "id": "c1"}]),
        AIMessage(content="Here is your week."),
    ]))
    ctx = _ctx()
    out = ai.run_agent("Plan my study week", [], ctx, llm)
    assert out == "Here is your week."
    assert ctx.plan, "the tool should leave the plan on the context for the UI"
    assert ctx.daily_cap_hours == 3
    # The tool result was sent back to the model on the second call.
    assert any("Global Markets Quiz" in str(m.content) for m in llm.seen[1])


def test_agent_prompt_carries_system_prompt_and_chat_history():
    llm = FakeToolModel(messages=iter([AIMessage(content="Sure.")]))
    history = [("user", "I am taking BUDT 704 this term."), ("assistant", "Noted.")]
    ai.run_agent("What did I say I'm taking?", history, _ctx(), llm)
    sent = llm.seen[0]
    assert isinstance(sent[0], SystemMessage) and "NexLearn AI" in sent[0].content
    assert "Wednesday, October 28, 2026" in sent[0].content
    assert any(isinstance(m, HumanMessage) and "BUDT 704" in m.content for m in sent)
    assert any(isinstance(m, AIMessage) and m.content == "Noted." for m in sent)


def test_update_progress_tool_matches_partial_names():
    ctx = _ctx()
    tools = {t.name: t for t in ai.build_tools(ctx)}
    assert "Set Leadership Essay to 40%" in tools["update_progress"].invoke({"assignment": "leadership", "percent_complete": 40})
    assert ctx.progress["Leadership Essay"] == 40
    assert "Could not match" in tools["update_progress"].invoke({"assignment": "e", "percent_complete": 10})  # ambiguous
    assert "Could not match" in tools["update_progress"].invoke({"assignment": "nonexistent", "percent_complete": 10})


def test_usage_caps():
    state = {}
    today = date(2026, 10, 28)
    for _ in range(ai.AI_CALLS_PER_SESSION):
        assert ai.take_ai_call(state, today) is None
    assert "limit" in ai.take_ai_call(state, today)


def test_friendly_error_for_bad_key():
    resp = httpx.Response(401, request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"))
    err = openai.AuthenticationError("bad key", response=resp, body=None)
    assert "OPENAI_API_KEY" in ai.friendly_error(err)
