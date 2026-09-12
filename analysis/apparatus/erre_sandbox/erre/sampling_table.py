"""Static ERRE mode → :class:`SamplingDelta` lookup table (M5).

Encodes the 8-mode × 3-parameter additive delta table from the
``persona-erre`` skill §ルール 2 as a module-level
:class:`MappingProxyType` constant. The FSM hook in
:func:`erre_sandbox.cognition.cycle.CognitionCycle._maybe_apply_erre_fsm`
reads this table when it constructs a fresh :class:`ERREMode`, so the next
:func:`erre_sandbox.inference.sampling.compose_sampling` call automatically
picks up the mode-appropriate delta.

The table is the single source of truth for the delta values in code.
The accompanying ``tests/test_erre/test_sampling_table.py`` asserts the
canonical values explicitly so any drift surfaces at CI time.

Canonical delta table (reproduced here for reviewers; **do not edit in
isolation** — change the values deliberately and update the test in lockstep):

    | mode          | temp  | top_p | repeat_penalty |
    |---------------|-------|-------|----------------|
    | peripatetic   | +0.3  | +0.05 | -0.1           |
    | chashitsu     | -0.2  | -0.05 | +0.1           |
    | zazen         | -0.3  | -0.1  |  0.0           |
    | shu_kata      | -0.2  | -0.05 | +0.2           |
    | ha_deviate    | +0.1  | +0.05 | -0.1           |
    | ri_create     | +0.2  | +0.1  | -0.2           |
    | deep_work     |  0.0  |  0.0  |  0.0           |
    | shallow       | -0.1  | -0.05 |  0.0           |
"""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from erre_sandbox.schemas import ERREModeName, SamplingDelta

if TYPE_CHECKING:
    from collections.abc import Mapping

SAMPLING_DELTA_BY_MODE: Final[Mapping[ERREModeName, SamplingDelta]] = MappingProxyType(
    {
        ERREModeName.PERIPATETIC: SamplingDelta(
            temperature=0.3,
            top_p=0.05,
            repeat_penalty=-0.1,
        ),
        ERREModeName.CHASHITSU: SamplingDelta(
            temperature=-0.2,
            top_p=-0.05,
            repeat_penalty=0.1,
        ),
        ERREModeName.ZAZEN: SamplingDelta(
            temperature=-0.3,
            top_p=-0.1,
            repeat_penalty=0.0,
        ),
        ERREModeName.SHU_KATA: SamplingDelta(
            temperature=-0.2,
            top_p=-0.05,
            repeat_penalty=0.2,
        ),
        ERREModeName.HA_DEVIATE: SamplingDelta(
            temperature=0.1,
            top_p=0.05,
            repeat_penalty=-0.1,
        ),
        ERREModeName.RI_CREATE: SamplingDelta(
            temperature=0.2,
            top_p=0.1,
            repeat_penalty=-0.2,
        ),
        # DEEP_WORK intentionally leaves the persona's base sampling intact;
        # all-zero delta is the explicit no-op, not an omission.
        ERREModeName.DEEP_WORK: SamplingDelta(),
        ERREModeName.SHALLOW: SamplingDelta(
            temperature=-0.1,
            top_p=-0.05,
            repeat_penalty=0.0,
        ),
    },
)


__all__ = ["SAMPLING_DELTA_BY_MODE"]
