from __future__ import annotations

import json
import logging
import sqlite3

from google import genai

from t3.bot.confirmation import PendingConflict, resolve
from t3.bot.onboarding import (
    IntervalsDerivedProfile,
    apply_corrections,
    flush_to_db,
    format_confirmation_message,
)
from t3.db import ConversationState, ConversationStateRepo
from t3.sync import ConflictInfo
from t3.tools.plan import generate_training_plan
from t3.config import settings

logger = logging.getLogger(__name__)

_CONFIRMATION_WORDS = frozenset({"yes", "y", "confirm", "ok", "yep", "sure"})


async def handle_turn(
    chat_id: int,
    user_text: str,
    conn: sqlite3.Connection,
    client: genai.Client,
) -> str:
    repo = ConversationStateRepo(conn)
    loaded = repo.load(chat_id)
    state = loaded[0] if loaded else ConversationState.IDLE
    payload_json = loaded[1] if loaded else None

    try:
        if state == ConversationState.ONBOARDING_AWAITING_CONFIRMATION:
            return await _handle_onboarding(chat_id, user_text, payload_json, conn, client, repo)

        elif state == ConversationState.CONFLICT_PENDING:
            return await _handle_conflict(chat_id, user_text, payload_json, conn, repo)

        else:
            from t3.agent import run
            return await run(user_text, client) or "I didn't get a response. Try again."

    except Exception as exc:
        logger.exception("handle_turn error for chat_id=%d", chat_id)
        msg = str(exc)
        if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
            return "Gemini API rate limit hit. Wait a minute and try again."
        elif "503" in msg or "UNAVAILABLE" in msg:
            return "Gemini is overloaded right now. Try again in a few seconds."
        return f"Something went wrong: {exc}"


async def _handle_onboarding(
    chat_id: int,
    user_text: str,
    payload_json: str | None,
    conn: sqlite3.Connection,
    client: genai.Client,
    repo: ConversationStateRepo,
) -> str:
    if payload_json is None:
        repo.clear(chat_id)
        return "Onboarding session expired. Send /start to begin again."

    profile_data = json.loads(payload_json)
    profile = IntervalsDerivedProfile(**profile_data)

    if user_text.strip().lower() in _CONFIRMATION_WORDS:
        flush_to_db(profile, conn)
        repo.save(chat_id, ConversationState.IDLE)
        try:
            generate_training_plan()
            return "Profile saved! Your training plan has been generated. Ask me anything to get started!"
        except Exception as exc:
            logger.exception("Plan generation error after onboarding")
            return f"Profile saved, but plan generation failed: {exc}"
    else:
        try:
            updated = apply_corrections(profile, user_text, client)
            updated_json = json.dumps(updated.__dict__)
            repo.save(chat_id, ConversationState.ONBOARDING_AWAITING_CONFIRMATION, updated_json)
            return format_confirmation_message(updated)
        except Exception as exc:
            logger.exception("Correction parsing error")
            return f"Couldn't apply that correction: {exc}. Please try again."


async def _handle_conflict(
    chat_id: int,
    user_text: str,
    payload_json: str | None,
    conn: sqlite3.Connection,
    repo: ConversationStateRepo,
) -> str:
    from t3.integrations import gcal as gcal_integration
    from t3.integrations import intervals as intervals_integration

    if payload_json is None:
        repo.clear(chat_id)
        return "No pending conflict found. You can ask me anything."

    data = json.loads(payload_json)
    conflict = ConflictInfo(**data["conflict"])
    pending = PendingConflict(
        conflict=conflict,
        moved_intervals_id=data.get("moved_intervals_id"),
        conflicting_intervals_id=data.get("conflicting_intervals_id"),
    )

    try:
        choice = int(user_text.strip())
    except ValueError:
        return "Please reply with 1, 2, or 3."

    class _GCal:
        def update_event_time(self, gcal_id: str, new_start: str) -> dict:
            return gcal_integration.update_event_time(gcal_id, new_start, db_path=settings.database_url)

        def delete_event(self, gcal_id: str) -> None:
            gcal_integration.delete_event(gcal_id, db_path=settings.database_url)

    class _Intervals:
        def update_workout_date(self, intervals_id: str, new_date: str) -> dict:
            return intervals_integration.update_workout_date(intervals_id, new_date)

        def delete_workout(self, intervals_id: str) -> None:
            intervals_integration.delete_workout(intervals_id)

    msg = resolve(choice, pending, conn, _GCal(), _Intervals())
    repo.clear(chat_id)
    return msg
