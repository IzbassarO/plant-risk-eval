# Phase 1 Independent Code Audit

Project: From Diagnosis to Decision: An Action-Level and Risk-Weighted Evaluation Framework for Deep Learning-Based Plant Disease Recognition  
Audit date: 2026-07-28  
Scope: audit only; no production source changed, no model trained, no commit made.

## Final verdict — REJECT

Phase 1 has useful, freshly tested engineering components, but is not a complete or scientifically safe foundation. The core mapping has zero approved rows; PlantVillage is unexecuted; PlantDoc train is incomplete; cross-dataset metrics have no enforceable leakage prerequisite; and the perceptual-hash search is quadratic at the intended scale. Phase 2 is not authorized, and no existing result is publishable.

## Executive summary

Fresh execution succeeded after editable installation: 52 tests passed and scripts/run_phase1_checks.sh exited 0. The package has 17 Python files, five installed CLIs, a four-action taxonomy, a syntactic evidence gate, core metric functions, and pHash tooling.

Those assets do not establish the claimed research foundation. The mapping has 27 pending rows, zero approved rows, and an empty approved lookup, so no disease label can yet be defensibly projected to an action. The local PlantDoc manifest is internally consistent but has only 636 images: 400 train and 236 test. PlantVillage correctly targets Hugging Face and fails loudly without its optional dependency, but has not been executed; there is no manifest, leaf-id evidence, or grouped split.

A read-only live GitHub tree query found 2,578 recognized PlantDoc image blobs: 2,342 train and 236 test, with 28 and 27 classes. This differs from the 2,598 count embedded in the brief and code. Reconcile it before using any manuscript count.

## Repository snapshot

| Item | Finding |
|---|---|
| pwd | <repository root> |
| Git | Not a Git repository; status, branch, and log all returned the fatal not-a-repository error. |
| Total size | 227M |
| data size | 224M |
| Source control | Cannot be demonstrated because no repository exists. |
| Package | 17 Python files in src/ica26. |
| Tests | Seven test modules plus conftest.py; the report's eight-file wording counts conftest. |
| CLI entry points | Five installed: plantdoc, plantvillage, leakage, validate-mapping, build-mapping. |
| Ignore safety | data/raw and data/interim are ignored, but checkpoints, experiment logs, HF caches, kaggle.json, and common secret files are not. |
| PII risk | data/interim/phash_index.csv contains absolute local paths with a personal username. |

The required find inventory was recorded at audit start. It showed the package, six notebooks, PlantDoc artifacts, and no PlantVillage manifest or raw dataset.

## Claim-by-claim verification of reports/PHASE1_REPORT.md

| Claim | Evidence inspected | Status | Explanation |
|---|---|---|---|
| Reusable package exists | Source inventory/imports | Verified | 17 package Python files exist. |
| Five CLIs | pyproject and installed metadata | Verified | All five named CLIs installed. |
| Eight test files | tests inventory | Verified | Seven test modules plus fixture file. |
| 52 tests pass | Fresh pytest | Verified | Exit 0 and 52 test dots. |
| Check script is green | Fresh script run | Verified | Exit 0. |
| Four active actions | YAML, constants, tests | Verified | Exact required four. |
| Evidence-gated mapping is complete | Validator and independent invalid rows | Partially verified | It checks non-empty strings and enums, not source/citation validity or authority. |
| Metrics complete and tested | Modules, tests, hand cases | Partially verified | Arithmetic works, but no leakage gate and selective-action coverage loses unmapped-true counts. |
| Development harm matrix is isolated | harm module and notebook 05 | Partially verified | Package labels it development-only; notebook 05 retains hard-coded harm logic/output. |
| PlantDoc is partial at 636 | Filesystem, manifest, summary | Verified | 400 train + 236 test. |
| PlantDoc test is complete at 236/27 | Live source tree and filesystem | Verified | Remote and local test counts match. |
| Zero corrupt local images | Manifest and independent opens | Verified | Manifest reports zero; three samples verified/opened. |
| Mapping is 27 pending, zero approved | CSV and approved lookup | Verified | Approved lookup is empty. |
| Leakage has four exact, zero near | Fresh script/artifacts | Verified | On local 636 images at threshold 5. |
| No train-test leakage | Pair artifact | Partially verified | No pHash pair at threshold 5 crosses split; not proof of no missed/semantic leakage. |
| PlantVillage HF/leaf-id code exists | plantvillage.py and CLI output | Partially verified | Implemented but not executed. |
| Kaggle PlantVillage mirrors forbidden | Code and notebook text | Verified | HF is the declared source; Kaggle is explicitly forbidden. |
| PROJECT_BRIEF.md absent | Current inventory | False | It is present and was read fully. |
| No scientific result claimed | Report and old notebooks | Partially verified | Report disclaims results, but old notebook output remains. |
| Package is notebook single source of truth | Notebook import search | False | No notebook imports ica26; duplicated logic remains. |
| Engineering foundation complete | All evidence | False | Required data/control/mapping state is incomplete. |

