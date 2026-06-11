from t3.db import init_db
from t3.bot.onboarding import (
    QUESTIONS,
    TRANSITIONS,
    OnboardingSession,
    OnboardingState,
    flush_to_db,
)

# Answers in the order the state machine asks for them (START → COMPLETE)
FULL_ANSWERS = [
    "Manuel",  # name
    "32",  # age
    "male",  # sex
    "intermediate",  # experience
    "10",  # weekly_hours
    "1500m in 28min",  # swim_baseline
    "40km in 65min",  # bike_baseline
    "10km in 50min",  # run_baseline
    "Sprint July 2026",  # upcoming_races
    "none",  # injury_history
    "digest",  # notifications
]


def _run_full_flow(answers: list[str] = FULL_ANSWERS) -> OnboardingSession:
    session = OnboardingSession()
    session.state = OnboardingState.ASK_NAME
    for answer in answers:
        session.advance(answer)
    return session


# --- state machine ---


def test_initial_state_is_start() -> None:
    session = OnboardingSession()
    assert session.state == OnboardingState.START
    assert not session.is_complete()


def test_start_has_no_question() -> None:
    session = OnboardingSession()
    assert session.current_question() is None


def test_ask_name_has_question() -> None:
    session = OnboardingSession()
    session.state = OnboardingState.ASK_NAME
    question = session.current_question()
    assert question is not None
    assert "name" in question.lower()


def test_advance_stores_answer_and_transitions() -> None:
    session = OnboardingSession()
    session.state = OnboardingState.ASK_NAME
    next_state = session.advance("Manuel")
    assert next_state == OnboardingState.ASK_AGE
    assert session.answers["name"] == "Manuel"


def test_all_transitions_form_a_linear_chain_with_no_cycles() -> None:
    state = OnboardingState.START
    visited: set[OnboardingState] = set()
    while state != OnboardingState.COMPLETE:
        assert state not in visited, f"Cycle at {state}"
        visited.add(state)
        state = TRANSITIONS.get(state, OnboardingState.COMPLETE)


def test_every_non_terminal_state_has_a_question() -> None:
    skip = {OnboardingState.START, OnboardingState.COMPLETE}
    for state in OnboardingState:
        if state in skip:
            continue
        assert state in QUESTIONS, f"Missing question for {state}"


def test_full_flow_reaches_complete() -> None:
    session = _run_full_flow()
    assert session.is_complete()


def test_full_flow_stores_all_answers() -> None:
    session = _run_full_flow()
    assert session.answers["name"] == "Manuel"
    assert session.answers["age"] == "32"
    assert session.answers["experience"] == "intermediate"
    assert session.answers["notifications"] == "digest"


def test_advance_strips_whitespace() -> None:
    session = OnboardingSession()
    session.state = OnboardingState.ASK_NAME
    session.advance("  Manuel  ")
    assert session.answers["name"] == "Manuel"


# --- db flush ---


def test_flush_creates_athlete_profile_row() -> None:
    conn = init_db()
    session = _run_full_flow()
    row_id = flush_to_db(session, conn)
    assert row_id == 1


def test_flush_stores_name_and_age() -> None:
    conn = init_db()
    session = _run_full_flow()
    flush_to_db(session, conn)
    row = conn.execute("SELECT name, age FROM athlete_profile WHERE id = 1").fetchone()
    assert row[0] == "Manuel"
    assert row[1] == 32


def test_flush_stores_non_numeric_age_as_null() -> None:
    answers = FULL_ANSWERS.copy()
    answers[1] = "thirty-two"  # non-numeric age
    conn = init_db()
    session = _run_full_flow(answers)
    flush_to_db(session, conn)
    row = conn.execute("SELECT age FROM athlete_profile WHERE id = 1").fetchone()
    assert row[0] is None


def test_flush_multiple_sessions_get_separate_rows() -> None:
    conn = init_db()
    flush_to_db(_run_full_flow(), conn)
    flush_to_db(_run_full_flow(), conn)
    count = conn.execute("SELECT COUNT(*) FROM athlete_profile").fetchone()[0]
    assert count == 2
