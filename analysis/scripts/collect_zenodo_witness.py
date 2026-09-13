#!/usr/bin/env python3
"""Record what a public archive says about the deposited copies of the sealed files.

This is the **outside half** of the binding, and it is the only script here that touches the
network. It reads a deposit record through the archive's public read API -- no account, no token,
no authenticated endpoint -- and writes down two things a reader cannot get from this repository
alone: the per-file checksums the archive holds, and the times the archive's own server assigned
to the record and to its files. ``verify_seal.py --witness`` then compares those checksums against
the local sealed files, offline, and ``repro.sh`` runs that comparison whenever the witness file
exists. Because that comparison is offline, it checks the recorded answer against these bytes and
not the archive against anything; re-running this script is what checks the record itself.

**Why the mapping is done by content and not by name.** A deposit's file names are flat and are
chosen by whoever uploaded them, so a witness that paired "this deposited file is that sealed
path" by hand would put the author back in the middle of the one link that is supposed to come
from outside. Instead each sealed file is hashed locally and matched against the checksums the
archive publishes. A wrong pairing cannot survive: the checksum has to equal the digest of the
local bytes, so the correspondence is established by the content rather than asserted about it.
If any sealed file has no counterpart in the deposit, nothing is written at all -- a partial
witness that reads as a complete one is worse than none, and ``verify_seal.py`` would in any case
refuse it.

**What running this establishes, and what merely reading its output does not.** Running it reads
a public record and writes down what that record said. A reader who runs it again against the URL
in the output, and gets the same file, has checked the outside half. A reader who only reads the
output has a document written by the author, and ``verify_seal.py --witness`` -- which is offline
-- can go no further than the internal consistency of that document. The distinction is not a
quibble: an independent review produced a witness out of thin air, with locally computed digests
and invented timestamps, and watched it pass. The repair has two parts, and both are needed. The
checker closes the document against itself. The manuscript says plainly that a recorded external
half is not a checked one until somebody re-reads the record.

What even a re-read establishes is bounded. The digests are the archive's **MD5**, so agreement is
agreement on that digest rather than a proof of identical bytes. And a deposit record remains
editable by its owner for a period after publication with the identifier unchanged, so these times
bound when the deposit was last touched -- not when the protocol was written, and certainly not
that no run preceded it. The manuscript states both rather than leaving a reader to find them.

**The anchor is a maximum, not a pick.** ``latest_server_time`` is the latest of every
server-assigned time this witness carries: the record's creation and modification times, the
creation and modification times of every file in it, and -- when the registry is consulted -- the
DOI registration time. Taking the maximum is the conservative direction: it is the time after
which nothing in the deposit changed, so a claim made against it cannot be strengthened by
choosing a different field. The depositor-supplied publication date is recorded separately, under
a key the checker refuses to read as part of the anchor, because the depositor chooses it.

**No identifier is baked into this file.** The record to read is a required argument. That is not
a convenience: this file is sealed, which means it ships unchanged to an anonymous review and is
itself deposited, so a record URL written into it would name the depositor in a file that cannot
be redacted without breaking every hash that makes it evidence.

Usage:
    python analysis/scripts/collect_zenodo_witness.py \\
        --record-api-url https://<host>/api/records/<id> \\
        --datacite-api-base https://<registry-host>/dois

    python analysis/scripts/collect_zenodo_witness.py \\
        --record-api-url https://<host>/api/records/<id> \\
        --datacite-absent-reason "the DOI had not been registered when this was collected"

Exactly one of ``--datacite-api-base`` and ``--datacite-absent-reason`` is required. A registry
time that is simply left out would narrow the anchor silently; naming the reason it is missing
keeps the omission visible, and ``verify_seal.py`` requires one or the other to be present.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime
from collections.abc import Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

#: The schema label and the digest algorithm are imported from the checker rather than declared
#: here. They are the contract, and the checker is what enforces it; keeping one copy means this
#: script cannot drift into writing a document the run will refuse.
from verify_seal import DEPOSIT_ALGORITHM, SEALED_PATHS, WITNESS_SCHEMA  # noqa: E402

USER_AGENT: str = "collapsed-decision-space-witness/1 (+repro.sh)"

#: How a JSON endpoint is read. Injectable for one reason only: the mutation suite drives this
#: script end to end against a synthetic archive response and then hands the result to the sealed
#: checker. Without that round-trip, a tightening of the checker could leave this script writing
#: a document the run refuses -- and the place that would surface is after the deposit, where
#: nothing can be changed. The default is the real reader; nothing in production passes anything
#: else.
Fetcher = Callable[[str, float], dict[str, Any]]


def _die(message: str) -> None:
    print(f"[witness] FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def fetch_json(url: str, timeout: float) -> dict[str, Any]:
    """Read one public JSON endpoint over HTTPS, with no credentials of any kind."""
    if not url.startswith("https://"):
        _die(f"refusing to fetch {url!r}: only https is read here")
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            payload = response.read()
    except urllib.error.HTTPError as exc:
        _die(
            f"{url} returned HTTP {exc.code}. The read API is public, so a 401 or 403 means "
            "the URL is wrong rather than that a credential is missing"
        )
    except urllib.error.URLError as exc:
        _die(f"{url} could not be reached: {exc.reason}")
    try:
        parsed: dict[str, Any] = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _die(f"{url} did not return JSON: {exc}")
    return parsed


def digest_of(path: Path) -> str:
    """The deposit's digest algorithm, applied to a local file."""
    digest = hashlib.new(DEPOSIT_ALGORITHM, usedforsecurity=False)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def deposit_files(
    record_api_url: str, timeout: float, fetch: Fetcher = fetch_json
) -> list[dict[str, Any]]:
    """Return one entry per file the record holds, as the archive reports them.

    Only the fields the witness needs are kept, and they are kept verbatim: the checksum the
    archive publishes, its own size, and the two times it assigned. Nothing is recomputed, because
    the point of these values is that they come from somewhere else.
    """
    payload = fetch(f"{record_api_url.rstrip('/')}/files", timeout)
    entries = payload.get("entries")
    if not isinstance(entries, list) or not entries:
        _die("the files endpoint returned no entries, so the record holds nothing to witness")
    collected: list[dict[str, Any]] = []
    for entry in entries:
        checksum = str(entry.get("checksum", ""))
        algorithm, _, digest = checksum.partition(":")
        if algorithm != DEPOSIT_ALGORITHM or not digest:
            _die(
                f"the record publishes {checksum!r} for {entry.get('key')!r}; this script "
                f"records {DEPOSIT_ALGORITHM} digests and will not guess at another format"
            )
        collected.append(
            {
                "key": entry.get("key"),
                "checksum": checksum,
                "size": entry.get("size"),
                "created": entry.get("created"),
                "updated": entry.get("updated"),
            }
        )
    return collected


