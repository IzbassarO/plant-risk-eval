# Phase-1 Review Decision Validation

**Project:** *From Diagnosis to Decision* (ICA 2026) — Phase-1 closeout, Phase B.
**Generated:** 2026-08-02 by `python3 scripts/validate_phase1_review.py` (stdlib-only, deterministic).
**Machine-readable findings:** `data/interim/phase1_review_validation.csv` (75 rows)
**Summary + checksums:** `data/interim/phase1_review_validation_summary.json`

---

## Verdict — **BLOCKED**

**74 blocking findings. 0 warnings. 1 informational pass.**

Phase C (apply reviewed decisions) and Phase D (Dataset V1 freeze) **were not started**, per
the standing rule that a blocking issue stops the closeout after the reports are produced.

The root cause is singular and unambiguous: **the human-review packet has not been returned.**
All 44 decisions the packet requested (16 near-duplicate + 28 action-mapping) are still blank.
`phase1_return_package.zip` is byte-identical to the outbound packet built on 2026-07-30 and
contains no `data/mapping/` directory; no returned copy exists anywhere on this machine.

---

## 1 · Cross-dataset near-duplicate review

`data/exclusions/cross_dataset_near_duplicate_review.csv` — SHA-256
`a9823815600bb80d11f3e9978407e1202b2e0e27d3a813439e362f2e0b1d12f4`

| Metric | Value |
|---|---:|
| Rows | 16 |
| Authoritative near pairs (`leakage_…_pairs.csv`) | 16 |
| **Decided** (non-blank, terminal `human_decision`) | **0** |
| Excluded (`final_disposition = exclude_evaluation`) | 0 |
| Kept (`final_disposition = keep`) | 0 |
| **Unresolved** | **16** |
| Invalid / unsupported values | 0 |
| Rows in `cross_dataset_reviewed_exclusions.csv` | 0 |
| Rows in `cross_dataset_exact_exclusions.csv` | 0 |

### Structural checks — all PASS

| Check | Result |
|---|---|
| `pair_id` present and unique | ✅ 16/16 unique (`ndp-01` … `ndp-16`) |
| Source/target record fields complete | ✅ all 8 identity fields non-blank on every row |
| SHA-256 well-formed (64-hex, lowercase) | ✅ 32/32 values |
| Pair present in the authoritative pHash pair table | ✅ 16/16 — **no reviewed pair disappeared** |
| `phash_distance` matches the authoritative table | ✅ 16/16 (15 × d=6, 1 × d=4) |
| `phash_distance` inside the near band `0 < d ≤ 6` | ✅ 16/16 |
| Training image present in `plantvillage_manifest.csv` | ✅ 16/16 |
| Evaluation image present in `plantdoc_manifest.csv` | ✅ 16/16 |
| Contact sheet exists on disk | ✅ 4/4 referenced sheets |
| Every authoritative near pair has a review row | ✅ 0 unreviewed pairs |
| **No unreviewed pair is being treated as resolved** | ✅ reviewed-exclusions file is empty, so nothing is claimed resolved |
| Exact-exclusions file free of near (d>0) pairs | ✅ 0 rows |

Pair identity was resolved through the authoritative pHash pair table and the recorded
SHA-256 values. **No duplicate status was inferred from any filename.**

### Blocking findings

| ID | Check | Rows | Detail |
|---|---|---:|---|
| BLOCK-01 | `NDP-DECISION-PRESENT` | 16 | `human_decision` is blank — the pair has not been adjudicated |
| BLOCK-02 | `NDP-DISPOSITION-PRESENT` | 16 | `final_disposition` is blank — no disposition to apply |

Affected: `ndp-01` … `ndp-16` (every row). `reviewer` and `reviewed_at` are correspondingly
blank; that is consistent with "not yet reviewed" and is not reported as a separate defect.

**Consequence.** `reports/LEAKAGE_GATE_EXCLUSION_POLICY.md` §"status = pass requires ALL of"
condition (3) — *every pHash-near pair resolved, 0 pending and 0 uncertain* — is unmet.
`reports/leakage_gate.json` therefore correctly remains `status = fail` with
`unresolved_pair_count = 16`. The gate was **not** touched and was **not** forced to pass.

---

## 2 · Action-mapping review

`data/mapping/action_mapping_review.csv` — SHA-256
`d4d63addf7654c718dda43955f22f9e2773f8e42ed0bebb9e3d8de77782fd4e4`

