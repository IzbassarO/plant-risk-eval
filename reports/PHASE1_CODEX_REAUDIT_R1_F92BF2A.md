# Phase-1 Integrity Remediation R1 — Independent Re-audit

**Verdict: BLOCKED**
**Audited remediation commit:** `f92bf2a2da59a49a9ee8da776b908171d6d74b3f`
**Pre-remediation audit commit:** `fb28233f4416ff229439cfb53aa81ae2f2f89942`
**Original audited implementation commit:** `ec482333031e5b1dc596bd1f8f48a39f8b2b8d6d`

This independent, read-only re-audit used temporary directories for every
mutation, regeneration, gate, and fresh-environment output. No production code,
data, mapping, configuration, review record, or scientific artifact was changed.
The validator timestamp written during execution was restored before this report.

## Executive result

R1 materially improves the repository: the six case-collision-lost PlantDoc
records are restored, the legacy integer exclusion override is gone, all gate
inputs are bound, generated gate JSON is deterministic, and the real 16
cross-dataset reviews authenticate. It is nevertheless **not accepted**.

Two critical blockers remain.

1. `compute_gate` compares only the *counts* of freshly detected pairs and the
   supplied pair table. A synthetically forged table with the same count but
   unrelated existing endpoints, plus a matching exclusion record, produced a
   `pass` for a true exact duplicate. This defeats the claimed record-derived
   exact authorization and applies structurally to near pairs too.
2. The restored PlantDoc V1 contains 12 byte-exact duplicate-SHA groups (24
   records). Eleven cross train/test and nine assign identical pixels to
   different diagnosis labels. These are direct split leakage and unresolved
   label conflicts. The Phase-1 script does not examine them and still prints
   `OVERALL: PASS`.

| Targeted finding | Result | Basis |
|---|---|---|
| AUD-EC-001 near-review authentication | **PARTIAL / not closed** | Full endpoint fields are checked, but any unique arbitrary `pair_id` and a malformed nonblank timestamp authenticate. |
| AUD-EC-002 exact authorization | **PARTIAL / not closed** | The unbound integer is removed, but a same-count forged authoritative-pair table can still authorize an unrelated exclusion. |
| AUD-EC-003 PlantDoc restoration | **PASS** | 2,578 source records map exactly to 2,578 active records; all six lost records are restored from the pinned archive. |
| AUD-EC-004 packet preservation | **PARTIAL / not closed** | Real no-op regeneration preserves all decisions byte-for-byte, but relative-path identity drift is not raised as an error. |
| AUD-EC-008 input binding/determinism | **PASS** | All six file inputs plus configuration/schema are bound and stale after one-byte mutation; deterministic gate bytes were reproduced. |
| AUD-EC-009 generated CSV LF | **PASS** | The named generated CSVs are LF-only. Remaining `git diff --check` output is historical Markdown trailing whitespace, not CRLF CSV output. |

## A. Git and audit-chain integrity

At audit start, `HEAD` and `origin/main` both resolved to
`f92bf2a2da59a49a9ee8da776b908171d6d74b3f`; the worktree was clean. The parent
is `fb28233f4416ff229439cfb53aa81ae2f2f89942`, whose parent is
`ec482333031e5b1dc596bd1f8f48a39f8b2b8d6d`.

The committed original audit is verbatim: both
`git show fb28233:reports/PHASE1_CODEX_AUDIT_EC482333.md` and the checked-out
file have SHA-256
`a2a4e31628e168398f953c6d7865b638aa4a551d96fd3fbb2eb6ea227050d306`.
Git history permits that blob-to-working-file comparison; it cannot establish a
separate pre-Git local copy that is no longer present.

The complete `ec482333..f92bf2a` name-status inventory has 33 paths, no
deletions:

```text
M data/indexes/phash_index_meta.json
M data/indexes/phash_index_plantdoc.csv
M data/interim/phase1_review_validation.csv
M data/interim/phase1_review_validation_summary.json
A data/manifests/plantdoc_case_collision_mapping.csv
M data/manifests/plantdoc_manifest.csv
M data/manifests/plantdoc_source_inventory.csv
M data/manifests/plantdoc_source_snapshot.json
M data/manifests/plantdoc_summary.json
M data/mapping/plantvillage_class_list.csv
A reports/NEAR_DUPLICATE_REVIEW_CHANGES.md
A reports/PHASE1_CODEX_AUDIT_EC482333.md
A reports/PHASE1_INTEGRITY_REMEDIATION_R1.md
A reports/PLANTDOC_CASE_COLLISION_POLICY.md
M reports/PLANTDOC_CASE_COLLISION_REVIEW.md
M reports/PLANTDOC_COUNT_RECONCILIATION.md
M reports/leakage_gate.json
M reports/leakage_gate_guard_test.json
A reports/leakage_gate_run.json
M reports/leakage_plantvillage_vs_plantdoc_summary.json
M scripts/prepare_human_review.py
A scripts/restore_plantdoc_collisions.py
M scripts/run_phase1_data_completion.py
M scripts/run_phase1_local.py
M scripts/validate_phase1_review.py
M src/ica26/datasets/plantdoc.py
M src/ica26/evaluation/cross_dataset.py
M src/ica26/leakage/gate.py
M tests/test_cross_dataset.py
M tests/test_leakage_gate.py
M tests/test_near_duplicate_decisions.py
A tests/test_plantdoc_collisions.py
A tests/test_review_packet_preservation.py
```

No raw image tree, archive, virtual environment, cache, model/checkpoint, or
personal/secret path is introduced by this diff. The 17 pending PlantDoc disease
mapping rows are not in the diff, and no PlantVillage action mappings were
fabricated. `plantvillage_class_list.csv` changed only CRLF to LF; its 38 data
rows and values are unchanged.

## B. AUD-EC-001 — near-review authorization

`PairIdentity` comprises training dataset, relative path, class, manifest SHA-256;
evaluation dataset, relative path, class, manifest SHA-256; pHash distance; and
classification. `pair_id` is not part of that identity. The implementation
checks the nine review-visible endpoint/distance fields at
`src/ica26/leakage/gate.py:220-232`, requires unique IDs and path-pairs at
`:260-293`, and verifies review/exclusion bijection at `:316-362`.

The production 16-row review is valid: 16 resolved, 16 kept, zero excluded,
zero unresolved, and zero violations. The following temporary mutations were
made against those real records. “Reject” means authorization was not OK, so a
gate cannot pass.

| Mutation | Observed authorization | Result |
|---|---|---|
| Baseline | OK; 16 resolved, 0 unresolved, 0 violations | PASS |
| Duplicate `pair_id` | reject; 15 resolved, 1 unresolved, 2 violations | PASS |
| Duplicate full identity with a new ID | reject; 16 resolved, 1 violation | PASS |
| Unique arbitrary `pair_id` | **OK; 16 resolved, 0 violations** | **FAIL** |
| Surplus unmatched review | reject; 16 resolved, 1 violation | PASS |
| Missing/remove one authoritative row | reject; 15 resolved, 1 unresolved, 1 violation | PASS |
| Change any dataset, class, SHA-256, or pHash distance | reject; 15 resolved, 1 unresolved | PASS |
| Change either relative path | reject; 15 resolved, 1 unresolved, 2 violations | PASS |
| Unsupported decision or disposition | reject; 15 resolved, 1 unresolved | PASS |
| Blank reviewer | reject; 15 resolved, 1 unresolved | PASS |
| `reviewed_at=tomorrow` | **OK; 16 resolved, 0 violations** | **FAIL** |
| Blank `reviewed_at` or decision reason | reject; 15 resolved, 1 unresolved | PASS |
| Human exclude without propagated row | reject; 15 resolved, 1 unresolved | PASS |
| Matching exclusion propagated exactly once | OK; 16 resolved | PASS |
| Duplicate propagated exclusion | reject; 15 resolved, 1 unresolved | PASS |
| Propagated exclusion without human exclude | reject; 16 resolved, 1 violation | PASS |
| Unknown reviewed exclusion | reject; 16 resolved, 1 violation | PASS |

Individually, changed training dataset, training class, training SHA,
evaluation dataset, evaluation class, evaluation SHA, and pHash distance each
gave 15 resolved, 1 unresolved, 1 violation. Changed training or evaluation
relative path each gave 15 resolved, 1 unresolved, 2 violations. Thus the
combined rows in the table do not conceal a field that was left untested.

Thus invalid endpoint identity and surplus/missing rows no longer inflate the
resolved count. However, the stated requirement was that an unknown pair ID and
malformed timestamp fail. The code merely requires a nonblank timestamp
(`:310-314`) and does not bind an ID to an independently derived authority.
AUD-EC-001 is therefore not closed.

## C. AUD-EC-002 — exact exclusions

The legacy `excluded_pair_count` / `excluded_pairs` parameters are absent from
the `compute_gate` signature. In a temporary dataset with one true exact pair:

