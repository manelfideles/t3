import asyncio
from datetime import datetime
from typing import Any, cast

from google import genai
from google.genai import types

from t3.config import settings
from t3.logger import logger
from t3.tools.registry import REGISTRY

REGISTRY.discover("t3.tools")

_MAX_TURNS = 5
_RETRYABLE = {"429", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE"}
_FALLBACK_CODES = {"503", "UNAVAILABLE", "404", "NOT_FOUND"}


def build_client() -> genai.Client:
    return genai.Client(api_key=settings.gemini_api_key)


def dispatch_tool(name: str, args: dict[str, Any]) -> Any:
    return REGISTRY.dispatch(name, args)


async def _try_model(
    client: genai.Client,
    model: str,
    contents: list,
    config: types.GenerateContentConfig,
):
    """Call generate_content for one model with exponential-backoff retry on transient errors."""
    delay = 2.0
    for attempt in range(4):
        try:
            return await asyncio.to_thread(
                client.models.generate_content,
                model=model,
                contents=contents,
                config=config,
            )
        except Exception as exc:
            msg = str(exc)
            if any(code in msg for code in _RETRYABLE) and attempt < 3:
                logger.warning(
                    "Gemini %s transient error (attempt %d/3), retrying in %.0fs: %s",
                    model,
                    attempt + 1,
                    delay,
                    msg[:120],
                )
                await asyncio.sleep(delay)
                delay *= 2
            else:
                raise


async def generate_response(
    client: genai.Client,
    contents: list,
    config: types.GenerateContentConfig,
):
    """Try the primary model; fall back to `gemini_fallback_model` on `503`/`404`."""
    try:
        return await _try_model(client, settings.gemini_model, contents, config)
    except Exception as exc:
        fallback = settings.gemini_fallback_model
        if fallback and fallback != settings.gemini_model and any(c in str(exc) for c in _FALLBACK_CODES):
            logger.warning(
                "Primary model %s unavailable (%s), falling back to %s",
                settings.gemini_model,
                str(exc)[:80],
                fallback,
            )
            return await _try_model(client, fallback, contents, config)
        raise


async def run(text: str, client: genai.Client) -> str:
    """Send a message and loop until the model returns a text response.

    Dispatches all tool calls the model makes, feeds results back, and
    repeats until Gemini produces a final text answer (no more function
    calls) or the turn limit is hit.
    """
    now = datetime.now().strftime("%A, %d %B %Y %H:%M")
    contents: list = [text]
    config = types.GenerateContentConfig(
        tools=cast(list[Any], REGISTRY.functions),
        system_instruction=(
            f"You are T3, a personal triathlon training assistant. "
            f"The current date and time is {now}. "
            "When the user refers to relative dates (today, tomorrow, next Monday, etc.) "
            "resolve them to exact dates before calling any tools. "
            "Be extremely concise. Sacrifice grammar for the sake of concision."
        ),
    )

    for _ in range(_MAX_TURNS):
        response = await generate_response(client, contents, config)
        candidate = response.candidates[0]
        if candidate.content is None:
            return response.text or ""
        calls = [part.function_call for part in candidate.content.parts if getattr(part, "function_call", None)]

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