| Metric | Value |
|---|---:|
| Rows | 28 (all `dataset = PlantDoc`) |
| **Approved** | **0** |
| **Excluded** | **0** |
| **Pending** (`review_status = needs_review`) | **28** |
| Invalid / unsupported values | 0 |
| PlantDoc classes in manifest / mapped | 28 / 28 (100 %) |
| PlantVillage classes in manifest / mapped | 38 / **0** (0 %) |
| Healthy rows | 10 |
| Arthropod-pest rows | 1 |

### Structural checks — all PASS

| Check | Result |
|---|---|
| `dataset` + `dataset_class` present and unique | ✅ 28/28, original labels preserved verbatim |
| `canonical_crop` present | ✅ 28/28 (13 distinct crops) |
| `canonical_disease` present | ✅ 28/28 (16 distinct conditions) |
| Candidate action in the 4-class taxonomy | ✅ 28/28 — fungicide 13, monitor 11, copper_sanitation 2, remove_vector 2 |
| No forbidden action (`abiotic_correction`) | ✅ 0 occurrences |
| `pathogen_type` recognised where present | ✅ 18/18 (fungal, bacterial, viral, oomycete, mite) |
| `mapping_confidence` valid | ✅ 28/28 (high 26, medium 2) |
| `review_status` in the allowed enum | ✅ 28/28 (`needs_review`) |
| Healthy-class treatment internally consistent | ✅ all 10 healthy classes → `monitor` |
| PlantDoc class coverage | ✅ 28/28, no class missing a row |

### Blocking findings

| ID | Check | Rows | Detail |
|---|---|---:|---|
| BLOCK-03 | `MAP-STATUS-TERMINAL` | 28 | `review_status = needs_review` — no terminal human decision (`approved` / `excluded`) recorded |
| BLOCK-04 | `CHECKLIST-DECIDED` | 1 (covers 28) | All 28 `Human choice` fields in `reports/ACTION_MAPPING_HUMAN_CHECKLIST.md` are still `______` |
| BLOCK-05a | `MAP-EVIDENCE-GATE` | 10 | Evidence gate **unsatisfiable as authored** |
| BLOCK-05b | `MAP-SCHEMA-VOCAB` | 1 | Review CSV / canonical schema action-column divergence |
| BLOCK-06 | `MAP-SCOPE-ARTHROPOD` | 1 | Arthropod-pest class lacks an explicit scope decision |
| BLOCK-07 | `MAP-COVERAGE-DATASET` | 1 | PlantVillage has 0 mapping rows |

#### BLOCK-05a — the 10 healthy rows cannot be approved as authored

`Apple leaf`, `Bell_pepper leaf`, `Blueberry leaf`, `Cherry leaf`, `Peach leaf`,
`Raspberry leaf`, `Soyabean leaf`, `Strawberry leaf`, `Tomato leaf`, `grape leaf`.

Each has blank `pathogen_type`, `source_url` and `source_identifier`. All three are listed in
`src/ica26/schemas.py:EVIDENCE_FIELDS_REQUIRED_FOR_APPROVAL`, so
`src/ica26/mapping/validation.py` **rejects** any of these rows marked `approved`. A reviewer
who writes `approve` on all 28 checklist entries would produce a mapping table that fails its
own validator — the decision would be silently unusable.

This needs a **human policy decision**, not a code fix: either (a) healthy classes are exempt
from the pathogen-evidence gate and the exemption is encoded explicitly, or (b) they carry
`pathogen_type = unknown` plus a real taxonomy/extension source. **I did not choose between
these.**

#### BLOCK-05b — action-column divergence

The review CSV names the action column `candidate_action_class`; the canonical schema
(`MAPPING_COLUMNS`) requires `action_class`. `read_mapping()` tolerates the mismatch by
injecting a **blank** `action_class`, which then fails the evidence gate on a field the
reviewer was never shown. No script in `scripts/` transcribes review → canonical template, so
there is currently no non-manual path from a recorded decision to an applied one.

#### BLOCK-06 — arthropod-pest scope

`Tomato two spotted spider mites leaf` (`pathogen_type = mite`, candidate `monitor`,
confidence `medium`) is an **arthropod pest**, not a plant pathogen. It is currently
`needs_review`, so it is neither included nor excluded — correct fail-closed behaviour, but
unresolved. Whether a mite-damage class belongs in a *plant-disease* recognition dataset is a
scientific scope call reserved for the human reviewer. **It has not been silently included.**

Note: PlantDoc's `test` split has 27 classes to `train`'s 28 — this class is the one absent
from `test`. Whatever scope decision is made must account for that asymmetry.

#### BLOCK-07 — PlantVillage mapping coverage is 0 %