| Case | Status | Exact detected/excluded | Unresolved | Violations |
|---|---|---:|---:|---:|
| No exclusion record | fail | 1 / 0 | 1 | 1 |
| One matching record | pass | 1 / 1 | 0 | 0 |
| Duplicate record | fail | 1 / 1 | 0 | 1 |
| Unknown record | fail | 1 / 0 | 1 | 2 |
| Mutated class in matching-path record | fail | 1 / 1 | 0 | 1 |
| No detected pair and no record | pass | 0 / 0 | 0 | 0 |

Attempts to supply the old integer values 1 and 999 are impossible: neither
argument exists. This closes the original arithmetic exploit. Missing, duplicate,
unknown, and mutated records are violations in
`authenticate_exact_exclusions` (`src/ica26/leakage/gate.py:384-437`), so
`max(0, ...)` at `:597` cannot hide an over-count without a violation.

However, exact authorization still trusts a supplied *pair table* whose
membership is not verified against fresh detection. The only reconciliation is
its near/exact count at `src/ica26/leakage/gate.py:582-591`.

I created four synthetic images. `train/c/one.png` and `test/c/one.png` were
the one true exact pair. The table instead declared unrelated existing endpoints
`train/c/other.png -> test/c/other.png` as one exact pair with distance zero,
and the exclusion record named that forged pair. Production `compute_gate`
returned:

```text
actual exact=1; table=other -> other; excluded=1; unresolved=0;
authorization violations=[]; status=pass
```

The pair table also supplies class strings without comparison to a manifest
class field, and exact-exclusion CSV rows contain no endpoint SHA columns to
compare. Input digests detect later mutation, but do not prove the table was
correct when the gate was generated. Therefore the integer exploit is closed,
but required record-derived exact authorization is not; AUD-EC-002 remains open
in substance.

## AUD-EC-009 — generated CSV line endings

`data/interim/phase1_review_validation.csv`,
`data/mapping/plantvillage_class_list.csv`, and the current review/exclusion
CSVs are LF-only and terminate with LF. `git diff --check ec48233..f92bf2a`
reports only pre-existing Markdown trailing whitespace in the copied historical
Codex audit, not a generated CSV CRLF warning. AUD-EC-009 is closed.

## D. AUD-EC-008 — binding and deterministic artifacts

`GateInputs` binds the two manifests, the single combined pair-table CSV,
near-review CSV, reviewed-near-exclusions CSV, and exact-exclusions CSV
(`src/ica26/leakage/gate.py:443-478`). The table has logical exact and near
subsets, not two separate files; its one digest covers both. The configuration
digest includes threshold, pHash algorithm, training/evaluation dataset names,
and schema version. `validate_gate` rejects an unsupported schema directly and
redigests every named input (`:646-692`).

In a valid temporary gate, a one-byte mutation of each item below gave
`valid=False` with one stale-input error; changing the gate threshold likewise
gave one configuration-digest error:

```text
training_manifest, evaluation_manifest, pair_table, near_review,
reviewed_exclusions, exact_exclusions, leakage_config_threshold
```

Two independent complete CLI builds over the real 54,305 PlantVillage and
2,578 PlantDoc files were byte-identical with SHA-256
`b275a33546abc904c78e7bf1dbc73ecbae3d384d666c33b6a99a28fb72abdf9f`.
The authoritative JSON has no wall-clock field. Its separate run report has a
timestamp but is not read by `require_valid_gate`.

The R1-reported SHA is also reproducible, but only with its recorded provenance
(`command=run_phase1_data_completion.py:gate`, `training_config=color`): a full
fresh build produced an artifact byte-identical to the committed gate and SHA-256
`ce78e3b83e2521024e961813eeff34dd17c8a9671d93c29b159ebc96301f3437`.
The CLI’s different, deterministic provenance explains `b275…`; it is not
timestamp nondeterminism. AUD-EC-008 is closed.

## E. AUD-EC-004 — review regeneration

An end-to-end regeneration in an isolated copy of the current inputs produced:

```text
pairs=16, csv_rows=16, preserved=16, new=0, dropped=0, drift=0,
review_bytes_unchanged=True, exclusions_bytes_unchanged=True, sheets=4
```

Reasons, reviewer IDs, timestamps, and final dispositions were therefore
byte-equivalent. The review and reviewed-exclusion CSV writers use `.part` plus
`os.replace` (`scripts/prepare_human_review.py:396-405`), and reset is explicit
(`:417-429`). Unit tests also cover added undecided pairs, reported removed
pairs, reviewed-exclusion preservation, and explicit reset.

