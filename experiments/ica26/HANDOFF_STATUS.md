# ICA 2026 — status

Updated 2026-08-06. Branch `claude/ica26-training-launch`.

**Submission goes to CMT today. The final `.tex` were assembled and checked by
hand outside this repository.** Do not regenerate anything expecting it to match
what was submitted.

---

## ⚠ Read before ever running the table generator again

`table6_calibration_compact.tex` and `table9_significance_across_seeds_compact.tex`
are **transposed** in the submitted version:

| table | submitted form | previous form |
|---|---|---|
| `table6_calibration_compact` | **3 rows** (one per backbone), 4 ECE columns | 18 rows (one per setting) |
| `table9_significance_across_seeds_compact` | **3 rows** (one per evaluation), 3 column groups | 9 rows (one per comparison) |

Those two rotations are what bought two pages. **If the generator emits them in
the old row-per-setting form, the paper grows from 15 pages to 17 and breaks the
conference limit.**

The transposed builders are committed (`table_calibration_compact` in
`ica26_build_tables.py`, `write_consistency_table_compact` in
`ica26_significance.py`) and `tests/test_table_generation.py` asserts the 3-row
shape — but those tests are **not committed yet** (see below).

No value was lost in transposing: all 12 ECE cells were verified present in the
full table, and all 9 significance triples verified against
`significance_all_seeds.json`.

---

## Done from the handoff list

1. **Double LaTeX escaping — fixed and committed.** Data and authored markup now
   go through separate paths in `src/ica26/experiments/latexfmt.py`. A `Raw`
   marker is registered by content, because `DataFrame.rename` and
   `Series.replace` strip the subclass and the marker would otherwise be lost
   inside pandas.
2. **Integer separators — fixed and committed.** One `fmt_int` shared by both
   generators. `Seed` is excluded as an identifier: 1337 names a run.
3. **Table widths — measured, not guessed.** `scripts/ica26_fit_tables.py`
   measures every table against the real `llncs.cls` in one compile. Widths
   matched the handoff's independent numbers to within 2 mm across all ten
   overflowing tables. Four need `sidewaystable` (not three): `table6_calibration`
   misses the 180 mm supplement measure by 2.6 mm.
4. **Preflight — installed** as `scripts/ica26_preflight.py` and wired into
   `ica26_build_paper.sh` before both compiles.
5. **All 12 bridge macros now generated**, so `results_macros_additions.tex` is a
   no-op and both `[PENDING]` are gone. `EceRatio` (1.48/1.55/1.94) and
   `TempSdMax` (0.0076) reproduced the handoff's independently computed values.
   `TempSdMax` is PlantVillage-only — pooling PlantDoc gives 0.0512 and overstates
   it sixfold.
6. **21-class in-domain control** (`scripts/ica26_shared_space_control.py`) —
   answers Limitation 1 without retraining. Scoring PlantVillage test through the
   identical shared-space pipeline gives a 77.0 / 77.0 / 81.2 % drop against
   76.9 / 76.9 / 81.2 % for 38-way → 21-way. The label-space change contributes
   almost nothing; the collapse is domain shift.
7. **Value snapshot** — `build/table_numbers.json`, taken from the pre-change git
   revision so the "no digit moved" check was real. 1,404 tokens across 21 tables,
   none moved.

---

## Not committed (working tree only)

Everything below works but is **uncommitted**, by instruction:

- `scripts/ica26_fit_tables.py`, `ica26_preflight.py`, `ica26_verify_tables.py`,
  `ica26_shared_space_control.py`
- `tests/test_table_generation.py`, `tests/test_ica26_latexfmt.py` (140 tests)
- changes to `ica26_build_paper_macros.py` (the 12 macros) and
  `ica26_build_paper.sh` (preflight + fitting)
- `paper/supplementary.tex` (`\usepackage{rotating}`), `build/table_numbers.json`

**21 files in `experiments/ica26/tables/` are modified but uncommitted.** A
`ica26_fit_tables.py` run finished moments before the stop instruction and
rewrote their size prologues. They are left exactly as that run left them —
neither committed nor reverted. Since the submitted `.tex` were assembled outside
the repository, this does not affect the submission.

---

## Still open

- **Ablation without label smoothing** — one run, one backbone, one seed. Would
  either lift or confirm the Limitations caveat that the calibration finding is
  tied to the label-smoothing + in-domain-temperature pairing.
- **ICA 2023/2024/2025 CCIS references** — `references.bib` still cites none.
- The size ceilings in `PREFERRED_MAX_SIZE` (`ica26_fit_tables.py`) exist because
  width is not the binding constraint; page height is. Picking the largest font
  that fits pushed the paper to 16 pages. Raising a ceiling can cost a page.
