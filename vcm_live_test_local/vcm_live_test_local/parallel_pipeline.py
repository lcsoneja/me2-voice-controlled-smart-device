"""Testable primitives for the monitor's parallel all-gates page."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

T = TypeVar("T")


def run_in_parallel(tasks: Mapping[str, Callable[[], T]]) -> dict[str, T]:
    """Run one independent inference callable per gate concurrently; preserve keys/results."""
    if not tasks:
        raise ValueError("parallel inference requires at least one task")
    with ThreadPoolExecutor(max_workers=len(tasks), thread_name_prefix="vcm-gate") as pool:
        futures = {name: pool.submit(task) for name, task in tasks.items()}
        return {name: future.result() for name, future in futures.items()}


def select_parallel_action(*, wake_active: bool, intent: str | None,
                           intent_confidence: float, threshold: float,
                           specialists: Mapping[str, Mapping[str, Any]],
                           routing: Mapping[str, str]) -> dict[str, Any]:
    """Gate an intent light on confirmed wake + G2 threshold; show routed slot value."""
    if not wake_active or intent is None or intent_confidence < threshold:
        return {"active": False, "intent": intent, "route": None, "gate": None, "value": None,
                "final": None, "intent_conf": float(intent_confidence)}

    route = routing.get(intent)
    if route is None:
        specialist = None
    else:
        specialist = specialists.get(route)
    value = specialist.get("label") if specialist else None
    final = value if value else intent
    return {"active": True, "intent": intent, "route": route, "gate": route, "value": value,
            "final": final, "intent_conf": float(intent_confidence),
            "slot_conf": float(specialist["conf"]) if specialist and specialist.get("conf") is not None else None}