PlantVillage supplies 54,305 images across 38 classes and is the **training** source for the
cross-dataset design. `action_mapping_review.csv`, `class_crosswalk.csv` and
`disease_pathogen.csv` all cover **PlantDoc only** (28 rows each). No PlantVillage class can
be projected to an action. Action-level evaluation over the training distribution is therefore
impossible until a PlantVillage mapping table is authored **and** reviewed — a second review
round that has not been scoped.

---

## 3 · Findings by check

| Check ID | Findings | Severity |
|---|---:|---|
| `NDP-DECISION-PRESENT` | 16 | blocker |
| `NDP-DISPOSITION-PRESENT` | 16 | blocker |
| `MAP-STATUS-TERMINAL` | 28 | blocker |
| `MAP-EVIDENCE-GATE` | 10 | blocker |
| `CHECKLIST-DECIDED` | 1 | blocker |
| `MAP-COVERAGE-DATASET` | 1 | blocker |
| `MAP-SCHEMA-VOCAB` | 1 | blocker |
| `MAP-SCOPE-ARTHROPOD` | 1 | blocker |
| `MAP-HEALTHY-CONSISTENT` | 1 | info (**pass**) |
| **Total** | **75** | 74 blocker / 1 info |

Every check that could pass **did** pass. The reviewed files are structurally sound, complete,
internally consistent and correctly bound to the authoritative indexes and manifests. The only
thing missing is the human judgement they were built to carry.

---

## 4 · What was *not* done, and why

| Phase | Status | Reason |
|---|---|---|
| C — apply reviewed decisions | **not started** | 74 blockers; there are no decisions to apply |
| D — Dataset V1 freeze | **not started** | gated on C; freezing now would bake in an unresolved leakage gate and 0 approved mappings |
| E — testing / deterministic rebuild | **not run** | gated on C/D; the environment also lacks `pytest`, `pandas`, `imagehash` and `ica26` |

Nothing was applied, patched, regenerated, deleted, or reinterpreted. The leakage gate was not
touched and remains `fail` (fail-closed).

---

## 5 · Exact human actions required to unblock

1. **Adjudicate the 16 near-duplicate pairs.** Open
   `reports/near_duplicate_contact_sheets/contact_sheet_0[1-4].png`, then for each row of
   `data/exclusions/cross_dataset_near_duplicate_review.csv` fill `human_decision`
   (`same_source_image` | `same_scene_different_crop` | `visually_similar_but_independent` |
   `clearly_different` | `uncertain`), `final_disposition` (`exclude_evaluation` | `keep` |
   `needs_secondary_review`), `decision_reason`, `reviewer`, `reviewed_at`. Copy every
   `exclude_evaluation` row into `data/exclusions/cross_dataset_reviewed_exclusions.csv`.
   *Note: `uncertain` / `needs_secondary_review` do not resolve a pair — the gate stays closed.*

2. **Decide the healthy-class evidence policy** (BLOCK-05a) before approving any healthy row.

3. **Decide the arthropod-pest scope question** (BLOCK-06) for
   `Tomato two spotted spider mites leaf`.

4. **Fill the 28 `Human choice` fields** in `reports/ACTION_MAPPING_HUMAN_CHECKLIST.md` and set
   `review_status` in `data/mapping/action_mapping_review.csv` to `approved` or `excluded`
   accordingly — `approved` only where the evidence gate is genuinely satisfied.

5. **Decide the PlantVillage mapping scope** (BLOCK-07): author + review a 38-class
   PlantVillage mapping, or formally restrict action-level evaluation to PlantDoc and record
   that restriction as a design decision.

6. **Restore the environment and version control** (BLOCK-08/09) so Phase C–E can execute and
   be fingerprinted:
   `python3.13 -m venv .venv && pip install -e ".[hf,dev]"`, then `git init` + initial commit.

Then re-run `python3 scripts/validate_phase1_review.py` — it must exit `0` before Phase C
begins.

---

## 6 · Explicit statements

- **No human decision was invented, defaulted, inferred, or overridden.**
- **No blank field was filled in on the reviewer's behalf.**
- **No duplicate status was inferred from a filename** — pair identity came from the
  authoritative pHash pair table and recorded SHA-256 values.
- **No reviewed source file was modified.** Post-run checksums match §1 and §2 exactly.
- **No raw data was deleted.**
- **The leakage gate was not forced to pass.**
- **No model was trained; no Phase-2 experiment was started.**
- **This report asserts mechanical validity only. It is not scientific acceptance of any
  mapping, exclusion, or dataset.**
