"""Hierarchical reduction of JSON values."""

from __future__ import annotations

from typing import Any, Callable

from crashmin.ddmin import ddmin

Interesting = Callable[[Any], bool]


def reduce_json(value: Any, interesting: Interesting) -> Any:
    """Shrink *value* while *interesting(candidate)* stays true.

    Walks objects → arrays → primitives. Never falls back to raw bytes.
    One structural pass — no flip-flopping between equally-interesting values.
    """
    if not interesting(value):
        return value
    return _reduce_once(value, interesting)


def _reduce_once(value: Any, interesting: Interesting) -> Any:
    if isinstance(value, dict):
        return _reduce_object(value, interesting)
    if isinstance(value, list):
        return _reduce_array(value, interesting)
    if isinstance(value, str):
        return _reduce_string(value, interesting)
    if isinstance(value, bool):
        return _reduce_bool(value, interesting)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _reduce_number(value, interesting)
    if value is not None and interesting(None):
        return None
    return value


def _reduce_object(obj: dict[str, Any], interesting: Interesting) -> dict[str, Any]:
    keys = list(obj.keys())

    def test(subset: list[str]) -> bool:
        return interesting({k: obj[k] for k in subset})

    kept_keys = ddmin(keys, test, assume_original=True)
    current = {k: obj[k] for k in kept_keys}

    for key in list(current.keys()):
        original = current[key]

        def inner(candidate: Any, k: str = key, base: dict[str, Any] = current) -> bool:
            trial = dict(base)
            trial[k] = candidate
            return interesting(trial)

        shrunk = reduce_json(original, inner)
        if shrunk != original:
            current[key] = shrunk

        # Prefer a smaller stand-in when the concrete value does not matter.
        # Only try a short, ordered list; never both booleans (that oscillates).
        for alt in (None, 0, "", []):
            if alt == current[key]:
                continue
            if inner(alt):
                current[key] = alt
                break
    return current


def _reduce_array(arr: list[Any], interesting: Interesting) -> list[Any]:
    indices = list(range(len(arr)))

    def test(subset: list[int]) -> bool:
        return interesting([arr[i] for i in subset])

    kept = ddmin(indices, test, assume_original=True)
    current = [arr[i] for i in kept]

    for i, original in enumerate(list(current)):

        def inner(candidate: Any, idx: int = i, base: list[Any] = current) -> bool:
            trial = list(base)
            trial[idx] = candidate
            return interesting(trial)

        shrunk = reduce_json(original, inner)
        if shrunk != original:
            current[i] = shrunk
    return current


def _reduce_string(text: str, interesting: Interesting) -> str:
    if interesting(""):
        return ""
    # Binary-search the shortest prefix that still fails.
    lo, hi = 1, len(text)
    best = text
    while lo <= hi:
        mid = (lo + hi) // 2
        cand = text[:mid]
        if interesting(cand):
            best = cand
            hi = mid - 1
        else:
            lo = mid + 1
    # Try a one-character string if any character alone works.
    if len(best) > 1:
        for ch in dict.fromkeys(best):
            if interesting(ch):
                return ch
    return best


def _reduce_number(num: int | float, interesting: Interesting) -> int | float:
    candidates: list[int | float] = [0, 1, -1]
    if isinstance(num, float) and num != int(num):
        candidates.append(int(num))
    for cand in candidates:
        if cand != num and interesting(cand):
            return cand
    return num


def _reduce_bool(value: bool, interesting: Interesting) -> Any:
    # Canonicalize toward false / 0, never flip both ways.
    if value is True and interesting(False):
        return False
    if interesting(0):
        return 0
    return value
