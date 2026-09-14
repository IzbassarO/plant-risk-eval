# R2B.1 critical-remediation evidence

## Scope and outcome

This record covers only the five current R2B.1 control-plane findings. It does
not change duplicate adjudication, G01–G12 decisions, retained or excluded
identities, labels, splits, image bytes, mappings, human approvals, audit
sign-offs, or Dataset V1's freeze state.

Dataset V1 remains **not frozen**. Its phase gate is mechanically healthy but
scientifically blocked by six real human or independent-audit decisions. A
technical artifact cannot substitute for any of those decisions.

## Finding-by-finding remediation

| Finding | Fail-closed remediation | Evidence |
| --- | --- | --- |
| 1. pHash candidate indexing | Replaced insertion-order BK trees with exact recursive striped Hamming partitioning over distinct fixed-width hashes. It records candidate checks, exact distance evaluations, recursive partitions, memberships, and leaf bounds. | `src/ica26/leakage/phash.py`; `tests/test_phash_scalability.py`; [PHASH_EXACT_SCALABILITY_BENCHMARK.md](PHASH_EXACT_SCALABILITY_BENCHMARK.md) |
| 2. G07/G08/G10 second review | Requires exactly three self-contained, packet-bound group records; each independently validates identities, byte hashes, canonical record and label, reviewer, timestamp, rationale, citations, decision, confidence, and action. | `src/ica26/governance/second_review.py`; `tests/test_governance_approvals.py` |
| 3. Approval self-staleness | Version 2 approvals bind `reviewed_repository_commit`, not their own later record commit. Git ancestry, reviewed blobs, current blobs, one-time record introduction, and current worktree equality are all required. | `src/ica26/governance/approvals.py`; synthetic Git-history tests |
| 4. PlantVillage persisted provenance | The source snapshot and summary now use a versioned, manifest-bound provenance schema with all four authoritative components, immutable locators, SHA-256 values, byte counts, and verification state. | `src/ica26/datasets/plantvillage.py`; `tests/test_plantvillage_pinning.py` |
| 5. Arbitrary freeze JSON | The runner validates a deterministic technical freeze record, exact frozen bytes/Git blobs, readiness, approval, audit, review, mapping, harm, and reconstructed dataset fingerprint. Absent is `BLOCKED`; present-invalid is `HARD_FAILURE`. | `src/ica26/governance/freeze.py`; `scripts/materialize_dataset_v1_freeze.py`; `tests/test_governance_freeze.py` |

## Exact pHash search

For a Hamming radius `t`, the implementation partitions unresolved positions
into `t + 1` disjoint striped blocks. A pair within radius `t` must agree in one
block, so recursively following equal-block buckets has complete recall. A leaf
performs full popcounts only for at most 512 candidate pairs, unless the
remaining unresolved bit count proves every pair is a true output. No BK-tree,
global candidate-pair set, or unbounded candidate bucket is constructed.

| Dense-band, near-empty fixture | Candidate checks / exact evaluations | Output pairs | Elapsed |
| --- | ---: | ---: | ---: |
| 1,000 hashes | 15,652 | 0 | 0.017 s |
| 10,000 hashes | 196,854 | 0 | 0.677 s |

The 10,000-item run evaluates 0.394% of its 49,995,000 possible pairs. A dense
true-output fixture returns all 496 required pairs and evaluates exactly 496
distances. Differential tests cover random, duplicate, intra-dataset,
cross-dataset, boundary, threshold 0–11, and deterministic-order fixtures.

## Strict second-review contract

The human artifact remains absent. If supplied, its `groups` list must contain
exactly G07, G08, and G10, one record each. `agree` is the only terminal
decision that can satisfy readiness; `uncertain` and `disagree` remain blocked.

| Invalid input | Result |
| --- | --- |
| generic verdict/citation arrays or arbitrary strings | rejected |
| missing, extra, duplicate, or contradictory group | rejected |
| placeholder reviewer, rationale, citation, timestamp, or action | rejected |
| mismatched packet digest, member identity/hash, or canonical identity/label | rejected |
| one group attempting to supply another's evidence | rejected |
| `uncertain` treated as approval | rejected and remains blocked |

## Reviewed-state approval and technical freeze workflow

```text
reviewed commit (exact approved blobs)
        |
        v
human approval record in one descendant commit
        |  validates ancestry + reviewed/current Git blobs
        v
fresh, decision-free readiness report
        |
        v
one-file technical-freeze successor commit
        |  validates exact dependencies + Dataset V1 fingerprint
        v
valid frozen Dataset V1
```

The technical record cannot be written unless all human and audit decisions are
already valid. It is intentionally absent in this repository. The checker
rejects `{}`, ready-looking JSON, wrong schema/type, copied/stale records,
missing approval/review/audit artifacts, changed manifests, changed mappings or
harm matrix, mismatched reviewed states, and dirty/uncommitted evidence.

## Persisted PlantVillage components

| Component | Immutable revision | SHA-256 verified | Bytes |
| --- | --- | --- | ---: |
| `data.zip` | `9e97599868962bd0079b8db4b7f1efa9185fa1e7` | yes | 2,184,723,441 |
| `splits/color_train.txt` | same | yes | 4,151,500 |
| `splits/color_test.txt` | same | yes | 1,018,650 |
| `leaf_grouping/leaf-map.json` | same | yes | 2,429,879 |

The source snapshot and summary both bind the exact current PlantVillage
manifest SHA-256 `b9acc43637ef2e930bd9e5e8a09b1d5025c720d65f9dd3fc9aabdfbd7e399591`
and validate its 54,305 records before readiness can satisfy this machine
condition.

## Invariance and current state

| Invariant | Result |
| --- | --- |
| PlantDoc effective manifest | 2,564 records; SHA-256 `36ee9ece519d11dd0f38aed53d6177fe19728349025665ebd843b2ab9c4cb3fc` |
| PlantVillage manifest | 54,305 records; SHA-256 `b9acc43637ef2e930bd9e5e8a09b1d5025c720d65f9dd3fc9aabdfbd7e399591` |
| Cross-dataset pHash result | 0 exact, 16 near, 16 resolved, 0 unresolved |
| Pair/review decisions | authenticated pair and review artifacts byte-unchanged |
| Dataset V1 | not ready, not frozen; 9 satisfied and 6 real human/audit blockers |

No scientific review, mapping approval, harm approval, audit sign-off, freeze
approval, or technical freeze record has been fabricated. No training was
started.
