#!/usr/bin/env python3
"""閾値が実走より前に凍結されていたことを、repo 上で辿れる形で検査する.

「margin 0.10 は ``tv_bar = 0.038065`` を見てから決めたのでは」という問いに対する
反証を機械化する。示すことを 2 つに分け、**それぞれの射程を混ぜない**。

1. **値の一致** — 同梱 apparatus の凍結定数が、完了済み実走の ``verdict.json`` の
   ``thresholds`` と一致する。run パラメータ (``k_contexts`` / ``m_draws``) は定数では
   ないので ``manifest.json`` の ``run`` と照合する。
2. **bytes の同一性 (content-addressed)** — 同梱されている定数ファイルが、
   ``analysis/freeze-provenance.json`` が名指しする**上流 commit の blob そのもの**で
   あることを、git blob 識別子 ``sha1(b"blob <size>\\0" + content)`` の再計算で確かめる。
   ネットワークも git の実行も要らない。

**この 2 つが示さないもの**: commit の**日付そのもの**。日付は公開されている上流
リポジトリの性質であり、``freeze-provenance.json`` の URL を辿って確認する。
「凍結が実走より前だった」は 1 と 2 と日付の連言であって、どれか 1 つでは言えない。
``--upstream-repo <path>`` を渡すと、上流の clone に対して blob / 日付 / ancestor 関係を
**追加で**機械検査する (既定はオフライン)。

この分割は ``codex-review.md`` §6 が残した宿題への回答である。Codex は
「git 履歴上の凍結日時までは検証していない。ファイル内容上の定数・verdict JSON の
一致だけ確認した」と明記していた。ここを曖昧にすると
``feedback_checker_handed_target_is_not_checked`` と同型になる。

使い方:
    python analysis/scripts/verify_threshold_freeze.py
    python analysis/scripts/verify_threshold_freeze.py --upstream-repo /path/to/ERRE-Sandbox
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _provenance import (  # noqa: E402
    check_upstream_blob,
    check_upstream_commit_time,
    git,
    git_blob_sha1,
    load_json,
)

#: 浮動小数の比較許容。verdict.json は 6 桁量子化された値を持つ。
FLOAT_TOL = 1e-9


def _values_agree(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return abs(float(left) - float(right)) <= FLOAT_TOL
    return bool(left == right)


def check_apparatus_closure(
    repo_root: Path, provenance: dict[str, Any], upstream: Path | None
) -> list[str]:
    """同梱 apparatus 全件が上流 commit の blob と byte 一致することを確かめる.

    ``manuscript/main.md`` §13 は apparatus を「上流から byte-for-byte で複製した
    import 閉包」と書いている。**主張で終わらせずに検査する**ため、閉包の全ファイルの
    blob 識別子を突き合わせる。閾値が載っている 2 本 (``frozen_files``) だけを
    検査していると、残りは無検査の影になる。
    """
    problems: list[str] = []
    closure = provenance["apparatus_closure"]
    shipped_root = repo_root / closure["shipped_prefix"]
    recorded = {entry["path"] for entry in closure["files"]}

    if len(closure["files"]) != closure["file_count"]:
        problems.append(
            f"apparatus_closure: file_count={closure['file_count']} だが "
            f"files は {len(closure['files'])} 件"
        )

    for entry in closure["files"]:
        shipped = shipped_root / entry["path"]
        if not shipped.is_file():
            problems.append(
                f"apparatus に無い: {closure['shipped_prefix']}{entry['path']}"
            )
            continue
        actual = git_blob_sha1(shipped.read_bytes())
        if actual != entry["blob_sha1"]:
            problems.append(
                f"{closure['shipped_prefix']}{entry['path']}: blob SHA-1 が上流 "
                f"{closure['upstream_commit'][:7]} の記録と違う "
                f"(expected={entry['blob_sha1']} actual={actual})"
            )
        elif upstream is not None:
            problems.extend(
                check_upstream_blob(
                    upstream,
                    closure["upstream_commit"],
                    closure["upstream_prefix"] + entry["path"],
                    entry["blob_sha1"],
                )
            )

    on_disk = {
        path.relative_to(shipped_root).as_posix()
        for path in shipped_root.rglob("*.py")
    }
    unrecorded = sorted(on_disk - recorded)
    if unrecorded:
        problems.append(
            f"apparatus に来歴の無いファイルがある: {unrecorded}。"
            "閉包に足したなら freeze-provenance.json にも登録すること"
        )

    if not problems:
        suffix = "" if upstream is None else " (上流 clone でも照合済)"
        print(
            f"[freeze] closure OK {closure['file_count']} files "
            f"== 上流 {closure['upstream_commit'][:7]} の blob{suffix}"
        )
    return problems


def check_blob_identity(repo_root: Path, provenance: dict[str, Any]) -> list[str]:
    """同梱ファイルが凍結 commit の blob と byte 一致することを確かめる."""
    problems: list[str] = []
    for entry in provenance["frozen_files"]:
        shipped = repo_root / entry["shipped_path"]
        if not shipped.is_file():
            problems.append(f"同梱ファイルが無い: {entry['shipped_path']}")
            continue
        actual = git_blob_sha1(shipped.read_bytes())
        expected = entry["blob_sha1"]
        if actual != expected:
            problems.append(
                f"{entry['shipped_path']}: blob SHA-1 が凍結 commit "
                f"{entry['freeze_commit'][:7]} の記録と違う "
                f"(expected={expected} actual={actual})"
            )
        else:
            print(
                f"[freeze] blob OK  {entry['shipped_path']} "
                f"== {expected[:12]}… @ {entry['freeze_commit'][:7]} "
                f"({entry['freeze_commit_utc']})"
            )
    return problems


def load_shipped_module(shipped: Path, module_name: str) -> ModuleType:
    """同梱ファイルの **bytes をその場で評価して** モジュールを作る.

    ``import_module`` を使わないのは、``__pycache__`` が古いと **ファイルの中身と
    import された値が食い違いうる**からである (2026-09-12 に実測: 同梱ファイルを
    書き戻した直後、ディスク上は ``0.10`` なのに import は ``0.15`` を返した)。
    ここで評価するのは :func:`check_blob_identity` が blob SHA-1 で検証したのと
    **同じ bytes** であり、値の検査と bytes の検査が同一の出所を読むようにしてある。
    """
    source = shipped.read_bytes()
    module = ModuleType(module_name)
    module.__file__ = str(shipped)
    module.__package__ = module_name.rpartition(".")[0]
    code = compile(source, str(shipped), "exec")
    # `@dataclass` は `sys.modules[cls.__module__]` を引くので、exec の前に
    # 登録しておかないと `AttributeError: 'NoneType' object has no attribute
    # '__dict__'` になる。登録しておくと、これらのモジュールを import する側
    # (bank_scorer → bank_power) も同じ「検証済み bytes」を読むことになる。
    sys.modules[module_name] = module
    try:
        exec(code, module.__dict__)  # noqa: S102
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


def check_threshold_values(
    repo_root: Path, provenance: dict[str, Any], verdict: dict[str, Any]
) -> list[str]:
    """凍結定数が verdict.json の thresholds と一致することを確かめる."""
    problems: list[str] = []
    apparatus = repo_root / "analysis" / "apparatus"
    if str(apparatus) not in sys.path:
        sys.path.insert(0, str(apparatus))

    thresholds = verdict["thresholds"]
    covered: set[str] = set()

    for entry in provenance["frozen_files"]:
        shipped = repo_root / entry["shipped_path"]
        if not shipped.is_file():
            problems.append(f"同梱ファイルが無い: {entry['shipped_path']}")
            continue
        module = load_shipped_module(shipped, entry["module"])
        for threshold_key, constant_name in entry["threshold_map"].items():
            if threshold_key not in thresholds:
                problems.append(
                    f"verdict.json の thresholds に {threshold_key} が無い"
                )
                continue
            constant_value = getattr(module, constant_name)
            recorded = thresholds[threshold_key]
            covered.add(threshold_key)
            if not _values_agree(constant_value, recorded):
                problems.append(
                    f"MISMATCH {threshold_key}: "
                    f"{entry['module']}.{constant_name}={constant_value} "
                    f"vs verdict.json={recorded}"
                )
            else:
                print(
                    f"[freeze] value OK {threshold_key:>14} = {recorded} "
                    f"({constant_name})"
                )

    uncovered = sorted(set(thresholds) - covered)
    expected_uncovered = sorted(provenance["run_parameter_map"])
    if uncovered != expected_uncovered:
        problems.append(
            "thresholds のうち定数照合されなかったキーが想定と違う "
            f"(expected={expected_uncovered} found={uncovered})。"
            "新しい閾値が黙って増えていないか確認すること"
        )
    return problems


def check_run_parameters(
    provenance: dict[str, Any], verdict: dict[str, Any], manifest: dict[str, Any]
) -> list[str]:
    """run パラメータが manifest の run と一致することを確かめる."""
    problems: list[str] = []
    thresholds = verdict["thresholds"]
    run = manifest["run"]
    for threshold_key, run_key in provenance["run_parameter_map"].items():
        if not _values_agree(thresholds[threshold_key], run[run_key]):
            problems.append(
                f"MISMATCH {threshold_key}: verdict.json={thresholds[threshold_key]} "
                f"vs manifest.json run.{run_key}={run[run_key]}"
            )
        else:
            print(
                f"[freeze] run   OK {threshold_key:>14} = {run[run_key]} "
                "(manifest.run)"
            )
    return problems


def check_recorded_ordering(provenance: dict[str, Any]) -> list[str]:
    """記録された凍結 commit 時刻が実走 commit 時刻より前であることを確かめる.

    これは **記録の内部整合性** の検査であって、日付そのものの検証ではない。
    日付は上流の公開リポジトリを辿って確認する (`--upstream-repo` で機械化できる)。
    """
    problems: list[str] = []
    run_at = datetime.fromisoformat(
        provenance["run_commit"]["commit_utc"].replace("Z", "+00:00")
    )
    for entry in provenance["frozen_files"]:
        froze_at = datetime.fromisoformat(
            entry["freeze_commit_utc"].replace("Z", "+00:00")
        )
        if froze_at >= run_at:
            problems.append(
                f"{entry['shipped_path']}: 記録上の凍結時刻 {froze_at.isoformat()} が "
                f"実走 commit {run_at.isoformat()} より後になっている"
            )
        else:
            delta = run_at - froze_at
            print(
                f"[freeze] recorded-order OK {entry['shipped_path'].split('/')[-1]}: "
                f"凍結は実走の {delta} 前"
            )
    return problems


def check_upstream(upstream: Path, provenance: dict[str, Any]) -> list[str]:
    """上流の clone に対して blob / 日付 / ancestor を追加検査する (任意)."""
    problems: list[str] = []
    run_commit = provenance["run_commit"]["commit"]

    code, _ = git(upstream, "cat-file", "-e", f"{run_commit}^{{commit}}")
    if code != 0:
        return [
            f"--upstream-repo {upstream}: 実走 commit {run_commit[:7]} が見つからない"
        ]

    problems.extend(
        check_upstream_commit_time(
            upstream, run_commit, provenance["run_commit"]["commit_utc"]
        )
    )

    for entry in provenance["frozen_files"]:
        commit = entry["freeze_commit"]
        problems.extend(
            check_upstream_blob(
                upstream, commit, entry["upstream_path"], entry["blob_sha1"]
            )
        )
        problems.extend(
            check_upstream_commit_time(upstream, commit, entry["freeze_commit_utc"])
        )
        code, _ = git(upstream, "merge-base", "--is-ancestor", commit, run_commit)
        if code != 0:
            problems.append(
                f"凍結 commit {commit[:7]} が実走 commit {run_commit[:7]} の "
                "ancestor ではない"
            )
        else:
            print(
                f"[freeze] upstream OK {commit[:7]} は {run_commit[:7]} の ancestor / "
                "blob と日時が記録と一致"
            )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="repo root",
    )
    parser.add_argument(
        "--upstream-repo",
        type=Path,
        default=None,
        help=(
            "上流 ERRE-Sandbox の clone。渡すと blob / commit 日時 / ancestor を"
            "追加検査する (既定はオフライン検査のみ)"
        ),
    )
    args = parser.parse_args(argv)
    repo_root: Path = args.repo_root

    provenance = load_json(repo_root / "analysis" / "freeze-provenance.json")
    verdict = load_json(repo_root / "data" / "raw" / "cproper-verdict.json")
    manifest = load_json(repo_root / "data" / "raw" / "cproper-manifest.json")

    problems: list[str] = []
    problems.extend(check_blob_identity(repo_root, provenance))
    problems.extend(
        check_apparatus_closure(repo_root, provenance, args.upstream_repo)
    )
    problems.extend(check_threshold_values(repo_root, provenance, verdict))
    problems.extend(check_run_parameters(provenance, verdict, manifest))
    problems.extend(check_recorded_ordering(provenance))

    if args.upstream_repo is not None:
        problems.extend(check_upstream(args.upstream_repo, provenance))
    else:
        print(
            "[freeze] note: オフライン検査のみ。commit の日付は "
            f"{provenance['upstream']['repository']} を辿って確認する "
            "(--upstream-repo で機械検査できる)"
        )

    if problems:
        print("[freeze] FAIL", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print("[freeze] OK: 値の一致と bytes の同一性を確認した")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
