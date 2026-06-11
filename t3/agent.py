import asyncio
import logging
from typing import Any

from google import genai
from google.genai import types

import t3.tools.gcal  # noqa: F401 — triggers @tool registration
import t3.tools.intervals  # noqa: F401 — triggers @tool registration
from t3.config import settings
from t3.tools.registry import REGISTRY

logger = logging.getLogger(__name__)

_MAX_TURNS = 5
_RETRYABLE = {"429", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE"}


def build_client() -> genai.Client:
    return genai.Client(api_key=settings.gemini_api_key)


def dispatch_tool(name: str, args: dict[str, Any]) -> Any:
    return REGISTRY.dispatch(name, args)


async def _generate(client: genai.Client, contents: list, config: types.GenerateContentConfig):
    """Single generate_content call with exponential-backoff retry on transient errors."""
    delay = 2.0
    for attempt in range(4):
        try:
            return client.models.generate_content(
                model=settings.gemini_model,
                contents=contents,
                config=config,
            )
        except Exception as exc:
            msg = str(exc)
            if any(code in msg for code in _RETRYABLE) and attempt < 3:
                logger.warning(
                    "Gemini transient error (attempt %d/3), retrying in %.0fs: %s",
                    attempt + 1, delay, msg[:120],
                )
                await asyncio.sleep(delay)
                delay *= 2
            else:
                raise


async def run(text: str, client: genai.Client) -> str:
    """Send a message and loop until the model returns a text response.

    Dispatches all tool calls the model makes, feeds results back, and
    repeats until Gemini produces a final text answer (no more function
    calls) or the turn limit is hit.
    """
    contents: list = [text]
    config = types.GenerateContentConfig(tools=REGISTRY.functions)

    for _ in range(_MAX_TURNS):
        response = await _generate(client, contents, config)
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
