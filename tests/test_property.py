"""Lightweight property-style checks (no extra deps)."""

from __future__ import annotations

import random

from crashmin.ddmin import ddmin
from crashmin.json_reduce import reduce_json


def test_ddmin_always_subset_and_interesting():
    rng = random.Random(0)
    for _ in range(40):
        items = list(range(rng.randint(3, 16)))
        needed = set(rng.sample(items, k=rng.randint(1, min(3, len(items)))) )

        def interesting(subset, need=needed):
            return need.issubset(subset)

        out = ddmin(items, interesting)
        assert needed.issubset(out)
        assert set(out).issubset(items)
        # 1-minimal: dropping any leftover element loses interestingness
        for i, _ in enumerate(out):
            dropped = out[:i] + out[i + 1 :]
            if not needed.issubset(dropped):
                assert not interesting(dropped)


def test_json_reduce_never_grows_and_preserves_predicate():
    rng = random.Random(1)
    for _ in range(20):
        n = rng.randint(4, 12)
        keys = [f"k{i}" for i in range(n)]
        needed = keys[rng.randint(0, n - 1)]
        blob = {k: rng.randint(1, 9) for k in keys}
        blob[needed] = "keep-me"

        def interesting(value, key=needed):
            return isinstance(value, dict) and value.get(key) == "keep-me"

        out = reduce_json(blob, interesting)
        assert interesting(out)
        assert isinstance(out, dict)
        assert set(out).issubset(blob)
        assert len(str(out)) <= len(str(blob))
