from __future__ import annotations

from typing import Any, Callable


class ToolRegistry:
    def __init__(self) -> None:
        self._functions: list[Callable] = []
        self._handlers: dict[str, Callable] = {}

    def register(self, fn: Callable) -> Callable:
        self._functions.append(fn)
        self._handlers[fn.__name__] = fn
        return fn

    @property
    def functions(self) -> list[Callable]:
        return list(self._functions)

    def dispatch(self, name: str, args: dict[str, Any]) -> Any:
        handler = self._handlers.get(name)
        if handler is None:
            return f"[unknown tool: {name}]"
        return handler(**args)


REGISTRY = ToolRegistry()
tool = REGISTRY.register
