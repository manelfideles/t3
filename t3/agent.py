import logging
from typing import Any

from google import genai
from google.genai import types

from t3.config import settings
import t3.tools.gcal  # noqa: F401 — registers gcal tools on import
import t3.tools.intervals  # noqa: F401 — registers intervals tools on import
from t3.tools.registry import REGISTRY

logger = logging.getLogger(__name__)

_MAX_TURNS = 5


def build_client() -> genai.Client:
    return genai.Client(api_key=settings.gemini_api_key)


def dispatch_tool(name: str, args: dict[str, Any]) -> Any:
    return REGISTRY.dispatch(name, args)


async def run(text: str, client: genai.Client) -> str:
    """Send a message and loop until the model returns a text response.

    Dispatches all tool calls the model makes, feeds results back, and
    repeats until Gemini produces a final text answer (no more function
    calls) or the turn limit is hit.
    """
    contents: list = [text]
    config = types.GenerateContentConfig(tools=REGISTRY.functions)

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
            if getattr(
                part,
                "function_call",
                None,
            )
        ]

        if not calls:
            return response.text or ""

        contents.append(candidate.content)
        result_parts = [
            types.Part(
                function_response=types.FunctionResponse(
                    name=fn.name,
                    response={
                        "result": dispatch_tool(
                            fn.name,
                            dict(fn.args),
                        )
                    },
                )
            )
            for fn in calls
        ]
        contents.append(types.Content(role="user", parts=result_parts))

    logger.warning("agent.run reached turn limit (%d) without a text response", _MAX_TURNS)
    return ""