Claim totals: 11 verified, 7 partially verified, 3 false.

## Specification compliance matrix

| Requirement | Status | Evidence |
|---|---|---|
| Exactly four action classes | PASS | Required tuple/YAML exact. |
| abiotic_correction absent from active action logic | PASS | Forbidden and rejected. |
| Master Plant Disease never used for training | PARTIAL | No package training use found, but no explicit source guard exists. |
| PlantVillage Kaggle mirrors rejected | PASS | HF source fixed; Kaggle declared forbidden. |
| leaf_id preserved and not fabricated | PASS | Original value plus has_leaf_id recorded. |
| Approved mapping requires evidence | PASS | Missing fields fail approval. |
| Unsupported mapping cannot silently validate | PASS | Invalid/forbidden action fails; lookup uses approved rows. |
| Unapproved/missing mappings explicitly counted | PARTIAL | Ordinary action metric counts them; selective action path drops unmapped truths. |
| Harm weights not asserted as established truth | PARTIAL | Package is labelled example-only; notebook 05 conflicts. |
| Example harm isolated from production claims | PARTIAL | In package yes; legacy notebook no. |
| Severity not a completed contribution | PARTIAL | Brief/report demote it; notebook 02 defines intervention tiers despite known flaw. |
| Smoke values not scientific findings | PARTIAL | Report/brief disclaim; stale notebook outputs/figures remain. |
| Cross-dataset metrics cannot run before leakage check | FAIL | No leakage-status parameter, artifact, or refusal in metric functions. |
| Reusable outside notebooks | PASS | Package/CLIs work independently. |
| Colab free-tier suitability | PARTIAL | Core dependencies light, but all-pairs pHash is unsuitable at target scale. |
| PlantDoc completeness established | FAIL | Train incomplete; hard-coded 2,598 differs from live 2,578 image enumeration. |
| PlantVillage acquisition executed/verified | NOT TESTED | Optional datasets dependency absent; CLI blocked correctly. |
| Cross-dataset leakage checked before cross work | FAIL | PlantVillage absent; no cross check exists. |
| Evidence-backed action mapping started | FAIL | All 27 rows pending, none approved. |
| Majority baseline and harm control available | PASS | Both functions exist and were hand-checked. |
| Double-blind/release discipline | PARTIAL | Interim data has personal absolute paths; ignores are incomplete. |

Requirement totals: 9 PASS, 7 PARTIAL, 4 FAIL, 1 NOT TESTED.

## Commands executed

| Command | Exit | Result |
|---|---:|---|
| python --version | 0 | Python 3.13.9 |
| python -m pip --version | 0 | pip 25.3 |
| python -m pip install -e . (sandboxed) | 1 | DNS prevented fetching setuptools build dependency. |
| python -m pip install -e . (approved network retry) | 0 | Editable installation completed. |
| python -m pytest -q | 0 | 52 tests passed. |
| ./scripts/run_phase1_checks.sh | 0 | Tests, taxonomy, local manifest, mapping validation, and leakage completed. |
| python -m ica26.datasets.plantvillage --limit 1 | 2 | Expected loud block because datasets is not installed. |
| Read-only GitHub PlantDoc tree query | 0 | 2,578 recognized images: train 2,342/28 classes, test 236/27 classes. |

The bundled check regenerated existing manifest/mapping/leakage artifacts as designed. No production source was edited.

## Test-quality assessment

Tests are deterministic synthetic unit tests. They exercise action enums, invalid actions, missing evidence fields, pHash equality/boundaries, corrupt-file recording, ordering, ordinary metric arithmetic, and selected selective-prediction cases. No tests are skipped or xfailed.

