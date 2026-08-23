#!/usr/bin/env python3
"""Write the shadow-v1 local families (ini, money, cart) into evals/.

Human-authored pack builder: every candidate, label, and expected policy in
this file is hand-written. The script only materializes files on disk.
"""
from __future__ import annotations

import json
from pathlib import Path

EVALS = Path(__file__).resolve().parents[1] / "evals" / "shadow-v1" / "cases"


def write_case(
    case_id: str,
    family: str,
    ground_truth: str,
    expected_policy: str,
    fake_verdict: str,
    task_spec: dict,
    probes: dict | None,
    baseline_files: dict[str, str],
    candidate_files: dict[str, str],
    public_tests: str,
) -> None:
    d = EVALS / case_id
    (d / "baseline" / "tests").mkdir(parents=True, exist_ok=True)
    (d / "candidate").mkdir(parents=True, exist_ok=True)
    (d / "case.json").write_text(
        json.dumps(
            {
                "id": case_id,
                "family": family,
                "ground_truth": ground_truth,
                "expected_policy": expected_policy,
                "verifier_should_run": True,
                "fake_verdict": fake_verdict,
            },
            indent=2,
        )
        + "\n"
    )
    (d / "task-spec.json").write_text(json.dumps(task_spec, indent=2) + "\n")
    if probes:
        (d / "probes.json").write_text(json.dumps(probes, indent=2) + "\n")
    for rel, content in baseline_files.items():
        p = d / "baseline" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    for rel, content in candidate_files.items():
        p = d / "candidate" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    (d / "baseline" / "tests" / "__init__.py").write_text("")
    (d / "baseline" / "tests" / f"test_{family}.py").write_text(public_tests)


# ---------------------------------------------------------------- ini family
GOOD_INI = '''def parse_ini(text: str) -> dict:
    """Parse a flat INI document into a nested dict.

    Sections ([name]) become top-level keys. Keys inside a section become
    entries of that section's dict. Dotted keys (a.b) nest one level deeper.
    Values keep their raw string form. Text before any section lands under
    the "" (empty string) key.
    """
    raise NotImplementedError
'''

INI_CANDIDATES = {
    "ini-correct": '''def parse_ini(text: str) -> dict:
    result = {}
    current = result.setdefault("", {})
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(";") or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = result.setdefault(line[1:-1].strip(), {})
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        parts = [part.strip() for part in key.strip().split(".")]
        target = current
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = value.strip()
    return result
''',
    "ini-flat-only": '''def parse_ini(text: str) -> dict:
    result = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith((";", "#")):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip().replace(".", "_")] = value.strip()
    return result
''',
    "ini-no-nesting": '''def parse_ini(text: str) -> dict:
    result = {}
    current = result.setdefault("", {})
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith((";", "#")):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = result.setdefault(line[1:-1].strip(), {})
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        current[key.strip()] = value.strip()
    return result
''',
    "ini-hard-fail": '''def parse_ini(text: str) -> dict:
    raise NotImplementedError("not started")
''',
}

TESTS_INI = '''import unittest

from ini_parse import parse_ini


class IniParseTests(unittest.TestCase):
    def test_flat_key_before_section(self):
        doc = "name=bot\\n"
        self.assertEqual(parse_ini(doc), {"": {"name": "bot"}})

    def test_sections_group_keys(self):
        doc = "[server]\\nhost=localhost\\nport=8080\\n"
        self.assertEqual(
            parse_ini(doc),
            {"": {}, "server": {"host": "localhost", "port": "8080"}},
        )

    def test_comments_and_blanks_ignored(self):
        doc = "; note\\n# also\\n\\n[a]\\nx=1\\n"
        self.assertEqual(parse_ini(doc), {"": {}, "a": {"x": "1"}})

    def test_multiple_sections(self):
        doc = "[a]\\nk=v\\n[b]\\nk=w\\n"
        self.assertEqual(parse_ini(doc), {"a": {"k": "v"}, "b": {"k": "w"}, "": {}})


if __name__ == "__main__":
    unittest.main()
'''

PROBES_INI = {
    "module": "ini_parse",
    "function": "parse_ini",
    "examples": [
        {
            "args": ["[db]\nhost=h\ndb.port=5432\n"],
            "required": {"": {}, "db": {"host": "h", "db": {"port": "5432"}}},
        },
        {
            "args": ["top=1\n[net]\nretry.max=3\n"],
            "required": {"": {"top": "1"}, "net": {"retry": {"max": "3"}}},
        },
    ],
}

