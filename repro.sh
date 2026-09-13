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
#  14. the deposit's own checksums, once there is one  analysis/scripts/verify_seal.py --witness
#
# Step 12 was deliberately absent until seal/protocol.md existed. Wiring it earlier would have
# meant shipping a placeholder inside the thing whose whole purpose is to be fixed.
#
# Steps 13 and 14 were wired while neither of their inputs existed, which is the opposite
# decision, for a reason worth stating. This file is sealed. Adding either step later would change
# these bytes, fail step 12, and force the seal to be rebuilt -- leaving a record of the seal being
# remade after the fact, which is precisely the story the seal exists to rule out. Step 13 would
# have been added with the results in hand; step 14 with the deposit already made, so that the
# deposited copy of this file would be the copy without the check. So both went in beforehand, and
# each activates itself when its own input appears. Whether either has anything to read is
# reported by the step, on every run; nothing here asserts it either way.
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
echo "[repro] 1/14 uv sync"
uv sync --frozen --no-install-project --project env

RUN=(uv run --project env --no-sync)

# --- 2. Lint ---
echo "[repro] 2/14 ruff check"
"${RUN[@]}" ruff check analysis/scripts

# --- 3. Integrity of the frozen inputs ---
echo "[repro] 3/14 verify_data_hashes"
if [ -n "${ERRE_SANDBOX_REPO:-}" ]; then
  "${RUN[@]}" python analysis/scripts/verify_data_hashes.py \
    --upstream-repo "$ERRE_SANDBOX_REPO"
else
  "${RUN[@]}" python analysis/scripts/verify_data_hashes.py
fi

# --- 4. The threshold freeze ---
echo "[repro] 4/14 verify_threshold_freeze"
if [ -n "${ERRE_SANDBOX_REPO:-}" ]; then
  "${RUN[@]}" python analysis/scripts/verify_threshold_freeze.py \
    --upstream-repo "$ERRE_SANDBOX_REPO"
else
  "${RUN[@]}" python analysis/scripts/verify_threshold_freeze.py
fi

# --- 5. Recompute the recorded verdict from the shipped data ---
# The strongest check here. Every other step compares a record against a shipped file; this one
# establishes that the central verdict follows from the shipped data and the shipped apparatus.
echo "[repro] 5/14 recompute_verdict"
"${RUN[@]}" python analysis/scripts/recompute_verdict.py

# --- 6. Extract the quantities the paper quotes ---
echo "[repro] 6/14 extract_verdict_table -> data/derived/verdict-table.md"
"${RUN[@]}" python analysis/scripts/extract_verdict_table.py \
  --out data/derived/verdict-table.md > /dev/null

# --- 7. Regenerate the power table ---
echo "[repro] 7/14 power_curve -> data/derived/power-curve.md"
"${RUN[@]}" python analysis/scripts/power_curve.py \
  --out data/derived/power-curve.md > /dev/null

# --- 8. Support of the decision space, and the null floor of the estimand ---
# Two properties the reframed claim rests on. Derived here rather than quoted, for the same
# reason the verdict is recomputed rather than copied.
echo "[repro] 8/14 collapse_and_floor -> data/derived/collapse-and-floor.md"
"${RUN[@]}" python analysis/scripts/collapse_and_floor.py --out data/derived/collapse-and-floor.md --json-out data/derived/collapse-and-floor.json > /dev/null

# --- 9. Compare the quoted numbers with the frozen inputs ---
# "Not transcribed by hand" is a policy, not a check. This is the check.
echo "[repro] 9/14 check_manuscript_numbers"
"${RUN[@]}" python analysis/scripts/check_manuscript_numbers.py

# --- 10. Claim boundary ---
echo "[repro] 10/14 check_claim_boundary"
"${RUN[@]}" python analysis/scripts/check_claim_boundary.py

