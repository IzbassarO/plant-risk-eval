# Independent Phase-1 Human-Review and Policy Audit

**Audited commit:** ec482333031e5b1dc596bd1f8f48a39f8b2b8d6d  
**Parent:** 21df1f88de24766301017b13a97e4ed3cd9c2e3d  
**Audit date:** 2026-08-02  
**Verdict:** **BLOCKED**

This independent audit inspected Git history, code, manifests, raw local source archive,
generated artifacts, and a fresh virtual environment. It did not accept previous reports as
evidence. No scientific mapping, model training, Phase-2 work, commit, or push was performed.

## Executive result

The recorded state is internally consistent: 16 actual near-pair decisions are all keeps; 10
healthy mappings reproduce; and the mite classes remain in diagnosis manifests. However the
runtime leakage gate is **unsafe**. It can certify mutated review data and an arbitrary exact
exclusion count, and it does not bind its persisted result to review/pair/exclusion inputs. The
active PlantDoc manifest also omits six distinct upstream images. Those defects block Dataset V1
freeze and any scientifically defensible cross-dataset metric.

The detailed requirement matrix records **85 PASS, 13 PARTIAL, 21 FAIL, 0 NOT TESTED** atomic
checks. Of 11 substantive claims in reports/PHASE1_HUMAN_DECISIONS_2026-08-02.md, **9 are
verified, 1 partially verified, and 1 false as an end-to-end claim**. The partially verified claim
is human visual inspection: the sheets and decision records exist, but a repository audit cannot
prove the human act. The false claim is end-to-end arthropod exclusion: the sanctioned
cross-dataset evaluation function does not load or pass the scope.

## A. Repository and commit integrity

Before this report was created, git status --short was empty. HEAD and origin/main both equalled
the audited commit. The full parent-to-target diff has 29 files, 2,457 insertions, and 196
deletions:

- Added: configs/evaluation_scope.yaml; data/mapping/action_mapping_apply_summary.json;
  data/mapping/action_mapping_approved.csv; data/mapping/plantvillage_class_list.csv;
  reports/ARTHROPOD_PEST_EVALUATION_SCOPE.md; reports/HEALTHY_CLASS_ACTION_POLICY.md;
  reports/PHASE1_HUMAN_DECISIONS_2026-08-02.md; scripts/apply_action_mapping_review.py;
  src/ica26/evaluation/scope.py; src/ica26/mapping/review.py; and four review/policy test files.
- Modified: review and validation CSV/JSON artifacts; action review CSV; checklist, gate policy,
  gate JSON; preparation/completion/validation scripts; schemas, mapping validation, leakage gate,
  conftest, and related production tests.

Complete created/modified/deleted listing (A/M/D):

    A configs/evaluation_scope.yaml
    M data/exclusions/cross_dataset_near_duplicate_review.csv
    M data/interim/phase1_review_validation.csv
    M data/interim/phase1_review_validation_summary.json
    A data/mapping/action_mapping_apply_summary.json
    A data/mapping/action_mapping_approved.csv
    M data/mapping/action_mapping_review.csv
    A data/mapping/plantvillage_class_list.csv
    M reports/ACTION_MAPPING_HUMAN_CHECKLIST.md
    A reports/ARTHROPOD_PEST_EVALUATION_SCOPE.md
    A reports/HEALTHY_CLASS_ACTION_POLICY.md
    M reports/LEAKAGE_GATE_EXCLUSION_POLICY.md
    A reports/PHASE1_HUMAN_DECISIONS_2026-08-02.md
    M reports/leakage_gate.json
    A scripts/apply_action_mapping_review.py
    M scripts/prepare_human_review.py
    M scripts/run_phase1_data_completion.py
    M scripts/run_phase1_local.py
    M scripts/validate_phase1_review.py
    A src/ica26/evaluation/scope.py
    M src/ica26/leakage/gate.py
    A src/ica26/mapping/review.py
    M src/ica26/mapping/validation.py
    M src/ica26/schemas.py
    M tests/conftest.py
    A tests/test_apply_action_mapping_review.py
    A tests/test_evaluation_scope.py
    A tests/test_healthy_policy.py
    A tests/test_near_duplicate_decisions.py