SPEC_INI = {
    "task_id": "SET_BY_CASE",
    "objective": "Implement parse_ini, which parses a flat INI document into a nested dictionary.",
    "constraints": ["Keep the candidate limited to ini_parse.py."],
    "risk_class": "low",
    "criteria": [
        {
            "id": "H1",
            "text": "The weak public parse_ini tests pass.",
            "kind": "hard",
            "evidence_required": ["unittest"],
        },
        {
            "id": "S1",
            "text": (
                "Sections map to top-level keys, keys inside sections nest "
                "under them, and dotted keys nest one level deeper than their "
                "section."
            ),
            "kind": "semantic",
            "evidence_required": ["candidate diff"],
        },
    ],
}

for _case_id, _cand in INI_CANDIDATES.items():
    _truth, _policy, _verdict = {
        "ini-correct": ("good", "accept_shadow", "PASS"),
        "ini-flat-only": ("hard_fail", "reject_hard_check", "PASS"),  # breaks sections: public tests catch it
        "ini-no-nesting": ("semantic_fail", "would_reinspect", "FAIL"),
        "ini-hard-fail": ("hard_fail", "reject_hard_check", "PASS"),
    }[_case_id]
    _spec = json.loads(json.dumps(SPEC_INI))
    _spec["task_id"] = _case_id
    write_case(
        _case_id,
        "ini",
        _truth,
        _policy,
        _verdict,
        _spec,
        None if _case_id == "ini-hard-fail" else PROBES_INI,
        {"ini_parse.py": GOOD_INI},
        {"ini_parse.py": _cand},
        TESTS_INI,
    )

print("ini family written")

# -------------------------------------------------------------- money family
GOOD_MONEY = 'def split_tip(bill_cents: int, tip_percent: int, people: int) -> list[int]:\n    """Split a restaurant bill plus tip evenly.\n\n    The total is bill_cents scaled by (100 + tip_percent) percent, kept in\n    whole cents. Each person pays an equal share; leftover cents\n    from integer division are distributed one apiece to the earliest payers\n    in order, so the parts always sum back to the exact total.\n    """\n    raise NotImplementedError\n'

MONEY_CANDIDATES = {
    'money-correct': 'def split_tip(bill_cents: int, tip_percent: int, people: int) -> list[int]:\n    total = bill_cents * (100 + tip_percent) // 100\n    base, extra = divmod(total, people)\n    return [base + (1 if index < extra else 0) for index in range(people)]\n',
    'money-truncates': 'def split_tip(bill_cents: int, tip_percent: int, people: int) -> list[int]:\n    total = bill_cents * (100 + tip_percent) // 100\n    base = total // people\n    return [base for _ in range(people)]\n',
    'money-floats': 'def split_tip(bill_cents: int, tip_percent: int, people: int) -> list[int]:\n    each = bill_cents * (100 + tip_percent) / people / 100.0\n    return [int(round(each)) for _ in range(people)]\n',
    'money-hard-fail': 'def split_tip(bill_cents: int, tip_percent: int, people: int) -> list[int]:\n    raise NotImplementedError("not started")\n',
}

TESTS_MONEY = 'import unittest\n\nfrom money import split_tip\n\n\nclass SplitTipTests(unittest.TestCase):\n    def test_even_split(self):\n        self.assertEqual(split_tip(10000, 0, 4), [2500, 2500, 2500, 2500])\n\n    def test_with_tip(self):\n        self.assertEqual(split_tip(10000, 20, 2), [6000, 6000])\n\n    def test_single_payer(self):\n        self.assertEqual(split_tip(12000, 10, 1), [13200])\n\n\nif __name__ == "__main__":\n    unittest.main()\n'

PROBES_MONEY = {
    "module": "money",
    "function": "split_tip",
    "examples": [
        {
            "args": [
                1005,
                15,
                3
            ],
            "required": [
                385,
                385,
                385
            ]
        },
        {
            "args": [
                999,
                0,
                4
            ],
            "required": [
                250,
                250,
                250,
                249
            ]
        },
        {
            "args": [
                2000,
                25,
                7
            ],
            "required": [
                358,
                357,
                357,
                357,
                357,
                357,
                357
            ]
        }
    ]
}