# --- 11. Reach of the sealed decision rules ---
# The rules file decides which claim the run licenses. Running it once shows it produces an
# answer; this shows that a moved threshold, a reordered evaluation, or a malformed input
# produces a different one -- and that a no-op change does not.
echo "[repro] 11/14 check_seal_scope"
"${RUN[@]}" python analysis/scripts/check_seal_scope.py

# --- 12. The seal ---
# The bytes of the sealed files against the manifest, the manifest's own self-hash, and -- the
# half that is easy to miss -- that the decision rules a reader reads in the protocol and in the
# manuscript are *generated* from the sealed file rather than written out a second time beside it.
# Two statements of the same rules drift; one statement and a renderer cannot.
echo "[repro] 12/14 verify_seal"
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
  echo "[repro] 13/14 apply_decision_rules -> data/derived/decision-report.json"
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
  echo "[repro] 13/14 apply_decision_rules: SKIPPED -- no prospective verdict present"
  echo "[repro]       (expects $CONTROL_VERDICT and $PRIMARY_VERDICT; the branch this repository"
  echo "[repro]        reports is re-derived here the moment they exist)"
  SKIP_13=1
fi

# --- 14. The deposit's own checksums, as recorded ---
# Steps 3 to 13 compare records inside this repository against one another, and an author with
# write access can change both sides of any one of them in a single commit. This step reaches for
# a copy held by somebody else -- an archive publishes a checksum for every file it holds,
# readable without an account -- but it reaches for it through a *recorded* answer, and it is
# worth being exact about what that buys.
#
# This step is offline. It establishes that the recorded witness and these bytes agree, and that
# the witness is closed against itself: its anchor is the maximum of the server times it carries,
# and those times are exactly the ones its own deposit listing implies, one created and one
# updated per deposited file. It does **not** establish that the witness is what the archive
# returned. An independent review made that concrete by writing a witness out of nothing --
# locally computed digests, invented timestamps -- and watching an earlier version of this check
# report no problems.
#
# Turning a recorded external half into a checked one is an online act, and it is the reader's to
# perform: the witness records the public URL it was read from, and re-running
# analysis/scripts/collect_zenodo_witness.py against that URL reproduces the file. That is
# deliberately not a step here. This script has to run with no network and inside a de-identified
# copy, where the URL is redacted; a step that needed either would make the reproduction depend on
# the thing the de-identification removes.
#
# Guarded on the witness file, for the same reason step 13 is guarded on the verdicts: a condition
# does not freeze "this has not happened yet" into a sealed file.
WITNESS="seal/zenodo-witness.json"
SKIPPED=""

if [ -f "$WITNESS" ]; then
  echo "[repro] 14/14 verify_seal --witness $WITNESS"
  "${RUN[@]}" python analysis/scripts/verify_seal.py --witness "$WITNESS"
else
  echo "[repro] 14/14 verify_seal --witness: SKIPPED -- no deposit witness present"
  echo "[repro]       (expects $WITNESS. Every check above is internal to this repository;"
  echo "[repro]        until this file exists, take the external half as absent, not as passed)"
  SKIP_14=1
fi

# --- What the last line is allowed to say ---
# "All fourteen steps passed" was printed here unconditionally, including on runs where steps 13
# and 14 had skipped. An independent review caught it. The line is the one a reader quotes, and a
# summary that overstates a guarded run is worse than no summary: it turns two honest skips into a
# claim that two checks were made. So the summary reports which steps actually ran.
# Written as `if` blocks rather than `test && assign`: under `set -e` a short-circuiting `&&`
# list is a documented ambiguity, and this script must not exit 0 early or non-zero late because
# of one.
if [ -n "${SKIP_13:-}" ]; then
  SKIPPED="$SKIPPED 13"
fi
if [ -n "${SKIP_14:-}" ]; then
  SKIPPED="$SKIPPED 14"
fi

if [ -z "$SKIPPED" ]; then
  echo "[repro] DONE: all fourteen steps ran and passed"
else
  echo "[repro] DONE: every step that ran passed. Skipped, as reported above:$SKIPPED"
  echo "[repro]       (a skipped step is a check that was not made, not a check that succeeded)"
fi
