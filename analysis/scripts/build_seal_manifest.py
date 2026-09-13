#!/usr/bin/env python3
"""Write ``seal/SEAL-MANIFEST.json`` from the current contents of the sealed files.

Kept separate from ``verify_seal.py`` on purpose. A single script with a write mode and a compare
mode is one wrong flag away from writing when it was meant to be checking, and a check that quietly
becomes a write reports success for a file it never examined. Here the checker cannot write and the
writer cannot check.

This script is **not** part of ``repro.sh``. It is run once, by the author, when the seal is
prepared; after that the manifest is a fixed input and any need to re-run this is a signal that
something sealed has changed.

The set of sealed paths is imported from the checker rather than declared here, so the two cannot
drift apart.

Usage:  python analysis/scripts/build_seal_manifest.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _provenance import sha256_of  # noqa: E402
from verify_seal import (  # noqa: E402
    CANONICALISATION,
    MANIFEST_SCHEMA,
    SEALED_PATHS,
    canonical_self_hash,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    repo_root = Path(__file__).resolve().parents[2]
    parser.add_argument("--repo-root", type=Path, default=repo_root)
    args = parser.parse_args()
    root: Path = args.repo_root

    missing = [rel for rel in SEALED_PATHS if not (root / rel).is_file()]
    if missing:
        print(f"[seal-build] FAIL: sealed files are missing: {missing}", file=sys.stderr)
        return 1

    files: dict[str, Any] = {}
    for rel in sorted(SEALED_PATHS):
        target = root / rel
        files[rel] = {"sha256": sha256_of(target), "size": target.stat().st_size}

    manifest: dict[str, Any] = {
        "schema": MANIFEST_SCHEMA,
        "purpose": (
            "Fixes the bytes of the decision rules, the arm specification, the protocol, and "
            "the code that applies them, so that the branch reported after the run can be "
            "re-derived from the rules as they stood before it."
        ),
        "scope_note": (
            "This document establishes internal consistency only. It cannot show that the "
            "files are old, nor that a sealed file and this manifest were not edited "
            "together. The external half is the deposit, which publishes a per-file "
            "checksum that anyone can read without an account."
        ),
        "self_hash_canonicalisation": CANONICALISATION,
        "files": files,
    }
    manifest["self_sha256"] = canonical_self_hash(manifest)

    out = root / "seal" / "SEAL-MANIFEST.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"[seal-build] wrote {out} ({len(files)} files)")
    print(f"[seal-build] self_sha256 = {manifest['self_sha256']}")
    print("[seal-build] now run verify_seal.py; it is the only thing that checks this")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