Independent merge checks observed a genuinely new authoritative pair as blank
and assigned a new high-water ID; a removed decided pair was included in the
change report with its prior decision; and `reset=True` was required to clear a
decision. Normal regeneration used `reset=False`. CSV replacement is atomic, so
an interrupted CSV write cannot replace the old valid CSV with its `.part` file.

Identity testing found an important residual. Changing dataset, class, SHA, or
distance on a decided row raises `HumanDecisionDrift`. Changing either relative
path does **not** raise: `_identity_key` is only the two paths (`:408-410`), so
the old decided record is reported as dropped and the changed record becomes a
new blank decision (`:443-481`). It does not inherit the old decision, which is
safe from silent reuse, but it contradicts the documented promise to fail closed
on any identity drift. Markdown/contact-sheet writes are also direct writes,
rather than atomic replacement. AUD-EC-004 is only partially closed.

## F. PlantDoc restoration and source-record integrity

The pinned archive is
`data/raw/plantdoc/_archive/plantdoc-5467f6012d78.tar.gz`, matching source
revision `5467f6012d78d1c446145d5f582da6096f852ae8`. Independent archive,
inventory, active-file, manifest, and decoded-pixel checks found:

| Check | Result |
|---|---|
| Source inventory / active manifest | 2,578 / 2,578 |
| Train / test | 2,342 / 236 |
| Expected source-record paths versus active paths | exact 2,578-path bijection |
| Inventory-to-manifest SHA, size, dimensions, mode, split, class | 0 mismatches |
| Materialized bytes/SHA versus active manifest | 0 errors |
| Collision mapping / archive SHA | 12 members, 0 errors |
| Collision decoded-RGB digest | 12 members, 0 errors |
| Active Unicode-NFC/casefold path collisions | 0 |
| Corrupt / zero-byte active records | 0 / 0 |

The six originally missing records were each read from the archive and verified
at their collision-safe active path:

| Archive path | Active path | SHA-256 | Bytes | Dimensions | Class / split | Pixels |
|---|---|---|---:|---:|---|---|
| `train/Apple rust leaf/CAR1.jpg` | `train/Apple rust leaf/CAR1__ff8e845061e3.jpg` | `ff8e845061e3a305e55ae0b60218008bafa88e392bfb5f36e0e9f58f379526dc` | 249,767 | 498x841 | Apple rust leaf / train | readable, digest matches |
| `train/Blueberry leaf/blueberry-leaf.jpg` | `train/Blueberry leaf/blueberry-leaf__a488765c32aa.jpg` | `a488765c32aa6a0b5e971e4086f1985e11451c30f9cd95f5edc28918f5cbf753` | 1,234,441 | 1422x2000 | Blueberry leaf / train | readable, digest matches |
| `train/Blueberry leaf/blueberry-leaves.jpg` | `train/Blueberry leaf/blueberry-leaves__2e99aae9cb26.jpg` | `2e99aae9cb2602280f7ef9c52bb13913620e6a1e2381d9f7385db7fe4d31b0ba` | 24,227 | 450x338 | Blueberry leaf / train | readable, digest matches |
| `train/Corn leaf blight/northern-corn-leaf-blight.jpg` | `train/Corn leaf blight/northern-corn-leaf-blight__2c2cc7cec2c4.jpg` | `2c2cc7cec2c4cc95a28f7bdd46b7e3adb9a194b528aa95af28f979da6b732dac` | 59,950 | 750x350 | Corn leaf blight / train | readable, digest matches |
| `train/Peach leaf/peach-leaf.jpg` | `train/Peach leaf/peach-leaf__0571261a682b.jpg` | `0571261a682b6174b2f9ee041e4cf9bfbfb5b6f9e6b045c367e05fa900fadf45` | 148,756 | 2136x1424 | Peach leaf / train | readable, digest matches |
| `train/Potato leaf early blight/potato-blight-phytophora-infestans-close-up-of-infected-leaf-showing-a60hxn.jpg` | `train/Potato leaf early blight/potato-blight-phytophora-infestans-close-up-of-infected-leaf-showing-a60hxn__0ea1317f5e20.jpg` | `0ea1317f5e200ddec3cfadee3b1815620f2a49506c1838a23f69555f5d7d7d1b` | 113,078 | 640x447 | Potato leaf early blight / train | readable, digest matches |

