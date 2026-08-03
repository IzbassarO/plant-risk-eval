# Phase-1 Integrity Remediation — Round 2A

**Re-audited commit:** `f92bf2a2da59a49a9ee8da776b908171d6d74b3f`
**Re-audit report:** `reports/PHASE1_CODEX_REAUDIT_R1_F92BF2A.md` (committed unmodified in `a12e1d2`)
**Scope:** R1-CRIT-001, R1-CRIT-002, R1-HIGH-001, R1-HIGH-002, R1-MED-001

_No duplicate decision was applied, no mapping approved, no label or split changed, no metric
computed, no model trained, and Dataset V1 remains unfrozen._

---

## 1. Findings addressed

| ID | Severity | Finding | Status |
|---|---|---|---|
| R1-CRIT-001 | Critical | Fresh detection reconciled to the pair table by **count** only | **Fixed** |
| R1-CRIT-002 | Critical | 12 byte-exact duplicate groups inside PlantDoc, unreviewed | **Packet built; awaiting human decisions** |
| R1-HIGH-001 | High | Arbitrary display `pair_id` and malformed `reviewed_at` authenticate | **Fixed** |
| R1-HIGH-002 | High | Path drift on a decided review row does not raise | **Fixed** |
| R1-MED-001 | Medium | `run_phase1_checks.sh` prints an overbroad `OVERALL: PASS` | **Fixed** |

Out of scope this round: R1-LOW-001 (pHash docstring), R1-INFO-001 (validator timestamp side
effect), AUD-EC-005/006/007 from the earlier audit.

---

## 2. Canonical pair identity (Task B)

A pair's scientific identity is its two endpoints and their relationship — never its label and
never its position in a file. Implemented in `src/ica26/leakage/gate.py`.

**Versioned serialization** — `CANONICAL_PAIR_SCHEMA = "ica26.leakage.pair/1"`, emitted as
sorted-key compact JSON. Only serialization is normalised (key order, separators, integer
typing); no scientific value is trimmed, case-folded, or defaulted.

Fields: `pair_type` · `training_dataset` · `training_relpath` · `training_class` ·
`training_sha256` · `evaluation_dataset` · `evaluation_relpath` · `evaluation_class` ·
`evaluation_sha256` · `phash_distance` · `phash_algorithm` · `phash_bits`.

```
canonical_pair_id = "<pair_type>-" + sha256(canonical_serialization)[:16]
```

- **Namespaced by pair type** in both the prefix and the payload, so the same endpoints as an
  exact pair and as a near pair can never collide.
- **Order-independent**: a pure function of content, so the id is identical on any machine, in
  any row order, in any file.
- **Display ids are separate.** `display_pair_ids()` assigns `ndp-01…` from a canonical *sort* of
  the identities. A display id labels; it authorises nothing.

Endpoint digests **and class labels** for a fresh identity are read from the manifests, so a
forged table cannot inject either. The persisted table may *declare* `training_sha256` /
`evaluation_sha256`; those declarations are never used but are now validated against the
manifest, so the table cannot assert a digest that is false.

Generated tables carry `canonical_pair_id` and `pair_schema` columns.

---

## 3. Fresh vs persisted identity-set equality (Task C) — R1-CRIT-001

`compute_gate` now builds the canonical identity set **directly from the fresh detection result**
and requires **exact set equality** with the persisted table:

```
fresh_set == persisted_set     (canonical ids; not counts)
```

`reconcile_pair_sets()` reports `fresh_only`, `persisted_only`, `duplicates`, and the schema.
Equality is a **precondition**: when it fails the gate returns `incomplete` and **review and
exclusion authorization are not run at all** — authenticating against the wrong identities would
be meaningless.

### The re-audit's exploit, reproduced

`tests/test_pair_identity_equality.py::test_forged_same_count_exact_table_is_rejected` builds
exactly the audit's scenario: one true exact pair `train/c/one.png → test/c/one.png`, a forged
table declaring the unrelated existing pair `other → other` with the **same row count**, and a
matching forged exclusion record.

| | R1 (`f92bf2a`) | R2A |
|---|---|---|
| status | **`pass`** | **`incomplete`** |
| authorization violations | `[]` | real pair missing **and** forged pair surplus |
| exact excluded | 1 (forged) | **0** — arithmetic never ran |

Also rejected with the same row count: mutated `training_class`, `evaluation_class`,
`training_sha256`, `evaluation_sha256`, `hamming_distance`, and exact↔near type substitution;
plus surplus rows, missing rows, and duplicate identities. The same rule covers the near subset.

**Current real result:** `fresh=16, persisted=16, equal=True, fresh_only=[], persisted_only=[]`.

---

## 4. Review authentication (Tasks D, E) — R1-HIGH-001

**Pair identity.** A review row must carry `canonical_pair_id` matching the identity-derived
value, and its display `pair_id` must match the authoritative display map. Rejected: missing
canonical id, mismatched canonical id, duplicate canonical id, duplicate display id, arbitrary
unique display id, and any changed identity field.

