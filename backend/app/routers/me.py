from fastapi import APIRouter, Depends, HTTPException
from psycopg import Connection
from pydantic import BaseModel

from ..auth import User, current_user
from ..db import db

router = APIRouter(tags=["me"])


class Me(BaseModel):
    id: str
    email: str | None
    display_name: str | None
    timezone: str


@router.get("/me", response_model=Me)
def me(user: User = Depends(current_user), conn: Connection = Depends(db)) -> Me:
    row = conn.execute("select display_name, timezone from profiles where id = %s", (user.id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Profile not found")
    return Me(id=user.id, email=user.email, **row)
