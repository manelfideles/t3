from __future__ import annotations

from t3.sync import ConflictInfo


def conflict_prompt(conflict: ConflictInfo, original_time: str, new_time: str) -> str:
    return (
        f"⚠️ *Schedule conflict detected!*\n\n"
        f"You moved a session to *{new_time[:10]}*, but another session is already scheduled that day.\n\n"
        f"Choose a resolution:\n"
        f"1️⃣ Revert move — put the moved session back to {original_time[:16]}\n"
        f"2️⃣ Keep move, remove other — keep the moved session, delete the conflicting one\n"
        f"3️⃣ Remove moved — delete the session you just moved\n\n"
        f"Reply with 1, 2, or 3."
    )


def weather_warning(location: str, forecast: str) -> str:
    raise NotImplementedError


def weekly_digest(summary: str) -> str:
    raise NotImplementedError


def vacation_probe(athlete_name: str) -> str:
    raise NotImplementedError
