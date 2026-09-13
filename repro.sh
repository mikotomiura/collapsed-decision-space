#!/usr/bin/env bash
# One-command reproduction.
#
# Until this exits 0, nothing in this repository claims to be reproducible.
#
# Usage:  bash repro.sh
#
# Requires:
#   - uv (https://docs.astral.sh/uv/)
#   - network access, for the first dependency installation
#
# Optional:
#   ERRE_SANDBOX_REPO=/path/to/upstream/clone
#     Additionally checks upstream commit dates and ancestry against that clone. Without it the
#     provenance checks run offline and establish content rather than chronology; manuscript/main.md
#     section 10.2 states which half establishes what.
#
# Steps, in order. Any failure ends the run immediately with a non-zero status:
#   1. pin the environment from the lockfile
#   2. lint
#   3. frozen inputs: SHA-256 and upstream blobs   analysis/scripts/verify_data_hashes.py
#   4. threshold freeze: values and bytes          analysis/scripts/verify_threshold_freeze.py
#   5. recompute the recorded verdict              analysis/scripts/recompute_verdict.py
#   6. extract the quantities the paper quotes     analysis/scripts/extract_verdict_table.py
#   7. regenerate the power table                  analysis/scripts/power_curve.py
#   8. support of the decision space + null floor  analysis/scripts/collapse_and_floor.py
#   9. compare quoted numbers with the inputs      analysis/scripts/check_manuscript_numbers.py
#  10. claim-boundary check and positive control   analysis/scripts/check_claim_boundary.py
#  11. reach of the rules and of the seal         analysis/scripts/check_seal_scope.py
#  12. the seal, and that the rule text is generated  analysis/scripts/verify_seal.py
#  13. the reported branch, once the arms have run   analysis/scripts/apply_decision_rules.py
#
# Step 12 was deliberately absent until seal/protocol.md existed. Wiring it earlier would have
# meant shipping a placeholder inside the thing whose whole purpose is to be fixed.
#
# Step 13 is wired now and does nothing yet, which is the opposite decision, for a reason worth
# stating. It is the third of the three checks the manuscript says hold the rules in place, and
# this file is sealed. Adding the step after the arms had run would change these bytes, fail step
# 12, and force the seal to be rebuilt -- leaving a record of the seal being remade with the
# results in hand, which is precisely the story the seal exists to rule out. So the wiring goes in
# while nothing is known, and the step activates itself when the inputs appear.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

# --- Fix the seed ---
# This is the repository-wide convention value. The measurement seed is 20260708, frozen in
# manuscript/main.md section 6.3; determinism of the generated artefacts comes from that one.
SEED_VALUE="$(cat SEED)"
export PYTHONHASHSEED="$SEED_VALUE"
export ERRE_SEED="$SEED_VALUE"
echo "[repro] SEED=$SEED_VALUE (repository-wide seed)"

# Keep diagnostics readable on a Windows console.
export PYTHONUTF8=1

# Import the vendored apparatus. That these modules resolve to paths inside this repository is the
# condition for it being self-contained; see "Provenance of the apparatus" in data/data.md.
export PYTHONPATH="$REPO_ROOT/analysis/apparatus"

# --- 1. Pin the environment from the lockfile ---
# `--no-install-project` is required. env/pyproject.toml is the upstream project definition, kept
# verbatim beside env/uv.lock so the lockfile the measurement ran under is preserved unmodified. It
# declares a source root this repository does not have. The analysis scripts read the apparatus
# through PYTHONPATH, so the project itself never needs installing.
echo "[repro] 1/13 uv sync"
uv sync --frozen --no-install-project --project env

RUN=(uv run --project env --no-sync)

# --- 2. Lint ---
echo "[repro] 2/13 ruff check"
"${RUN[@]}" ruff check analysis/scripts

# --- 3. Integrity of the frozen inputs ---
echo "[repro] 3/13 verify_data_hashes"
if [ -n "${ERRE_SANDBOX_REPO:-}" ]; then
  "${RUN[@]}" python analysis/scripts/verify_data_hashes.py \
    --upstream-repo "$ERRE_SANDBOX_REPO"
else
  "${RUN[@]}" python analysis/scripts/verify_data_hashes.py
fi

# --- 4. The threshold freeze ---
echo "[repro] 4/13 verify_threshold_freeze"
if [ -n "${ERRE_SANDBOX_REPO:-}" ]; then
  "${RUN[@]}" python analysis/scripts/verify_threshold_freeze.py \
    --upstream-repo "$ERRE_SANDBOX_REPO"
