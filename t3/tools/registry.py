from __future__ import annotations

from typing import Any, Callable, cast


class ToolRegistry:
    def __init__(self) -> None:
        self._functions: list[Callable[..., Any]] = []
        self._handlers: dict[str, Callable[..., Any]] = {}

    def register(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        self._functions.append(fn)
        self._handlers[cast(Any, fn).__name__] = fn
        return fn

    @property
    def functions(self) -> list[Callable[..., Any]]:
        return list(self._functions)

    def dispatch(self, name: str, args: dict[str, Any]) -> Any:
        handler = self._handlers.get(name)
        if handler is None:
            return f"[unknown tool: {name}]"
        return handler(**args)


REGISTRY = ToolRegistry()
tool = REGISTRY.register