“Bijection” needs three distinct meanings here. Source-record identity is the
unique upstream path plus source metadata; under the documented collision policy
it maps one-to-one to 2,578 active path identities. SHA/content identity is not
one-to-one: it has 2,566 distinct values because 12 SHA values each occur twice.
Thus SHA *multiset* equality is necessary but not alone a source-record
bijection; the intended-path, metadata, and archive checks above establish the
latter. No class or split label changed during collision restoration.

Two independent in-memory manifest rebuilds each produced 2,578 rows with the
same active collision-safe paths and core image metadata as the committed
manifest. `collision_safe_relpath` is a pure original-path plus SHA-prefix
function (`src/ica26/datasets/plantdoc.py:223-238`); no restored file is corrupt
or zero-byte.

AUD-EC-003 is closed.

## G. Fresh cross-dataset leakage recomputation

A full fresh source computation hashed 54,305 PlantVillage and 2,578 PlantDoc
images with `imagehash.phash`, 64 bits, Hamming threshold 6. It took 76.582
seconds and returned:

```text
exact=0, exact excluded=0, near=16, near resolved=16,
near kept=16, near excluded=0, unresolved=0, violations=[], status=pass
```

I also compared the full freshly detected identity set, not only its count, with
`reports/leakage_plantvillage_vs_plantdoc_pairs.csv`:

```text
fresh=16; table=16; equal=True; fresh_only=0; table_only=0;
restored-PlantDoc participants=0
```

The committed cross-dataset table is currently correct after restoration; none
of the six restored files occurs in it. This does not remove the count-only
forged-table vulnerability in section C.

The indexed pHash implementation matches its brute-force reference in the fresh
suite for intra/cross random cases and several thresholds, and the full real
scan completed without skipped files. It streams images one at a time. Its
module documentation still calls the search a BK-tree although the active
implementation is the complete banded multi-index at
`src/ica26/leakage/phash.py:248-274`; this is documentation drift, not evidence
of a missed pair. pHash is not a substitute for the exact-SHA within-PlantDoc
audit below.

## H. New exact-duplicate audit inside PlantDoc

All active records were grouped by SHA-256 and decoded to RGB. There are **12
duplicate-SHA groups**, **24 records**, and every group has two byte-identical
members with the same decoded-pixel SHA. In the table, every `active <- archive`
record has its split/class, byte count, and dimensions stated. “Contradictory”
means the manifest assigns different diagnosis labels; this audit does not
adjudicate biological truth.

Every `same` in the table is a verified equality:
`original_archive_path == active relative path shown`. These duplicate groups do
not use collision-safe renamed paths, so each displayed full active path is also
the full original archive path.

