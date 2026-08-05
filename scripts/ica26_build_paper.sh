#!/usr/bin/env bash
# Build the ICA 2026 paper from current, verified artifacts.
#
#   bash scripts/ica26_build_paper.sh
#
# The order matters and is the point of this script: tables, figures, and result
# macros are all regenerated from experiments/ica26/metrics/*.json before LaTeX
# runs, so the PDF can never be built from a stale number that a completed run
# has since superseded.
#
# Compilation uses tectonic, which resolves llncs.cls and splncs04.bst on demand;
# no local TeX Live installation is required. If tectonic is absent the script
# regenerates every input and stops there, reporting what it did rather than
# failing silently.

set -u
cd "$(dirname "$0")/.."
REPO="$(pwd)"
PY="${PY:-$REPO/.venv/bin/python}"
PAPER="$REPO/paper"
TECTONIC="${TECTONIC:-$(command -v tectonic || true)}"

echo "== regenerating tables and figures from result files =="
"$PY" scripts/ica26_build_tables.py || { echo "table build FAILED"; exit 1; }

echo
echo "== regenerating result macros =="
"$PY" scripts/ica26_build_paper_macros.py || { echo "macro build FAILED"; exit 1; }

echo
echo "== anonymity gate on paper sources =="
# The paper is the double-blind artifact. A home path or account name in it
# would deanonymise the submission as surely as a name on the title page.
"$PY" - <<'PYEOF'
import re, sys
from pathlib import Path
sys.path.insert(0, "src")
from ica26.portability import scan_text

hits = []
for path in sorted(Path("paper").rglob("*")):
    if path.suffix not in {".tex", ".bib", ".md"} or not path.is_file():
        continue
    for name, match in scan_text(path.read_text(errors="replace")):
        hits.append(f"  {path}: {name}: {match}")
if hits:
    print("ANONYMITY GATE FAILED:")
    print("\n".join(hits))
    sys.exit(1)
print("OK: no home paths, usernames, or non-allowlisted emails in paper sources")
PYEOF
[ $? -ne 0 ] && exit 1

if [ -z "$TECTONIC" ]; then
  echo
  echo "tectonic not found; inputs are regenerated but no PDF was built."
  echo "Install with: brew install tectonic"
  exit 0
fi

echo
echo "== compiling supplementary =="
cd "$PAPER"
if "$TECTONIC" -X compile supplementary.tex --keep-logs 2>&1 | grep -E "^(error|warning: .*Overfull)" | head -5; then :; fi
if [ -f "$PAPER/supplementary.pdf" ]; then
  SPAGES=$(sed -n 's/.*Output written on .*(\([0-9]*\) pages.*/\1/p' supplementary.log | tail -1)
  echo "wrote paper/supplementary.pdf (${SPAGES:-?} pages)"
else
  echo "supplementary compilation FAILED"
fi

echo
echo "== compiling paper =="
if "$TECTONIC" -X compile ica2026.tex --keep-logs 2>&1 | tail -20; then
  echo
  if [ -f "$PAPER/ica2026.pdf" ]; then
    echo "wrote paper/ica2026.pdf"
    # Page count matters here: the venue caps submissions at 15 pages. Read it
    # from the engine's own report; the PDF itself uses object streams, so the
    # page tree is compressed and not greppable.
    PAGES=$(sed -n 's/.*Output written on .*(\([0-9]*\) pages.*/\1/p' ica2026.log | tail -1)
    [ -n "$PAGES" ] && echo "pages: $PAGES  (venue limit: 12-15)"
    # A [PENDING] marker on the page means a cited number does not exist yet.
    if grep -q "ResultPending" generated/results_macros.tex \
       && grep -c "ResultPending}{\\\\ResultPending" generated/results_macros.tex >/dev/null 2>&1; then
      NPENDING=$(grep -c '{\\ResultPending}$' generated/results_macros.tex || true)
      [ "${NPENDING:-0}" -gt 0 ] && echo "WARNING: $NPENDING macro(s) typeset as [PENDING]"
    fi
  fi
else
  echo "LaTeX compilation FAILED"
  exit 1
fi