Limitations:

- The approved-evidence fixture is fabricated non-empty text. It proves field presence, not source authority, URL/identifier/date validity, or agronomic support.
- No test proves that cross-dataset metrics refuse to run until a persisted leakage pass exists; no such production gate exists.
- No test compares a remote source listing with a partial local acquisition.
- No pHash time/memory benchmark covers target scale.
- No test detects notebook/package divergence.
- No test prevents a training workflow from accepting Master Plant Disease data.

Independent temporary checks showed that missing evidence, unknown actions, and abiotic_correction fail; majority ties are deterministic; zero-retained coverage produces coverage zero and NaN; one sample/all-equal confidence behave deterministically; exact pairs are found; a two-bit pair appears at threshold two but not one; and an all-bit-different pair is not flagged at threshold five.

## Dataset and manifest findings

### PlantDoc

| Check | Finding |
|---|---|
| Direct local split images | 636 |
| Manifest rows | 636 |
| Filesystem versus manifest paths | 0 missing in either direction |
| Local train | 400 images, 6 classes |
| Local test | 236 images, 27 classes |
| Live source tree | 2,342 train plus 236 test equals 2,578 images; 28/27 classes |
| Train-only source class | Tomato two spotted spider mites leaf |
| Train completeness | 400/2,342 = 17.1% |
| Test completeness | 236/236 = 100% by live source tree |
| Corrupt local records | 0 |
| Independent SHA samples | 3/3 match manifest |
| Independent image opens | 3/3 verified |
| Duplicate output | 4 exact, 0 near at threshold 5 |

The manifest is trustworthy as an inventory of the local subset, not as evidence of a complete acquisition. Its expected total of 2,598 is not supported by the current live source enumeration of 2,578. The four exact duplicate pairs are all within training/class directories and should be removed or grouped before training.

### PlantVillage

Implementation targets the authoritative HF repository mohanty/PlantVillage and supports color, grayscale, and segmented. It records leaf_id and has_leaf_id and reports partial/no grouping rather than creating IDs. The CLI blocked loudly because datasets is not installed. Therefore it is implemented, not executed; no actual source fields, counts, missing IDs, or grouped split have been verified.

## Metric implementation audit

Hand example: f1 and f2 map to fungicide, v to remove_vector, h to monitor. True labels were [f1,f2,v,h], predictions [f2,v,f1,h].

| Metric | Expected | Actual | Result |
|---|---:|---:|---|
| Disease top-1 | 1/4 = 0.25 | 0.25 | PASS |
| Action accuracy | 2/4 = 0.50 | 0.50 | PASS |
| Majority action | fungicide, 2/4 = 0.50 | fungicide, 0.50 | PASS |
| Example harm error | (0+2+4+0)/4 = 1.50 | 1.50 by implementation | PASS |
| Asymmetry | remove_vector to fungicide=4; reverse=2 | 4 and 2 | PASS |
| Unmapped accounting | true-unmapped excluded, pred-unmapped wrong | total=2, included=1, excluded=1, score=0 | PASS |
| Selective disease/zero/one/equal cases | Deterministic | Deterministic | PASS |
| Selective action unmapped coverage | Original total visible | Dropped before table | PARTIAL |
| Leakage prerequisite for cross metrics | Must block | No mechanism | FAIL |

Action projection mechanically inflates accuracy in the hand example from 0.25 to 0.50. Any scientific report must therefore include disease accuracy, action distribution, majority-action baseline, and harm together. The available harm matrix is not scientifically usable until reviewed weights exist.

## Leakage implementation and scalability

Correctness checks passed: exact and near pairs are separated; near means 0 < distance <= threshold; threshold is inclusive; intra pairs use ia < ib, excluding self and reversed duplicates; output is sorted; dataset/path identity is retained; corrupt/missing paths are reported; and a one-dataset run makes no cross-cleanliness claim.

The implementation computes block-by-all hashes, so it is O(N squared).

| Operation | Approximate comparisons | Assessment |
|---|---:|---|
| 636 intra | 0.2 million unique | Usable; completed fresh. |
| 2,600 intra | 3.4 million unique | Usable. |
| 54,000 intra | 1.46 billion unique (implementation computes full grid) | Not realistic for routine Colab free-tier use. |
| 54,000 by 18,000 cross | 972 million | Impractical/risky without candidate indexing/pruning. |

