from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Response
from langchain_core.language_models import BaseChatModel
from psycopg import Connection
from pydantic import BaseModel, Field

from nexlearn import ai

from ..ai_deps import ai_failure, get_chat_model, take_ai_request
from ..auth import User, current_user
from ..config import Settings, get_settings
from ..db import db, user_transaction
from ..planning import display_names, frame, load_assignments, local_now, save_plan, user_tz
from .plan import PlanSettings

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    plan_settings: PlanSettings = PlanSettings()


class ChatMessage(BaseModel):
    role: str
    content: str
    created_at: datetime


class ChatReply(BaseModel):
    reply: str
    plan_updated: bool
    progress_updated: list[str] = Field(description="Assignments whose progress the agent changed")


@router.get("", response_model=list[ChatMessage])
def history(conn: Connection = Depends(db)) -> list[ChatMessage]:
    rows = conn.execute(
        "select role, content, created_at from (select * from chat_messages order by created_at desc, id desc limit 50) m "
        "order by created_at, id"
    ).fetchall()
    return [ChatMessage(**r) for r in rows]


@router.delete("", status_code=204)
def clear(conn: Connection = Depends(db)) -> Response:
    conn.execute("delete from chat_messages")
    return Response(status_code=204)


@router.post("", response_model=ChatReply)
def chat(
    body: ChatIn,
    user: User = Depends(current_user),
    llm: BaseChatModel = Depends(get_chat_model),
    settings: Settings = Depends(get_settings),
) -> ChatReply:
    # 1. Read everything the agent needs, then release the connection: the model call
    #    can take several seconds and should not hold a pooled connection open.
    with user_transaction(user) as conn:
        take_ai_request(conn, "chat", settings)
        rows = load_assignments(conn)
        tz = user_tz(conn)
        past = conn.execute(
            "select role, content from (select * from chat_messages order by created_at desc, id desc limit %s) m "
            "order by created_at, id",
            (ai.MAX_HISTORY_MESSAGES,),
        ).fetchall()

    # 2. Run the agent on a snapshot of the student's assignments.
    names = display_names(rows)
    df, progress = frame(rows, names, tz)
    ctx = ai.AgentContext(
        assignments=df, progress=dict(progress), now=local_now(tz),
        daily_cap_hours=body.plan_settings.daily_cap_hours,
        start_hour=body.plan_settings.start_hour, end_hour=body.plan_settings.end_hour,
    )
    try:
        reply = ai.run_agent(body.message, [(m["role"], m["content"]) for m in past], ctx, llm)
    except Exception as e:
        raise ai_failure(e) from e

    # 3. Save the turn and anything the agent's tools changed.
    id_by_name = {name: id_ for id_, name in names.items()}
    changed = {name: pct for name, pct in ctx.progress.items() if progress.get(name) != pct}
    with user_transaction(user) as conn:
        conn.execute(
            "insert into chat_messages (role, content) values ('user', %s), ('assistant', %s)", (body.message, reply)
        )
        for name, pct in changed.items():
            updated = conn.execute(
                "update assignments set completion_pct = %s where id = %s returning id", (pct, id_by_name[name])
            ).fetchone()
            if updated:  # skip assignments deleted while the agent was thinking
                conn.execute(
                    "insert into progress_events (assignment_id, completion_pct, changed_by) values (%s, %s, 'agent')",
                    (id_by_name[name], pct),
                )
        if ctx.plan is not None:
            save_plan(conn, ctx.plan, id_by_name, tz)

    return ChatReply(reply=reply, plan_updated=ctx.plan is not None, progress_updated=sorted(changed))