There are no deleted files.

The complete changed-file listing was inspected with git diff --name-status. The commit is limited
to Phase-1 review/policy machinery and generated artifacts. No raw image, archive, credential,
personal identifier, virtual environment, cache, or model output was added.

| Artifact | SHA-256 |
|---|---|
| data/exclusions/cross_dataset_near_duplicate_review.csv | 381a971c1bb6e9808a82fde61eabe1bec307e57b5892cd2a55e0b256c04c9205 |
| data/exclusions/cross_dataset_reviewed_exclusions.csv | 6ef83daba8e9f070d8191acc6c4f7212ec503a69f4da6136893e616ed6a9ee3a |
| data/mapping/action_mapping_review.csv | 4efb48a4a5aac5c61bf80ce42ad7821d6772c7994313ba9c1bb38cde08588b06 |
| data/mapping/action_mapping_approved.csv | 5b98bf45ce02cf82594d7fe42bc473cc68941ecdadc5b3d96f536326ddde298c |
| data/mapping/action_mapping_apply_summary.json | 83841236fd6dafed1218d02b988be8787735c162a864b01162696687c4acf973 |
| configs/evaluation_scope.yaml | 7f8b2a9ce72bf8709a3fa413f81ee6788a751f5e78606b002251bd6ad6c79272 |
| reports/leakage_gate.json | c7e28576377c32064cacdffdcd70dcd9bbc87589fc48cbdf0b5f89a613d8f5a1 |

git diff --check reports CRLF-as-trailing-whitespace warnings in two generated CSV files. This is
a low-severity formatting/reproducibility issue, not a demonstrated semantic data change.

## B. Near-duplicate decision audit

The authoritative pair table has exactly 16 near rows. The review CSV has exactly 16 rows with
IDs ndp-01 through ndp-16. IDs ndp-01 to ndp-15 are clearly_different / keep; ndp-16 is
visually_similar_but_independent / keep. There are no uncertain, deferred, or exclude decisions,
and the reviewed-exclusions CSV is header-only.

Each decision has nonblank reviewer human_reviewer_1, consistent timestamp
2026-08-02T21:10:00+05:00, and a nonblank reason. Parent/target comparison shows that only
human_decision, decision_reason, reviewer, reviewed_at, and final_disposition changed. Every
dataset name, path, class, SHA-256 field, pHash distance, contact-sheet path, and pair ID is
byte-identical to the parent. All 16 endpoints resolve to the current manifests; the records are
not basename-only evidence.

Fresh full computation returned exact=0, near=16, resolved=16, unresolved=0, status=pass. This
numerical result is not hard-coded, but it is not a safe authorization.

### Temporary adversarial tests

| Mutation of otherwise real review | Observed | Required | Result |
|---|---|---|---|
| Blank decision | 15 resolved, 1 unresolved | no credit | PASS |
| uncertain | 15 resolved, 1 unresolved | no credit | PASS |
| needs_secondary_review | 15 resolved, 1 unresolved | no credit | PASS |
| Unsupported vocabulary | 15 resolved, 1 invalid, 1 unresolved | no credit | PASS |
| Duplicate pair_id | 16 resolved, 0 invalid | fail/incomplete | FAIL |
| Unknown pair_id | 16 resolved, 0 invalid | fail/incomplete | FAIL |
| Changed training SHA-256 | 16 resolved | fail/incomplete | FAIL |
| Changed evaluation SHA-256 | 16 resolved | fail/incomplete | FAIL |
| pHash distance changed to 999 | 16 resolved | fail/incomplete | FAIL |
| Remove one authoritative key | 15 resolved, 1 unmatched, 0 unresolved | fail/incomplete | FAIL |
| Exclude not propagated | 15 resolved, 1 invalid, 1 unresolved | no credit | PASS |
| Reviewed exclusion without human exclude | 16 resolved, 0 invalid | fail/incomplete | FAIL |
| Unmatched extra review row | 16 resolved, 1 unmatched, 0 unresolved | fail/incomplete | FAIL |
| Manifest change after gate generation | validate_gate: 1 error | reject stale gate | PASS |

