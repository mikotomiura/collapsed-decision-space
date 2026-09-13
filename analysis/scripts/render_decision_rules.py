#!/usr/bin/env python3
"""Render the sealed decision rules as the markdown block the protocol carries.

The manuscript used to state its decision rules in hand-written prose and the sealed file used to
state them again in JSON. Two statements of the same thing drift, and a drift check written as a
parser of the prose drifts with them -- it has to be taught every way a sentence can be phrased,
and it fails open on the phrasing it was not taught.

So the prose is not parsed. It is **generated**. ``seal/decision-rules.json`` is the only statement
of the rules; this module renders it into one canonical markdown block, and ``verify_seal.py``
requires that block to appear verbatim between the markers in ``manuscript/main.md`` and
``seal/protocol.md``. Editing a threshold in the manuscript then fails because the generated text no
longer matches, and editing it in the sealed file fails because the seal hash no longer matches.
There is no third place to edit.

The renderer is itself sealed. A renderer that could be changed after the fact could be taught to
emit whatever the manuscript happens to say.

What this establishes: the rule text in the manuscript is a function of the sealed rules.
What it does not: that the rules are the right rules, or when they were fixed.

Usage:
    python analysis/scripts/render_decision_rules.py            # print the block
    python analysis/scripts/render_decision_rules.py --check    # exit 1 if a carrier has drifted
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _provenance import load_json  # noqa: E402

BEGIN_MARKER: str = "<!-- BEGIN GENERATED FROM seal/decision-rules.json -- DO NOT EDIT BY HAND -->"
END_MARKER: str = "<!-- END GENERATED FROM seal/decision-rules.json -->"

#: Files that must carry the generated block. The manuscript is here because a reader reads the
#: manuscript; the protocol is here because the deposit holds the protocol.
BLOCK_CARRIERS: tuple[str, ...] = (
    "manuscript/main.md",
    "seal/protocol.md",
)

#: How each comparison is written. Deliberately not the JSON operator names: the block is read by
#: humans, and ``gte`` on a page is worse than ``>=``.
_OP_TEXT: dict[str, str] = {
    "lt": "<",
    "lte": "≤",
    "gt": ">",
    "gte": "≥",
    "eq": "==",
    "ne": "!=",
}

_AND = " ∧ "
_OR = " ∨ "


def _literal(value: Any) -> str:
    """Render a JSON scalar the way the JSON file holds it, not the way Python prints it."""
    return json.dumps(value, ensure_ascii=False)


def _render_predicate(predicate: dict[str, Any]) -> str:
    if "combine" in predicate:
        joiner = _AND if predicate["combine"] == "all" else _OR
        inner = joiner.join(_render_predicate(member) for member in predicate["predicates"])
        return f"({inner})"
    quantity = predicate["quantity"]
    op = predicate["op"]
    if op == "abs_diff_lte":
        centre = _literal(predicate["centre"])
        return f"|`{quantity}` − {centre}| ≤ {_literal(predicate['value'])}"
    return f"`{quantity}` {_OP_TEXT[op]} {_literal(predicate['value'])}"


def _render_rule(rule: dict[str, Any]) -> list[str]:
    joiner = _AND if rule["combine"] == "all" else _OR
    conditions = joiner.join(_render_predicate(member) for member in rule["predicates"])
    lines = [
        f"**{rule['id']} — {rule['label']}** · arm `{rule['arm']}` "
        f"· role `{rule['role']}`",
        "",
        f"- **Satisfied when**: {conditions}",
    ]
    if rule.get("rationale"):
        lines.append(f"- **Why these values**: {rule['rationale']}")
    for outcome_key, prefix in (("on_pass", "Satisfied"), ("on_fail", "Not satisfied")):
        outcome = rule[outcome_key]
        text = f"- **{prefix} → {outcome['action']}.**"
        if outcome.get("states"):
            text += f" {outcome['states']}"
        lines.append(text)
    lines.append("")
    return lines


def render(rules: dict[str, Any]) -> str:
    """Return the canonical block, markers included."""
    estimand = rules["estimand"]
    arms = rules["arms"]
    order = " → ".join(rules["evaluation_order"])
    by_id = {rule["id"]: rule for rule in rules["rules"]}

    lines = [
        BEGIN_MARKER,
        "",
        f"**Estimand.** `{estimand['quantity']}` — {estimand['definition']} "
        f"Materiality margin: {_literal(estimand['materiality_margin'])}.",
        "",
        "**Arms.** "
        + " · ".join(
            f"`{name}` = `{arm['model']}` — {arm['role']}"
            for name, arm in sorted(arms.items())
        ),
        "",
        f"**Evaluation order: {order}.** Evaluation is strictly ordered and stops at the first "
        "rule whose action is `stop`.",
        "",
    ]
    if rules.get("order_note"):
        lines += [rules["order_note"], ""]
    for rule_id in rules["evaluation_order"]:
        lines += _render_rule(by_id[rule_id])
    notes = rules.get("quantity_notes") or {}
    if notes:
        lines += ["**Quantities that are easy to misread.**", ""]
        lines += [f"- `{name}` — {text}" for name, text in sorted(notes.items())]
        lines.append("")
    lines.append(END_MARKER)
    return "\n".join(lines)


def extract_block(text: str, label: str) -> str:
    """Pull the marked block out of a carrier file. Absent or duplicated markers are errors."""
    if text.count(BEGIN_MARKER) != 1 or text.count(END_MARKER) != 1:
        raise ValueError(
            f"{label}: expected exactly one generated block, found "
            f"{text.count(BEGIN_MARKER)} start and {text.count(END_MARKER)} end markers"
        )
    start = text.index(BEGIN_MARKER)
    end = text.index(END_MARKER) + len(END_MARKER)
    if end <= start:
        raise ValueError(f"{label}: the end marker precedes the start marker")
    return text[start:end]


def _first_difference(expected: str, found: str) -> str:
    expected_lines = expected.splitlines()
    found_lines = found.splitlines()
    for index, (left, right) in enumerate(zip(expected_lines, found_lines), start=1):
        if left != right:
            return (
                f"First difference at line {index} of the block:\n"
                f"      sealed renders: {left}\n"
                f"      the file holds: {right}"
            )
    if len(expected_lines) != len(found_lines):
        return (
            f"The file holds {len(found_lines)} lines; the sealed rules render "
            f"{len(expected_lines)}."
        )
    return "The blocks differ in trailing whitespace only."


def check(root: Path) -> list[str]:
    """Return one problem per carrier whose block is not what the sealed rules render to."""
    expected = render(load_json(root / "seal" / "decision-rules.json"))
    problems: list[str] = []
    for rel in BLOCK_CARRIERS:
        path = root / rel
        if not path.is_file():
            problems.append(f"{rel}: missing, but it must carry the generated rule block")
            continue
        try:
            found = extract_block(path.read_text(encoding="utf-8"), rel)
        except ValueError as exc:
            problems.append(str(exc))
            continue
        if found != expected:
            problems.append(
                f"{rel}: the rule text has drifted from seal/decision-rules.json. "
                f"{_first_difference(expected, found)}"
            )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument(
        "--check",
        action="store_true",
        help="Compare the carriers against the rendered block instead of printing it.",
    )
    args = parser.parse_args(argv)

    if not args.check:
        print(render(load_json(args.repo_root / "seal" / "decision-rules.json")))
        return 0

    problems = check(args.repo_root)
    if problems:
        print("[rule-text] FAIL", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print(f"[rule-text] OK: {len(BLOCK_CARRIERS)} carriers hold the block the sealed rules render")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
