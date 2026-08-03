# Phase-1 Integrity Remediation — Round 2B

**Starting commit:** `433c3ce236b5061a7f9afaaf04348f91902fe77b`
**Branch:** `main`
**Scope:** apply the completed human adjudication of the 12 PlantDoc byte-exact duplicate groups
(R1-CRIT-002), and complete the internal duplicate gate so it verifies the application rather
than merely the decision.

_No model was trained, no metric was computed, no mapping was approved, no cross-dataset
decision was revisited, and **Dataset V1 remains unfrozen**. Every label, split and exclusion
below was read from a human decision row; none was inferred._

---

## 1. What R2A left open, and what R2B closes

R2A enumerated the twelve groups, proved byte and decoded-pixel identity, and built a
decision-neutral review packet. It deliberately applied nothing. The gate it shipped answered one
question — *has a human decided?* — and reported `incomplete`.

A human has now decided all twelve. R2B applies those decisions and closes the gap between the
two claims that a schema-1.0 `pass` conflated:

| Claim | R2A | R2B |
|---|---|---|
| A human recorded a terminal decision for every group | verified | verified |
| Those decisions were **applied** to the data | not asked | **verified** |
| No exact duplicate survives across train/test | not asked | **verified (0)** |
| No record outside the reviewed set changed | not asked | **verified (2,554 byte-identical)** |
| Persisted output equals a fresh rebuild by identity | not asked | **verified (set equality)** |

---

## 2. Preflight reconciliation

Run before anything was written; all twelve checks clean.

| Check | Result |
|---|---|
| `git rev-parse HEAD` | `433c3ce236b5061a7f9afaaf04348f91902fe77b` ✓ |
| Working tree | clean except the untracked `human_review/` drop |
| Adjudication CSV schema | header **identical** to the issued packet's 19 columns |
| Group ids | 12 rows, 12 distinct ids, set-equal to a **fresh enumeration from the manifest** |
| Evidence columns | 0 drift across all 12 rows (digests, member/split/class counts, class labels) |
| Members | 24/24 present in the manifest with matching digest, label, split, size, geometry |
| Member set | set-equal to a fresh enumeration |
| Decisions | 10 `keep_one_record`, 2 `exclude_all_records`, 0 `needs_further_review` |
| Canonical labels | all 10 exist in PlantDoc's own 28-class vocabulary |
| Validation JSON | every declared field reconciles with the actual CSV (below) |

```
declared output_sha256                6a21f927a58006644713769435e2709725dd36650388a989bddfcb8867f8a7ef  ✓
declared members_csv_untouched_sha256 628cdb029f99eb8fc76a4a568d85e627af620dfa881c9be261f2fca2a31b82ad  ✓
declared rows / terminal / keep_one / exclude_all / move_to_train = 12 / 12 / 10 / 2 / 10        ✓
```

One incidental artifact accompanied the drop: an empty zero-byte file `human_review/c`, evidently
a shell slip. It contained nothing and was removed rather than committed.

### The reviewed records do not touch R2A

The 24 reviewed PlantDoc records and the 7 PlantDoc endpoints of the 16 cross-dataset near pairs
are **disjoint** (intersection = ∅). R2B therefore cannot perturb the 16 accepted near-pair
decisions even in principle — and the reconstructed cross-dataset gate confirms it (§8).

---

## 3. Preserved evidence

Evidence is append-only: the completed decision file is filed **beside** the inputs the reviewer
saw, never over them.

```
human_review/
  README.md
  evidence_manifest.json                  <- generated, never hand-edited
  plantdoc_exact_duplicates/
    original/                             <- the packet AS ISSUED. Immutable.
      plantdoc_exact_duplicate_groups.csv       8fb8cc8a…  all 6 decision columns blank
      plantdoc_exact_duplicate_members.csv      628cdb02…  24 evidence rows
      PLANTDOC_EXACT_DUPLICATE_HUMAN_REVIEW.md  e6f28602…
      packet_manifest.json                      658a5787…  incl. the 4 contact sheets shown
    adjudicated/
      plantdoc_exact_duplicate_groups.adjudicated.csv   6a21f927…
      PLANTDOC_EXACT_DUPLICATE_ADJUDICATION_PROPOSAL.md b95e27c2…
      plantdoc_exact_duplicate_adjudication_validation.json a6c2db02…
```

