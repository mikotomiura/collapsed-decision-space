"""Machine-readable T20 acceptance checklist.

The human-facing runbook uses the same :attr:`AcceptanceItem.id` values so
manual operator checks map 1-to-1 to this list.

Consumers:

* ``tests/test_integration/test_acceptance_coverage.py`` (future) — parametrize
  one test per item once automated verification is wired
* The T20 acceptance session — operator walks the Markdown runbook and updates
  the ``verification`` status out-of-band (no mutation of this file expected)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class AcceptanceItem:
    """One line of the T20 acceptance checklist.

    Attributes:
        id: Stable identifier (e.g. ``"ACC-SCHEMA-FROZEN"``). Referenced from
            the Markdown runbook.
        category: Grouping tag — one of ``"schema"``, ``"runtime"``,
            ``"memory"``, ``"observability"``, ``"docs"``, ``"reproducibility"``.
        description: What the operator or test verifies.
        verification: Short imperative how-to
            (e.g. ``"run `uv run pytest tests/test_integration` and expect green"``).
    """

    id: str
    category: str
    description: str
    verification: str


ACCEPTANCE_CHECKLIST: Final[tuple[AcceptanceItem, ...]] = (
    AcceptanceItem(
        id="ACC-SCHEMA-FROZEN",
        category="schema",
        description="ControlEnvelope と Thresholds の json_schema が snapshot と一致",
        verification="uv run pytest tests/test_integration/test_contract_snapshot.py",
    ),
    AcceptanceItem(
        id="ACC-SCENARIO-WALKING",
        category="runtime",
        description="S_WALKING が 3 連続実行で全て成功する",
        verification=(
            "uv run pytest tests/test_integration/test_scenario_walking.py"
            " -n 1 --count 3"
        ),
    ),
    AcceptanceItem(
        id="ACC-SCENARIO-MEMORY-WRITE",
        category="memory",
        description="S_MEMORY_WRITE で episodic 4 + semantic 1 件が sqlite-vec に書込",
        verification=(
            "uv run pytest tests/test_integration/test_scenario_memory_write.py"
        ),
    ),
    AcceptanceItem(
        id="ACC-SCENARIO-TICK-ROBUSTNESS",
        category="runtime",
        description="S_TICK_ROBUSTNESS で tick drop / reconnect に耐える",
        verification=(
            "uv run pytest tests/test_integration/test_scenario_tick_robustness.py"
        ),
    ),
    AcceptanceItem(
        id="ACC-LATENCY-P50",
        category="runtime",
        description="p50 envelope latency ≤ M2_THRESHOLDS.latency_p50_ms_max",
        verification="scenario ログから latency 分布を抽出、p50 を計算し閾値比較",
    ),
    AcceptanceItem(
        id="ACC-LATENCY-P95",
        category="runtime",
        description="p95 envelope latency ≤ M2_THRESHOLDS.latency_p95_ms_max",
        verification="同上 p95",
    ),
    AcceptanceItem(
        id="ACC-TICK-JITTER",
        category="runtime",
        description="tick 周期の σ / 公称周期 ≤ M2_THRESHOLDS.tick_jitter_sigma_max",
        verification="WorldTickMsg 受信間隔の系列を収集、σ/μ を計算",
    ),
    AcceptanceItem(
        id="ACC-MEMORY-WRITE-RATE",
        category="memory",
        description="memory 書込み成功率 ≥ M2_THRESHOLDS.memory_write_success_rate_min",
        verification="ログから write attempt / success を集計",
    ),
    AcceptanceItem(
        id="ACC-STATE-RANGE",
        category="runtime",
        description="AgentState.{arousal, valence, attention} が閾値範囲内 (逸脱 0 件)",
        verification="scenario 実行中の AgentUpdateMsg を全件検査し値域チェック",
    ),
    AcceptanceItem(
        id="ACC-LOGS-PERSISTED",
        category="observability",
        description="全 envelope と memory write のログが永続化されている",
        verification="logs/ 配下の目視、scenario 実行時の TS 網羅を確認",
    ),
    AcceptanceItem(
        id="ACC-REPRO-SEED",
        category="reproducibility",
        description="ランダムシード固定で scenario が再現する",
        verification="同一シード 2 回実行、AgentUpdateMsg 列の同値性を diff 確認",
    ),
    AcceptanceItem(
        id="ACC-DOCS-UPDATED",
        category="docs",
        description="docs/architecture.md の WS/Gateway 節が T14 完成版に更新済み",
        verification="git log --follow docs/architecture.md で T14 関連 commit 確認",
    ),
    AcceptanceItem(
        id="ACC-MASTER-PLAN-SYNC",
        category="docs",
        description="MASTER-PLAN tasklist の T14/T19/T20 が完了マーク + PR 番号併記",
        verification=(
            "Confirm the MASTER-PLAN tasklist marks T14/T19/T20 complete "
            "with their PR numbers."
        ),
    ),
    AcceptanceItem(
        id="ACC-CI-GREEN",
        category="runtime",
        description="ruff check / ruff format --check / mypy src / pytest が main で緑",
        verification="GitHub Actions の main 最新ビルドが全 job 成功",
    ),
    AcceptanceItem(
        id="ACC-TAG-READY",
        category="docs",
        description="CITATION.cff と pyproject.toml のバージョンが v0.1.0-m2 に一致",
        verification="grep '0.1.0' CITATION.cff pyproject.toml",
    ),
)
"""M2 acceptance checklist. 15 items covering 6 categories.

Categories: schema (1), runtime (6), memory (2), observability (1),
reproducibility (1), docs (3).
"""


__all__ = ["ACCEPTANCE_CHECKLIST", "AcceptanceItem"]
