import logging
from typing import Any

from google import genai
from google.genai import types

from t3.config import settings
from t3.tools.gcal_tools import GCAL_FUNCTIONS, GCAL_HANDLERS
from t3.tools.intervals_tools import INTERVALS_FUNCTIONS, INTERVALS_HANDLERS

logger = logging.getLogger(__name__)

ALL_FUNCTIONS = GCAL_FUNCTIONS + INTERVALS_FUNCTIONS
ALL_HANDLERS: dict[str, Any] = {**GCAL_HANDLERS, **INTERVALS_HANDLERS}

_MAX_TURNS = 10


def build_client() -> genai.Client:
    return genai.Client(api_key=settings.gemini_api_key)


def dispatch_tool(name: str, args: dict[str, Any]) -> Any:
    handler = ALL_HANDLERS.get(name)
    if handler is None:
        return f"[unknown tool: {name}]"
    return handler(**args)


async def run(text: str, client: genai.Client) -> str:
    """Send a message and loop until the model returns a text response.

    Dispatches all tool calls the model makes, feeds results back, and
    repeats until Gemini produces a final text answer (no more function
    calls) or the turn limit is hit.
    """
    contents: list = [text]
    config = types.GenerateContentConfig(tools=ALL_FUNCTIONS)

    for _ in range(_MAX_TURNS):
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=contents,
            config=config,
        )
        candidate = response.candidates[0]
        calls = [
            part.function_call
            for part in candidate.content.parts
            if getattr(part, "function_call", None)
        ]

        if not calls:
            return response.text or ""

        contents.append(candidate.content)
        result_parts = [
            types.Part(
                function_response=types.FunctionResponse(
                    name=fn.name,
                    response={"result": dispatch_tool(fn.name, dict(fn.args))},
                )
            )
            for fn in calls
        ]
        contents.append(types.Content(role="user", parts=result_parts))

    logger.warning("agent.run reached turn limit (%d) without a text response", _MAX_TURNS)
    return ""
