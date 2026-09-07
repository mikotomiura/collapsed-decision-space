"""M13-ES3 locomotion → sampling-modulation conformance evidence layer.

Deterministic, GPU/LLM-free apparatus for the **third** step of the
embodiment-substrate arc (M13). On top of the ES-1 SPDM substrate (frozen GO) and
the ES-2 recombination replay (bounded INCONCLUSIVE), ES-3 asks whether an agent's
**kinetic history** — a locomotion-intensity EMA λ that is *decoupled from zone
identity* — wires into the resolved sampling temperature **inside static
``(persona, zone)`` cells**, i.e. as a channel structurally distinct from the
existing ``peripatetic`` location channel (the zone-triggered static +0.3 temp).

The layer is **USE-only** over the core: it composes sampling through the frozen
``inference.sampling.compose_sampling`` and ``erre.locomotion_sampling`` and reads
``erre`` constants; it never imports ``cognition`` or mutates a frozen ES-1 / ES-2
asset. The estimand is the **nested fixed-effect reduced model** ``E ~ C(p, z)``
with **headroom-normalised** within-cell amplitude ``D_loco`` (:mod:`decomposition`,
ADR §2, Codex HIGH-1/HIGH-2 — the vacuous standalone N_zone η² of v2 is removed).
World geometry is **mirrored** (not imported) and pinned to ``world.zones`` in the
scenario test. Every threshold in :mod:`constants` is pre-registered (§5 numeric
freeze, user-ratified) *before* any result.

**Falsifiability** (the design's central guarantee, ``design-final.md`` §2.4 / §3):

* the blind-walk **generator is exact and frozen** — uniform over
  ``ADJACENCY[z] ∪ {z}`` (stay probability ``1/(deg+1)`` is graph-determined, not
  a designer knob), so λ varies *within* a zone visit and is **not** a function of
  the zone;
* the **zone-function positive control** forces λ = h(z) and shows ``D_loco``
  collapses to 0 — the estimand *can* read 0, so a non-zero ``D_loco`` on the blind
  walk is a real within-cell locomotion signal, not a constructive guarantee;
* the **ablation** is expressed as the *bit-equality* of the ``loco_delta=None``
  path and the ``gain=0`` path (Codex L2), not a magnitude difference;
* the bootstrap unit is the **per-walk-seed aggregate ``D_loco^(b)``** (the EMA
  autocorrelation forbids a step-row bootstrap, Codex HIGH-4);
* headroom saturation (base+mode near the clamp) is **INCONCLUSIVE**, an effective
  modulation below ``AMP_FLOOR`` with sufficient headroom is **NO_GO** (Codex M2),
  never conflated.

Claim boundary (``design-final.md`` §0 / §8): a GO is "**eligible to proceed to
ES-4 / divergence measurement**", *not* a test of walking → creative divergence
(that needs LLM power, deferred). Oppezzo 2014's treadmill-wall RCT is the best
external *warrant* for trying ES-3, not direct causal evidence. NO_GO is a
progressive finding; INCONCLUSIVE is kept distinct.
"""

from __future__ import annotations