| Group | Content SHA-256 / decoded RGB SHA-256 | Records | Assessment |
|---|---|---|---|
| G01 | `07b9b0a3395d6643e0033f5327c188305479c20a67b9e0081efec85139d63306` / `838b864a6ecd8bcef3f37360774f1f3dfb4bf105e33b7dcee7ba9ec746704fc0` | `test/Blueberry leaf/blueberry-leaves-normal-above-and-iron-deficient-below-bgahf8.jpg` <- same; test/Blueberry leaf; 59,840 B; 390x540. `train/Blueberry leaf/blueberry-leaves-normal-above-and-iron-deficient-below-bgahf8.jpg` <- same; train/Blueberry leaf; 59,840 B; 390x540. | byte/pixel exact; compatible class; direct train/test leakage |
| G02 | `3c52144e19e95cc3d4170407eaf729d0981b934615eaa183f7f5aa29d8ef265a` / `3833455ba9dde5f8b75769c4ff68ec49b38412739185318e70fc41202dca3e0a` | `test/Tomato leaf yellow virus/tylcv-seminar-1-638.jpg` <- same; test/Tomato leaf yellow virus; 69,933 B; 638x479. `train/Tomato leaf yellow virus/tylcv-seminar-1-638.jpg` <- same; train/Tomato leaf yellow virus; 69,933 B; 638x479. | byte/pixel exact; compatible class; direct train/test leakage |
| G03 | `64c0f7b5701e815769bad881c0834ffb3b58018233fc3af42c3a1b7968f86973` / `79e02b28f24cb1dee9cb9deaf4e934bceada9eaf546b081e8b90fc46ddd7156c` | `test/Potato leaf early blight/backus-056-potato-blight.jpg` <- same; test/early; 1,477,148 B; 2848x2136. `train/Potato leaf late blight/backus-056-potato-blight.jpg` <- same; train/late; 1,477,148 B; 2848x2136. | byte/pixel exact; cross-split contradictory labels |
| G04 | `6e777d1b6829140e66573f918c0f1681ca4cd2979859c37435c84977153ec223` / `bb6cddbe3c7246574630162c846df2b91b820a8ca9a1179e20d375e0d92dd8bd` | `test/Corn leaf blight/2015070295153021.jpg` <- same; test/blight; 225,240 B; 1224x1632. `train/Corn Gray leaf spot/2015070295153021.jpg` <- same; train/Gray spot; 225,240 B; 1224x1632. | byte/pixel exact; cross-split contradictory labels |
| G05 | `9120578a76fd8539da220def6e0609ebb2435decc7a9c34b949e46e86e794c8d` / `a385b6ed71a3a24cb23c7ca79038058b6f26733c17046c64be7b5af84cecef29` | `test/Corn leaf blight/corn-gray-leaf-spot-f4.jpg` <- same; test/blight; 652,989 B; 672x832. `train/Corn Gray leaf spot/corn-gray-leaf-spot-f4.jpg` <- same; train/Gray spot; 652,989 B; 672x832. | byte/pixel exact; cross-split contradictory labels |
| G06 | `93c989d8551209bf34d4002ee9fae48ddbf6ab66fc3c27466c0473bcc7c0a2b7` / `0c4bd829bc90e5bc0d69128ebf78553584f7ed296867e284faad28ad365020c2` | `test/Tomato Septoria leaf spot/early-blight-septoria-ls-fig-3.jpg` <- same; test/Septoria; 1,178,259 B; 1500x1125. `train/Tomato Septoria leaf spot/early-blight-septoria-ls-fig-3.jpg` <- same; train/Septoria; 1,178,259 B; 1500x1125. | byte/pixel exact; compatible class; direct train/test leakage |
| G07 | `9dd93b4217495fbb725cfdded86d3dc5f98955c9616fff5323be1a00df17be8b` / `6698fb65e7508618830d0e4518364e198e72e109fa12135d10472af6e9854be1` | `test/Potato leaf late blight/irish-blight-symptoms-on-potato-leaves-atmf8b.jpg` <- same; test/late; 56,066 B; 640x437. `train/Potato leaf early blight/irish-blight-symptoms-on-potato-leaves-atmf8b.jpg` <- same; train/early; 56,066 B; 640x437. | byte/pixel exact; cross-split contradictory labels |
| G08 | `a981ee59e5e1dcafd0d225f74369a05969200352c17743318c31987083ab6f4c` / `2b49ec06043cd087d410e5d32235b75895135385c6c4e6a02210d291f08d6e63` | `test/Potato leaf late blight/5816740026_d42ef24413_Phytophthora-Infestans.jpg` <- same; test/late; 98,347 B; 333x500. `train/Potato leaf early blight/5816740026_d42ef24413_Phytophthora-Infestans.jpg` <- same; train/early; 98,347 B; 333x500. | byte/pixel exact; cross-split contradictory labels |
| G09 | `c53ad8d40c38debfbc0b79a87d0f3649c20b933a65f5b78a6931f59d06aad498` / `ce2ea9ee7939fd30c74c2c71719255696ec9ff80523d0c90313594d84dd2b1cf` | `test/Potato leaf late blight/1421_0.jpeg?itok=FMtmgePj.jpg` <- same; test/late; 59,758 B; 640x480. `train/Potato leaf early blight/1421_0.jpeg?itok=FMtmgePj.jpg` <- same; train/early; 59,758 B; 640x480. | byte/pixel exact; cross-split contradictory labels |
| G10 | `e23a29c94b58aac28e92f57f95eb6f53e99c874323cb2b90ebd327085721574e` / `2c6e36b745ce86fb2bb03b2ab1ecf7ba02df95238c285d006ccb8a24f97bb683` | `test/Tomato leaf bacterial spot/tomato_V8.jpg` <- same; test/bacterial; 14,032 B; 350x260. `train/Tomato Septoria leaf spot/tomato_V8.jpg` <- same; train/Septoria; 14,032 B; 350x260. | byte/pixel exact; cross-split contradictory labels |
| G11 | `e5f14a70fc7a687a5846749d5499872c7c3320e81aea1358e481f7100b7ba242` / `455f28f2b68fc6b43f18c783c662ffca5860ed6109a9ab06d5caf1511ef5e433` | `train/Potato leaf early blight/18028_1.jpg` <- same; train/early; 216,600 B; 832x624. `train/Potato leaf late blight/24064_1.jpg` <- same; train/late; 216,600 B; 832x624. | byte/pixel exact; same-split contradictory labels |
| G12 | `ee3838e2249e671b7b4510b0d3831f30882e2bcbf20c9c8c42ee8f4e1b95fcce` / `a0747f2b4f42924a64b4d33e7c822dd95b1fffda37fb7164cb1bc4e6ff8a69fa` | `test/Corn Gray leaf spot/IMG_42231.jpg` <- same; test/Gray spot; 1,577,792 B; 3264x2448. `train/Corn leaf blight/IMG_42231.jpg` <- same; train/blight; 1,577,792 B; 3264x2448. | byte/pixel exact; cross-split contradictory labels |

