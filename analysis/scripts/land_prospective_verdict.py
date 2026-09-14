#!/usr/bin/env python3
"""Move a prospective arm's verdict from the driver's artefact directory into ``data/raw/``.

The driver writes ``run-verdict.json``. Step 13 of ``repro.sh`` reads
``data/raw/<arm>-verdict.json``. ``repro.sh`` is sealed, so the two names cannot be made to
agree, and the gap has to be crossed by a copy.

**Crossing it by hand is the problem this script exists to remove.** Renaming a file into the
position a checker reads is exactly how the wrong file ends up under the right name, and the
failure is silent: every downstream check would then run happily against whatever was copied.
There are three specific ways to get it wrong, and each is refused here.

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

The bytes are copied **verbatim**. The driver writes its artefacts through a canonicalising
serialiser with quantised floats so that the two legs of the CI agree byte for byte; re-encoding
them here would put a second serialiser in the path for no gain.

**This is not a verification step, and it does not stand in for one.** Whether the run was of the
sealed size, under the sealed model digests and the sealed context bank, is established by the
driver's ``--verify`` -- which must have exited **0**; ``2`` means a bundle that is internally
consistent but smaller than the seal describes -- and by the sealed ``verify_seal.py
--run-manifest`` that it calls. This script checks that the file being landed is a plausible,
distinct, well-formed verdict and that it lands where step 13 will look.

Usage:
    python analysis/scripts/land_prospective_verdict.py --arm control --from <artefact dir>
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _provenance import sha256_of  # noqa: E402
from verify_data_hashes import PROSPECTIVE_OUTPUTS, parse_raw_table  # noqa: E402

#: The driver's own names, in its artefact directory.
DRIVER_VERDICT = "run-verdict.json"
DRIVER_QUARANTINED = "run-verdict.DEVIATION.json"
DRIVER_MANIFEST = "run-manifest.json"


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

    target = repo_root / "data" / "raw" / target_name
    if target.is_file() and not args.force:
        return _die(
            f"data/raw/{target_name} already exists ({sha256_of(target)[:12]}…). Landing over "
            "it would replace an analysed result without a trace; pass --force to mean it"
        )
    if target.is_file():
        print(f"[land] replacing data/raw/{target_name} ({sha256_of(target)[:12]}…)")

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
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
