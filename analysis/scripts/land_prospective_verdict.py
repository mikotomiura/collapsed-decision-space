#!/usr/bin/env python3
"""Move a prospective arm's verdict from the driver's artefact directory into ``data/raw/``.

The driver writes ``run-verdict.json``. Step 13 of ``repro.sh`` reads
``data/raw/<arm>-verdict.json``. ``repro.sh`` is sealed, so the two names cannot be made to
agree, and the gap has to be crossed by a copy.

**Crossing it by hand is the problem this script exists to remove.** Renaming a file into the
position a checker reads is exactly how the wrong file ends up under the right name, and the
failure is silent: every downstream check would then run happily against whatever was copied.
There are five specific ways to get it wrong, and each is refused here.

1. **The quarantined verdict.** When the sealed seal check does not pass, the driver renames its
   output to ``run-verdict.DEVIATION.json`` rather than leaving a failed result under a green
   name. A directory holding only that file has produced no landable verdict, and the message
   says so instead of reporting a missing file.
2. **A copy of a frozen input.** ``data/raw/cproper-verdict.json`` satisfies the control gate and
   stops at R1. Copied into both arms it yields a complete decision report and a green run out of
   a file that predates the prospective design entirely.
3. **A silent overwrite.** Landing the second arm over the first, or a re-run over the run that
   was analysed, loses the thing being replaced without a trace. ``--force`` is required, and
   what is being replaced is printed.
4. **The wrong arm.** ``--arm control --from <primary artefact dir>`` would land the primary
   arm's verdict under the control arm's name, and every check downstream would then be reading
   the wrong model's result under the right label. An independent review found this open, and it
   is why the seal check below is run here and not merely assumed to have been run earlier.
5. **A bundle that was never verified.** A directory containing any well-formed JSON and an empty
   manifest satisfied every other condition in this list.

Points 4 and 5 are closed the same way: this script runs the **sealed** ``verify_seal.py`` with
``--run-manifest``, ``--run-verdict`` and ``--arm``, and refuses unless it exits 0. That is the
checker the driver itself calls; it compares the manifest's model, digest, context bank and
thresholds against the arm's sealed specification, so a primary bundle presented as the control
arm fails on the model it names.

**"Could not run" is not folded into "passed."** If the sealed checker is missing or cannot be
started, the landing is refused rather than allowed with a warning: a check that silently
disappears when its target is absent is the failure mode this repository keeps finding.

The bytes are copied **verbatim**, through a temporary file that is renamed into place, and the
digest is recomputed after the copy. The driver writes its artefacts through a canonicalising
serialiser with quantised floats so that the two legs of the CI agree byte for byte; re-encoding
them here would put a second serialiser in the path for no gain.

**This does not make landing a substitute for verifying.** The driver's ``--verify`` must have
exited **0** -- ``2`` means a bundle that is internally consistent but smaller than the seal
describes -- and it checks things this script does not, including that the verdict is the one its
own scorer produces from the recorded annotation.

Usage:
    python analysis/scripts/land_prospective_verdict.py --arm control --from <artefact dir>
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess  # noqa: S404
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _provenance import sha256_of  # noqa: E402
from verify_data_hashes import PROSPECTIVE_OUTPUTS, parse_raw_table  # noqa: E402

#: The driver's own names, in its artefact directory.
DRIVER_VERDICT = "run-verdict.json"
DRIVER_QUARANTINED = "run-verdict.DEVIATION.json"
DRIVER_MANIFEST = "run-manifest.json"

#: Outcomes of the sealed seal check. Three values, not two: "could not be run" is its own
#: answer and must not be read as a pass.
SEAL_OK = "ok"
SEAL_FAILED = "failed"
SEAL_NOT_RUN = "not-run"


def run_sealed_seal_check(
    *, repo_root: Path, manifest: Path, verdict: Path, arm: str
) -> tuple[str, str]:
    """Run the sealed ``verify_seal.py`` over the bundle, and return its outcome and output.

    The canonical checker is invoked rather than reimplemented. Duplicating what it compares
    would put a second statement of the seal's reach beside the sealed one, which is the drift
    this repository designs against everywhere else.
    """
    script = repo_root / "analysis" / "scripts" / "verify_seal.py"
    if not script.is_file():
        return SEAL_NOT_RUN, f"the sealed checker is missing: {script}"
    command = [
        sys.executable,
        str(script),
        "--run-manifest",
        str(manifest),
        "--arm",
        arm,
        "--run-verdict",
        str(verdict),
    ]
    try:
        completed = subprocess.run(  # noqa: S603
            command, cwd=repo_root, capture_output=True, text=True, check=False
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return SEAL_NOT_RUN, f"the sealed checker could not be started: {exc}"
    output = (completed.stdout + completed.stderr).strip()
    return (SEAL_OK if completed.returncode == 0 else SEAL_FAILED), output


def destination_for(arm: str) -> str:
    """The name step 13 reads for ``arm``.

    Derived from the arm rather than listed, then checked against
    :data:`~verify_data_hashes.PROSPECTIVE_OUTPUTS`, so that a typo cannot quietly create a third
    landing site that the frozen-input checks would then reject.
    """
    return f"{arm}-verdict.json"


def _die(message: str) -> int:
    print(f"[land] FAIL: {message}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="repository root",
    )
    parser.add_argument(
        "--arm",
        required=True,
        choices=sorted(name.removesuffix("-verdict.json") for name in PROSPECTIVE_OUTPUTS),
        help="which arm's verdict is being landed",
    )
    parser.add_argument(
        "--from",
        dest="source_dir",
        required=True,
        type=Path,
        help="the driver's artefact directory for that arm",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace an already landed verdict (what is replaced is reported)",
    )
    args = parser.parse_args(argv)

    repo_root: Path = args.repo_root
    source_dir: Path = args.source_dir
    target_name = destination_for(args.arm)
    if target_name not in PROSPECTIVE_OUTPUTS:
        return _die(
            f"{target_name!r} is not one of the landing sites the checks recognise "
            f"({sorted(PROSPECTIVE_OUTPUTS)})"
        )

    source = source_dir / DRIVER_VERDICT
    if not source.is_file():
        if (source_dir / DRIVER_QUARANTINED).is_file():
            return _die(
                f"{source_dir} holds {DRIVER_QUARANTINED} and no {DRIVER_VERDICT}. The driver "
                "quarantines a verdict under that name when the sealed seal check does not "
                "pass, so this run produced no landable result. Fix the deviation and re-run; "
                "do not rename the file"
            )
        return _die(f"{source} does not exist")

    if not (source_dir / DRIVER_MANIFEST).is_file():
        return _die(
            f"{source_dir} holds {DRIVER_VERDICT} but no {DRIVER_MANIFEST}. The manifest is what "
            "the sealed verify_seal.py --run-manifest compares against the seal; a verdict "
            "separated from it cannot be checked against anything"
        )

    try:
        parsed = json.loads(source.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return _die(f"{source} is not readable as JSON ({exc})")
    if not isinstance(parsed, dict):
        return _die(
            f"{source} parses as {type(parsed).__name__}, not a JSON object. The sealed "
            "evaluator reads quantities by key"
        )

    digest = sha256_of(source)
    frozen = parse_raw_table(repo_root / "data" / "data.md")
    for entry in frozen:
        if entry.sha256 == digest:
            return _die(
                f"{source} is byte-for-byte identical to the frozen input {entry.name}. A "
                "prospective arm cannot have produced a file that existed before the seal"
            )

    # The arm the bundle says it is, before asking the seal which arm it looks like. The sealed
    # checker compares the model and digest; this compares the label the driver wrote, so a
    # mismatch is reported as a mix-up rather than as a model that fails its specification.
    manifest_path = source_dir / DRIVER_MANIFEST
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return _die(f"{manifest_path} is not readable as JSON ({exc})")
    recorded_arm = manifest.get("arm") if isinstance(manifest, dict) else None
    if recorded_arm != args.arm:
        return _die(
            f"{manifest_path} records arm {recorded_arm!r} but {args.arm!r} was asked for. "
            "Landing a bundle under the other arm's name is how the wrong model's result ends "
            "up under the right label"
        )

    outcome, output = run_sealed_seal_check(
        repo_root=repo_root,
        manifest=manifest_path,
        verdict=source,
        arm=args.arm,
    )
    for line in output.splitlines():
        if line.strip():
            print(f"[land][seal] {line}")
    if outcome != SEAL_OK:
        reason = (
            "the sealed seal check could not be run"
            if outcome == SEAL_NOT_RUN
            else "the sealed seal check did not pass"
        )
        return _die(
            f"{reason}. A bundle is landed only once verify_seal.py has compared its manifest "
            f"with the {args.arm} arm's sealed specification; not having run the check is not "
            "the same as having passed it"
        )

    target = repo_root / "data" / "raw" / target_name
    if target.is_file() and not args.force:
        return _die(
            f"data/raw/{target_name} already exists ({sha256_of(target)[:12]}…). Landing over "
            "it would replace an analysed result without a trace; pass --force to mean it"
        )
    if target.is_file():
        print(f"[land] replacing data/raw/{target_name} ({sha256_of(target)[:12]}…)")

    # Copy aside and rename into place, so an interrupted copy cannot leave a truncated verdict
    # under the name step 13 reads -- and, with --force, cannot destroy the landed result it was
    # replacing. Then re-read what actually landed: the digest printed below is of the bytes on
    # disk, not of the bytes that were read a moment earlier.
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.with_name(target.name + ".landing")
    shutil.copyfile(source, staging)
    staging.replace(target)
    landed_digest = sha256_of(target)
    if landed_digest != digest:
        return _die(
            f"data/raw/{target_name} hashes to {landed_digest} but the source hashed to "
            f"{digest} when it was read. The source changed underneath the copy"
        )
    print(f"[land] {source} -> data/raw/{target_name}  ({digest[:12]}… / {target.stat().st_size:,} bytes)")

    remaining = sorted(
        name
        for name in PROSPECTIVE_OUTPUTS
        if not (repo_root / "data" / "raw" / name).is_file()
    )
    if remaining:
        print(f"[land] still to land: {remaining}. Step 13 stays guarded until both are here")
    else:
        print(
            "[land] both arms have landed. Next: derive the branch by hand from the two "
            "verdicts and the sealed rules, record the derivation in "
            "manuscript/REPORTED-BRANCH.md, write the marker into the results section of "
            "manuscript/main.md, then run render_reported_branch.py and bash repro.sh"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