| Aggregate category | Groups | Records |
|---|---:|---:|
| Same class, same split | 0 | 0 |
| Same class, cross split | 3 | 6 |
| Cross class, same split | 1 | 2 |
| Cross class, cross split | 8 | 16 |
| Exact train/test overlaps | 11 | 22 |
| Conflicting-label exact duplicates | 9 | 18 |

The class-name conflict specifically includes Corn leaf blight versus Corn Gray
leaf spot (G04, G05, G12), as well as early/late potato and tomato
Septoria/bacterial conflicts. The required handling classification is **both
group-aware split and label adjudication required**.

This blocks Dataset V1 freeze, PlantDoc diagnosis metrics, and any
cross-dataset/action/risk metric that relies on the contaminated PlantDoc
evaluation population. It does not block read-only scientific-source verification
for the 17 mappings. A new compact human-review packet is required: one
group-summary row and two immutable member rows per group (12 summaries, 24
member rows) with group ID, content SHA, decoded-RGB SHA, archive and active
paths, split, class, byte size, dimensions, cross-split/class flags, reviewer,
timestamp, group-handling decision, canonical-label decision, and rationale.
No such decision or packet was created in this audit.

## I. Fresh reproduction and test quality

Fresh environment:

```text
path: /private/tmp/ica26-r1audit.2Zm7AM (removed after audit)
Python: 3.13.9
install: /private/tmp/ica26-r1audit.2Zm7AM/bin/python -m pip install -e .
test dependency: pytest>=8,<9 (declared pyproject dev extra)
```

Resolved relevant versions were ica26 0.1.0 (editable), numpy 2.5.1, pandas
3.0.5, Pillow 11.3.0, ImageHash 4.3.2, PyYAML 6.0.3, requests 2.34.2,
SciPy 1.18.0, PyWavelets 1.9.0, and pytest 8.4.2. The initial dependency fetch
was sandbox-DNS blocked; the approved retry succeeded.

| Fresh command/check | Exit/result |
|---|---|
| `python -m pytest -q -o addopts=''` | `272 passed in 2.65s` |
| `python scripts/validate_phase1_review.py` | exit 1; 48 findings, 19 blockers (17 PlantDoc disease rows, checklist, 0/38 PlantVillage mapping coverage) |
| `PYTHON=fresh ./scripts/run_phase1_checks.sh` | exit 0; 9/9 hard checks, `OVERALL: PASS` |
| `ica26-validate-mapping data/mapping/action_mapping_template.csv` | 0 errors, 28 `needs_review` template rows |
| `python scripts/apply_action_mapping_review.py --check` | current; emits 10 healthy monitor rows, zero disease rows |
| `ica26-portability` | passed |
| Full leakage discovery/gate twice | cross results in section G; deterministic artifacts in section D |
| Gate validation of independently rebuilt `ce78…` gate | `pass`, schema 2.0, near 16/resolved 16 |
| Packet-preservation end-to-end test | 16 preserved, byte-identical review/exclusion files |
| Archive/inventory/filesystem integrity checks | all results in section F |
| `git diff --check ec48233..f92bf2a` | only existing trailing whitespace in the added historical audit Markdown |

The test suite is strong for most R1 mutations but insufficient for the two
observed residual paths: it has no test that a unique arbitrary review ID is
bound to an authoritative ID or that timestamps parse as ISO-8601, no test that
fresh pair identities equal the pair-table identities rather than their counts,
and no real-data within-PlantDoc SHA duplicate gate.

## J. Status and claim consistency

`run_phase1_checks.sh` labels a result PASS if datasets are marked complete,
PlantVillage pixels are present, and the saved cross-dataset gate says pass
(`scripts/run_phase1_checks.sh:79-119`). It does not check the review validator,
mapping coverage, Dataset V1 freeze, or intra-PlantDoc exact duplicates. Its
current PASS must not be read as scientific Phase-1 acceptance.