else
  "${RUN[@]}" python analysis/scripts/verify_threshold_freeze.py
fi

# --- 5. Recompute the recorded verdict from the shipped data ---
# The strongest check here. Every other step compares a record against a shipped file; this one
# establishes that the central verdict follows from the shipped data and the shipped apparatus.
echo "[repro] 5/13 recompute_verdict"
"${RUN[@]}" python analysis/scripts/recompute_verdict.py

# --- 6. Extract the quantities the paper quotes ---
echo "[repro] 6/13 extract_verdict_table -> data/derived/verdict-table.md"
"${RUN[@]}" python analysis/scripts/extract_verdict_table.py \
  --out data/derived/verdict-table.md > /dev/null

# --- 7. Regenerate the power table ---
echo "[repro] 7/13 power_curve -> data/derived/power-curve.md"
"${RUN[@]}" python analysis/scripts/power_curve.py \
  --out data/derived/power-curve.md > /dev/null

# --- 8. Support of the decision space, and the null floor of the estimand ---
# Two properties the reframed claim rests on. Derived here rather than quoted, for the same
# reason the verdict is recomputed rather than copied.
echo "[repro] 8/13 collapse_and_floor -> data/derived/collapse-and-floor.md"
"${RUN[@]}" python analysis/scripts/collapse_and_floor.py --out data/derived/collapse-and-floor.md --json-out data/derived/collapse-and-floor.json > /dev/null

# --- 9. Compare the quoted numbers with the frozen inputs ---
# "Not transcribed by hand" is a policy, not a check. This is the check.
echo "[repro] 9/13 check_manuscript_numbers"
"${RUN[@]}" python analysis/scripts/check_manuscript_numbers.py

# --- 10. Claim boundary ---
echo "[repro] 10/13 check_claim_boundary"
"${RUN[@]}" python analysis/scripts/check_claim_boundary.py

# --- 11. Reach of the sealed decision rules ---
# The rules file decides which claim the run licenses. Running it once shows it produces an
# answer; this shows that a moved threshold, a reordered evaluation, or a malformed input
# produces a different one -- and that a no-op change does not.
echo "[repro] 11/13 check_seal_scope"
"${RUN[@]}" python analysis/scripts/check_seal_scope.py

# --- 12. The seal ---
# The bytes of the sealed files against the manifest, the manifest's own self-hash, and -- the
# half that is easy to miss -- that the decision rules a reader reads in the protocol and in the
# manuscript are *generated* from the sealed file rather than written out a second time beside it.
# Two statements of the same rules drift; one statement and a renderer cannot.
echo "[repro] 12/13 verify_seal"
"${RUN[@]}" python analysis/scripts/verify_seal.py

# --- 13. The reported branch, once there is one ---
# The manuscript names three checks that hold the decision rules in place: the sealed bytes, the
# generated rule text, and this -- the evaluator applied to the recorded quantities. The first two
# run above. This one has nothing to read until the prospective arms exist, so it is guarded on
# its inputs rather than omitted.
#
# The guard is on file existence, not on a date or a flag. That matters: a conditional does not
# freeze "this has not happened yet" into a sealed file, and so does not become false later. When
# the two verdicts appear the step starts running, without this file changing.
CONTROL_VERDICT="data/raw/control-verdict.json"
PRIMARY_VERDICT="data/raw/primary-verdict.json"
REPORTED_BRANCH="manuscript/reported-branch.txt"

if [ -f "$CONTROL_VERDICT" ] && [ -f "$PRIMARY_VERDICT" ]; then
  echo "[repro] 13/13 apply_decision_rules -> data/derived/decision-report.json"
  EXPECT=()
  if [ -f "$REPORTED_BRANCH" ]; then
    EXPECT=(--expect-branch "$(tr -d '[:space:]' < "$REPORTED_BRANCH")")
  fi
  "${RUN[@]}" python analysis/scripts/apply_decision_rules.py \
    --control "$CONTROL_VERDICT" \
    --primary "$PRIMARY_VERDICT" \
    --out data/derived/decision-report.json \
    "${EXPECT[@]}"
else
  echo "[repro] 13/13 apply_decision_rules: SKIPPED -- no prospective verdict yet"
  echo "[repro]       (expects $CONTROL_VERDICT and $PRIMARY_VERDICT; the branch this repository"
  echo "[repro]        reports is re-derived here the moment they exist)"
fi

echo "[repro] DONE: all thirteen steps passed"