The decision-neutrality tests now assert against `original/` — which is the artifact the claim
"the pipeline offered no recommendation" was ever about. The live packet legitimately carries
decisions now, and asserting blankness on it would have meant either a false failure or a quietly
deleted test.

The adjudicated CSV was installed into the packet through the repository's **normal builder**
(`build_plantdoc_duplicate_packet.py`), which preserves recorded decisions, re-derives every
evidence column, and regenerates `packet_manifest.json`. No digest was written by hand. The
builder normalises `current_status` `unresolved → decision_recorded`, so the installed packet CSV
digests `9cc04ebb…` while the reviewer's own file stays byte-preserved at `6a21f927…`.

`scripts/build_human_review_evidence_manifest.py` digests the archive; `--check` is a hard check
in `run_phase1_checks.sh`.

---

## 4. Remediation design

`src/ica26/datasets/duplicate_remediation.py`, applied by
`scripts/apply_plantdoc_duplicate_adjudication.py`.

**Two decisions are implementable, and only these two.**

- `keep_one_record` — retain exactly one canonical member, on the adjudicated split, with the
  adjudicated label; every other member leaves the effective dataset.
- `exclude_all_records` — every member leaves. **No label is assigned**: the point of the decision
  is that no defensible label exists.

Any other terminal decision is a **violation, not a no-op**. `keep_all_records` on a group that
straddles train/test would leave byte-identical pixels on both sides of the split, and the
pipeline will not silently materialise that. It stops instead.

**Canonical member selection is mechanical, because it is not a scientific choice.** The members
are byte-identical; only the split and the label were decisions, and a human made both. The rule,
stated once: prefer a member already on the adjudicated split (so no file need move), then take
the lexicographically smallest active relative path. Order-independent and reproducible.

**Nothing on disk is touched.** No image is moved, deleted, or rewritten, and
`data/manifests/plantdoc_manifest.csv` is unchanged (`548b8151…`, still 2,578 rows). The retained
record's split and label are *overridden* in a derived effective manifest, with both the source
and effective values recorded in the resolution table. Three records therefore sit at a path whose
directory name no longer matches their adjudicated label (G07, G08, G10) — the provenance row is
what carries the truth, not the folder.

### Derived artifacts

| Artifact | Content |
|---|---|
| `data/exclusions/plantdoc_internal_duplicate_resolution.csv` | 24 rows — one per reviewed record: action, source vs effective label/split, both digests, geometry, decision, reason, reviewer, timestamp |
| `data/manifests/plantdoc_effective_manifest.csv` | 2,564 rows — the PlantDoc component of the effective Dataset V1, in the identical 12-column manifest schema |

Both are a pure function of the manifest and the decisions, canonically ordered, with no
wall-clock field.

### Authentication

A decision row is credited only if it reproduces the freshly enumerated group's identity
field-for-field: `group_id`, `display_group_id`, both digests, `member_count`, `crosses_split`,
`crosses_class`, `train_count`, `test_count`, `class_count`, `class_labels`. Because the group id
is itself a digest over every member's path, split and label, a substituted member set cannot keep
its id — the same-row-count substitution that R1-CRIT-001 exploited fails here too (§7).

---

## 5. Per-group outcome — G01…G12

