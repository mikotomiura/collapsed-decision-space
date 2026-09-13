#!/usr/bin/env python3
"""Apply the sealed decision rules to the arm results and emit a structured report.

The protocol states its decision rules in prose. Prose is not a check: after the data exist,
nothing mechanical stops the branch from being read differently from the way it was written. Under
in-principle acceptance a recommender held that line. Without one, this script holds it.

The rules live in ``seal/decision-rules.json``, whose bytes are fixed by ``seal/SEAL-MANIFEST.json``
and verified by ``verify_seal.py``. This script reads them, evaluates them against the recorded
quantities of each arm in the sealed order, and writes ``decision-report.json``: the branch reached,
the truth value of **every** predicate, and whether evaluation stopped there.

What this establishes: the reported branch follows from the sealed rules applied to the shipped
quantities. Changing the band, the order, or a threshold after the fact changes the bytes of the
sealed file, which ``verify_seal.py`` rejects.

What it does not: that the quantities themselves are right (``recompute_verdict.py`` covers that),
or anything about *when* the rules were fixed. Neither this check nor any other can establish that
no draw was taken before the seal.

Deliberately strict. A quantity that is missing, null, NaN, or of the wrong type is an error, not a
false predicate: a rule that silently evaluates to False on a broken input is worse than no rule.

Usage:
    python analysis/scripts/apply_decision_rules.py \\
        --control data/raw/cproper-verdict.json \\
        --primary data/raw/primary-verdict.json \\
        --out data/derived/decision-report.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _provenance import load_json  # noqa: E402

REPORT_SCHEMA: str = "powered-null-decision-report-1"
RULES_SCHEMA: str = "powered-null-decision-rules-1"

#: Comparison operators. Each takes (observed, predicate) and returns a bool.
#: ``abs_diff_lte`` is the only two-parameter form: it reads ``centre`` as well as ``value``.
_NUMERIC_OPS = frozenset({"lt", "lte", "gt", "gte", "abs_diff_lte"})
_ANY_OPS = frozenset({"eq", "ne"})
_OPS = _NUMERIC_OPS | _ANY_OPS


def _die(message: str) -> None:
    print(f"[decision] FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def _require_number(value: Any, quantity: str) -> float:
    """Return ``value`` as a float, or abort.

    ``True`` is an ``int`` in Python, so bools are rejected explicitly; a stringified number is
    rejected rather than coerced, because coercion is how a malformed record passes unnoticed.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _die(f"{quantity!r} must be a number, got {type(value).__name__}: {value!r}")
    number = float(value)
    if math.isnan(number) or math.isinf(number):
        _die(f"{quantity!r} is not finite: {value!r}")
    return number


def _observed(source: dict[str, Any], quantity: str, arm: str) -> Any:
    """Read a quantity by key. A missing key is an error, never a default."""
    if quantity not in source:
        _die(f"the {arm} record has no key {quantity!r}")
    value = source[quantity]
    if value is None:
        _die(f"the {arm} record has {quantity!r} = null")
    return value


def _evaluate_leaf(predicate: dict[str, Any], source: dict[str, Any], arm: str) -> dict[str, Any]:
    """Evaluate one comparison and return its row of the truth table."""
    quantity = predicate.get("quantity")
    op = predicate.get("op")
    if not isinstance(quantity, str) or op not in _OPS:
        _die(f"malformed predicate (quantity/op): {predicate!r}")
    if "value" not in predicate:
        _die(f"predicate has no 'value': {predicate!r}")

    observed = _observed(source, quantity, arm)
    expected = predicate["value"]

    if op in _ANY_OPS:
        # A record whose type does not match the rule is malformed, not merely unequal.
        # Letting ``0`` stand in for ``False`` here would turn a broken input into a
        # quietly failing predicate, which is the failure mode this script exists to remove.
        if type(observed) is not type(expected):
            _die(
                f"{quantity!r} is {type(observed).__name__} ({observed!r}) but the rule "
                f"compares it with {type(expected).__name__} ({expected!r})"
            )
        equal = observed == expected
        result = equal if op == "eq" else not equal
        rendered = f"{quantity} {op} {expected!r}"
    else:
        left = _require_number(observed, quantity)
        right = _require_number(expected, f"{quantity}.value")
        if op == "abs_diff_lte":
            if "centre" not in predicate:
                _die(f"abs_diff_lte needs a 'centre': {predicate!r}")
            centre = _require_number(predicate["centre"], f"{quantity}.centre")
            result = abs(left - centre) <= right
            rendered = f"|{quantity} - {centre}| <= {right}"
        else:
            result = {
                "lt": left < right,
                "lte": left <= right,
                "gt": left > right,
                "gte": left >= right,
            }[op]
            rendered = f"{quantity} {op} {right}"

    return {
        "predicate": rendered,
        "quantity": quantity,
        "observed": observed,
        "result": bool(result),
    }


