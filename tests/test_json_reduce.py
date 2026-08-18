from crashmin.json_reduce import reduce_json


def test_drop_unused_keys_keep_nested_trigger():
    blob = {
        "noise": 1,
        "payload": {
            "unused": True,
            "deeply": {
                "ignored": "x",
                "nested": {"trigger": "boom", "extra": 1},
            },
        },
        "arr": [1, 2, 3],
    }

    def interesting(value):
        try:
            return value["payload"]["deeply"]["nested"]["trigger"] == "boom"
        except Exception:
            return False

    out = reduce_json(blob, interesting)
    assert out == {"payload": {"deeply": {"nested": {"trigger": "boom"}}}}


def test_array_keeps_only_needed_item():
    blob = {"items": [{"kind": "ok"}, {"kind": "evil", "pad": 1}, {"kind": "ok"}]}

    def interesting(value):
        items = value.get("items") if isinstance(value, dict) else None
        return isinstance(items, list) and any(
            isinstance(i, dict) and i.get("kind") == "evil" for i in items
        )

    out = reduce_json(blob, interesting)
    assert out == {"items": [{"kind": "evil"}]}


def test_pair_fields_kept_together():
    blob = {"alpha": "one", "beta": "two", "gamma": "nope"}

    def interesting(value):
        return isinstance(value, dict) and value.get("alpha") == "one" and value.get("beta") == "two"

    out = reduce_json(blob, interesting)
    assert out == {"alpha": "one", "beta": "two"}


def test_shorten_string_prefix():
    def interesting(value):
        return isinstance(value, str) and value.startswith("bo")

    assert reduce_json("boomxxxx", interesting) == "bo"