| Group | Canonical content id | Decision | Canonical label | Split | Retained | Excluded |
|---|---|---|---|---|---:|---:|
| G01 | `pdup-f7ce4475e7faab5c` | `keep_one_record` | `Blueberry leaf` | `train` | 1 | 1 |
| G02 | `pdup-b521e39920981129` | `keep_one_record` | `Tomato leaf yellow virus` | `train` | 1 | 1 |
| G03 | `pdup-0e389c7e23bd56b9` | `exclude_all_records` | — | — | **0** | 2 |
| G04 | `pdup-454040445d1210af` | `keep_one_record` | `Corn Gray leaf spot` | `train` | 1 | 1 |
| G05 | `pdup-a4b93bd747ef3454` | `keep_one_record` | `Corn Gray leaf spot` | `train` | 1 | 1 |
| G06 | `pdup-7ec26dad51adee34` | `keep_one_record` | `Tomato Septoria leaf spot` | `train` | 1 | 1 |
| G07 | `pdup-00d12bcd997986d0` | `keep_one_record` | `Potato leaf late blight` | `train` | 1 | 1 |
| G08 | `pdup-884a18bbd9375029` | `keep_one_record` | `Tomato leaf late blight` | `train` | 1 | 1 |
| G09 | `pdup-1de023f9a042587b` | `keep_one_record` | `Potato leaf early blight` | `train` | 1 | 1 |
| G10 | `pdup-e05ca426fe0bf730` | `keep_one_record` | `Tomato leaf bacterial spot` | `train` | 1 | 1 |
| G11 | `pdup-37644c61e7e47362` | `exclude_all_records` | — | — | **0** | 2 |
| G12 | `pdup-eeff73e307da9ed1` | `keep_one_record` | `Corn leaf blight` | `train` | 1 | 1 |
| | | | | **totals** | **10** | **14** |

### Retained canonical records (10)

| Group | Effective record id | Path (unchanged on disk) | Split | Label |
|---|---|---|---|---|
| G01 | `erec-c4a378c93fa9a220` | `train/Blueberry leaf/blueberry-leaves-normal-above-and-iron-deficient-below-bgahf8.jpg` | train → train | Blueberry leaf → Blueberry leaf |
| G02 | `erec-457fa2484df095db` | `train/Tomato leaf yellow virus/tylcv-seminar-1-638.jpg` | train → train | Tomato leaf yellow virus → Tomato leaf yellow virus |
| G04 | `erec-83aba8d282644b2c` | `train/Corn Gray leaf spot/2015070295153021.jpg` | train → train | Corn Gray leaf spot → Corn Gray leaf spot |
| G05 | `erec-aa08c1b448e3f5a6` | `train/Corn Gray leaf spot/corn-gray-leaf-spot-f4.jpg` | train → train | Corn Gray leaf spot → Corn Gray leaf spot |
| G06 | `erec-fb8a05315b0be6d7` | `train/Tomato Septoria leaf spot/early-blight-septoria-ls-fig-3.jpg` | train → train | Tomato Septoria leaf spot → Tomato Septoria leaf spot |
| G07 | `erec-5373969d2572bb1d` | `train/Potato leaf early blight/irish-blight-symptoms-on-potato-leaves-atmf8b.jpg` | train → train | Potato leaf early blight → **Potato leaf late blight** |
| G08 | `erec-7692837fe06b10af` | `train/Potato leaf early blight/5816740026_d42ef24413_Phytophthora-Infestans.jpg` | train → train | Potato leaf early blight → **Tomato leaf late blight** |
| G09 | `erec-dab9202bf4fc65ef` | `train/Potato leaf early blight/1421_0.jpeg?itok=FMtmgePj.jpg` | train → train | Potato leaf early blight → Potato leaf early blight |
| G10 | `erec-80b6c8a97fcda29a` | `train/Tomato Septoria leaf spot/tomato_V8.jpg` | train → train | Tomato Septoria leaf spot → **Tomato leaf bacterial spot** |
| G12 | `erec-b4d4206b9553ddc9` | `train/Corn leaf blight/IMG_42231.jpg` | train → train | Corn leaf blight → Corn leaf blight |

Every one of the ten was already in `train`, so `move_to_train` moved nothing; it fixed which side
the surviving copy sits on. Three carry a relabel (G07, G08, G10), each traced to a written
rationale in the adjudication.

### Excluded records (14)