def _evaluate_group(group: dict[str, Any], source: dict[str, Any], arm: str) -> tuple[bool, list[dict[str, Any]]]:
    """Evaluate a combine group, returning its value and the flattened truth table.

    Every predicate is evaluated: no short-circuiting. A reader of the report is entitled to see
    which conditions held and which did not, not only the ones that decided the outcome.
    """
    combine = group.get("combine")
    if combine not in {"all", "any"}:
        _die(f"combine must be 'all' or 'any', got {combine!r}")
    members = group.get("predicates")
    if not isinstance(members, list) or not members:
        _die(f"a combine group needs a non-empty 'predicates' list: {group!r}")

    rows: list[dict[str, Any]] = []
    values: list[bool] = []
    for member in members:
        if not isinstance(member, dict):
            _die(f"malformed predicate: {member!r}")
        if "combine" in member:
            nested_value, nested_rows = _evaluate_group(member, source, arm)
            values.append(nested_value)
            rows.extend(nested_rows)
        else:
            row = _evaluate_leaf(member, source, arm)
            values.append(row["result"])
            rows.append(row)

    value = all(values) if combine == "all" else any(values)
    return value, rows


def _load_rules(path: Path) -> dict[str, Any]:
    rules = load_json(path)
    if rules.get("schema") != RULES_SCHEMA:
        _die(f"{path.name}: schema is {rules.get('schema')!r}, expected {RULES_SCHEMA!r}")
    order = rules.get("evaluation_order")
    if not isinstance(order, list) or not order:
        _die(f"{path.name}: 'evaluation_order' must be a non-empty list")
    by_id = {rule.get("id"): rule for rule in rules.get("rules", [])}
    if set(order) != set(by_id) or len(by_id) != len(rules.get("rules", [])):
        _die(
            f"{path.name}: 'evaluation_order' {sorted(order)} does not match the rule ids "
            f"{sorted(k for k in by_id if k is not None)}"
        )
    return rules


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    repo_root = Path(__file__).resolve().parents[2]
    parser.add_argument("--rules", type=Path, default=repo_root / "seal" / "decision-rules.json")
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--primary", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument(
        "--expect-branch",
        help="Fail unless the branch reached is this one. Used by repro.sh to bind the "
        "manuscript's stated branch to the rules.",
    )
    args = parser.parse_args()

    rules = _load_rules(args.rules)
    sources: dict[str, dict[str, Any]] = {"control": load_json(args.control)}
    if args.primary is not None:
        sources["primary"] = load_json(args.primary)

    by_id = {rule["id"]: rule for rule in rules["rules"]}
    evaluated: list[dict[str, Any]] = []
    branch: str | None = None
    stopped_at: str | None = None

    for rule_id in rules["evaluation_order"]:
        rule = by_id[rule_id]
        arm = rule["arm"]
        if arm not in sources:
            # The primary arm is not interpreted when the gate before it stopped evaluation;
            # reaching a rule whose arm was never supplied is a usage error, not a result.
            _die(
                f"rule {rule_id} is defined on the {arm!r} arm but no {arm} record was given. "
                "Evaluation reached it, so it cannot be skipped."
            )
        value, rows = _evaluate_group(rule, sources[arm], arm)
        outcome = rule["on_pass"] if value else rule["on_fail"]
        entry = {
            "id": rule_id,
            "arm": arm,
            "label": rule.get("label"),
            "role": rule.get("role"),
            "combine": rule["combine"],
            "value": value,
            "action": outcome["action"],
            "failing_predicates": [r["predicate"] for r in rows if not r["result"]],
            "truth_table": rows,
        }
        if "states" in outcome:
            entry["states"] = outcome["states"]
        evaluated.append(entry)
        if outcome["action"] == "stop":
            branch = rule_id
            stopped_at = rule_id
            break
        if outcome["action"] != "continue":
            _die(f"rule {rule_id}: unknown action {outcome['action']!r}")

    if branch is None:
        _die(
            "evaluation ran off the end of the rule list without reaching a stop action. "
            "The rules do not cover the observed quantities."
        )

    report = {
        "schema": REPORT_SCHEMA,
        "branch": branch,
        "stopped_at": stopped_at,
        "arms_supplied": sorted(sources),
        "rules_evaluated": [entry["id"] for entry in evaluated],
        "detail": evaluated,
    }

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(f"[decision] wrote {args.out}")

    print(f"[decision] branch = {branch} ({by_id[branch].get('label')})")
    for entry in evaluated:
        mark = "pass" if entry["value"] else "fail"
        print(f"[decision]   {entry['id']:<3} {mark}  -> {entry['action']}")
        for failing in entry["failing_predicates"]:
            print(f"[decision]         not satisfied: {failing}")

    if args.expect_branch is not None and args.expect_branch != branch:
        _die(
            f"the branch reached is {branch!r} but {args.expect_branch!r} was expected. "
            "The sealed rules and the claimed result disagree."
        )

    print("[decision] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
