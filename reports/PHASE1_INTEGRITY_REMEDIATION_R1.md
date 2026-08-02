# Phase-1 Integrity Remediation — Round 1

**Audited commit:** `ec482333031e5b1dc596bd1f8f48a39f8b2b8d6d`
**Audit report:** `reports/PHASE1_CODEX_AUDIT_EC482333.md` (committed unmodified in `fb28233`)
**Scope:** AUD-EC-001, AUD-EC-002, AUD-EC-003, AUD-EC-004, AUD-EC-008 (+ AUD-EC-009)

_No mapping was approved, no dataset was frozen, no metric was computed, and no model was
trained._

---

## 1. Findings addressed

| ID | Severity | Finding | Status |
|---|---|---|---|
| AUD-EC-001 | Critical | Gate accepts unauthenticated review mutations | **Fixed** |
| AUD-EC-002 | Critical | Exact exclusion forced by an unbound integer | **Fixed** |
| AUD-EC-003 | Critical | Six distinct PlantDoc images absent from active V1 | **Fixed** |
| AUD-EC-004 | High | Packet regeneration destroys human review | **Fixed** |
| AUD-EC-008 | Medium | Gate not input-bound, not byte-deterministic | **Fixed** |
| AUD-EC-009 | Low | Generated CSVs written CRLF | **Fixed** |

Deliberately **not** addressed (out of scope for this round): AUD-EC-005 (scope absent from the
production evaluation entry point), AUD-EC-006 (healthy policy accepts malformed tokens and
invalid dates), AUD-EC-007 (README/PROJECT_BRIEF contradict live artifacts), AUD-EC-010.

---

## 2. AUD-EC-003 — PlantDoc restored to 2,578 distinct images

The upstream tree is case-sensitive; the extraction filesystem is not. Six casefold groups
collapsed 12 upstream records to 6 files, and the manifest — built by scanning that tree — could
not see what was never written.

Policy: **`reports/PLANTDOC_CASE_COLLISION_POLICY.md`** (`policy:plantdoc-casefold-safe-v1`).
Every member of a colliding group now gets a content-disambiguated active path
`<stem>__<sha12><ext>`, so no member wins by extraction order.

### Population before / after

| Quantity | Before | After |
|---|---:|---:|
| Source inventory records | 2,578 | 2,578 |
| **Active manifest records** | **2,572** | **2,578** |
| Distinct SHA-256 in manifest | 2,560 | 2,566 |
| Train / test | 2,336 / 236 | **2,342 / 236** |
| Train / test classes | 28 / 27 | 28 / 27 |
| Casefold path collisions | 6 | **0** |
| Corrupt / zero-byte | 0 / 0 | 0 / 0 |
| `run_phase1_checks.sh` verdict | PARTIAL (2,572/2,578) | **PASS** |

The manifest SHA-256 **multiset is now identical to the inventory's** — a bijection: every
upstream record represented exactly once, nothing dropped, nothing invented.

### The six restored identities

| Group | Upstream archive path | SHA-256 | Bytes | Dims | Active path |
|---|---|---|---:|---:|---|
| cg01 | `train/Apple rust leaf/CAR1.jpg` | `ff8e845061e3…` | 249,767 | 498×841 | `train/Apple rust leaf/CAR1__ff8e845061e3.jpg` |
| cg02 | `train/Blueberry leaf/blueberry-leaf.jpg` | `a488765c32aa…` | 1,234,441 | 1422×2000 | `train/Blueberry leaf/blueberry-leaf__a488765c32aa.jpg` |
| cg03 | `train/Blueberry leaf/blueberry-leaves.jpg` | `2e99aae9cb26…` | 24,227 | 450×338 | `train/Blueberry leaf/blueberry-leaves__2e99aae9cb26.jpg` |
| cg04 | `train/Corn leaf blight/northern-corn-leaf-blight.jpg` | `2c2cc7cec2c4…` | 59,950 | 750×350 | `train/Corn leaf blight/northern-corn-leaf-blight__2c2cc7cec2c4.jpg` |
| cg05 | `train/Peach leaf/peach-leaf.jpg` | `0571261a682b…` | 148,756 | 2136×1424 | `train/Peach leaf/peach-leaf__0571261a682b.jpg` |
| cg06 | `train/Potato leaf early blight/…-a60hxn.jpg` | `0ea1317f5e20…` | 113,078 | 640×447 | `train/Potato leaf early blight/…-a60hxn__0ea1317f5e20.jpg` |

All 12 group members (both the six restored and the six already present) are in
`data/manifests/plantdoc_case_collision_mapping.csv` with `collision_group`,
`original_archive_path`, `collision_safe_relative_path`, split, class, SHA-256, byte size,
dimensions, and a **computed decoded-pixel SHA-256**.

### Authority and safety