| Group | Action | Path | Split | Source label |
|---|---|---|---|---|
| G01 | `exclude_duplicate` | `test/Blueberry leaf/blueberry-leaves-normal-above-and-iron-deficient-below-bgahf8.jpg` | test | Blueberry leaf |
| G02 | `exclude_duplicate` | `test/Tomato leaf yellow virus/tylcv-seminar-1-638.jpg` | test | Tomato leaf yellow virus |
| G03 | `exclude_group` | `test/Potato leaf early blight/backus-056-potato-blight.jpg` | test | Potato leaf early blight |
| G03 | `exclude_group` | `train/Potato leaf late blight/backus-056-potato-blight.jpg` | train | Potato leaf late blight |
| G04 | `exclude_duplicate` | `test/Corn leaf blight/2015070295153021.jpg` | test | Corn leaf blight |
| G05 | `exclude_duplicate` | `test/Corn leaf blight/corn-gray-leaf-spot-f4.jpg` | test | Corn leaf blight |
| G06 | `exclude_duplicate` | `test/Tomato Septoria leaf spot/early-blight-septoria-ls-fig-3.jpg` | test | Tomato Septoria leaf spot |
| G07 | `exclude_duplicate` | `test/Potato leaf late blight/irish-blight-symptoms-on-potato-leaves-atmf8b.jpg` | test | Potato leaf late blight |
| G08 | `exclude_duplicate` | `test/Potato leaf late blight/5816740026_d42ef24413_Phytophthora-Infestans.jpg` | test | Potato leaf late blight |
| G09 | `exclude_duplicate` | `test/Potato leaf late blight/1421_0.jpeg?itok=FMtmgePj.jpg` | test | Potato leaf late blight |
| G10 | `exclude_duplicate` | `test/Tomato leaf bacterial spot/tomato_V8.jpg` | test | Tomato leaf bacterial spot |
| G11 | `exclude_group` | `train/Potato leaf early blight/18028_1.jpg` | train | Potato leaf early blight |
| G11 | `exclude_group` | `train/Potato leaf late blight/24064_1.jpg` | train | Potato leaf late blight |
| G12 | `exclude_duplicate` | `test/Corn Gray leaf spot/IMG_42231.jpg` | test | Corn Gray leaf spot |

The files remain on disk; they are excluded from the effective dataset, not deleted.

---

## 6. Before / after

### Records and splits

| | Before | After | Δ |
|---|---:|---:|---:|
| Records | 2,578 | **2,564** | −14 |
| train | 2,342 | 2,339 | −3 |
| test | 236 | 225 | −11 |
| Distinct byte digests | 2,566 | **2,564** | −2 |
| Classes | 28 | **28** | 0 |

### Exact duplicates

| | Before | After |
|---|---:|---:|
| Exact-duplicate groups | 12 | **0** |
| Records in duplicate groups | 24 | **0** |
| Groups crossing train/test | 11 | **0** |
| Groups with contradictory labels | 9 | **0** |
| Byte digests present in both train and test | 11 | **0** |

After remediation `distinct_byte_digests == record_count`, so **no exact duplicate survives
anywhere in PlantDoc** — which subsumes, rather than merely asserts, the train/test claim.

### Classes touched (24 unchanged of 28)

| Class | Before | After | Δ |
|---|---:|---:|---:|
| Blueberry leaf | 117 | 116 | −1 |
| Corn Gray leaf spot | 68 | 67 | −1 |
| Corn leaf blight | 192 | 190 | −2 |
| Potato leaf early blight | 117 | 113 | −4 |
| Potato leaf late blight | 105 | 101 | −4 |
| Tomato Septoria leaf spot | 151 | 149 | −2 |
| Tomato leaf late blight | 111 | **112** | **+1** |
| Tomato leaf yellow virus | 76 | 75 | −1 |

The single increase is G08's relabel. No class was emptied, and no class was invented: the
effective vocabulary is exactly the source vocabulary.

### Proof that nothing else moved

All **2,554** records outside the reviewed identity set are present in the effective manifest and
**byte-identical across all twelve columns** — 0 absent, 0 field drift, 0 additions. This is
checked by field comparison, not by row count, and it is a gate condition, not just a report line.

---

## 7. The completed gate

`reports/plantdoc_internal_duplicate_gate.json`, schema **2.0** (was 1.0).

