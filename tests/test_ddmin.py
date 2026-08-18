from crashmin.ddmin import ddmin, split


def test_split_even():
    assert split(list(range(4)), 2) == [[0, 1], [2, 3]]


def test_split_uneven():
    chunks = split(list(range(5)), 3)
    assert [len(c) for c in chunks] == [2, 2, 1]
    assert sum(chunks, []) == list(range(5))


def test_ddmin_single_needed():
    items = list("abcdefgh")

    def interesting(subset):
        return "d" in subset

    assert ddmin(items, interesting) == ["d"]


def test_ddmin_pair_needed():
    items = list("abcdef")

    def interesting(subset):
        return "b" in subset and "e" in subset

    assert ddmin(items, interesting) == ["b", "e"]


def test_ddmin_empty_is_interesting():
    assert ddmin([1, 2, 3], lambda s: True) == []


def test_ddmin_all_needed():
    items = [1, 2, 3]

    def interesting(subset):
        return set(subset) == {1, 2, 3}

    assert ddmin(items, interesting) == [1, 2, 3]


def test_ddmin_idempotent_on_minimal():
    items = ["only"]
    assert ddmin(items, lambda s: "only" in s) == ["only"]
