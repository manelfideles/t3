from __future__ import annotations

import importlib
import pkgutil
from typing import Any, Callable, cast


class ToolRegistry:
    def __init__(self) -> None:
        self._functions: list[Callable[..., Any]] = []
        self._handlers: dict[str, Callable[..., Any]] = {}

    def register(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        self._functions.append(fn)
        self._handlers[cast(Any, fn).__name__] = fn
        return fn

    def discover(self, package: str) -> None:
        """Import every module under *package* so their @tool decorators fire."""
        mod = importlib.import_module(package)
        pkg_path = getattr(mod, "__path__", None)
        if pkg_path is None:
            return
        for _, name, _ in pkgutil.walk_packages(pkg_path, prefix=f"{package}."):
            importlib.import_module(name)

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