```
status "pass" · groups 12 · records 24 · resolved 12 · unresolved 0 · violations 0
remediation: evaluated true · ok true · retained 10 · excluded 14
             effective 2564 / source 2578 · surviving_exact_duplicate_groups 0
             surviving_cross_split 0 · surviving_contradictory_label 0
             non_reviewed_records_unchanged true · unique_relpaths true
             unique_effective_identities true
identity_reconciliation: fresh 2564 == persisted 2564 · equal true
             digest 2c258bc766bef7daa9e5af02a5798a000f9dd427d463a014c7b0204a6959d1d6
```

A schema-1.0 gate is **rejected, never reinterpreted** — its `pass` meant only that decisions had
been recorded, so the two statuses are not comparable. `validate_internal_gate()` exists so a
consumer cannot read `status` alone: an unevaluated remediation block is indistinguishable from a
passing one if you do not look.

**No check is skippable.** Called without a manifest, the remediation runs over the groups' own
members rather than being silently omitted. Called without a persisted effective set, the gate
**fails** — "nothing to compare against" means the decisions were not applied.

### It fails closed on

| Condition | Result |
|---|---|
| A group with no decision row | `incomplete` |
| A duplicated decision row | `fail` |
| A decision naming an unknown group | `fail` (twice: unknown row **and** undecided group) |
| An unsupported or non-terminal decision | `fail` |
| A terminal decision with no defined remediation (`keep_all_records`, `exclude_from_evaluation`) | `fail` |
| Missing reason / reviewer / timestamp, or a malformed, naive or future timestamp | `fail` |
| Any drift in a group's evidence columns (either digest, counts, class labels, display id) | `fail` |
| `keep_one_record` with no label, `not_applicable`, or a label outside the vocabulary | `fail` |
| `keep_one_record` with no single destination split | `fail` |
| `exclude_all_records` that nevertheless asserts a label or split | `fail` |
| A reviewed record absent from, or duplicated in, the manifest | `fail` |
| A manifest digest, label, split or geometry that no longer matches the reviewed evidence | `fail` |
| A retained record on the wrong split or with the wrong label | `fail` |
| An excluded record still present | `fail` |
| **Any change to a record outside the reviewed set** | `fail` |
| A group silently dropped from the outcomes | `fail` |
| Any surviving exact duplicate | `fail` |
| **Same row count, forged member identities** | `fail` |
| **Same row count, one effective record substituted** | `fail` |

### The forged-identity exploit, reproduced

Two adversarial cases are pinned as tests, both at *identical row counts*:

1. `test_forged_group_with_the_same_row_count_is_refused` — two real groups, two decision rows,
   one written against a substituted member set. Its content-derived id no longer matches
   anything: the count agrees and the authorization fails twice over.
2. `test_forged_effective_manifest_with_the_same_row_count_is_refused` — a persisted effective set
   of the right size with one record swapped. `fresh_count == persisted_count` and the identity
   digests differ, so it does not reconcile.

Comparing sets of `erec-<16 hex>` identities — a digest over dataset, path, split, label, byte
digest and geometry under an explicitly versioned serialization — is what makes counting
insufficient.

---

## 8. Verification

Every command below was run at the final tree state.

| # | Command | Exit |
|---|---|---:|
| 1 | `python scripts/build_plantdoc_duplicate_packet.py` | 0 |
| 2 | `python scripts/build_plantdoc_duplicate_packet.py --check` | 0 |
| 3 | `python scripts/apply_plantdoc_duplicate_adjudication.py` | 0 |
| 4 | `python scripts/apply_plantdoc_duplicate_adjudication.py --check` | 0 |
| 5 | `python scripts/build_plantdoc_internal_duplicate_gate.py` | 0 |
| 6 | `python scripts/build_plantdoc_internal_duplicate_gate.py --check` | 0 |
| 7 | `python scripts/build_human_review_evidence_manifest.py` | 0 |
| 8 | `python scripts/build_human_review_evidence_manifest.py --check` | 0 |
| 9 | `python scripts/run_phase1_data_completion.py --steps gate --no-download` | 0 |
| 10 | `python -m ica26.portability` | 0 |
| 11 | `python -m pytest -q` | 0 — **430 passed** |
| 12 | `bash scripts/run_phase1_checks.sh` | 2 — all 11 hard checks PASS; BLOCKED on mapping + freeze |

