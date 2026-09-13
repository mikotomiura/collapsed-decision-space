#!/usr/bin/env python3
"""Build the anonymous supplementary bundle, and refuse to build one that still identifies anyone.

Double-blind review means the supplement is read by people who must not learn who wrote it. That is
easy to say and easy to get wrong, because identity leaks out of a research compendium through more
than the author line: a repository URL names its owner, a deposit identifier resolves to a landing
page with a name on it, an absolute path carries a username, and a ``.git`` directory carries the
whole authorship history in a form nobody looks at.

So this is not a redaction pass with a checklist. It is a redaction pass followed by a **scan that
fails the build**, and the scan is written against patterns rather than against the list of
substitutions, so a leak the substitution list did not anticipate is still caught.

**The property this exists to preserve.** Every sealed file must be *byte-identical* between the
public repository and this bundle. If a sealed file had to be redacted, the reviewer's copy and the
copy the deposit holds would be different bytes, and comparing them -- which is the entire point of
a content-addressed seal -- would be meaningless. The build therefore asserts that identity, and
fails rather than redacting a sealed file. When that assertion fires, the fix is to move the
identifying string out of the sealed file, as ``analysis/upstream-links.json`` records having been
done once already.

What this establishes: the bundle contains no string matching the patterns below, contains no
``.git``, and holds the sealed files unchanged.
What it does not: that a reviewer cannot identify the author by other means -- writing style, the
subject matter, or a preprint they have already read. Anonymity here is a property of the bytes,
not a guarantee about the world.

Usage:
    python analysis/scripts/make_anonymous_bundle.py --out build/anonymous
    python analysis/scripts/make_anonymous_bundle.py --out build/anonymous --zip
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from verify_seal import SEALED_PATHS  # noqa: E402

#: Substitutions applied to every text file that is not sealed. Longest first, so that a name
#: contained inside a URL is replaced by the URL rule rather than half-replaced by the name rule.
SUBSTITUTIONS: tuple[tuple[str, str], ...] = (
    ("https://github.com/mikotomiura/collapsed-decision-space", "https://anonymous.invalid/repo"),
    ("https://github.com/mikotomiura/ERRE-Sandbox", "https://anonymous.invalid/upstream"),
    ("https://orcid.org/0009-0000-4196-0508", "https://anonymous.invalid/orcid"),
    ("0009-0000-4196-0508", "0000-0000-0000-0000"),
    ("mikotomiura", "anonymous"),
    ("Mikoto Miura", "Anonymous Author"),
    ("Miura, Mikoto", "Author, Anonymous"),
    ("Mikoto", "Anonymous"),
    ("Miura", "Author"),
    ("mmiura.network@gmail.com", "anonymous@anonymous.invalid"),
)

#: What the scan looks for afterwards. These are written independently of the substitutions above:
#: a scan derived from the redaction list can only confirm that the redaction list was applied,
#: which is not the question. ``ORCID`` and ``DOI`` are shape patterns and will match the
#: placeholders too, so the placeholders are excluded explicitly rather than by being unmatchable.
LEAK_PATTERNS: tuple[tuple[str, str], ...] = (
    ("a personal name", r"\bmikoto\b|\bmiura\b"),
    ("a GitHub user or organisation", r"github\.com/(?!anonymous\b)[A-Za-z0-9-]+"),
    ("an ORCID identifier", r"\b\d{4}-\d{4}-\d{4}-\d{3}[\dX]\b"),
    ("a DOI", r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+"),
    ("a Zenodo record", r"zenodo\.org|zenodo\.\d+"),
    ("a Windows absolute path", r"[A-Za-z]:\\\\[A-Za-z0-9_.-]+\\\\"),
    ("a POSIX home directory", r"/(?:home|Users)/[A-Za-z0-9_.-]+"),
    ("an email address", r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
)

#: Strings the shape patterns above are allowed to match, because they are the placeholders this
#: script itself installs. Listing them beats loosening the patterns: a loosened pattern stops
#: catching the real thing.
ALLOWED: tuple[str, ...] = (
    "0000-0000-0000-0000",
    "anonymous@anonymous.invalid",
    "github.com/anonymous",
)

#: DOIs that belong to **other people's papers** and must stay in the bibliography. A DOI is
#: identifying when it is the author's own deposit and inert when it is a citation, and no pattern
#: can tell those apart. So the pattern stays broad and every citation is declared here by hand.
#: Adding a reference therefore fails this build until its DOI is written down as someone else's,
#: which is the right amount of friction: the alternative -- narrowing the pattern to one
#: registrar's prefix -- would silently stop catching a deposit made anywhere else.
CITED_DOIS: tuple[str, ...] = (
    "10.18653/v1/2020.emnlp-main.745",
    "10.1177/1948550617697177",
    "10.1007/s10462-025-11412-6",
    "10.1140/epjds/s13688-026-00674-x",
)

#: Suffixes read as text. Anything else is copied byte for byte and scanned as bytes.
TEXT_SUFFIXES: frozenset[str] = frozenset(
    {".md", ".py", ".json", ".toml", ".yml", ".yaml", ".cff", ".txt", ".sh", ".lock", ".cfg"}
)

#: Paths never copied into the bundle, matched against the path relative to the repository root.
#: ``.github`` goes because a workflow file names the repository in its badge and its artefact
#: names, and because CI configuration is not evidence. ``build`` goes because the bundle is built
#: there and must not contain a previous copy of itself.
EXCLUDED_PREFIXES: tuple[str, ...] = (".git/", ".github/", "build/", "data/derived/")

#: Paths copied byte for byte whatever their extension, and where a redaction would be an error
#: rather than a fix. These are the same paths ``.gitattributes`` marks ``-text``, for the same
#: reason: their SHA-256 and their git blob identifier are recorded, so rewriting a line ending
#: changes the digest and the recorded digest is what makes them evidence. This is not
#: hypothetical. The first version of this script treated ``.json`` as text and wrote it back with
#: LF endings, which took ``data/raw/es3-verdict-forensic.json`` from 11,743 bytes to 11,401 and
#: failed step 3 of the bundle's own reproduction -- the same 342 bytes a global ``core.autocrlf``
#: setting had removed once before.
VERBATIM_PREFIXES: tuple[str, ...] = ("data/raw/", "env/uv.lock")


def _die(message: str) -> None:
    print(f"[anon] FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def require_clean_tree(repo_root: Path) -> None:
    """Refuse to build from a working tree that git and the filesystem disagree about.

    The file list comes from ``git ls-files``, so a file that exists but is not tracked is
    invisible here and simply does not reach the bundle. That already happened once: a newly
    written provenance file was left out of a build, and nothing said so -- not the copy count,
    and not the leak scan, which cannot scan a file that is not there. An uncommitted *edit* fails
    the other way, shipping a submission that matches no commit. Both are caught by insisting the
    tree be clean, which for a submission artefact is the right bar anyway.
    """
    completed = subprocess.run(
        ["git", "-C", str(repo_root), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        _die(f"git status failed: {completed.stderr.strip()}")
    dirty = [line for line in completed.stdout.splitlines() if line.strip()]
    if dirty:
        listing = "\n  ".join(dirty[:20])
        more = f"\n  ... and {len(dirty) - 20} more" if len(dirty) > 20 else ""
        _die(
            "the working tree is not clean, and the bundle is built from what git tracks. "
            "An untracked file would be silently absent from the bundle and from the leak "
            "scan; an uncommitted edit would be silently absent from the submission:"
            f"\n  {listing}{more}"
        )


def tracked_files(repo_root: Path) -> list[str]:
    """List the files git tracks. Untracked scratch files must not reach a submission."""
    completed = subprocess.run(
        ["git", "-C", str(repo_root), "ls-files", "-z"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        _die(f"git ls-files failed: {completed.stderr.strip()}")
    names = [name for name in completed.stdout.split("\0") if name]
    if not names:
        _die("git ls-files returned nothing; refusing to build an empty bundle")
    return names


def redact(text: str) -> str:
    for old, new in SUBSTITUTIONS:
        text = text.replace(old, new)
    return text


def _mask_allowed(text: str) -> str:
    for allowed in (*ALLOWED, *CITED_DOIS):
        text = text.replace(allowed, "")
    return text


def scan(root: Path) -> list[str]:
    """Return one problem per file still carrying something that looks like identity."""
    problems: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, ValueError):
            text = path.read_bytes().decode("latin-1")
        haystack = _mask_allowed(text)
        for label, pattern in LEAK_PATTERNS:
            for match in re.finditer(pattern, haystack, re.IGNORECASE):
                line_no = haystack.count("\n", 0, match.start()) + 1
                problems.append(f"{rel}:{line_no}: {label}: {match.group(0)!r}")
    return problems


def anonymise_citation(path: Path) -> None:
    """Blind the author block of CITATION.cff without deleting the file.

    ``check_claim_boundary.py`` aborts if ``CITATION.cff``, ``README.md`` or ``README.ja.md`` is
    absent, so removing them would leave step 10 unable to start and the bundle unable to
    reproduce itself. A blinded copy keeps the check running on the text that matters -- the
    abstract, which must still equal the manuscript's.
    """
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        '  - family-names: "Author"\n'
        '    given-names: "Anonymous"\n'
        '    alias: "anonymous"\n'
        '    orcid: "https://anonymous.invalid/orcid"\n'
        '    affiliation: "Independent Researcher"\n',
        '  - name: "Anonymous (withheld for double-blind review)"\n',
    )
    path.write_text(text, encoding="utf-8", newline="\n")


def build(repo_root: Path, out: Path) -> Path:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    sealed = set(SEALED_PATHS)
    copied = 0
    rewritten_paths: list[str] = []
    for rel in tracked_files(repo_root):
        if rel.startswith(EXCLUDED_PREFIXES):
            continue
        source = repo_root / rel
        if not source.is_file():
            continue
        target = out / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        copied += 1

        verbatim = (
            rel in sealed
            or rel.startswith(VERBATIM_PREFIXES)
            or source.suffix.lower() not in TEXT_SUFFIXES
        )
        if verbatim:
            shutil.copyfile(source, target)
            # A sealed or frozen file that *needs* redacting is a design problem, not something to
            # fix here by rewriting it. Say so instead of shipping a quietly different digest.
            if rel.startswith(VERBATIM_PREFIXES):
                original = source.read_text(encoding="utf-8", errors="replace")
                if redact(original) != original:
                    _die(
                        f"{rel} is copied verbatim because its digest is recorded, but it "
                        "contains something the redaction list would change. Take the "
                        "identifying string out of the frozen input instead"
                    )
            continue

        original = source.read_text(encoding="utf-8")
        redacted_text = redact(original)
        if redacted_text == original:
            # Writing back an unchanged file is how line endings get normalised by accident.
            shutil.copyfile(source, target)
        else:
            target.write_text(redacted_text, encoding="utf-8", newline="\n")
            rewritten_paths.append(rel)

    redacted = len(rewritten_paths)

    citation = out / "CITATION.cff"
    if citation.is_file():
        anonymise_citation(citation)

    print(f"[anon] copied {copied} tracked files, rewrote {redacted} of them: {rewritten_paths}")
    return out, rewritten_paths


def check_sealed_unchanged(repo_root: Path, out: Path) -> list[str]:
    """The sealed files must be the same bytes here as in the public repository."""
    problems: list[str] = []
    for rel in SEALED_PATHS:
        left = repo_root / rel
        right = out / rel
        if not right.is_file():
            problems.append(f"{rel}: sealed, but missing from the bundle")
        elif left.read_bytes() != right.read_bytes():
            problems.append(
                f"{rel}: sealed, but the bundle's copy differs. A sealed file that has to be "
                "redacted cannot be compared with the deposited copy, which is what the seal is "
                "for. Move the identifying string out of the sealed file instead"
            )
    return problems


def check_only_redacted_files_differ(
    repo_root: Path, out: Path, rewritten: list[str]
) -> list[str]:
    """Every file the builder did not redact must be byte-identical to its source.

    The narrower check above covers the sealed files. This covers the rest, and it is the one that
    catches a whole class of accident rather than a named one: a copy that goes through ``str``
    rewrites line endings, and a digest recorded elsewhere in the repository then no longer
    matches a file whose visible content did not change at all.
    """
    expected_different = set(rewritten)
    problems: list[str] = []
    for path in sorted(out.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(out).as_posix()
        source = repo_root / rel
        if not source.is_file():
            continue  # files this script generates, such as ANONYMISED.md
        if rel in expected_different:
            continue
        if source.read_bytes() != path.read_bytes():
            problems.append(
                f"{rel}: differs from the source although no redaction applied to it. "
                "Copying through text mode is the usual cause, and a recorded digest is the "
                "usual casualty"
            )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    repo_root = Path(__file__).resolve().parents[2]
    parser.add_argument("--repo-root", type=Path, default=repo_root)
    parser.add_argument("--out", type=Path, default=repo_root / "build" / "anonymous")
    parser.add_argument("--zip", action="store_true", help="also write <out>.zip")
    args = parser.parse_args(argv)

    require_clean_tree(args.repo_root)
    out, rewritten = build(args.repo_root, args.out)

    problems = check_only_redacted_files_differ(args.repo_root, out, rewritten)
    if problems:
        print("[anon] FAIL: files changed that no redaction touched", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print(
        f"[anon] OK: {len(rewritten)} file(s) rewritten by redaction; every other file is "
        "byte-identical to the source"
    )

    problems = check_sealed_unchanged(args.repo_root, out)
    if problems:
        print("[anon] FAIL: the seal does not survive anonymisation", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print(f"[anon] OK: all {len(SEALED_PATHS)} sealed files are byte-identical in the bundle")

    if (out / ".git").exists():
        _die("the bundle contains a .git directory")

    problems = scan(out)
    if problems:
        print(f"[anon] FAIL: {len(problems)} thing(s) in the bundle still identify someone",
              file=sys.stderr)
        for problem in problems[:40]:
            print(f"  - {problem}", file=sys.stderr)
        if len(problems) > 40:
            print(f"  ... and {len(problems) - 40} more", file=sys.stderr)
        return 1
    print(
        f"[anon] OK: nothing in the bundle matches any of the {len(LEAK_PATTERNS)} leak patterns, "
        f"excluding {len(ALLOWED)} placeholders this script installs and {len(CITED_DOIS)} DOIs "
        "declared as belonging to cited work"
    )

    (out / "ANONYMISED.md").write_text(
        "# Anonymous supplementary bundle\n\n"
        "This is the research compendium with author-identifying strings removed for "
        "double-blind review. Names, the repository URL, the ORCID identifier and the deposit "
        "identifier are replaced by placeholders under `anonymous.invalid`.\n\n"
        "`bash repro.sh` runs here exactly as it does in the public repository, and reaches the "
        "same result: none of its twelve steps needs the network, an account, or any identifier "
        "that was removed. In particular the seal check -- the one that binds the reported branch "
        "to the rules as they stood before the run -- is fully exercisable from inside this "
        "bundle.\n\n"
        "The files under `seal/` are **byte-identical** to the public and deposited copies. That "
        "is deliberate: it is what lets a reader compare this bundle with a third-party archive "
        "once the identifiers are disclosed at camera-ready.\n",
        encoding="utf-8",
        newline="\n",
    )

    if args.zip:
        archive = shutil.make_archive(str(out), "zip", root_dir=out)
        size = Path(archive).stat().st_size
        print(f"[anon] wrote {archive} ({size / 1_048_576:.1f} MB)")

    manifest = {
        "sealed_files_unchanged": list(SEALED_PATHS),
        "leak_patterns_checked": [label for label, _ in LEAK_PATTERNS],
    }
    (out / "anonymisation-report.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"[anon] bundle at {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