The closeout validator contains stronger duplicate/path/distance/exclusion checks
(scripts/validate_phase1_review.py:175-340), but production evaluation invokes only
require_valid_gate and never invokes that validator. It also does not validate review SHA values
against current manifest content. It is therefore not a runtime mitigation.

## C. Leakage-gate semantic audit — UNSAFE

src/ica26/leakage/gate.py:143-175 authenticates a review decision only by the two paths; it does
not inspect pair ID, datasets, classes, review SHA-256, distance, sheet, reviewer, or timestamp.
It counts invalid/unmatched rows but compute_gate uses only resolved
(src/ica26/leakage/gate.py:213-225), so invalid extras do not stop pass.

The integer --excluded-pairs is passed straight to arithmetic
(src/ica26/leakage/gate.py:187-218 and :343-359), not derived from or matched to
cross_dataset_exact_exclusions.csv. A temporary one-image dataset with one true exact pair gave:

    excluded-pairs=0:   exact=1 resolved=0 unresolved=1 status=fail
    excluded-pairs=1:   exact=1 resolved=0 unresolved=0 status=pass
    excluded-pairs=999: exact=1 resolved=0 unresolved=0 status=pass

max(0, ...) prevents negative counts, but hides over-crediting instead of rejecting it. Any future
exact overlap can thus be waived without an auditable exclusion row.

Manifest binding is correct at src/ica26/leakage/gate.py:274-294. The gate has no digest of the
review CSV, reviewed-exclusions CSV, or pHash pair table, however. validate_gate accepts the
persisted gate after any of those inputs change if manifests remain unchanged.

Full gate recomputation twice was semantically identical but not byte-identical:

    one.json  6dc4936016341de17e829a51a1e3416123087fab051c9ce55a188d76a0a02de5
    two.json  612663f048812cc1b0904654ade00c63e8a37d2b45b568a2de7230a181a91cdf

Only generated_at differed; removing it makes the JSON objects equal. The computation is
deterministic, but the committed artifact is not byte-deterministic.

## D. Healthy-policy audit

The approved canonical file has exactly 10 rows: all PlantDoc, all healthy, all monitor, blank
pathogen name/type, and no non-healthy approved row. It validates successfully. The normal
non-healthy evidence gate remains in place; fungal, bacterial, viral, oomycete, mite, abiotic,
unknown, blank, and arbitrary labels do not use the healthy branch. The actual rows contain no
fabricated pathogen source or URL.

The policy correctly requires monitor, action/evidence prose, a nonblank date, policy citation,
and blank pathogen fields (src/ica26/mapping/validation.py:49-73). Case/whitespace tolerance is
deliberately documented, rather than an accidental broadening.

However cites_healthy_policy is only a substring test
(src/ica26/mapping/validation.py:36-46), and evidence_checked_at is not parsed. Temporary
transform tests showed that evidence_checked_at=not-a-date, and policy strings
xpolicy:healthy-monitor-v1 or policy:healthy-monitor-v1-not-exact, validate and emit. The shipped
rows are good; the required exact-policy and valid-date guarantees are not.

## E. Arthropod scope audit

The exact PlantDoc and PlantVillage labels are present and diagnosis-eligible in
configs/evaluation_scope.yaml, with action/risk flags false. Direct manifest counts are PlantDoc
2 and PlantVillage 1,676 (1,356 train, 320 test). The PlantDoc review row is excluded and absent
from the 10-row canonical mapping. No PlantVillage action mapping was fabricated; no manifest/raw
data were deleted.

The apply script correctly loads the committed scope and rejects an artificially approved mite row
with zero emitted rows (scripts/apply_action_mapping_review.py:97-113). But it fails open with a
missing scope path (:106-108): that artificial approved row emits.

More importantly, guarded_cross_dataset_action_evaluation creates an unscoped lookup at
src/ica26/evaluation/cross_dataset.py:46-51. It neither loads the YAML policy nor accepts/passes a
scope argument. Existing scope tests explicitly inject a scope
(tests/test_evaluation_scope.py:135-166); they do not test this production entry point. Thus
scope filtering is not end-to-end enforced.

## F. Review-to-canonical transformation