Exit 2 from (12) is the correct outcome: `SCIENTIFIC PHASE-1 STATUS` is `BLOCKED` while the
mapping review is incomplete and Dataset V1 is unfrozen. It is not an R2B failure.

### Clean reconstruction, not just validation

- **Effective dataset** — rebuilt from `data/manifests/plantdoc_manifest.csv` + the decision rows,
  with the duplicate groups re-enumerated from scratch (byte digests re-grouped, decoded-RGB
  digests recomputed from the pixels on disk). Identity-set equal to the persisted file; digests
  identical.
- **Cross-dataset leakage gate (R2A)** — recomputed end to end over 54,305 PlantVillage + 2,578
  PlantDoc images. Result **byte-identical** to the R2A artifact:
  `d5c720192dbe109c22e60ff07f4c23714b83df7302d48bcadb94c78bbcdb1b3c`, `status=pass`, exact 0,
  near 16, resolved 16, unresolved 0, violations 0. Only the non-authoritative run-report
  timestamp changed.
- **Idempotency** — the remediation and gate were executed twice from a clean read of the
  authoritative inputs. All three outputs are byte-identical across runs; no additional exclusion,
  no mutated decision, no changed identity.

### Dataset V1 integrity battery

| Dimension | Result |
|---|---|
| Schema | effective manifest header ≡ source header ≡ `IMAGE_MANIFEST_COLUMNS`; `validate_manifest` 0 errors, 0 warnings |
| Duplicate relpaths | 0 |
| File integrity | all 2,564 records re-hashed from disk — 0 missing, 0 digest mismatches, 0 size mismatches |
| Image integrity | 0 undecodable, 0 flagged `is_corrupt` |
| Split leakage | 0 byte digests in both splits (was 11); 0 relpaths in both splits |
| Label vocabulary | effective ⊆ source (28/28); 0 invented, 0 emptied; all 10 canonical labels in-vocabulary |
| Exclusion provenance | 24 rows / 12 groups; 10 retained all present, 14 excluded all absent; every row carries reviewer + timestamp + reason |
| Non-reviewed records | 2,554 byte-identical; 0 changed; 0 added |
| Checksums | `packet_manifest.json`, `evidence_manifest.json` and all five gate input digests match current files |
| R2A near-review | 16 rows, all `keep`, untouched; 0 overlap with the reviewed records |

---

## 9. Tests

**430 passed** (was 338; +92).

| Suite | Cases | Covers |
|---|---:|---|
| `tests/test_plantdoc_duplicate_remediation.py` *(new)* | **90** | all twelve G01–G12 decisions; `keep_one_record`; `exclude_all_records`; canonical label and split application; the three relabelled groups; contradictory-label groups; train/test duplicate removal; missing / duplicated / unknown / unremediable / unsupported / non-terminal decisions; missing attribution; malformed, naive and future timestamps; evidence drift on 11 columns; hash mismatch; membership change; **same-count forged group**; **same-count forged effective manifest**; silently replaced record; silently dropped group; a record claimed by two groups; changes outside the reviewed set; idempotent second execution; fresh-vs-persisted identity equality; identity primitives |
| `tests/test_plantdoc_duplicates.py` *(updated)* | 41 | enumeration from live data; byte + pixel identity; **decision neutrality of the issued packet**; issued-vs-live group agreement; every live group terminal; packet determinism; gate counts, input binding, byte-identical rebuild; a recorded-but-unapplicable decision does **not** pass |
| `tests/test_leakage_gate.py`, `test_pair_identity_equality.py`, `test_near_duplicate_decisions.py`, `test_review_packet_preservation.py` | 120 | R2A, unchanged and still passing |

Adversarial cases use synthetic fixtures. No test asserts on row counts alone.

Four existing assertions were retargeted rather than deleted, because the state they described
genuinely changed: decision-neutrality now reads the preserved `original/` packet; the gate is
`pass` rather than `incomplete`; its `--check` exits 0; and a terminal-but-unremediable decision is
now expected to fail rather than pass. Each is a tightening, not a relaxation.

---