- Bytes came from the pinned archive `plantdoc-5467f6012d78.tar.gz`; every SHA-256 and byte size
  was verified against the inventory **before** writing.
- Distinctness re-proved at restore time: within every group the members differ in SHA-256 **and**
  in decoded-pixel hash. Byte- or pixel-identical members would have aborted the restore, because
  that would be a duplicate decision, not a rename.
- No source image was deleted. An ambiguous natural-path file was unlinked only after both group
  members existed at verified collision-safe paths; the independent `_collisions/` copies are
  untouched.
- `PD.acquire()` now calls `assert_collision_safe()`, so **any** manifest build that would omit a
  distinct upstream digest fails closed instead of producing a short manifest that looks
  internally consistent.

### Not decided here

The upstream tree separately contains **12 SHA-256 values that each appear at two paths**
(2,578 records over 2,566 distinct digests). Several cross split *and* class — e.g.
`test/Corn leaf blight/2015070295153021.jpg` and `train/Corn Gray leaf spot/2015070295153021.jpg`
are the same bytes under two different labels. These were already present in the 2,572 manifest;
restoring six images neither created nor removed any. They are a real scientific issue for any
future split and **require a human decision that has not been made**. No exclusion was invented.

---

## 3. AUD-EC-001 / 002 / 008 — leakage gate schema 2.0

### Canonical pair identity

Every detected pair now has an immutable identity assembled from the authoritative pair table and
the **current manifests**:

```
training_dataset, training_relpath, training_class, training_sha256,
evaluation_dataset, evaluation_relpath, evaluation_class, evaluation_sha256,
phash_distance, classification
```

Endpoint digests are read from the manifests, never from the review file, so editing a SHA-256 in
the review CSV cannot make it authenticate.

### Near-pair authorization (AUD-EC-001)

A review row is credited only if it reproduces that identity field-for-field **and** the review
set is in **strict bijection** with the authoritative near set. Violations force `fail`; they no
longer merely forfeit credit. Rejected: duplicate `pair_id`, duplicate identity, unknown/surplus
row, missing authoritative pair, any identity-field mutation, unsupported vocabulary, terminal
decision without reviewer/timestamp/reason, `exclude_evaluation` without exactly one
identity-consistent propagated record, and orphan reviewed-exclusion rows.

### Exact-pair authorization (AUD-EC-002)

`--excluded-pairs` and the `excluded_pair_count` parameter are **removed**. Exact credit is
derived from `data/exclusions/cross_dataset_exact_exclusions.csv`, requiring exactly one
identity-matching record per detected exact pair. Missing, duplicate, unknown, surplus, or
mismatched records are violations. A regression test asserts the parameter no longer exists, and
that hand-forging the counts into the artifact still fails validation because the recorded
violations survive.

### Input binding and determinism (AUD-EC-008)

The gate binds a SHA-256 of **seven** inputs, and `validate_gate` recomputes all of them:

| Bound input | Digest |
|---|---|
| `training_manifest` | `b9acc43637ef2e93…` |
| `evaluation_manifest` | `548b815197c51bc2…` |
| `pair_table` | `16d187c4f711d03a…` |
| `near_review` | `381a971c1bb6e980…` |
| `reviewed_exclusions` | `6ef83daba8e9f070…` |
| `exact_exclusions` | `0cacb177b00395cd…` |
| `leakage_config` | `bf22dd2c15c22359…` |

`leakage_config` digests the threshold, algorithm, dataset names, and schema version, so a
threshold change makes the gate stale too.

The wall-clock field is **gone** from the gate. Execution metadata moved to the explicitly
non-authoritative `reports/leakage_gate_run.json`. Two complete independent rebuilds:

```
build 1  ce78e3b83e2521024e961813eeff34dd17c8a9671d93c29b159ebc96301f3437
build 2  ce78e3b83e2521024e961813eeff34dd17c8a9671d93c29b159ebc96301f3437   byte-identical
```

Schema 1.x gates are **rejected**, not reinterpreted — their counts do not mean the same thing.

The pipeline guard test grew from 5 to **14 states**, including one stale state per bound input,
so no binding can silently go missing (`reports/leakage_gate_guard_test.json`, `all_pass=true`).

---

## 4. AUD-EC-004 — regeneration preserves human review

`scripts/prepare_human_review.py` previously built every decision field as `""` and
unconditionally rewrote a header-only reviewed-exclusions file.

It now merges prior decisions back by **canonical identity** (not row order, not `pair_id`):

- terminal decisions, reasons, reviewer ids, timestamps, and dispositions are carried over
  verbatim, and `pair_id` follows the pair rather than the row position;
- reviewed exclusions are preserved and revalidated against the merged review;
- new authoritative pairs are added **undecided**;
- identity drift on a *decided* pair raises `HumanDecisionDrift` and aborts;
- removed pairs are reported explicitly, never dropped silently;
- destruction requires the explicit `--reset-human-decisions` flag, **not used in this task**;
- all writes are atomic with LF endings.