This component is otherwise strong. Source review CSV is read, not overwritten; only approved rows
emit, and pending/needs-review/excluded rows do not
(src/ica26/mapping/review.py:124-175). Candidate action is explicitly copied to canonical action
class and constrained to four classes. Canonical data are revalidated through the healthy policy
before output (:181-186). Dataset/class, reviewer, timestamp, policy references, and source-row
provenance are retained; malformed/duplicate input fails closed. Output uses .part plus os.replace
(:211-225), and --check passed.

Two independent temporary writes were byte-identical:

    CSV:  3e27f3fc4d736c37e2346d3a3a0e1aa1d6394969a539dc1b738ab811e71aef22
    JSON: 9ae7521d223650d98c33df744621c1cb6f480f49cabff0dd1d183c64f00fcd5e

Counts match: 28 review rows = 17 needs review + 10 approved + 1 excluded; 10 emitted healthy
monitor rows; zero emitted disease rows. The claimed artificial-mite guarantee is conditional on a
caller supplying the scope.

## G. Checklist and review regeneration

**FAIL.** prepare_human_review constructs all review decisions, reasons, reviewers, timestamps, and
dispositions as empty strings (scripts/prepare_human_review.py:355-372), then replaces the real
review CSV (:408-418). It also unconditionally writes a header-only reviewed-exclusions CSV
(:450-457). Running it after human review destroys decisions and propagated exclusions. Mapping
checklist rendering is correct: approved becomes approve, excluded becomes exclude, and
needs_review stays blank; revise/insufficient are not supported statuses.

## H. PlantDoc 2,572/2,578 case-collision audit

The discrepancy is real. The source inventory has 2,578 records; the active manifest has 2,572
(2,336 train, 236 test). Six casefold groups have 12 collision-safe source records, and exactly
six distinct source records have no SHA-256 represented in the active manifest:

| Group | Missing upstream source image | SHA prefix | Bytes | Dimensions |
|---|---|---:|---:|---:|
| cg01 | Apple rust leaf/CAR1.jpg | ff8e845061e3 | 249,767 | 498x841 |
| cg02 | Blueberry leaf/blueberry-leaf.jpg | a488765c32aa | 1,234,441 | 1422x2000 |
| cg03 | Blueberry leaf/blueberry-leaves.jpg | 2e99aae9cb26 | 24,227 | 450x338 |
| cg04 | Corn leaf blight/northern-corn-leaf-blight.jpg | 2c2cc7cec2c4 | 59,950 | 750x350 |
| cg05 | Peach leaf/peach-leaf.jpg | 0571261a682b | 148,756 | 2136x1424 |
| cg06 | Potato leaf early blight/...-a60hxn.jpg | 0ea1317f5e20 | 113,078 | 640x447 |

I read every collision member directly from the pinned source tar archive. Every archive SHA
matches inventory and collision-safe materialization. Members of every group have different bytes,
dimensions, and decoded RGB-pixel hashes. This is case-insensitive extraction loss, not duplicate
or re-encoded content. All source bytes remain physically recoverable under _collisions, but six
images are not in the model-consumable active manifest. The repository itself calls for a human
decision and rederived manifest at reports/PLANTDOC_CASE_COLLISION_REVIEW.md:43-46.

## I. Clean reproduction

Fresh environment:

    Python 3.13.9
    fresh venv: /private/tmp/ica26-fresh-audit.i93lkp/venv
    install: .../venv/bin/python -m pip install --no-cache-dir '.[dev]'

The sandboxed install initially failed only on DNS. The approved retry installed the pyproject
package/dependencies successfully, including numpy 2.5.1, pandas 3.0.5, Pillow 11.3.0, ImageHash
4.3.2, pytest 8.4.2, PyYAML 6.0.3, and SciPy 1.18.0.

