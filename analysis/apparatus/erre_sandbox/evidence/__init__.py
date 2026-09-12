"""Evidence layer — post-hoc metric computation over persisted run data.

Two metric suites live here:

* ``metrics`` — M8 baseline quality (L6 D1 後半): self_repetition_rate /
  cross_persona_echo_rate / bias_fired_rate. CLI: ``baseline-metrics``.
* ``scaling_metrics`` — M8 scaling bottleneck profiling (L6 D2 spike):
  pair_information_gain / late_turn_fraction / zone_kl_from_uniform with
  analytic-bound thresholds. CLI: ``scaling-metrics``.

Both modules are pure-function suites with thin ``aggregate(...)`` I/O
wrappers; the live run is responsible for persistence (sqlite +
journal NDJSON) and the post-hoc CLI computes scalars.

Layer dependency:

* allowed: ``erre_sandbox.cognition`` (constants only),
  ``erre_sandbox.memory``, ``erre_sandbox.schemas``
* forbidden: ``world``, ``integration``, ``ui``
"""

from erre_sandbox.evidence.metrics import (
    aggregate,
    compute_bias_fired_rate,
    compute_cross_persona_echo_rate,
    compute_self_repetition_rate,
)
from erre_sandbox.evidence.scaling_metrics import (
    aggregate as scaling_aggregate,
)
from erre_sandbox.evidence.scaling_metrics import (
    compute_late_turn_fraction,
    compute_pair_information_gain,
    compute_zone_kl_from_uniform,
    default_thresholds,
    evaluate_thresholds,
)

__all__ = [
    "aggregate",
    "compute_bias_fired_rate",
    "compute_cross_persona_echo_rate",
    "compute_late_turn_fraction",
    "compute_pair_information_gain",
    "compute_self_repetition_rate",
    "compute_zone_kl_from_uniform",
    "default_thresholds",
    "evaluate_thresholds",
    "scaling_aggregate",
]