The real closeout state remains: 17 PlantDoc disease mappings are unreviewed;
PlantVillage action-mapping coverage is 0/38; Dataset V1 is unfrozen; no valid
metrics or trained model exist. README is explicitly BLOCKED but stale on data
counts and gate/review state (`README.md:15-35`). PROJECT_BRIEF is a valuable
governing research specification but its current-state narrative still says
PlantDoc 2,598, describes a truncated tree, and calls mapping work not started
(`PROJECT_BRIEF.md:161-166,265-305,432-449`).

## Findings ordered by severity

### Critical

**R1-CRIT-001 — Fresh detection is reconciled to the pair table by count only.**
**Evidence:** synthetic true `one -> one` exact pair with forged `other -> other`
table/exclusion passed; `src/ica26/leakage/gate.py:575-594`.
**Impact:** a passing gate is not proof that exclusions/reviews correspond to
the freshly detected pair identities.
**Correction:** derive canonical pair records directly from fresh result rows,
including endpoint content SHA; serialize a canonical deterministic pair ID; and
require exact identity-set equality before authorizing either subset.
**Blocks:** gate trust, all metrics, V1 freeze, and Phase 2.

**R1-CRIT-002 — PlantDoc has 11 direct train/test exact overlaps and nine
cross-class label conflicts.**
**Evidence:** section H full SHA/archive/pixel enumeration.
**Impact:** held-out accuracy can memorize training pixels; contradictory labels
make diagnosis/action inferences scientifically invalid.
**Correction:** create the specified compact packet, then make a documented
group-aware split and label-adjudication decision, regenerate provenance and
dependent artifacts, and re-audit.
**Blocks:** V1 freeze and metrics.

### High

**R1-HIGH-001 — Near-review pair IDs and timestamps are not authenticated as
claimed.**
**Evidence:** arbitrary unique ID and `tomorrow` timestamp passed; section B and
`src/ica26/leakage/gate.py:260-314`.
**Correction:** persist an ID derived from full immutable canonical identity and
validate strict timestamp syntax/timezone.
**Blocks:** robust review provenance and gate trust.

**R1-HIGH-002 — Path drift in packet regeneration does not raise.**
**Evidence:** both relative-path changes become dropped+new rather than
`HumanDecisionDrift`; `scripts/prepare_human_review.py:408-492`.
**Correction:** recognize every decided-record drift, halt before writes, and
make all emitted artifacts atomic.
**Blocks:** reproducible closeout.

### Medium

**R1-MED-001 — The Phase-1 check-script PASS is materially overbroad.**
**Evidence:** it passed despite 19 review blockers and the new direct PlantDoc
leakage; `scripts/run_phase1_checks.sh:79-119`.
**Correction:** distinguish data/mechanical checks from scientific acceptance
and explicitly incorporate review, mapping, V1, and internal-duplicate status.
**Blocks:** release/freeze claims.

### Low / informational

**R1-LOW-001 — pHash module narrative says BK-tree while active search uses
banded multi-index.** Update the description; parity and full runtime evidence
show no current correctness failure.

**R1-INFO-001 — `validate_phase1_review.py` writes a timestamped summary during
validation.** Its output was restored here; a `--check` or output-directory mode
would avoid this audit side effect.

## Explicit answers and exact next step

- **Is AUD-EC-001 closed?** No; partial only.
- **Is AUD-EC-002 closed?** No; the integer is removed but pair-table
  substitution leaves authorization unsafe.
- **Is AUD-EC-003 closed?** Yes.
- **Is AUD-EC-004 closed?** No; partial only.
- **Is AUD-EC-008 closed?** Yes.
- **Is R1 accepted?** No — **BLOCKED**.
- **Is it safe to begin R2?** Not as a progression or approval step. A narrowly
  scoped R2 remediation is required first for the two critical findings.
- **Is read-only scientific source verification of the 17 mappings safe?** Yes,
  if rows remain unapproved and no metrics or mapping decisions are made.
- **Is Dataset V1 safe to freeze?** No.
- **Is Phase 2 authorized?** No.
- **Is a new exact-duplicate human-review packet required?** Yes.

**Recommended next step:** write and approve a narrowly scoped R2 plan that
first makes fresh pair identity-set equality, not count equality, a fail-closed
gate invariant, then produces the 12-group/24-member PlantDoc duplicate review
packet. Do not freeze V1, train, compute metrics, or approve mappings until the
resulting decisions and regenerated artifacts receive a fresh independent audit.