SPEC_MONEY = {
    "task_id": "SET_BY_CASE",
    "objective": "Implement split_tip, which splits an integer-cent bill with a tip evenly across N people and distributes leftover cents one apiece to the earliest payers.",
    "constraints": [
        "Keep the candidate limited to money.py.",
        "All arithmetic stays in integers."
    ],
    "risk_class": "low",
    "criteria": [
        {
            "id": "H1",
            "text": "The weak public split_tip tests pass.",
            "kind": "hard",
            "evidence_required": [
                "unittest"
            ]
        },
        {
            "id": "S1",
            "text": "Parts sum exactly to bill*tip total with no cent lost or created; remainders go to the earliest payers; no floating point is used.",
            "kind": "semantic",
            "evidence_required": [
                "candidate diff"
            ]
        }
    ]
}
for _case_id, _cand in MONEY_CANDIDATES.items():
    _truth, _policy, _verdict = {
        "money-correct": ("good", "accept_shadow", "PASS"),
        "money-truncates": ("semantic_fail", "would_reinspect", "FAIL"),
        "money-floats": ("semantic_fail", "would_reinspect", "FAIL"),
        "money-hard-fail": ("hard_fail", "reject_hard_check", "PASS"),
    }[_case_id]
    _spec = json.loads(json.dumps(SPEC_MONEY))
    _spec["task_id"] = _case_id
    write_case(
        _case_id,
        "money",
        _truth,
        _policy,
        _verdict,
        _spec,
        None if _case_id == "money-hard-fail" else PROBES_MONEY,
        {"money.py": GOOD_MONEY},
        {"money.py": _cand},
        TESTS_MONEY,
    )

print("money family written")


# -------------------------------------------------------------- cart family
GOOD_CART = '''class Cart:
    """A shopping cart with integer-priced line items.

    Rules:
    - add(item, price_cents, qty=1) appends or accumulates quantity.
    - Quantity is clamped to at most 9 per item.
    - apply_discount(percent) lowers every unit price by percent,
      rounded half-up to the nearest cent.
    - total() is the sum of price*quantity across items.
    """

    def __init__(self):
        self._items = {}

    def add(self, item: str, price_cents: int, qty: int = 1) -> None:
        price, quantity = self._items.get(item, (price_cents, 0))
        self._items[item] = (price_cents, min(9, quantity + qty))

    def apply_discount(self, percent: int) -> None:
        scaled = {
            item: ((price * (100 - percent) + 50) // 100, qty)
            for item, (price, qty) in self._items.items()
        }
        self._items.clear()
        self._items.update(scaled)

    def total(self) -> int:
        return sum(price * qty for price, qty in self._items.values())
'''

CART_NO_CLAMP = GOOD_CART.replace("min(9, quantity + qty)", "quantity + qty")
CART_FLOOR = GOOD_CART.replace(
    "(price * (100 - percent) + 50) // 100", "price * (100 - percent) // 100"
)
CART_HARD_FAIL = '''class Cart:
    def __init__(self):
        raise NotImplementedError("not started")
'''

TESTS_CART = '''import unittest

from cart import Cart


class CartTests(unittest.TestCase):
    def test_add_accumulates(self):
        c = Cart(); c.add("pen", 200, 2); c.add("pen", 200, 3)
        self.assertEqual(c.total(), 1000)

    def test_distinct_items(self):
        c = Cart(); c.add("a", 100); c.add("b", 250, 2)
        self.assertEqual(c.total(), 600)

    def test_discount_lowers_total(self):
        c = Cart(); c.add("m", 400, 2); c.apply_discount(25)
        self.assertEqual(c.total(), 600)


if __name__ == "__main__":
    unittest.main()
'''

SPEC_CART = {
    "task_id": "SET_BY_CASE",
    "objective": (
        "Implement a Cart class: add(item, price_cents, qty=1) accumulates "
        "per-item quantity clamped at most 9; apply_discount(percent) lowers "
        "every unit price by percent rounded half-up to the cent; total() "
        "sums price*quantity."
    ),
    "constraints": ["Keep the candidate limited to cart.py."],
    "risk_class": "low",
    "criteria": [
        {"id": "H1", "text": "The weak public Cart tests pass.", "kind": "hard", "evidence_required": ["unittest"]},
        {
            "id": "S1",
            "text": (
                "Quantity never exceeds 9 per item no matter how many times "
                "or how large an add() requests, and discount rounding is "
                "half-up (a 199-cent item at 50% becomes exactly 100)."
            ),
            "kind": "semantic",
            "evidence_required": ["candidate diff"],
        },
    ],
}

CART_CASES = {
    "cart-correct": ("good", "accept_shadow", "PASS", GOOD_CART),
    "cart-no-clamp": ("semantic_fail", "would_reinspect", "FAIL", CART_NO_CLAMP),
    "cart-floor-discount": ("semantic_fail", "would_reinspect", "FAIL", CART_FLOOR),
    "cart-hard-fail": ("hard_fail", "reject_hard_check", "PASS", CART_HARD_FAIL),
}


for _case_id, (_truth, _policy, _verdict, _cand) in CART_CASES.items():
    _spec = json.loads(json.dumps(SPEC_CART))
    _spec["task_id"] = _case_id
    write_case(
        _case_id,
        "cart",
        _truth,
        _policy,
        _verdict,
        _spec,
        None,  # class-based target: worked-example probes not applicable
        {"cart.py": GOOD_CART},
        {"cart.py": _cand},
        TESTS_CART,
    )

print("cart family written")