**Timestamps.** `parse_review_timestamp()` requires strict ISO-8601, a real calendar date, an
**explicit timezone offset**, and a non-future instant.

| Input | R1 | R2A |
|---|---|---|
| `2026-08-02T21:10:00+05:00` | accepted | **accepted** (the confirmed stamp stays valid) |
| `tomorrow` | **accepted** | rejected — not ISO-8601 |
| `2026-02-30T00:00:00+00:00` | accepted | rejected — impossible calendar date |
| `2026-08-02T21:10:00` | accepted | rejected — no timezone offset |
| `2099-01-01T00:00:00+00:00` | accepted | rejected — in the future |
| blank | rejected | rejected |

Reviewer and decision-reason requirements are unchanged.

**Exact exclusions** now additionally require `canonical_pair_id`, `training_sha256`, and
`evaluation_sha256`, each matched against the freshly authenticated identity. A blank required
identity column is a violation. No integer authorises anything; the parameter does not exist.

**The 16 confirmed decisions were re-validated, not grandfathered.** Their canonical identities
were regenerated from the current manifests and every one matched; decision fields, reviewer,
timestamps and dispositions are byte-identical to the audited version, with `canonical_pair_id`
the only added column.

---

## 5. Regeneration drift (Task F) — R1-HIGH-002

`scripts/prepare_human_review.py` now indexes prior decisions by **canonical identity**, so any
identity change — including either relative path — makes a decided record unfindable and raises
`HumanDecisionDrift` **before anything is written**.

| Change on a *decided* row | R1 | R2A |
|---|---|---|
| dataset / class / SHA / distance | raises | raises |
| **training relative path** | dropped + new blank row | **raises** |
| **evaluation relative path** | dropped + new blank row | **raises** |
| **decided pair removed entirely** | reported as dropped | **raises** |
| undecided pair removed | reported | reported (not an error) |
| contact-sheet re-paging | preserved | preserved (cosmetic, not identity) |

All emitted artifacts — review CSV, reviewed-exclusions CSV, every Markdown report, and the
contact-sheet PNGs — now use temp file + `os.replace`.

**Schema migration** was deterministic: `canonical_pair_id` was added as the single new column;
all 16 rows' decisions and identity fields are byte-identical. Regeneration reports
`preserved=16, new=0, dropped=0`.

---

## 6. PlantDoc exact-duplicate review packet (Task G) — R1-CRIT-002

Enumerated independently from the active manifest by byte SHA-256, with decoded-RGB digests
computed per record.

| Aggregate | Value |
|---|---:|
| Duplicate groups | **12** |
| Records involved | **24** |
| Groups crossing train/test | **11** |
| Groups with contradictory labels | **9** |
| Same class, same split | 0 |
| Same class, cross split | 3 |
| Cross class, same split | 1 |
| Cross class, cross split | 8 |
| Byte-identical groups | 12 |
| Decoded-pixel-identical groups | 12 |

These match the re-audit's independent enumeration exactly.

| Display | Class labels | Split | Flags |
|---|---|---|---|
| G01 | Blueberry leaf | train 1 / test 1 | cross-split |
| G02 | Tomato leaf yellow virus | train 1 / test 1 | cross-split |
| G03 | Potato leaf early blight \| late blight | train 1 / test 1 | cross-split, **cross-class** |
| G04 | Corn Gray leaf spot \| Corn leaf blight | train 1 / test 1 | cross-split, **cross-class** |
| G05 | Corn Gray leaf spot \| Corn leaf blight | train 1 / test 1 | cross-split, **cross-class** |
| G06 | Tomato Septoria leaf spot | train 1 / test 1 | cross-split |
| G07 | Potato leaf early blight \| late blight | train 1 / test 1 | cross-split, **cross-class** |
| G08 | Potato leaf early blight \| late blight | train 1 / test 1 | cross-split, **cross-class** |
| G09 | Potato leaf early blight \| late blight | train 1 / test 1 | cross-split, **cross-class** |
| G10 | Tomato Septoria leaf spot \| Tomato leaf bacterial spot | train 1 / test 1 | cross-split, **cross-class** |
| G11 | Potato leaf early blight \| late blight | train 2 / test 0 | **cross-class** |
| G12 | Corn Gray leaf spot \| Corn leaf blight | train 1 / test 1 | cross-split, **cross-class** |

### Packet — `reports/plantdoc_exact_duplicate_review/`

| Artifact | Content |
|---|---|
| `plantdoc_exact_duplicate_groups.csv` | 12 rows; **all six decision columns blank** |
| `plantdoc_exact_duplicate_members.csv` | 24 immutable evidence rows |
| `PLANTDOC_EXACT_DUPLICATE_HUMAN_REVIEW.md` | checklist, blank prompts, no recommendation |
| `contact_sheet_01…04.png` | both members, full and uncropped, with split/class/SHA and explicit cross-split / cross-class flags |
| `packet_manifest.json` | SHA-256 of every packet artifact |
| `README.md` | how to review the packet |

Group ids are content-derived (`pdup-<16 hex>` over a versioned serialization, member-order
independent) with human-friendly `G01…G12` display labels.