## 10. Artifact digests

| Artifact | SHA-256 |
|---|---|
| `data/manifests/plantdoc_manifest.csv` *(unchanged)* | `548b815197c51bc26ea6adb2080b93cd670426623ca13d6eee8a43d49fb4ba55` |
| `data/manifests/plantdoc_effective_manifest.csv` | `36ee9ece519d11dd0f38aed53d6177fe19728349025665ebd843b2ab9c4cb3fc` |
| `data/exclusions/plantdoc_internal_duplicate_resolution.csv` | `88976a8846ec1ae37cb318e30d02d57bd9a78bea8fde49e4367bf60f9a90cc6c` |
| `reports/plantdoc_internal_duplicate_gate.json` | `e022c99a40424f1bc12ebcf4339be7a14e038028b88ff4a7b05dc51c2e53f6c8` |
| `reports/leakage_gate.json` *(unchanged, recomputed)* | `d5c720192dbe109c22e60ff07f4c23714b83df7302d48bcadb94c78bbcdb1b3c` |
| packet `plantdoc_exact_duplicate_groups.csv` | `9cc04ebb62b98063c44a81496926ea04dbb32c5ea75b45cc5c30121c1f2f229c` |
| packet `plantdoc_exact_duplicate_members.csv` *(untouched)* | `628cdb029f99eb8fc76a4a568d85e627af620dfa881c9be261f2fca2a31b82ad` |
| packet `packet_manifest.json` | `7f7ad027680c46758391d45f4116b7237f3cd240398e93a099e715b3bdf2462d` |
| `human_review/evidence_manifest.json` | `bff37d8c76b3ebcccb7f028afe57286c30896a6583afcfb80f1cabfb87f4453f` |
| adjudicated groups CSV *(as submitted)* | `6a21f927a58006644713769435e2709725dd36650388a989bddfcb8867f8a7ef` |
| adjudication validation JSON | `a6c2db024145404fb8e9e544e42c2d9fb94449c071619fd3603dd4df2758c906` |
| adjudication proposal MD | `b95e27c20087ff300f61fbb3486fff16ec46f9c1571b3a158edb9c85bfaa910e` |
| issued packet groups CSV *(pre-adjudication)* | `8fb8cc8a2a7064599a4f979d829ac6badb27d7b7e329325214386c1917ec3553` |
| effective-record identity set | `2c258bc766bef7daa9e5af02a5798a000f9dd427d463a014c7b0204a6959d1d6` |

---

## 11. Scientific status

| Dimension | Status |
|---|---|
| Mechanical / data checks | PASS (11/11 hard) |
| Cross-dataset leakage gate | PASS — byte-identical on clean reconstruction |
| Internal PlantDoc duplicate review | **PASS** — 12/12 adjudicated **and applied** |
| Mapping review | **INCOMPLETE** |
| Dataset V1 freeze | **NOT STARTED** |
| **Scientific Phase-1 status** | **BLOCKED** |

### Remaining conditions preventing a Dataset V1 freeze

1. **17 PlantDoc disease→action mapping rows** are still `needs_review`.
2. **PlantVillage action-mapping coverage is 0 / 38 classes.**
3. **AUD-EC-005 / 006 / 007** from the earlier Codex audit are still open.
4. No freeze artifact exists — `data/manifests/dataset_v1_freeze.json` is absent, and no freeze
   procedure, dataset card, or integrity report has been produced or approved.
5. The effective PlantDoc dataset produced here has **not been independently audited**. R2B is the
   remediation; the freeze decision is a separate, explicitly out-of-scope step.

### Explicit statements

- **No training was started.** No model, no checkpoint, no metric, no experiment.
- **Dataset V1 is NOT frozen** and was not declared frozen.
- **Phase 2 is not authorized.**
- **The 16 accepted cross-dataset near-pair decisions are unchanged**, byte-for-byte, and the
  reconstructed R2A gate is byte-identical.
- **No human decision was reinterpreted, replaced, or modified.** No new visual diagnosis was
  made; where a label appears it was read from a decision row.
- **No record outside the 12 reviewed groups was changed** — 2,554 verified byte-identical.
