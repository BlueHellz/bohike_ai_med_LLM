import os

import pytest

from app.agents.session import create_session, load_context
from app.models import SessionMessage


@pytest.mark.asyncio
async def test_load_context_limits_to_k(db_session):
    os.environ["RECENT_TURNS_K"] = "5"
    sid = await create_session(db_session, "patient-1")
    for i in range(50):
        db_session.add(
            SessionMessage(session_id=sid, sender="patient", text=f"msg-{i}", channel="text")
        )
    await db_session.commit()

    ctx = await load_context(db_session, sid, "current", sender="patient")
    assert len(ctx.recent_turns) == 5
    assert ctx.recent_turns[0].text == "msg-45"
    assert ctx.recent_turns[-1].text == "msg-49"
    assert ctx.current_input.text == "current"


@pytest.mark.asyncio
async def test_physician_message_in_recent_turns(db_session):
    sid = await create_session(db_session, "patient-2")
    db_session.add(
        SessionMessage(
            session_id=sid,
            sender="physician",
            text="ECG shows ST elevation",
            channel="text",
        )
    )
    await db_session.commit()

    ctx = await load_context(db_session, sid, "follow up", sender="patient")
    assert len(ctx.recent_turns) == 1
    assert ctx.recent_turns[0].sender == "physician"
    assert "ST elevation" in ctx.recent_turns[0].text