Every regeneration writes `reports/NEAR_DUPLICATE_REVIEW_CHANGES.md`.

**Verified result of this round's regeneration:** 16 preserved, 0 new, 0 dropped, and the review
CSV is **byte-identical to the committed audited version** (`381a971c1bb6e980…`).

---

## 5. Leakage state after the rebuild

All derived artifacts were regenerated through the canonical scripts — manifest, pHash indexes,
pair tables, exclusions, review packet, contact sheets, summaries, gate.

| Quantity | Before | After |
|---|---:|---:|
| PlantDoc images indexed | 2,572 | **2,578** |
| PlantVillage images indexed | 54,305 | 54,305 |
| Skipped (unhashable) | 0 | 0 |
| Exact pairs detected / excluded | 0 / 0 | **0 / 0** |
| Near pairs detected | 16 | **16** |
| Near resolved / kept / excluded | 16 / 16 / 0 | **16 / 16 / 0** |
| Unresolved | 0 | **0** |
| Authorization violations | (not computed) | **0** |
| Gate status | pass (schema 1.1) | **pass (schema 2.0)** |

**The six restored images created no new exact or near pairs.** The authoritative pair table is
byte-identical to the audited version, none of the 16 pairs' endpoints was among the renamed
files, and all 16 recorded decisions authenticate against the rebuilt manifests with zero
violations.

**No new human review round is required.**

---

## 6. Adversarial test outcomes

Every audit-listed failing case is now a regression test. Full suite: **272 passed** (was 178).

| Group | Cases | Result |
|---|---:|---|
| Near review — duplicate/unknown pair id, duplicate identity, changed training SHA, changed evaluation SHA, changed distance, changed path, changed classes, changed datasets, missing authoritative pair, surplus row, missing attribution | 20 | all rejected |
| Near review — exclusion not propagated, reviewed exclusion without human exclude, exclusion pair-id mismatch, orphan exclusion | 4 | all rejected |
| Near review — pending / uncertain / deferred | 3 | no credit, no violation (correct) |
| Exact exclusions — integer 1 and 999 without a record, duplicate, unknown, missing, identity mismatch, surplus | 7 | all rejected |
| Persisted gate — stale manifest, pair table, review CSV, reviewed exclusions, exact exclusions, config; old schema; unbound; recorded violations | 10 | all rejected |
| Persisted gate — two identical builds | 1 | byte-identical |
| Packet regeneration — decisions preserved, exclusions preserved, new pair blank, identity drift rejected, removal reported, reset explicit | 18 | all pass |
| PlantDoc — inventory 2,578, manifest 2,578, SHA multiset bijection, no casefold collision, six restored, group distinctness, shortfall guard | 26 | all pass |

---

## 7. Validation commands

| Command | Result |
|---|---|
| `python -m pytest` | **272 passed** |
| `python scripts/validate_phase1_review.py` | exit **1**, verdict BLOCKED, 19 expected blockers |
| `bash scripts/run_phase1_checks.sh` | 9/9 hard checks pass, **OVERALL: PASS** |
| `python -m ica26.mapping.validation data/mapping/action_mapping_approved.csv` | 0 errors, 10 rows |
| `python scripts/apply_action_mapping_review.py --check` | output current |
| `python -m ica26.portability` | OK — no personal identifiers |
| `python scripts/run_phase1_local.py --steps plantdoc,index,leakage,gate` | manifest 2,578; gate pass |
| gate built twice | byte-identical (`ce78e3b8…`) |
| `git diff --check` | clean |

---

## 8. Remaining blockers

1. **17 PlantDoc disease mappings** remain `needs_review` — independent scientific source
   verification is still required.
2. **PlantVillage action mapping does not exist** — 38 classes, 54,305 images, 0 rows, 0% coverage
   of the training set.
3. **AUD-EC-005** — `guarded_cross_dataset_action_evaluation` still builds an unscoped lookup, so
   arthropod scope is not enforced end-to-end at the production entry point.
4. **AUD-EC-006** — the healthy policy accepts malformed policy tokens and unparsed dates.
5. **AUD-EC-007** — `README.md` and `PROJECT_BRIEF.md` still describe a superseded state
   (gate fail, zero decisions, PlantDoc 2,598).
6. **12 upstream byte-duplicate pairs** inside PlantDoc, several crossing split and class, await a
   human decision (§2).

---

## 9. Explicit answers

| Question | Answer |
|---|---|
| Is Phase 2 authorized? | **No.** |
| Is Dataset V1 safe to freeze? | **No.** Blockers 1–5 above remain; §2's duplicate pairs are undecided. |
| Is another human near-duplicate review required? | **No.** The pair set is unchanged, and all 16 decisions authenticate with zero violations. |