| Fresh command | Exit | Result |
|---|---:|---|
| python -m pytest -q | 0 | 178 collected; all passed |
| scripts/validate_phase1_review.py | 1 | 48 findings, 19 expected blockers: 17 PlantDoc disease rows and PlantVillage 0/38 mapping coverage |
| mapping validator, approved CSV | 0 | 10 rows; 0 errors |
| mapping validator, candidate review CSV | 1 | 30 expected schema-boundary errors: candidate_action_class is not canonical action_class |
| apply_action_mapping_review.py --check | 0 | canonical output current |
| full fresh leakage-gate command | 0 | pass; 0 exact, 16 near, 16 resolved |
| python -m ica26.portability | 0 | passed |
| env PYTHON=fresh-python bash scripts/run_phase1_checks.sh | 2 | all nine hard checks passed; overall PARTIAL for 2,572/2,578 PlantDoc |
| mapping writes twice | 0, 0 | byte-identical |
| leakage writes twice | 0, 0 | timestamp prevents byte identity |

validate_phase1_review.py changes only its generated timestamp as a side effect. That audit-only
change was restored to the audited value; no generated data modification is retained.

Test quality is inadequate for the defects found: tests omit duplicate/unknown pair ID, changed
SHA/distance, stale review inputs, arbitrary exact count, and unmatched-extra persisted-gate cases.
Scope tests manually supply scope rather than using the sanctioned cross-dataset function. Healthy
tests omit malformed policy-token and invalid-date cases.

## J. Scientific state and PROJECT_BRIEF consistency

Live artifacts honestly retain 16 resolved near pairs, numerical gate pass, ten approved PlantDoc
healthy rows, one excluded mite row, 17 PlantDoc disease rows needing review, 38 PlantVillage
classes with zero mapping rows, no V1 freeze, no model training, and no performance claim.

Documentation is contradictory. README.md:21-25 still says gate fail, zero near decisions, and zero
approved mappings. PROJECT_BRIEF.md is stale as authoritative state: it states PlantDoc has 2,598
images (:161-166), calls mapping/harm work not started (:432-439), and describes an earlier
truncated local implementation in section 6. The brief correctly requires citable sources for
every disease-action row (:404-409); retaining all 17 disease rows unapproved respects that rule.
Reconcile status documents before freeze, metrics, or paper claims.

## Findings ordered by severity

### Critical

**AUD-EC-001 — Gate accepts unauthenticated review mutations.**  
**Locations:** src/ica26/leakage/gate.py:143-175, :213-225.  
**Evidence:** duplicate/unknown IDs, changed SHA/distance, a missing authoritative key, bogus
reviewed exclusion, and unmatched extra row can still yield a numerical pass.  
**Impact:** gate pass is not reliable evidence of the reviewed near-pair set.  
**Fix:** bind a canonical immutable pair ID to datasets, paths, endpoint SHA-256, distance and
pair table; reject unknown, duplicate, missing, invalid, or surplus review/exclusion rows before
status arithmetic.  
**Block status:** blocks metrics and V1 freeze, but not read-only source verification.

**AUD-EC-002 — Exact duplicate exclusion is forced by an unbound integer.**  
**Locations:** src/ica26/leakage/gate.py:187-218, :343-359.  
**Evidence:** a true exact pair passes with excluded-pairs 1 or 999 and no exact exclusion record.  
**Impact:** true overlap can be waived without an auditable evaluation-side exclusion.  
**Fix:** parse/validate exact-exclusion records, bind every detected exact pair once, reject count
disagreement and over-count.  
**Block status:** blocks metrics and V1 freeze.

**AUD-EC-003 — Six distinct PlantDoc source images are absent from active V1.**  
**Locations:** source inventory, active manifest, and
reports/PLANTDOC_CASE_COLLISION_REVIEW.md:7-13,43-46.  
**Evidence:** archive-level SHA, byte, dimension, and decoded-pixel comparison in section H.  
**Impact:** no reproducible scientific inclusion/exclusion decision for six training samples.  
**Fix:** decide handling, use collision-safe names, rederive manifest/splits/fingerprint/gate.  
**Block status:** blocks V1 freeze and metrics, not mapping-source research.

### High

**AUD-EC-004 — Packet regeneration destroys human review.**  
**Locations:** scripts/prepare_human_review.py:355-372,408-418,450-457.  
**Evidence:** it constructs blank decision fields and overwrites review/exclusion artifacts.  
**Impact:** a nominal reproducibility command loses decisions and provenance.  
**Fix:** merge existing terminal decisions by full canonical identity and fail on drift.  
**Block status:** blocks reproducible closeout.

