"""Frozen E2E scenarios for M2 acceptance (T19 / T20).

Each :class:`Scenario` is a typed, immutable time-series description of a
single end-to-end flow. Scenarios are **consumed** by:

* :mod:`tests.test_integration` skeleton tests (skipped until T14 lands)

The scenario data here is the machine-readable source of truth. The Markdown
narrative repeats the story in prose but does not redefine any step.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from erre_sandbox.schemas import ERREModeName, Zone


@dataclass(frozen=True, slots=True)
class ScenarioStep:
    """A single step inside a :class:`Scenario`.

    Attributes:
        t_s: Offset from the scenario start in seconds. Steps should be
            strictly monotonic per scenario so pytest parametrize can ``sorted``.
        actor: Which side of the system drives this step. One of
            ``"world"`` (tick / physics), ``"cognition"`` (LLM cycle),
            ``"gateway"`` (WS frame), ``"godot"`` (viewer action).
        action: Short imperative description of the step
            (e.g. ``"emit WorldTickMsg"``).
        expect: What the observer (test harness) must verify after this step.
    """

    t_s: float
    actor: str
    action: str
    expect: str


@dataclass(frozen=True, slots=True)
class Scenario:
    """A complete M2 end-to-end scenario.

    Attributes:
        id: Stable string identifier (e.g. ``"S_WALKING"``). Referenced from
            Markdown narrative and from individual test ids.
        title: Human-readable summary (ja, one line).
        persona_id: Which persona drives this scenario. M2 limits this to
            ``"kant"``.
        zone: Which zone is active. M2 limits this to
            :attr:`~erre_sandbox.schemas.Zone.PERIPATOS`.
        erre_modes: Expected ERRE-mode sequence during the scenario.
        steps: Ordered timeline of :class:`ScenarioStep` items.
    """

    id: str
    title: str
    persona_id: str
    zone: Zone
    erre_modes: tuple[ERREModeName, ...]
    steps: tuple[ScenarioStep, ...] = field(default_factory=tuple)


SCENARIO_WALKING: Final[Scenario] = Scenario(
    id="S_WALKING",
    title="Kant が Peripatos を歩き、SHALLOW → PERIPATETIC へ遷移する",
    persona_id="kant",
    zone=Zone.PERIPATOS,
    erre_modes=(ERREModeName.SHALLOW, ERREModeName.PERIPATETIC),
    steps=(
        ScenarioStep(
            t_s=0.0,
            actor="world",
            action="Kant エージェントをワールドに登録、Peripatos に初期配置",
            expect="AgentUpdateMsg が 1 件、erre_mode=SHALLOW、zone=PERIPATOS",
        ),
        ScenarioStep(
            t_s=1.0,
            actor="gateway",
            action="heartbeat tick を送出 (WorldTickMsg)",
            expect="クライアントが WorldTickMsg を 1 件受信",
        ),
        ScenarioStep(
            t_s=10.0,
            actor="cognition",
            action="最初の認知サイクルが走り、歩行方向を更新 (MoveMsg)",
            expect="MoveMsg 1 件、speed > 0、erre_mode=PERIPATETIC へ遷移済み",
        ),
        ScenarioStep(
            t_s=11.0,
            actor="godot",
            action="Godot 側 Avatar が Tween で target に向かって移動開始",
            expect="godot 側 animation=walk、position が target 方向に前進",
        ),
    ),
)

SCENARIO_MEMORY_WRITE: Final[Scenario] = Scenario(
    id="S_MEMORY_WRITE",
    title="歩行中に episodic 4 件 + semantic 1 件が memory-store に書き込まれる",
    persona_id="kant",
    zone=Zone.PERIPATOS,
    erre_modes=(ERREModeName.PERIPATETIC,),
    steps=(
        ScenarioStep(
            t_s=0.0,
            actor="world",
            action="S_WALKING の終端状態から継続 (Kant が Peripatos を歩行中)",
            expect="erre_mode=PERIPATETIC が維持されている",
        ),
        ScenarioStep(
            t_s=10.0,
            actor="cognition",
            action="4 episodic + 1 semantic 記憶を memory-store へ書込",
            expect="sqlite-vec に 5 行の増加、embedding prefix を正しく付与",
        ),
        ScenarioStep(
            t_s=11.0,
            actor="gateway",
            action="AgentUpdateMsg で新規記憶の要約を反映",
            expect="agent_state.memory_count が 5 増える",
        ),
    ),
)

SCENARIO_TICK_ROBUSTNESS: Final[Scenario] = Scenario(
    id="S_TICK_ROBUSTNESS",
    title="tick 抜け・disconnect/reconnect に対する回復性",
    persona_id="kant",
    zone=Zone.PERIPATOS,
    erre_modes=(ERREModeName.SHALLOW, ERREModeName.PERIPATETIC),
    steps=(
        ScenarioStep(
            t_s=0.0,
            actor="world",
            action="S_WALKING の初期状態から開始",
            expect="AgentUpdateMsg を 1 件受信",
        ),
        ScenarioStep(
            t_s=2.0,
            actor="gateway",
            action="heartbeat を 1 つ drop (シミュレート)",
            expect="クライアント側で liveness alarm は発報しない (3x 耐性)",
        ),
        ScenarioStep(
            t_s=10.0,
            actor="godot",
            action="WS を強制切断、5 秒後に再接続",
            expect="新 HandshakeMsg 交換、session は別 instance、AgentState 再送",
        ),
        ScenarioStep(
            t_s=20.0,
            actor="cognition",
            action="認知サイクル継続",
            expect="disconnect 前後で agent_id は同一、memory に矛盾なし",
        ),
    ),
)

M2_SCENARIOS: Final[tuple[Scenario, ...]] = (
    SCENARIO_WALKING,
    SCENARIO_MEMORY_WRITE,
    SCENARIO_TICK_ROBUSTNESS,
)
"""All M2 scenarios in execution order.

Used by :mod:`tests.test_integration` to iterate via pytest parametrize once
T14 gateway is in place and the skip marker is removed.
"""

__all__ = [
    "M2_SCENARIOS",
    "SCENARIO_MEMORY_WRITE",
    "SCENARIO_TICK_ROBUSTNESS",
    "SCENARIO_WALKING",
    "Scenario",
    "ScenarioStep",
]
