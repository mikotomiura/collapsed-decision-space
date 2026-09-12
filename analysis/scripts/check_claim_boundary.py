#!/usr/bin/env python3
"""``manuscript/CLAIM-BOUNDARY.md`` の禁止句が claim 面に出ていないことを検査する.

設計の要点は 3 つで、いずれも「緑であること」と「検査が走ったこと」を別物として
扱うために置いている (``feedback_negative_fixture_must_not_be_self_referential`` /
``feedback_checker_handed_target_is_not_checked``)。

1. **パターンの SSOT は ``manuscript/CLAIM-BOUNDARY.md``** であり、検査対象の本文から
   取らない。本文に禁止句リストを書いて「自分と一致しないこと」を確かめる形にすると
   自己言及で恒真になる。
2. **G1-G13 の 13 件ちょうどをパースできなければ落ちる。** パースに失敗して 0 件に
   なった検査器は、どんな本文に対しても「ヒット 0」を返す。件数を pin することで
   その経路を塞ぐ。
3. **「ヒット 0 が正解」の検査に陽性対照を添える。**
   ``manuscript/_claim_boundary_positive_control.md`` は 13 件すべてを故意に踏む
   fixture であり、**13 件すべてが発火しなければ exit != 0** になる。1 つでも
   発火しなければ、検査器が壊れているかパターンが言い回しを捕まえられていない。

加えて、本文が空・骨組みだけでも「ヒット 0」で通ってしまう穴を塞ぐため、
``manuscript/main.md`` の非空虚性 (必須アンカーの存在と最低語数) を前提条件として
検査する。

検査対象 (claim 面):
  - ``manuscript/main.md`` (英語。本検査の主対象)
  - ``README.md`` (日本語)
  - ``CITATION.cff`` (``abstract`` が GitHub の引用ウィジェットに出るため claim 面である)

**射程の限界を明示する。** ``CLAIM-BOUNDARY.md`` のパターンは**英語の正規表現**である
(投稿言語が英語なので本文がそう書かれている)。したがって日本語の ``README.md`` に対しては、
言語に依らない部分 — 識別子・数値・``D_loco`` のような literal — しか発火しない。
実際 2026-09-12 には README の G10 違反 (``D_loco = 7.40e-17``) をこの検査が捕まえたが、
日本語の散文で書かれた over-claim は捕まえられない。日本語パターン列の追加は
**未了の課題**であり、「README を検査した」は上の限定つきで読むこと。

``manuscript/CLAIM-BOUNDARY.md`` 自身と陽性対照 fixture は対象外である。前者は
パターンの定義そのものを (説明のための例示を含めて) 抱えており、後者は故意に踏む
ための fixture だからである。

あわせて、``main.md`` の ``## Abstract`` 節と ``CITATION.cff`` の ``abstract`` が
同一であることを検査する。片方だけ直すと、公開 repo の引用ウィジェットと本文が
静かに食い違う。

使い方:  python analysis/scripts/check_claim_boundary.py
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

#: 表の行が禁止句ガードであることの判定 (先頭セルが G<数字>)。
GUARD_ROW_RE = re.compile(r"^\|\s*(G\d+)\s*\|")

#: markdown 表のセル分割。パターン中の `\|` (エスケープされたパイプ) では割らない。
CELL_SPLIT_RE = re.compile(r"(?<!\\)\|")

#: セル内の backtick で囲まれた検査パターンを取り出す。
BACKTICKED_RE = re.compile(r"`([^`]+)`")

#: SSOT が持っているべきガード ID。件数と並びの両方を pin する。
EXPECTED_GUARD_IDS: tuple[str, ...] = tuple(f"G{i}" for i in range(1, 14))

#: 本文が非空虚であることの前提条件。落ちたら本文側が未完成である。
MAIN_REQUIRED_ANCHORS: tuple[str, ...] = (
    "Level 6",
    "R1",
    "R2",
    "R3",
    "R4",
    "R5",
    "eligibility",
    "tv_bar",
    "delta_tv_min",
)

#: 同上 (最低語数)。骨組みだけの main.md を通さない。
MAIN_MIN_WORDS = 1500


@dataclass(frozen=True)
class Guard:
    """1 つの禁止句ガード (`CLAIM-BOUNDARY.md` の表 1 行)."""

    guard_id: str
    patterns: tuple[re.Pattern[str], ...]


@dataclass(frozen=True)
class Hit:
    """パターンが本文にヒットした位置."""

    guard_id: str
    pattern: str
    path: str
    line_no: int
    line: str


def parse_guards(boundary_path: Path) -> tuple[Guard, ...]:
    """`CLAIM-BOUNDARY.md` の表から G1-G13 とその検査パターンを取り出す.

    Raises:
        SystemExit: ガード件数・ID・パターン数のいずれかが期待と違うとき。
    """
    guards: list[Guard] = []
    text = boundary_path.read_text(encoding="utf-8")

    for raw_line in text.splitlines():
        match = GUARD_ROW_RE.match(raw_line)
        if match is None:
            continue
        cells = [cell.strip() for cell in CELL_SPLIT_RE.split(raw_line)]
        # ['', 'G1', '書かない主張', '理由', 'パターン', '']
        if len(cells) < 6:
            _die(
                f"{boundary_path}: ガード行のセル数が足りない "
                f"({match.group(1)}, cells={len(cells)}): {raw_line}"
            )
        pattern_cell = cells[4]
        raw_patterns = BACKTICKED_RE.findall(pattern_cell)
        if not raw_patterns:
            _die(
                f"{boundary_path}: {match.group(1)} に検査パターンが 1 つも無い: "
                f"{pattern_cell}"
            )
        compiled: list[re.Pattern[str]] = []
        for raw_pattern in raw_patterns:
            # markdown 表のためにエスケープされたパイプを戻す。
            pattern = raw_pattern.replace(r"\|", "|")
            try:
                compiled.append(re.compile(pattern, re.IGNORECASE))
            except re.error as exc:
                _die(
                    f"{boundary_path}: {match.group(1)} のパターンが正規表現として "
                    f"不正: {pattern!r} ({exc})"
                )
        guards.append(Guard(match.group(1), tuple(compiled)))

    found_ids = tuple(guard.guard_id for guard in guards)
    if found_ids != EXPECTED_GUARD_IDS:
        _die(
            f"{boundary_path}: ガードの ID 並びが期待と違う。"
            f"expected={EXPECTED_GUARD_IDS} found={found_ids} "
            "(パース失敗で 0 件になった検査器はどんな本文でも通るので、"
            "ここで止める)"
        )
    return tuple(guards)


def normalise_whitespace(text: str) -> str:
    """改行・連続空白を 1 つの空白へ畳む.

    本文は 100 字程度でハードラップしてあるので、禁止句は容易に**改行をまたぐ**。
    行単位で走査すると、ラップされた句を取りこぼす (2026-09-12 に陽性対照側で実測:
    ``guarantees`` と ``Level 6`` が改行で割れて G9 が発火しなかった)。判定は
    正規化テキストに対して行い、行番号は補助情報として付ける。
    """
    return " ".join(text.split())


def scan(guards: tuple[Guard, ...], path: Path, repo_root: Path) -> list[Hit]:
    """1 ファイルを全ガードで走査する (改行をまたぐ句も捕まえる)."""
    hits: list[Hit] = []
    rel = path.relative_to(repo_root).as_posix()
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    flat = normalise_whitespace(text)

    for guard in guards:
        for pattern in guard.patterns:
            for match in pattern.finditer(flat):
                start, end = match.span()
                excerpt = flat[max(0, start - 60) : end + 60]
                # 同じ句が 1 行に収まっていれば行番号を出す。改行をまたいでいる
                # 場合は 0 にして、ヒット箇所は excerpt で示す。
                line_no = 0
                for index, line in enumerate(lines, start=1):
                    if pattern.search(line):
                        line_no = index
                        break
                hits.append(
                    Hit(guard.guard_id, pattern.pattern, rel, line_no, excerpt)
                )
    return hits


def check_manuscript_not_vacuous(main_path: Path) -> list[str]:
    """本文が空・骨組みだけでないことを確かめる (ヒット 0 の恒真性対策)."""
    problems: list[str] = []
    text = main_path.read_text(encoding="utf-8")
    word_count = len(text.split())
    if word_count < MAIN_MIN_WORDS:
        problems.append(
            f"{main_path.name}: 語数 {word_count} < {MAIN_MIN_WORDS}。"
            "本文が未完成のまま「禁止句ヒット 0」で通るのを防ぐための前提条件"
        )
    lowered = text.lower()
    missing = [
        anchor for anchor in MAIN_REQUIRED_ANCHORS if anchor.lower() not in lowered
    ]
    if missing:
        problems.append(f"{main_path.name}: 必須アンカーが無い: {missing}")
    return problems


def _extract_main_abstract(main_path: Path) -> str | None:
    """`main.md` の `## Abstract` 節の本文を取り出す (見出しと空行を除く)."""
    lines = main_path.read_text(encoding="utf-8").splitlines()
    body: list[str] = []
    in_abstract = False
    for line in lines:
        if line.startswith("## "):
            if in_abstract:
                break
            in_abstract = line.strip().lower() == "## abstract"
            continue
        if in_abstract:
            if line.strip() == "---":
                break
            body.append(line)
    text = " ".join(body).strip()
    return text or None


def check_abstract_consistency(main_path: Path, citation_path: Path) -> list[str]:
    """`main.md` の Abstract と `CITATION.cff` の `abstract` が同一であることを確かめる.

    片方だけ直すと、公開 repo の引用ウィジェットと本文が静かに食い違う。
    """
    import yaml  # noqa: PLC0415  (lockfile 環境にのみ存在する依存)

    manuscript_abstract = _extract_main_abstract(main_path)
    if manuscript_abstract is None:
        return [f"{main_path.name}: `## Abstract` 節が空か見つからない"]

    citation = yaml.safe_load(citation_path.read_text(encoding="utf-8"))
    citation_abstract = citation.get("abstract")
    if not citation_abstract:
        return [
            f"{citation_path.name}: `abstract` が空。"
            "本文が存在する以上、ここを空のまま公開しない"
        ]

    normalise = " ".join
    left = normalise(manuscript_abstract.split())
    right = normalise(str(citation_abstract).split())
    if left != right:
        return [
            f"{main_path.name} の Abstract と {citation_path.name} の abstract が違う。"
            "片方だけ直すと公開 metadata と本文が食い違う\n"
            f"      main.md      : {left[:120]}…\n"
            f"      CITATION.cff : {right[:120]}…"
        ]
    print(
        f"[claim-boundary] OK: {main_path.name} の Abstract と "
        f"{citation_path.name} の abstract は一致 ({len(left.split())} words)"
    )
    return []


def check_positive_control(guards: tuple[Guard, ...], fixture_path: Path) -> list[str]:
    """陽性対照で**すべてのパターンが 1 本残らず**発火することを確かめる.

    ガード単位 (「G7 のどれか 1 本が当たればよい」) では弱い。2026-09-12 の変異検査で、
    G7 の 2 本あるパターンの片方を壊しても、もう片方が fixture に当たるために検査が
    素通りすることを実測した。**パターン単位**にすることで、1 本でも壊れたら落ちる。
    """
    text = normalise_whitespace(fixture_path.read_text(encoding="utf-8"))
    silent = [
        f"{guard.guard_id}:{pattern.pattern}"
        for guard in guards
        for pattern in guard.patterns
        if not pattern.search(text)
    ]
    total = sum(len(guard.patterns) for guard in guards)
    if silent:
        return [
            f"{fixture_path.name}: 陽性対照で発火しなかったパターン "
            f"({len(silent)}/{total}): {silent}。"
            "検査器が壊れているか、パターンが言い回しを捕まえられていない"
        ]
    print(
        f"[claim-boundary] OK: 陽性対照で {total}/{total} パターンが発火 "
        f"({len(guards)} guards)"
    )
    return []


def _die(message: str) -> None:
    print(f"[claim-boundary] FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="repo root",
    )
    args = parser.parse_args(argv)
    repo_root: Path = args.repo_root

    boundary_path = repo_root / "manuscript" / "CLAIM-BOUNDARY.md"
    main_path = repo_root / "manuscript" / "main.md"
    fixture_path = repo_root / "manuscript" / "_claim_boundary_positive_control.md"
    citation_path = repo_root / "CITATION.cff"
    targets = (main_path, repo_root / "README.md", citation_path)

    for path in (boundary_path, main_path, fixture_path, *targets):
        if not path.is_file():
            _die(f"必要なファイルが無い: {path}")

    guards = parse_guards(boundary_path)
    print(f"[claim-boundary] {len(guards)} guards parsed from {boundary_path.name}")

    problems: list[str] = []
    problems.extend(check_manuscript_not_vacuous(main_path))
    problems.extend(check_abstract_consistency(main_path, citation_path))
    problems.extend(check_positive_control(guards, fixture_path))

    hits: list[Hit] = []
    for path in targets:
        hits.extend(scan(guards, path, repo_root))

    if hits:
        for hit in hits:
            problems.append(
                f"{hit.path}:{hit.line_no}: {hit.guard_id} "
                f"pattern={hit.pattern!r} に一致: {hit.line}"
            )

    if problems:
        print("[claim-boundary] FAIL", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        print(
            "\n  ヒットしたら本文を直す。検査を緩めない "
            "(CLAIM-BOUNDARY.md §2)。",
            file=sys.stderr,
        )
        return 1

    scanned = ", ".join(path.relative_to(repo_root).as_posix() for path in targets)
    print(
        f"[claim-boundary] OK: {scanned} に禁止句なし "
        "(パターンは英語。日本語の散文は言語非依存の literal しか検査されない)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
