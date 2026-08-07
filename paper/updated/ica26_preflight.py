#!/usr/bin/env python3
"""Preflight for the ICA 2026 build: verify every \\input resolves, and
optionally flatten the document into one self-contained .tex.

Why this exists
---------------
A single missing \\input file aborts the whole LaTeX run with "Emergency stop".
Everything after the missing file never gets typeset, so the PDF is silently
truncated and EVERY citation and cross-reference in the document renders as [?]
or ?? -- because the run never reached \\bibliography and never wrote a complete
.aux. The symptom looks like a bibliography problem. It is not.

Run check mode before every compile:

    python scripts/ica26_preflight.py --root .

Flatten mode (--flatten) writes a single self-contained file with every \\input
expanded in place. Use it to produce the submission upload, NOT to replace the
modular source: the modular source is what lets a regenerated results file
propagate into the paper without anyone retyping a number.

    python scripts/ica26_preflight.py --root . --flatten ica2026_flat.tex
"""

from __future__ import annotations

import argparse
import os
import re
import sys

INPUT_RE = re.compile(r"^(?P<indent>[^%\n]*?)\\(?:input|include)\{(?P<path>[^}]+)\}", re.M)
GRAPHICS_RE = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}")
BIB_RE = re.compile(r"\\bibliography\{([^}]+)\}")
BIBSTYLE_RE = re.compile(r"\\bibliographystyle\{([^}]+)\}")


def resolve(root: str, path: str) -> str | None:
    """LaTeX appends .tex when the name has no extension."""
    for candidate in (path, path + ".tex"):
        full = os.path.join(root, candidate)
        if os.path.isfile(full):
            return full
    return None


def resolve_graphic(root: str, path: str, graphicspath: list[str]) -> str | None:
    exts = ["", ".pdf", ".png", ".jpg", ".jpeg", ".eps"]
    dirs = [""] + graphicspath
    for d in dirs:
        for e in exts:
            full = os.path.join(root, d, path + e)
            if os.path.isfile(full):
                return full
    return None


def collect(root: str, entry: str, seen: set[str]) -> tuple[list[str], list[tuple[str, str]]]:
    """Walk \\input recursively. Returns (files found, (parent, missing) pairs)."""
    found: list[str] = []
    missing: list[tuple[str, str]] = []

    full = resolve(root, entry)
    if full is None:
        return found, [("<command line>", entry)]
    if full in seen:
        return found, missing
    seen.add(full)
    found.append(full)

    src = open(full, errors="ignore").read()
    src = re.sub(r"(?<!\\)%.*$", "", src, flags=re.M)  # ignore commented-out inputs

    for m in INPUT_RE.finditer(src):
        child = m.group("path")
        sub_found, sub_missing = collect(root, child, seen)
        found += sub_found
        missing += [(os.path.relpath(full, root), p) for _, p in sub_missing]

    return found, missing


def check(root: str, entry: str) -> int:
    print(f"preflight: {entry}\n")

    found, missing = collect(root, entry, set())

    print(f"  \\input resolved : {len(found) - 1}")
    for f in sorted(found[1:]):
        print(f"      ok  {os.path.relpath(f, root)}")

    problems = 0

    if missing:
        problems += len(missing)
        print(f"\n  \\input MISSING  : {len(missing)}")
        for parent, path in missing:
            print(f"      !!  {path}   (referenced from {parent})")
        print("\n      A missing \\input aborts LaTeX entirely. Every citation and")
        print("      cross-reference in the document will render as [?] or ?? until")
        print("      this is fixed. Fix this before looking at anything else.")

    # figures
    main_src = open(resolve(root, entry), errors="ignore").read()
    gp = re.search(r"\\graphicspath\{\{([^}]*)\}\}", main_src)
    graphicspath = [gp.group(1)] if gp else []

    all_src = "\n".join(open(f, errors="ignore").read() for f in found)
    all_src = re.sub(r"(?<!\\)%.*$", "", all_src, flags=re.M)

    missing_gfx = [
        g for g in GRAPHICS_RE.findall(all_src)
        if resolve_graphic(root, g, graphicspath) is None
    ]
    if missing_gfx:
        problems += len(missing_gfx)
        print(f"\n  \\includegraphics MISSING : {len(missing_gfx)}")
        for g in missing_gfx:
            print(f"      !!  {g}")

    # bibliography
    for m in BIB_RE.finditer(all_src):
        for name in m.group(1).split(","):
            if resolve(root, name.strip() + ".bib") is None:
                problems += 1
                print(f"\n  \\bibliography MISSING : {name.strip()}.bib")

    for m in BIBSTYLE_RE.finditer(all_src):
        style = m.group(1).strip()
        if not os.path.isfile(os.path.join(root, style + ".bst")):
            print(f"\n  note: {style}.bst is not in the project root.")
            print("      The build will still work if the TeX distribution ships it,")
            print("      but Springer expects the version they distribute. Upload")
            print(f"      {style}.bst (and llncs.cls) to be certain.")

    # labels vs refs
    labels = set(re.findall(r"\\label\{([^}]*)\}", all_src))
    refs = set(re.findall(r"\\(?:ref|autoref|cref)\{([^}]*)\}", all_src))
    dangling = sorted(refs - labels)
    if dangling:
        problems += len(dangling)
        print(f"\n  \\ref with no \\label : {len(dangling)}")
        for r in dangling:
            print(f"      !!  {r}")

    unused = sorted(labels - refs)
    if unused:
        print(f"\n  note: {len(unused)} label(s) never referenced: {', '.join(unused)}")

    print()
    if problems:
        print(f"FAIL: {problems} problem(s). Do not compile yet.")
    else:
        print("PASS: every input, figure, and reference resolves.")
    return 1 if problems else 0


def flatten(root: str, entry: str, out: str) -> int:
    """Expand every \\input in place, producing one self-contained file."""
    banner = (
        "% GENERATED by scripts/ica26_preflight.py --flatten. DO NOT EDIT.\n"
        "% Every \\input has been expanded in place. Edit the modular source\n"
        "% (ica2026.tex + tables/) and regenerate this file instead.\n"
    )

    def expand(path: str, depth: int = 0) -> str:
        if depth > 10:
            raise RuntimeError("input nesting too deep -- circular \\input?")
        full = resolve(root, path)
        if full is None:
            raise SystemExit(f"cannot flatten: missing {path}")
        src = open(full, errors="ignore").read()

        def repl(m: re.Match) -> str:
            line_prefix = m.group("indent")
            if line_prefix.strip():           # not a standalone \input line
                return m.group(0)
            child = m.group("path")
            rel = os.path.relpath(resolve(root, child) or child, root)
            return (
                f"% >>> begin {rel}\n"
                + expand(child, depth + 1).rstrip("\n")
                + f"\n% <<< end {rel}"
            )

        return INPUT_RE.sub(repl, src)

    result = expand(entry)
    result = result.replace("\\documentclass", banner + "\\documentclass", 1)
    with open(os.path.join(root, out), "w") as fh:
        fh.write(result)

    n = result.count("% >>> begin ")
    print(f"flattened {n} file(s) into {out}")
    print("Upload this single file plus references.bib and the figures.")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--entry", default="ica2026.tex")
    ap.add_argument("--flatten", metavar="OUT.tex")
    args = ap.parse_args()

    if args.flatten:
        sys.exit(flatten(args.root, args.entry, args.flatten))
    sys.exit(check(args.root, args.entry))


if __name__ == "__main__":
    main()