**AUD-EC-005 — Arthropod scope is optional and absent from production evaluation.**  
**Locations:** scripts/apply_action_mapping_review.py:97-108;
src/ica26/evaluation/cross_dataset.py:40-51.  
**Evidence:** an artificial approved mite emits without scope; cross-dataset evaluation is unscoped.  
**Impact:** a future mite mapping can enter action/risk metrics.  
**Fix:** require validated scope in the sole production entry point; apply action and risk filters.  
**Block status:** blocks action/risk metric authorization.

**AUD-EC-006 — Healthy policy accepts malformed provenance and invalid dates.**  
**Location:** src/ica26/mapping/validation.py:36-68.  
**Evidence:** adversarial malformed tokens and not-a-date validate.  
**Impact:** exact policy-reference and dated-evidence promises are not enforced.  
**Fix:** exact-token policy parsing and ISO-8601 date validation.  
**Block status:** blocks final canonical scientific release.

**AUD-EC-007 — Public/authoritative status documents contradict live artifacts.**  
**Locations:** README.md:21-35; PROJECT_BRIEF.md:161-166,265-290,432-439.  
**Evidence:** discrepancies listed in section J.  
**Impact:** reviewers can derive incompatible populations and review state.  
**Fix:** reconcile a dated source-of-truth status document and label historical reports.  
**Block status:** blocks freeze and paper claims.

### Medium

**AUD-EC-008 — Gate is neither review-input-bound nor byte-deterministic.**  
**Locations:** src/ica26/leakage/gate.py:227-255,260-294.  
**Evidence:** no review/exclusion/pair digests; only timestamp differs across repeat gates.  
**Impact:** stale pass can be reused after review mutation; exact artifact cannot reproduce.  
**Fix:** validate input digests and canonicalize reproducible metadata.  
**Block status:** blocks freeze and report release.

### Low

**AUD-EC-009 — Generated CSVs trip git diff --check CRLF warnings.**  
**Locations:** data/interim/phase1_review_validation.csv; data/mapping/plantvillage_class_list.csv.  
**Evidence:** parent-to-target diff check.  
**Impact:** noisy diffs only.  
**Fix:** write LF CSVs.  
**Block status:** no.

### Informational

**AUD-EC-010 — Closeout validation dirties a read-only audit.**  
**Location:** scripts/validate_phase1_review.py behavior.  
**Evidence:** generated timestamp changes on every invocation.  
**Impact:** clean audit worktree requires restoration.  
**Fix:** add a no-write/check mode or explicit output directory.  
**Block status:** no.

## Compact compliance matrix

| Section | PASS | PARTIAL | FAIL | Principal non-pass reason |
|---|---:|---:|---:|---|
| A repository/commit | 9 | 0 | 0 | — |
| B near decisions/adversarial gate | 17 | 0 | 8 | identity mutations accepted |
| C gate semantics | 3 | 3 | 5 | unsafe binding/count/staleness/determinism |
| D healthy policy | 11 | 2 | 1 | date/exact policy token missing |
| E arthropod scope | 6 | 3 | 1 | production path unscoped |
| F canonical transform | 15 | 1 | 0 | mite guarantee conditional |
| G regeneration | 3 | 1 | 3 | destroys decisions |
| H collisions | 5 | 2 | 1 | no V1 decision for six images |
| I clean reproduction | 9 | 0 | 1 | gate timestamp nondeterminism |
| J scientific state/spec | 7 | 1 | 1 | stale contradictions |
| **Total** | **85** | **13** | **21** | **0 not tested** |

## Explicit answers

1. **Is it safe to proceed to independent scientific source verification of the 17 remaining
   PlantDoc disease mappings?** **Yes, with boundaries.** This is read-only evidence collection.
   Keep every row needs_review, make no approval, and do not run action/risk metrics.
2. **Is it safe to freeze Dataset V1 now?** **No.** The six-image collision policy, unsafe leakage
   authorization, absent end-to-end scope enforcement, and zero PlantVillage mapping coverage
   prohibit a defensible freeze.
3. **Is Phase 2 authorized?** **No.**
