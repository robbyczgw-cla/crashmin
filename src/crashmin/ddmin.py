"""Classic minimizing delta debugging (Zeller / Hildebrandt)."""

from __future__ import annotations

from typing import Callable, Sequence, TypeVar

T = TypeVar("T")


class NotInteresting(RuntimeError):
    pass


def split(items: Sequence[T], n: int) -> list[list[T]]:
    items = list(items)
    if n <= 1:
        return [items]
    n = min(n, len(items))
    size, extra = divmod(len(items), n)
    chunks: list[list[T]] = []
    index = 0
    for i in range(n):
        take = size + (1 if i < extra else 0)
        chunks.append(items[index : index + take])
        index += take
    return [c for c in chunks if c]


def ddmin(
    items: Sequence[T],
    interesting: Callable[[list[T]], bool],
    *,
    assume_original: bool = False,
    complement_first: bool = True,
) -> list[T]:
    """Return a 1-minimal interesting subset of *items*.

    `interesting` must be True for the original list. If the empty list is
    interesting it is returned immediately.

    HTTP requests are usually "one needle in a haystack of tracking junk",
    so complements are tried first by default.
    """
    current = list(items)
    if not current:
        return current
    if not assume_original and not interesting(current):
        raise NotInteresting("original configuration is not interesting")
    if interesting([]):
        return []

    n = 2
    while True:
        if n > len(current):
            return current
        subsets = split(current, n)
        progressed = False

        def try_subsets() -> bool:
            nonlocal current, n
            for subset in subsets:
                if interesting(subset):
                    current = subset
                    n = 2
                    return True
            return False

        def try_complements() -> bool:
            nonlocal current, n
            if not (n > 2 or len(subsets) > 1):
                return False
            for subset in subsets:
                complement = without(current, subset)
                if not complement:
                    continue
                if interesting(complement):
                    current = complement
                    n = max(n - 1, 2)
                    return True
            return False

        if complement_first:
            progressed = try_complements() or try_subsets()
        else:
            progressed = try_subsets() or try_complements()
        if progressed:
            continue
        if n >= len(current):
            return current
        n = min(len(current), 2 * n)


def without(items: list[T], subset: list[T]) -> list[T]:
    """Remove one occurrence of each element of subset, preserving order."""
    remaining = list(items)
    for piece in subset:
        try:
            remaining.remove(piece)
        except ValueError:
            continue
    return remaining