def match_by_content(
    root: Path, deposited: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Pair every sealed file with a deposited file that has the same digest.

    Returns the witness entries and the sealed paths that had no counterpart. The pairing is
    one-directional on purpose: extra files in the deposit are not an error -- a deposit may hold
    a manuscript or a bundle as well -- but a sealed file with nothing to match it is, because the
    witness would then be silent about part of the seal while looking complete.
    """
    by_digest: dict[str, dict[str, Any]] = {}
    for entry in deposited:
        digest = str(entry["checksum"]).partition(":")[2]
        by_digest.setdefault(digest, entry)

    entries: list[dict[str, Any]] = []
    unmatched: list[str] = []
    for rel in sorted(SEALED_PATHS):
        local = root / rel
        if not local.is_file():
            _die(f"{rel} is sealed but not present locally, so there is nothing to compare")
        digest = digest_of(local)
        deposit_entry = by_digest.get(digest)
        if deposit_entry is None:
            unmatched.append(rel)
            continue
        # The digest already agreed, so a size that does not is either an archive reporting
        # something inconsistent about its own file or a bug here. Either way it is not a witness
        # worth writing, and the checker compares these two as well.
        local_size = local.stat().st_size
        if deposit_entry["size"] != local_size:
            _die(
                f"the record reports {deposit_entry['size']!r} bytes for "
                f"{deposit_entry['key']!r} but {rel} is {local_size} bytes, although the "
                f"{DEPOSIT_ALGORITHM} digests agree"
            )
        entries.append(
            {
                "sealed_path": rel,
                "checksum": f"{DEPOSIT_ALGORITHM}:{digest}",
                "deposit_key": deposit_entry["key"],
                "size": deposit_entry["size"],
            }
        )
    return entries, unmatched


def time_sources(record: dict[str, Any], deposited: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Every server-assigned time the record and its files carry, as named entries."""
    sources: list[dict[str, str]] = []
    for field in ("created", "updated"):
        value = record.get(field)
        if not isinstance(value, str) or not value:
            _die(
                f"the record has no {field!r} time; the anchor is a maximum over those times"
            )
        sources.append({"source": f"record.{field}", "value": value})
    for entry in deposited:
        for field in ("created", "updated"):
            value = entry.get(field)
            if not isinstance(value, str) or not value:
                _die(f"the deposited file {entry.get('key')!r} has no {field!r} time")
            sources.append({"source": f"files.{entry['key']}.{field}", "value": value})
    return sources


def registry_time(base: str, doi: str, timeout: float, fetch: Fetcher = fetch_json) -> str:
    """The registration time the DOI registry reports, read from its public API."""
    payload = fetch(f"{base.rstrip('/')}/{doi}", timeout)
    registered = payload.get("data", {}).get("attributes", {}).get("registered")
    if not isinstance(registered, str) or not registered:
        _die(f"the registry returned no 'registered' time for {doi}")
    return registered


def latest(sources: list[dict[str, str]]) -> str:
    """The latest value among the sources, returned verbatim rather than reformatted.

    Returning the winning string unchanged is what lets the checker recompute this maximum and
    compare it for equality. A normalised form would make the comparison depend on this script's
    formatting choices, which are not sealed against the file that records them.
    """
    parsed: list[tuple[datetime, str]] = []
    for entry in sources:
        try:
            moment = datetime.fromisoformat(entry["value"])
        except ValueError:
            _die(
                f"{entry['source']} carries {entry['value']!r}, which is not ISO-8601"
            )
        if moment.tzinfo is None:
            _die(f"{entry['source']} carries {entry['value']!r}, which has no timezone")
        parsed.append((moment, entry["value"]))
    return max(parsed, key=lambda pair: pair[0])[1]


def main(argv: list[str] | None = None, fetch: Fetcher = fetch_json) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    repo_root = Path(__file__).resolve().parents[2]
    parser.add_argument("--repo-root", type=Path, default=repo_root)
    parser.add_argument(
        "--record-api-url",
        required=True,
        help="The record's public read endpoint. Required, and deliberately not defaulted: this "
        "file is sealed and deposited, so an identifier written into it could not be redacted.",
    )
    parser.add_argument("--out", type=Path, default=repo_root / "seal" / "zenodo-witness.json")
    parser.add_argument("--timeout", type=float, default=30.0)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--datacite-api-base",
        help="The DOI registry's public API base. Its registration time joins the anchor.",
    )
    group.add_argument(
        "--datacite-absent-reason",
        help="Why no registry time is recorded. Required if the registry is not consulted, so "
        "that a narrower anchor is visible rather than silent.",
    )
    args = parser.parse_args(argv)
    root: Path = args.repo_root

    record = fetch(args.record_api_url.rstrip("/"), args.timeout)
    deposited = deposit_files(args.record_api_url, args.timeout, fetch)
    print(f"[witness] the record holds {len(deposited)} file(s)")

    entries, unmatched = match_by_content(root, deposited)
    if unmatched:
        print(
            "[witness] FAIL: these sealed files have no file of identical content in the "
            "deposit, so no witness was written:",
            file=sys.stderr,
        )
        for rel in unmatched:
            print(f"  - {rel}", file=sys.stderr)
        print(
            "[witness]        Deposit them and collect again. A witness covering part of the "
            "seal would read as covering all of it.",
            file=sys.stderr,
        )
        return 1

    sources = time_sources(record, deposited)
    absent_reason = args.datacite_absent_reason
    doi = record.get("doi")
    if args.datacite_api_base is not None:
        if not isinstance(doi, str) or not doi:
            _die("the record reports no DOI, so the registry cannot be consulted for one")
        sources.append(
            {
                "source": "datacite.registered",
                "value": registry_time(args.datacite_api_base, doi, args.timeout, fetch),
            }
        )

    witness: dict[str, Any] = {
        "schema": WITNESS_SCHEMA,
        "collected_by": "analysis/scripts/collect_zenodo_witness.py",
        "record_api_url": args.record_api_url.rstrip("/"),
        "record_id": record.get("id"),
        "version_doi": doi,
        "concept_doi": record.get("conceptdoi"),
        "anchor": (
            "latest_server_time is the maximum of the values in time_sources, taken verbatim. "
            "It bounds when the deposit was last touched, not when the sealed files were "
            "written, and not that no run preceded them."
        ),
        "depositor_supplied_not_part_of_the_anchor": {
            "publication_date": record.get("metadata", {}).get("publication_date"),
            "note": (
                "The depositor chooses this date and it carries no time of day. It is recorded "
                "so that its exclusion is visible, and the checker refuses to read it as an "
                "anchor."
            ),
        },
        "time_sources": sources,
        "latest_server_time": latest(sources),
        "deposit_files": deposited,
        "files": entries,
    }
    if absent_reason is not None:
        witness["datacite_absent_reason"] = absent_reason

    out: Path = args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(witness, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"[witness] wrote {out}: {len(entries)} sealed file(s) matched by content")
    print(f"[witness] latest server-assigned time = {witness['latest_server_time']}")
    if absent_reason is not None:
        print(f"[witness] no registry time recorded: {absent_reason}")
    print("[witness] now run verify_seal.py --witness; it is the only thing that checks this")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
