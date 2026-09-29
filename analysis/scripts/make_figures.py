#!/usr/bin/env python3
"""Draw the three figures of the manuscript from the shipped data, and check them.

**No number in a figure is typed by hand.** Each figure is TikZ generated here from the same files
the manuscript's numbers are checked against: the sealed decision rules (``seal/decision-rules.json``),
the per-draw annotations of the three runs, and the post hoc simulation's summaries
(``data/posthoc/``). The standard library is enough: TikZ draws, this script only computes where.

Two checks keep a figure tied to its data, and they are separate on purpose.

* **Source level** (``--check``). Every node that carries a number also carries a marker comment,
  ``% cds-value key=value``, on the same line as the text it sets. The check regenerates the
  expected values from the data and requires the generated ``.tex`` to hold exactly those markers,
  each with its value in the visible text of its node. A figure that went stale against its data, or
  a node edited after generation, fails here.
* **Page level** (``check_pdf_text.py``). The figures set their numbers as text, so the page carries
  them. :func:`expected_rows` gives, per figure, rows of a label followed by values in order, and
  the PDF check requires each row, in content-stream order (``pdftotext -raw``), on the page that
  carries the figure's caption. A number that was generated correctly but did not reach the page --
  clipped, overprinted, lost to a missing glyph -- fails there.

What neither check establishes: that the drawing *looks* right. A bar can be the right length and
the wrong colour. The rendered page is looked at before submission.

Usage:
    python analysis/scripts/make_figures.py --out-dir build/pdf
    python analysis/scripts/make_figures.py --out-dir build/pdf --check
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path
from typing import Any

#: The three runs, in the order the figures show them.
RUNS: tuple[tuple[str, str, str], ...] = (
    ("completed", "completed run (qwen3:8b)", "data/raw/bank_annotation.jsonl"),
    (
        "control",
        "control arm (qwen3:8b)",
        "data/prospective/control/run_annotation.jsonl",
    ),
    (
        "primary",
        "primary arm (llama3.1:8b)",
        "data/prospective/primary/run_annotation.jsonl",
    ),
)
ZONES: tuple[str, ...] = ("study", "garden", "peripatos", "agora", "chashitsu")
#: Fill per category. Greys and one hatch, so the figure survives printing in black and white.
FILLS: dict[str, str] = {
    "study": "black!70",
    "garden": "black!45",
    "peripatos": "black!25",
    "agora": "black!10",
    "chashitsu": "white",
    "None": "white",
}
DELTAS: tuple[str, ...] = (
    "0",
    "0.01",
    "0.02",
    "0.03",
    "0.04",
    "0.05",
    "0.075",
    "0.10",
    "0.15",
)
BASES: tuple[str, ...] = ("C", "K", "Cs", "U", "G")
DIRECTIONS: tuple[str, ...] = ("D1", "D2", "D3", "D4", "D5", "D6")
OPS: dict[str, str] = {
    "eq": "=",
    "lt": "<",
    "lte": r"$\leq$",
    "gt": ">",
    "gte": r"$\geq$",
    "abs_diff_lte": "within",
}

MARK = "% cds-value "
#: What a figure prints where there is no value. Not "--", which TeX sets as an en dash.
MISSING = "n/a"
#: Marks each bar of Figure 3 with the count it stands for, so its length can be read back.
BAR_MARK = "% cds-bar "
#: Marks each plotted point of Figure 2 with the curve and shift it stands for, so that its place
#: and its marker can be read back.
POINT_MARK = "% cds-point "
#: Width and height of Figure 2's plot, in cm, and the margin between the plot and its frame, so
#: that a curve at 0 or 1 is not drawn on the frame.
POWER_W, POWER_H = 8.0, 2.4
POWER_PAD_X, POWER_PAD_Y = 0.2, 0.15


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _tt(name: str) -> str:
    return r"\texttt{" + name.replace("_", r"\_") + "}"


# --------------------------------------------------------------------------------------------------
# Figure 1: the decision pipeline and what each gate reads


def _render_predicate(pred: dict[str, Any]) -> str:
    if "predicates" in pred:
        joiner = r" $\vee$ " if pred["combine"] == "any" else r" $\wedge$ "
        return "(" + joiner.join(_render_predicate(p) for p in pred["predicates"]) + ")"
    value = pred["value"]
    shown = str(value).lower() if isinstance(value, bool) else str(value)
    shown = shown.replace("_", r"\_")
    if pred["op"] == "abs_diff_lte":
        return f"{_tt(pred['quantity'])} within {shown} of the completed run"
    return f"{_tt(pred['quantity'])} {OPS[pred['op']]} {shown}"


def pipeline_values(root: Path) -> dict[str, str]:
    rules = _load_json(root / "seal" / "decision-rules.json")
    by_id = {r["id"]: r for r in rules["rules"]}
    values: dict[str, str] = {}
    for rule_id in rules["evaluation_order"]:
        rule = by_id[rule_id]
        joiner = r" $\vee$ " if rule["combine"] == "any" else r" $\wedge$ "
        values[rule_id] = joiner.join(_render_predicate(p) for p in rule["predicates"])
        values[f"{rule_id}.label"] = rule["label"]
    return values


def _draws_text(k: int, m: int) -> str:
    return rf"{k} contexts $\times$ 2 conditions $\times$ {m} draws"


def fig_pipeline(root: Path) -> str:
    rules = _load_json(root / "seal" / "decision-rules.json")
    values = pipeline_values(root)
    manifest = _load_json(root / "data" / "raw" / "cproper-manifest.json")
    m, k = manifest["run"]["m_draws"], manifest["run"]["k_contexts"]
    out = [
        r"\begin{tikzpicture}[font=\scriptsize, node distance=3mm,",
        r"  box/.style={draw, rounded corners=1pt, align=left, inner sep=2pt},",
        r"  gate/.style={draw, align=left, inner sep=2pt, text width=0.55\textwidth},",
        r"  note/.style={align=left, inner sep=1pt, text width=0.36\textwidth, font=\scriptsize\itshape}]",
        rf"\node[box] (draws) {{{_draws_text(k, m)} (channel-on block first)}}; "
        + MARK
        + f"draws={_draws_text(k, m)}",
        r"\node[box, below=of draws] (drop) {draws with no zone (\texttt{None}) dropped; "
        r"five zones renormalised};",
    ]
    previous = "drop"
    notes = {
        "R5": "control arm only",
        "R4": r"reads per-context entropy and the largest per-cell \texttt{None} rate, "
        r"not support or the on/off difference in \texttt{None}",
        "R3": "reads a pooled chi-square surrogate on the channel-off base, "
        "not the permutation test",
        "R1": r"decision's own test: stratified permutation test of \texttt{tv\_bar}",
        "R2": r"decision's own test: stratified permutation test of \texttt{tv\_bar}",
    }
    for rule_id in rules["evaluation_order"]:
        label, text = values[f"{rule_id}.label"], values[rule_id]
        out.append(
            rf"\node[gate, below=of {previous}] ({rule_id}) {{\textbf{{{rule_id}}} {label}: {text}}}; "
            + MARK
            + f"{rule_id}={text}"
        )
        out.append(rf"\node[note, right=2mm of {rule_id}] {{{notes[rule_id]}}};")
        out.append(rf"\draw[->] ({previous}) -- ({rule_id});")
        previous = rule_id
    out.append(r"\draw[->] (draws) -- (drop);")
    out.append(r"\end{tikzpicture}")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------------------------------
# Figure 2: per-context zone distribution, None included


def distribution_values(
    root: Path,
) -> dict[str, dict[tuple[str, str], collections.Counter[str]]]:
    runs: dict[str, dict[tuple[str, str], collections.Counter[str]]] = {}
    for key, _, rel in RUNS:
        cells: dict[tuple[str, str], collections.Counter[str]] = (
            collections.defaultdict(collections.Counter)
        )
        for line in (root / rel).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            zone = row["pre_bias_destination_zone"]
            context = row["frozen_ctx_id"].rsplit("-", 1)[1]
            cells[(context, row["condition"])][
                zone if zone is not None else "None"
            ] += 1
        runs[key] = dict(cells)
    return runs


def _contexts(
    runs: dict[str, dict[tuple[str, str], collections.Counter[str]]],
) -> list[str]:
    return sorted({c for cells in runs.values() for c, _ in cells}, key=int)


def fig_distribution(root: Path) -> str:
    runs = distribution_values(root)
    contexts = _contexts(runs)
    bar, gap, row_h = 3.2, 1.25, 0.27
    out = [r"\begin{tikzpicture}[font=\scriptsize, x=1cm, y=1cm]"]
    rows = [(context, condition) for context in contexts for condition in ("on", "off")]
    # The bars first, panel by panel ...
    for p, (key, title, _) in enumerate(RUNS):
        x0 = p * (bar + gap)
        out.append(
            rf"\node[anchor=south west] at ({x0:.2f},0.22) {{\textbf{{{title}}}}};"
        )
        out.append(
            rf"\node[anchor=south east, font=\tiny] at ({x0 + bar + 0.95:.2f},-0.03) "
            r"{\texttt{None}};"
        )
        for row, (context, condition) in enumerate(rows, start=1):
            y = -row * row_h
            counts = runs[key][(context, condition)]
            total = sum(counts.values())
            x = x0
            for category in (*ZONES, "None"):
                width = bar * counts[category] / total
                if width <= 0:
                    continue
                pattern = ", pattern=north east lines" if category == "None" else ""
                out.append(
                    rf"\fill[fill={FILLS[category]}{pattern}, draw=black, line width=0.2pt] "
                    rf"({x:.4f},{y + 0.03:.3f}) rectangle ({x + width:.4f},{y + row_h - 0.03:.3f}); "
                    + f"{BAR_MARK}{key}.ctx{context}.{condition}.{category}"
                )
                x += width
            # The zone counts are markers only: they fix the bar lengths above.
            for category in ZONES:
                out.append(
                    f"{MARK}{key}.ctx{context}.{condition}.{category}={counts[category]}"
                )
    # ... then the text, row by row: the label and the three None counts are consecutive in the
    # content stream, so text extraction in stream order reads each row as one run whatever
    # layout heuristics the extracting tool applies.
    for row, (context, condition) in enumerate(rows, start=1):
        y = -row * row_h + 0.08
        out.append(
            rf"\node[anchor=base east, font=\tiny] at (-0.05,{y:.3f}) {{ctx {context} {condition}}};"
        )
        for p, (key, _, _) in enumerate(RUNS):
            n_none = runs[key][(context, condition)]["None"]
            x = p * (bar + gap) + bar + 0.95
            out.append(
                rf"\node[anchor=base east, font=\tiny] at ({x:.2f},{y:.3f}) {{{n_none}}}; "
                + MARK
                + f"{key}.ctx{context}.{condition}.None={n_none}"
            )
    legend_y = -(len(contexts) * 2 + 1.6) * row_h
    x = 0.0
    for category in (*ZONES, "None"):
        pattern = ", pattern=north east lines" if category == "None" else ""
        label = r"\texttt{None}" if category == "None" else _tt(category)
        out.append(
            rf"\fill[fill={FILLS[category]}{pattern}, draw=black, line width=0.2pt] "
            rf"({x:.2f},{legend_y:.3f}) rectangle ({x + 0.3:.2f},{legend_y + 0.18:.3f});"
        )
        out.append(
            rf"\node[anchor=west] at ({x + 0.32:.2f},{legend_y + 0.09:.3f}) {{{label}}};"
        )
        x += 1.9
    out.append(r"\end{tikzpicture}")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------------------------------
# Figure 3: rejection rates against the size of the shift, and the size at which they reach 0.8


def power_values(root: Path) -> dict[str, Any]:
    summary = _load_json(root / "data" / "posthoc" / "pipeline-summary.json")
    side = _load_json(root / "data" / "posthoc" / "side-analyses.json")
    cells = {c["id"]: c for c in summary["cells"]}
    surrogate = {
        (r["base"], r["delta_tv"]): r["surrogate_power"]
        for r in side["surrogate_alongside"]
    }

    def rate(base: str, delta: str, quantity: str) -> float | None:
        cell_id = f"{base}|null|0" if delta == "0" else f"{base}|D1|{delta}"
        cell = cells.get(cell_id)
        if cell is None or cell["status"] != "run":
            return None
        return cell["summary"][quantity]["rate"]

    curves: dict[str, list[float | None]] = {}
    for base in ("C", "G"):
        curves[f"{base}.test"] = [rate(base, d, "test_reject") for d in DELTAS]
        curves[f"{base}.pipeline"] = [rate(base, d, "r2") for d in DELTAS]
        curves[f"{base}.surrogate"] = [surrogate.get((base, d)) for d in DELTAS]
    surface: dict[str, str] = {}
    for row in summary["reading_rules"]["rate_surface"]:
        test = row["test_reject"]["smallest_delta_point_estimate_at_least_0_8"]
        pipe = row["r2"]["smallest_delta_point_estimate_at_least_0_8"]
        surface[f"{row['base']}.{row['direction']}"] = f"{_short(test)}/{_short(pipe)}"
    return {"curves": curves, "surface": surface}


def _short(value: str | None) -> str:
    """``None`` in the reading rules is a rate that never reached 0.8 in the declared grid."""
    return "n.r." if value is None or value.startswith("not reached") else value


def _fmt(value: float | None) -> str:
    return MISSING if value is None else repr(value)


#: Marker shape per quantity and size per base (half-width in cm). The test and the pipeline on
#: ``C`` coincide, and every curve ends at 1.0, so a line style alone hides curves behind others:
#: a marker of another shape, or a smaller one drawn over a larger, keeps both in sight.
MARKER_SHAPES: dict[str, str] = {
    "test": "circle",
    "pipeline": "square",
    "surrogate": "triangle",
}
MARKER_SIZES: dict[str, float] = {"C": 0.09, "G": 0.05}


def _marker(shape: str, colour: str, x: float, y: float, size: float) -> str:
    """One marker centred on (x, y): a filled circle, an open square or an open triangle."""
    pen = f"{colour}, line width=0.4pt"
    if shape == "circle":
        return rf"\filldraw[{pen}] ({x:.3f},{y:.3f}) circle ({0.7 * size:.3f});"
    if shape == "square":
        return (
            rf"\draw[{pen}] ({x - size:.3f},{y - size:.3f}) rectangle "
            rf"({x + size:.3f},{y + size:.3f});"
        )
    half = 1.2 * size
    return (
        rf"\draw[{pen}] ({x:.3f},{y + size:.3f}) -- ({x - half:.3f},{y - size:.3f}) -- "
        rf"({x + half:.3f},{y - size:.3f}) -- cycle;"
    )


def fig_power(root: Path) -> str:
    values = power_values(root)
    curves, surface = values["curves"], values["surface"]
    w, h, step = POWER_W, POWER_H, POWER_W / (len(DELTAS) - 1)
    px, py = POWER_PAD_X, POWER_PAD_Y
    styles = {
        "C.test": "black, line width=0.8pt",
        "C.pipeline": "black, dashed, line width=0.6pt",
        "C.surrogate": "black, dotted, line width=0.9pt",
        "G.test": "black!45, line width=0.8pt",
        "G.pipeline": "black!45, dashed, line width=0.6pt",
        "G.surrogate": "black!45, dotted, line width=0.9pt",
    }
    names = {
        "C.test": r"\texttt{C}, test",
        "C.pipeline": r"\texttt{C}, pipeline",
        "C.surrogate": r"\texttt{C}, surrogate",
        "G.test": r"\texttt{G}, test",
        "G.pipeline": r"\texttt{G}, pipeline",
        "G.surrogate": r"\texttt{G}, surrogate",
    }
    out = [r"\begin{tikzpicture}[font=\scriptsize, x=1cm, y=1cm]"]
    out.append(rf"\draw ({-px},{-py}) rectangle ({w + px},{h + py});")
    for tick in (0.0, 0.5, 0.8, 1.0):
        out.append(
            rf"\draw[black!15] ({-px},{tick * h:.3f}) -- ({w + px},{tick * h:.3f});"
        )
        out.append(rf"\node[anchor=east] at ({-px},{tick * h:.3f}) {{{tick}}};")
    for i, delta in enumerate(DELTAS):
        out.append(rf"\node[anchor=north] at ({i * step:.3f},{-py}) {{{delta}}};")
    out.append(
        rf"\node at ({w / 2},-0.65) {{shift \texttt{{delta\_tv}} along D1 (not to scale)}};"
    )
    out.append(rf"\node[rotate=90] at ({-px - 0.75},{h / 2}) {{rejection rate}};")
    for key, series in curves.items():
        points = [(i * step, v * h) for i, v in enumerate(series) if v is not None]
        path = " -- ".join(f"({x:.3f},{y:.3f})" for x, y in points)
        out.append(rf"\draw[{styles[key]}] {path};")
    # The markers after every line, larger before smaller, so that none is hidden behind a line or
    # behind a marker drawn after it.
    for key in sorted(curves, key=lambda k: -MARKER_SIZES[k.split(".")[0]]):
        base, quantity = key.split(".")
        for i, v in enumerate(curves[key]):
            if v is None:
                continue
            out.append(
                _marker(
                    MARKER_SHAPES[quantity],
                    styles[key].split(",")[0],
                    i * step,
                    v * h,
                    MARKER_SIZES[base],
                )
                + f" {POINT_MARK}{key}.{DELTAS[i]}"
            )
    # The values, set under the plot so that they are on the page.
    for r, key in enumerate(curves):
        y = -1.0 - r * 0.4
        out.append(
            rf"\node[anchor=base east, font=\tiny] at (-0.55,{y:.2f}) {{{names[key]}}};"
        )
        base, quantity = key.split(".")
        out.append(
            rf"\draw[{styles[key]}] (-3.1,{y + 0.05:.2f}) -- (-2.5,{y + 0.05:.2f});"
        )
        out.append(
            _marker(
                MARKER_SHAPES[quantity],
                styles[key].split(",")[0],
                -2.8,
                y + 0.05,
                MARKER_SIZES[base],
            )
        )
        for i, v in enumerate(curves[key]):
            text = _fmt(v)
            out.append(
                rf"\node[font=\tiny, anchor=base] at ({i * step:.3f},{y:.2f}) {{{text}}}; "
                + MARK
                + f"{key}.{DELTAS[i]}={text}"
            )
    # Lower panel: the smallest declared shift at which each rate reaches 0.8.
    gy = -1.0 - len(curves) * 0.4 - 0.35
    out.append(
        rf"\node[anchor=west] at (-3.0,{gy:.2f}) {{smallest declared \texttt{{delta\_tv}} at which "
        r"the rate reaches 0.8 (point estimate), test / pipeline:};"
    )
    col = 1.35
    for j, direction in enumerate(DIRECTIONS):
        out.append(rf"\node at ({0.5 + j * col:.2f},{gy - 0.35:.2f}) {{{direction}}};")
    for i, base in enumerate(BASES):
        y = gy - 0.75 - i * 0.4
        out.append(
            rf"\node[anchor=base east, font=\tiny] at (-0.55,{y:.2f}) {{\texttt{{{base}}}}};"
        )
        for j, direction in enumerate(DIRECTIONS):
            text = surface.get(f"{base}.{direction}", MISSING)
            out.append(
                rf"\node[anchor=base, font=\tiny] at ({0.5 + j * col:.2f},{y:.2f}) {{{text}}}; "
                + MARK
                + f"surface.{base}.{direction}={text}"
            )
    out.append(r"\end{tikzpicture}")
    return "\n".join(out) + "\n"


FIGURES = {
    "pipeline": fig_pipeline,
    "distribution": fig_distribution,
    "power": fig_power,
}


# --------------------------------------------------------------------------------------------------
# Expected values, for both checks


def expected_markers(root: Path) -> dict[str, dict[str, str]]:
    """The ``key=value`` markers each figure must carry, computed from the data."""
    manifest = _load_json(root / "data" / "raw" / "cproper-manifest.json")
    pipe = {
        "draws": _draws_text(manifest["run"]["k_contexts"], manifest["run"]["m_draws"])
    }
    pipe.update({k: v for k, v in pipeline_values(root).items() if "." not in k})
    dist: dict[str, str] = {}
    for key, cells in distribution_values(root).items():
        for (context, condition), counts in cells.items():
            for category in (*ZONES, "None"):
                dist[f"{key}.ctx{context}.{condition}.{category}"] = str(
                    counts[category]
                )
    values = power_values(root)
    power = {
        f"{curve}.{DELTAS[i]}": _fmt(v)
        for curve, series in values["curves"].items()
        for i, v in enumerate(series)
    }
    power.update(
        {
            f"surface.{b}.{d}": values["surface"].get(f"{b}.{d}", MISSING)
            for b in BASES
            for d in DIRECTIONS
        }
    )
    return {"pipeline": pipe, "distribution": dist, "power": power}


def expected_rows(root: Path) -> dict[str, list[tuple[str, list[str]]]]:
    """Per figure, rows of (label, values in order) that must stand on one line of the page."""
    runs = distribution_values(root)
    dist = [
        (
            f"ctx {context} {condition}",
            [str(runs[key][(context, condition)]["None"]) for key, _, _ in RUNS],
        )
        for context in _contexts(runs)
        for condition in ("on", "off")
    ]
    values = power_values(root)
    labels = {
        "C.test": "C, test",
        "C.pipeline": "C, pipeline",
        "C.surrogate": "C, surrogate",
        "G.test": "G, test",
        "G.pipeline": "G, pipeline",
        "G.surrogate": "G, surrogate",
    }
    power = [(labels[k], [_fmt(v) for v in s]) for k, s in values["curves"].items()]
    power += [
        (base, [values["surface"].get(f"{base}.{d}", MISSING) for d in DIRECTIONS])
        for base in BASES
    ]
    # Figure 1: each rule's label followed by its predicates, as the page reads them, so that a
    # predicate lost from a box fails even though the box's label survives (TASK-POST review).
    predicates = pipeline_values(root)
    pipe = [
        (f"{rid} {label}:", _plain(predicates[rid]).split())
        for rid, label in _rule_labels(root)
    ]
    return {"pipeline": pipe, "distribution": dist, "power": power}


def _plain(tex: str) -> str:
    """The text a TeX predicate of Figure 1 reads as on the page."""
    for old, new in (
        (r"$\wedge$", "∧"),
        (r"$\vee$", "∨"),
        (r"$\geq$", "≥"),
        (r"$\leq$", "≤"),
        (r"\_", "_"),
    ):
        tex = tex.replace(old, new)
    return re.sub(r"\\texttt\{([^}]*)\}", r"\1", tex)


def _rule_labels(root: Path) -> list[tuple[str, str]]:
    rules = _load_json(root / "seal" / "decision-rules.json")
    by_id = {r["id"]: r for r in rules["rules"]}
    return [(rid, by_id[rid]["label"]) for rid in rules["evaluation_order"]]


def parse_markers(tex: str) -> tuple[dict[str, str], list[str]]:
    """Read the markers back out of a generated figure, with the problems found doing so."""
    found: dict[str, str] = {}
    problems: list[str] = []
    for line in tex.splitlines():
        if MARK not in line:
            continue
        body, marker = line.split(MARK, 1)
        key, _, value = marker.partition("=")
        if key in found:
            problems.append(f"marker {key} appears twice")
        found[key] = value
        # A number must be the whole text of its node: "0" or "1.0" occur by chance in any line
        # of TikZ. Only a long text (a rule's predicates) may stand inside a longer node text.
        exact = "{" + value + "}" in body
        if body.strip() and not exact and not (len(value) >= 12 and value in body):
            problems.append(
                f"marker {key}={value} does not match the text its node sets"
            )
    return found, problems


_RECT = re.compile(r"\(([-\d.]+),[-\d.]+\) rectangle \(([-\d.]+),[-\d.]+\);")


def check_bars(tex: str, markers: dict[str, str], bar: float = 3.2) -> list[str]:
    """Every bar of Figure 3 must be as long as the counts it stands for.

    The counts are read back from the figure's own markers and the length from the drawn rectangle,
    so this compares two things the generator wrote separately, not one value with itself.
    """
    problems: list[str] = []
    seen = 0
    for line in tex.splitlines():
        if BAR_MARK not in line:
            continue
        seen += 1
        body, key = line.split(BAR_MARK, 1)
        match = _RECT.search(body)
        row = key.rsplit(".", 1)[0]
        counts = [int(markers.get(f"{row}.{c}", "-1")) for c in (*ZONES, "None")]
        count = int(markers.get(key, "-1"))
        if match is None or min(counts) < 0 or count < 0:
            problems.append(
                f"bar {key}: its rectangle or its counts cannot be read back"
            )
            continue
        drawn = float(match.group(2)) - float(match.group(1))
        want = bar * count / sum(counts)
        if abs(drawn - want) > 2e-4:
            problems.append(
                f"bar {key} is {drawn:.4f} long; its counts give {want:.4f}"
            )
    if seen == 0:
        problems.append("no bar of the distribution figure carries a bar marker")
    return problems


_COORD = re.compile(r"\(([-\d.]+),([-\d.]+)\)")
_RADIUS = re.compile(r"circle \(([\d.]+)\)")


def _read_point(body: str) -> tuple[str, float, float, float] | None:
    """A drawn marker as (shape, centre x, centre y, width), read from its TikZ path."""
    coords = [(float(a), float(b)) for a, b in _COORD.findall(body)]
    radius = _RADIUS.search(body)
    if radius is not None and len(coords) == 1:
        (x, y), r = coords[0], float(radius.group(1))
        return "circle", x, y, 2 * r
    shape = "square" if "rectangle" in body else "triangle" if "cycle" in body else None
    if shape is None or len(coords) < 2:
        return None
    xs, ys = [c[0] for c in coords], [c[1] for c in coords]
    return (
        shape,
        (min(xs) + max(xs)) / 2,
        (min(ys) + max(ys)) / 2,
        max(xs) - min(xs),
    )


def check_points(tex: str, curves: dict[str, list[float | None]]) -> list[str]:
    """Every plotted value of Figure 2 must carry a marker, and coinciding markers must differ.

    Two curves with (nearly) the same values are drawn on top of each other, and a line style alone
    then shows one curve where there are two: the test and the pipeline on ``C`` agree to within
    0.002 at every shift. So each value carries a marker at its place, read back from the drawn path
    and compared with the data, and two markers that overlap must differ in shape or in size.
    """
    problems: list[str] = []
    step = POWER_W / (len(DELTAS) - 1)
    points: dict[str, tuple[str, float, float, float]] = {}
    for line in tex.splitlines():
        if POINT_MARK not in line:
            continue
        body, key = line.split(POINT_MARK, 1)
        key = key.strip()
        point = _read_point(body)
        if point is None:
            problems.append(f"point {key}: its marker cannot be read back")
        elif key in points:
            problems.append(f"point {key} is drawn twice")
        else:
            points[key] = point
    expected: set[str] = set()
    for curve, series in curves.items():
        for i, value in enumerate(series):
            key = f"{curve}.{DELTAS[i]}"
            if value is None:
                continue
            expected.add(key)
            point = points.get(key)
            if point is None:
                problems.append(f"point {key} has no marker")
                continue
            _, x, y, _ = point
            if abs(x - i * step) > 2e-3 or abs(y - value * POWER_H) > 2e-3:
                problems.append(
                    f"point {key} is drawn at ({x:.3f},{y:.3f}); its value puts it at "
                    f"({i * step:.3f},{value * POWER_H:.3f})"
                )
    problems += [
        f"point {k} is drawn where the data has no value"
        for k in sorted(set(points) - expected)
    ]
    for delta in DELTAS:
        here = sorted((k, p) for k, p in points.items() if k.endswith(f".{delta}"))
        here = [(k, p) for k, p in here if k[: -len(delta) - 1] in curves]
        for a, (key_a, pa) in enumerate(here):
            for key_b, pb in here[a + 1 :]:
                overlap = abs(pa[2] - pb[2]) < max(pa[3], pb[3]) / 2
                same_shape = pa[0] == pb[0]
                similar_size = max(pa[3], pb[3]) < 1.25 * min(pa[3], pb[3])
                if overlap and same_shape and similar_size:
                    problems.append(
                        f"points {key_a} and {key_b} coincide and cannot be told apart"
                    )
    return problems


def check_anchor(root: Path, markers: dict[str, str]) -> list[str]:
    """Figure 3's None counts, summed per arm and condition, must equal the held-out result's.

    ``analysis/heldout-stay/result.json`` was computed by the frozen held-out script from the same
    annotations by a different code path, so agreement is evidence that the figure reads them
    correctly, which recomputing the figure's own values could not give.
    """
    result = _load_json(root / "analysis" / "heldout-stay" / "result.json")
    problems: list[str] = []
    for arm in ("control", "primary"):
        for condition in ("on", "off"):
            total = sum(
                int(v)
                for k, v in markers.items()
                if k.startswith(f"{arm}.ctx") and k.endswith(f".{condition}.None")
            )
            want = int(result["arms"][arm]["none"][condition])
            if total != want:
                problems.append(
                    f"Figure 3 shows {total} None draws for {arm}/{condition}; the held-out "
                    f"result records {want}"
                )
    return problems


def check_figures(root: Path, out_dir: Path) -> list[str]:
    problems: list[str] = []
    expected = expected_markers(root)
    for name in FIGURES:
        path = out_dir / f"fig-{name}.tex"
        if not path.is_file():
            problems.append(f"{path} is missing")
            continue
        tex = path.read_text(encoding="utf-8")
        found, parse_problems = parse_markers(tex)
        problems += [f"fig-{name}: {p}" for p in parse_problems]
        if name == "distribution":
            problems += [f"fig-{name}: {p}" for p in check_bars(tex, found)]
            problems += [f"fig-{name}: {p}" for p in check_anchor(root, found)]
        if name == "power":
            curves = power_values(root)["curves"]
            problems += [f"fig-{name}: {p}" for p in check_points(tex, curves)]
        want = expected[name]
        for key in sorted(set(want) | set(found)):
            if found.get(key) != want.get(key):
                problems.append(
                    f"fig-{name}: {key} is {found.get(key)!r} in the figure but {want.get(key)!r} "
                    "in the data"
                )
    return problems


def self_test(root: Path, out_dir: Path) -> list[str]:
    """A node edited after generation, and a marker removed, must both fail the check."""
    import shutil  # noqa: PLC0415
    import tempfile  # noqa: PLC0415

    problems: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        for name in FIGURES:
            shutil.copyfile(out_dir / f"fig-{name}.tex", work / f"fig-{name}.tex")
        if check_figures(root, work):
            problems.append("self-test: the unmodified figures do not pass")
        power = work / "fig-power.tex"
        original = power.read_text(encoding="utf-8")
        edited, n = re.subn(
            r"\{0\.122\}; % cds-value C\.test\.0\.01=0\.122",
            "{0.9}; % cds-value C.test.0.01=0.9",
            original,
        )
        if n != 1:
            problems.append(
                "self-test: the node to edit was not found in fig-power.tex"
            )
        power.write_text(edited, encoding="utf-8")
        if not any("C.test.0.01" in p for p in check_figures(root, work)):
            problems.append(
                "self-test: a number edited in a generated figure was not caught"
            )
        power.write_text(
            re.sub(r"\n.*cds-value G\.test\.0\.02=.*", "", original, count=1),
            encoding="utf-8",
        )
        if not any("G.test.0.02" in p for p in check_figures(root, work)):
            problems.append(
                "self-test: a number removed from a generated figure was not caught"
            )
        # A plotted value left without its marker.
        power.write_text(
            re.sub(r"\n.*cds-point C\.pipeline\.0\.01\n", "\n", original, count=1),
            encoding="utf-8",
        )
        if not any(
            "C.pipeline.0.01 has no marker" in p for p in check_figures(root, work)
        ):
            problems.append(
                "self-test: a plotted value without a marker was not caught"
            )
        # The defect this check was written for: the pipeline on C drawn exactly as the test on C,
        # where the two coincide, so that the page shows one curve where there are two.
        test_body = re.search(r"\n(.*) % cds-point C\.test\.0\.05\n", original)
        if test_body is None:
            problems.append(
                "self-test: the marker to copy was not found in fig-power.tex"
            )
        else:
            power.write_text(
                re.sub(
                    r"\n.* (% cds-point C\.pipeline\.0\.05)\n",
                    lambda m: f"\n{test_body.group(1)} {m.group(1)}\n",
                    original,
                    count=1,
                ),
                encoding="utf-8",
            )
            if not any("cannot be told apart" in p for p in check_figures(root, work)):
                problems.append(
                    "self-test: two coinciding curves drawn alike were not caught"
                )
        power.write_text(original, encoding="utf-8")
        dist = work / "fig-distribution.tex"
        dist_original = dist.read_text(encoding="utf-8")
        # A bar drawn longer than its counts give.
        lengthened = re.sub(
            r"rectangle \(([-\d.]+),",
            lambda m: f"rectangle ({float(m.group(1)) + 0.05:.4f},",
            dist_original,
            count=1,
        )
        dist.write_text(lengthened, encoding="utf-8")
        if not any(
            "long; its counts give" in p
            for p in check_bars(lengthened, parse_markers(lengthened)[0])
        ):
            problems.append("self-test: a bar drawn at the wrong length was not caught")
        # One None draw moved from one context to another in the markers: the per-context values
        # change consistently, the held-out totals do not -- so only the anchor can see it.
        found = parse_markers(dist_original)[0]
        moved = dict(found)
        moved["control.ctx0.on.None"] = str(int(moved["control.ctx0.on.None"]) + 1)
        if not check_anchor(root, moved):
            problems.append(
                "self-test: a None total that disagrees with the held-out result was not caught"
            )
        dist.write_text(dist_original, encoding="utf-8")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="repository root",
    )
    parser.add_argument(
        "--out-dir", type=Path, required=True, help="where the figures go"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="check existing figures against the data instead",
    )
    args = parser.parse_args(argv)
    if args.check:
        problems = check_figures(args.repo_root, args.out_dir)
        problems += self_test(args.repo_root, args.out_dir)
        if problems:
            print("[figures] FAIL", file=sys.stderr)
            for problem in problems:
                print(f"  - {problem}", file=sys.stderr)
            return 1
        counts = {k: len(v) for k, v in expected_markers(args.repo_root).items()}
        print(
            f"[figures] OK: every value marker in the three figures matches the data ({counts}); "
            "an edited and a removed node, a bar at the wrong length, a None total that disagrees with "
            "the held-out result, a plotted value without its marker and two coinciding curves drawn "
            "alike are all caught"
        )
        return 0
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for name, make in FIGURES.items():
        (args.out_dir / f"fig-{name}.tex").write_text(
            make(args.repo_root), encoding="utf-8", newline="\n"
        )
    print(
        f"[figures] wrote {', '.join(f'fig-{n}.tex' for n in FIGURES)} to {args.out_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