The checklist states explicitly that **byte-exact identity is already machine-verified**, and
that human review is required for three questions only: evaluation inclusion policy, group-aware
split handling, and contradictory-label adjudication. **This packet answers none of them.**

Per repository policy (matching the existing near-duplicate sheets), the ~1.7 MB of rendered
PNGs are gitignored as regenerable derived collages; their digests remain recorded in
`packet_manifest.json`. All evidence CSVs, the checklist, the README, and the manifest are
tracked.

---

## 7. Internal duplicate gate (Task H)

`reports/plantdoc_internal_duplicate_gate.json`, built by
`scripts/build_plantdoc_internal_duplicate_gate.py` — deliberately **separate** from the
cross-dataset gate, because overloading one artifact with two different scientific questions is
how a "pass" comes to mean less than a reader assumes.

```
total_groups 12 · total_records 24 · cross_split 11 · cross_class 9
resolved 0 · unresolved 12 · violations 0 · status "incomplete"
```

Bound inputs (digested): PlantDoc manifest, duplicate group table, member table, group schema.
A group resolves only on a terminal decision with reason, anonymous reviewer, and a valid
timezone-aware timestamp. Missing, blank, deferred, unsupported, duplicate, or unknown decisions
all prevent `pass`. There is no count parameter and no override. No wall-clock field, so repeated
builds are byte-identical (`affb40f0f…`).

---

## 8. Check-script status (Task I) — R1-MED-001

`OVERALL: PASS` is gone. `run_phase1_checks.sh` now reports each dimension:

```
MECHANICAL / DATA CHECKS ....... PASS
CROSS-DATASET GATE ............. PASS
INTERNAL DUPLICATE REVIEW ...... INCOMPLETE
MAPPING REVIEW ................. INCOMPLETE
DATASET V1 FREEZE .............. NOT STARTED
SCIENTIFIC PHASE-1 STATUS ...... BLOCKED
```

`SCIENTIFIC PHASE-1 STATUS` is `ACCEPTED` only when every dimension passes; it is currently
`BLOCKED` and the script exits 2. The hard checks are labelled mechanical and explicitly stated
not to constitute scientific acceptance. No scientific decision was changed to reach a status.

---

## 9. Deterministic hashes

| Artifact | SHA-256 | Builds compared |
|---|---|---|
| `reports/plantdoc_internal_duplicate_gate.json` | `affb40f0fa3f774afd6f6bfda2ef24ced7edf34997437442acc87b42ba502258` | 2 — identical |
| Duplicate packet (CSV + MD + manifest) | see `packet_manifest.json` | 2 — identical |
| `reports/leakage_gate.json` | `d5c720192dbe109c22e60ff07f4c23714b83df7302d48bcadb94c78bbcdb1b3c` | 2 full builds over 54,305 + 2,578 images — identical |

The cross-dataset gate digest changed from R1's `ce78e3b8…` because schema 2.1 adds the
`pair_identity_reconciliation` provenance block; the computation is unchanged (still
exact 0, near 16, resolved 16, unresolved 0).

---

## 10. Test outcomes

**338 passed** (was 272). New suites:

| Suite | Cases | Covers |
|---|---:|---|
| `tests/test_pair_identity_equality.py` | 19 | forged same-count exact/near tables, missing/surplus identity, changed SHA/class/path/distance, exact↔near substitution, order independence, versioned serialization |
| `tests/test_plantdoc_duplicates.py` | 39 | group/member enumeration from live data, byte+pixel identity, blank decision fields, packet determinism, manifest hashes, gate incomplete/fail/pass, malformed timestamps |
| `tests/test_leakage_gate.py` | 62 | canonical id binding, display-id verification, exclusion identity columns |
| `tests/test_review_packet_preservation.py` | 25 | path drift raises, decided-pair removal raises, nothing written on failure |

---

## 11. Unresolved human decisions

**12 PlantDoc duplicate groups** await three decisions each: group handling, canonical label
(for the 9 contradictory groups), and split handling (for the 11 cross-split groups). Nothing in
this round pre-empts any of them.

Also still open: 17 PlantDoc disease mappings (`needs_review`), PlantVillage action-mapping
coverage 0/38, plus AUD-EC-005/006/007 from the earlier audit.

---

## 12. Scientific status

| Dimension | Status |
|---|---|
| Mechanical / data checks | PASS |
| Cross-dataset leakage gate | PASS (structural) |
| Internal PlantDoc duplicate review | **INCOMPLETE** |
| Mapping review | **INCOMPLETE** |
| Dataset V1 freeze | **NOT STARTED** |
| **Scientific Phase-1 status** | **BLOCKED** |

- **Is Dataset V1 safe to freeze?** **No.**
- **Is Phase 2 authorized?** **No.**
- **Were any labels or splits changed?** **No.** The manifest is unchanged at 2,578 records over
  2,566 distinct digests; no record was deleted, relabelled, moved between splits, or excluded.
- **Is human duplicate adjudication required?** **Yes** — all 12 groups.