This is a P0 blocker for full intended-scale leakage checking.

## Scientific-integrity findings

- No plaintext secret, API key, token, password, or actual Kaggle credential was found. Only instructions and a YOUR_KEY placeholder exist.
- data/interim/phash_index.csv contains absolute local paths with a personal username, a double-blind risk.
- The brief and Phase 1 report disclaim 0.414/407-image smoke work, but old notebook 05 retains a hard-coded harm matrix and a stored risk-weighted output including 0.746.
- Notebook 02 retains fixed severity-to-intervention boundaries despite the brief's documented target-domain segmentation flaw.
- No automatic approved action mapping was found; every active template row is pending.
- No evidence of Master Plant Disease training was found, but no durable source restriction prevents it.
- The PlantDoc live source was independently checked. Other report citations were not accepted merely because the report says they were fact-checked.

## PROJECT_BRIEF contradiction check

| Conflict | Severity |
|---|---|
| No approved evidence-backed mapping exists for the central contribution | BLOCKER |
| Cross-dataset metrics are not blocked pending leakage clearance | BLOCKER |
| pHash all-pairs algorithm is not viable at intended 54k-scale | BLOCKER |
| Notebook 05 hard-coded harm/output conflicts with example-only/no-result constraints | BLOCKER |
| Brief/code count 2,598 conflicts with current source tree count 2,578 | MAJOR |
| PlantDoc train is only 400/2,342 | MAJOR |
| PlantVillage is not acquired or leaf-grouped | MAJOR |
| Notebook 02 defines severity tiers despite severity demotion/flaw | MAJOR |
| Report calls package single source of truth but notebooks do not import it | MAJOR |
| No version control | MINOR |
| Incomplete ignores plus interim PII | MAJOR |

## Blockers

1. No approved authoritative disease-to-action mapping.
2. No enforceable leakage-clearance gate.
3. O(N squared) leakage implementation at intended scale.
4. PlantVillage unacquired and leaf grouping unverified.
5. Incomplete PlantDoc train and unresolved 2,598 versus 2,578 source-count discrepancy.
6. Conflicting notebook harm/severity logic.

## Required fixes

### P0 — before any Phase 2

- Build a real reviewed mapping with authoritative evidence and make an empty approved lookup a hard stop for action evaluation.
- Persist leakage clearance and require it for every cross-dataset metric/report.
- Replace all-pairs full-scale leakage with scalable candidate indexing and benchmark it.
- Reconcile/record PlantDoc source revision and count.
- Quarantine or remove hard-coded notebook harm/severity outputs.

### P1 — before model training

- Complete and verify PlantDoc acquisition.
- Execute PlantVillage HF acquisition, manifest it, disclose missing leaf_id counts, and verify grouped-split handling.
- Resolve the four PlantDoc exact training duplicates.
- Preserve original/unmapped counts in selective-action metrics.
- Add integration tests for provenance, leakage refusal, remote/local completeness, and notebook/package parity.

### P2 — before paper submission

- Remove personal paths and non-anonymous artifacts.
- Expand ignore rules for credentials, weights, trackers, and generated outputs.
- Validate each mapping source, harm rationale, dataset/license statement.
- Ensure smoke figures/notebooks cannot be mistaken for results.

### P3 — recommended

- Add input-length validation to metrics.
- Record pHash threshold/version/hash-size provenance.
- Make notebooks call package code or deprecate duplicate logic.

## Explicit answers

| Question | Answer |
|---|---|
| Is Phase 1 actually complete? | No. |
| Can PlantDoc acquisition be trusted? | Only as a 636-file local-subset manifest, not as complete acquisition. |
| Can PlantVillage acquisition be trusted? | Not yet; implemented but unexecuted. |
| Can the mapping validator be trusted? | For syntax/non-empty fields only, not scientific evidence validation. |
| Can the metrics be trusted? | Core arithmetic yes; required scientific workflow no. |
| Can leakage be trusted at intended scale? | No; correct on small inputs but O(N squared). |
| Is repository ready for Phase 2? | No. |
| Is any existing result publishable? | No. |

## Exact recommended next step

Before any Phase 2 work, perform a narrow Phase 1 remediation that makes action and cross-dataset evaluation fail closed: establish a non-empty authoritative mapping and a persisted, scalable leakage-clearance gate before any model or metric workflow can run.

