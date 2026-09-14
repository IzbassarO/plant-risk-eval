# ICA 2026 paper

Anonymized Springer LNCS draft. **Do not edit `generated/` by hand.**

```bash
bash scripts/ica26_build_paper.sh     # regenerate everything, then compile
```

That script is the only supported way to build. It regenerates tables, figures,
and result macros from `experiments/ica26/metrics/*.json` *before* running
LaTeX, so a PDF cannot be produced from a number that a later run has
superseded. It then runs the repository's anonymity gate over the paper sources
and compiles with `tectonic`, which fetches `llncs.cls` and `splncs04.bst` on
demand — no local TeX Live installation is needed.

## Files

| Path | Role |
|---|---|
| `ica2026.tex` | The paper. Contains **no** literal experimental number. |
| `references.bib` | Bibliography. |
| `generated/results_macros.tex` | Every experimental number, as macros. Generated. |
| `RESULTS_PLACEHOLDERS.md` | Table/figure slot status. Generated. |
| `ica2026.pdf` | Built output. |

## Why the numbers are macros

`ica2026.tex` cites `\MacroFXdRn`, never `0.2414`. The macro is defined in
`generated/results_macros.tex`, which `scripts/ica26_build_paper_macros.py`
writes from the dataset lock, the run result files, and `significance.json`.

Three properties follow, and they are the reason for the indirection:

1. **A number cannot be stale.** Regenerating updates every occurrence.
2. **A number cannot be invented.** A value with no result file behind it is
   defined as `\ResultPending` and typesets as a conspicuous `[PENDING]`
   marker. An incomplete draft looks incomplete instead of looking finished.
3. **A number cannot drift unnoticed.** `tests/test_ica26_paper_macros.py`
   recomputes the headline values independently from the result JSON, checks
   that a single seed prints a bare mean while two or more print `mean ± std`,
   and fails if the paper references a control sequence that is neither a
   result macro nor known LaTeX.

If you need a number the paper does not yet expose, add it to the generator.
Adding a `\newcommand` to `ica2026.tex` is rejected by the test suite, because
such a definition would escape regeneration and silently freeze at whatever
value was current when it was typed.

## Anonymity

The submission is double-blind. `ica26_build_paper.sh` runs
`ica26.portability.scan_text` over `paper/**.{tex,bib,md}` and fails the build
on a home path, an account name, or a non-allowlisted email address. The paper
is the artifact that is actually sent out, so it is in scope for that gate even
though the gate's default globs cover generated data artifacts.

Author, affiliation, funding, and any repository URL stay out until
camera-ready.

## Draft status

Sections 1–4 (introduction, related work, datasets and leakage control,
experimental protocol) and 8–10 (discussion, limitations, conclusion) are
written. Sections 5–7 carry the results narrative and are held until the
three-seed matrix finishes; their tables and figures already exist and are
included, so what is missing there is prose, not evidence.

The build reports its page count against the venue's 12–15 page limit. The
draft is already near the top of that range with sections 5–7 empty, so the
results narrative will need space freed elsewhere — most plausibly by moving
the provenance table and the per-run diagnostic figures to supplementary
material.

## Scope divergence from `PROJECT_BRIEF.md` — read before editing the framing

`PROJECT_BRIEF.md` §1 fixes the title *"From Diagnosis to Decision: An
Action-Level and Risk-Weighted Evaluation Framework for Deep Learning-Based
Plant Disease Recognition"* and marks it "final, do not change".

**This draft does not implement that framing, deliberately.** The Risk
Evaluation Layer that framing depends on — action mappings, harm matrix,
treatment recommendation — has no verified results. PlantVillage action-mapping
coverage is 0/38, tracked as open blocker BLOCK-07, and
`reports/ICA26_EXPERIMENT_PROTOCOL.md` §Scope already records the layer as
outside this paper. Writing the action-level paper would require inventing the
results it reports.

So this draft reports what the completed experiments actually support: the
leakage-controlled cross-domain evaluation. That is a genuine and defensible
contribution, but it is a **different paper** from the one the brief describes,
and the divergence is a decision for the author, not for the build system.

Two ways to resolve it, both of which need a human:

- Keep this scope and update the brief's title and framing to match. The
  venue's observed title conventions (11–16 words, a colon, names the domain and
  the method, constructive rather than provocative) are satisfied by the current
  working title.
- Restore the action-level scope, which requires closing BLOCK-07 and producing
  verified Risk Evaluation Layer results first.
