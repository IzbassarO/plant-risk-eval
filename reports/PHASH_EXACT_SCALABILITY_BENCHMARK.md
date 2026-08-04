# pHash search: complexity and scalability evidence

**This report was rewritten in R2B.2. Its previous version was wrong.**

The earlier version claimed the recursive striped partition's "quadratic
enumeration is either explicitly bounded or output-required", and offered
operation counts as evidence of bounded total work. That claim is **withdrawn**.
It described the work done at each *leaf* and did not account for the same pair
being re-visited through every block it agrees on, which is what actually
determines total cost. On a dense cluster of mutually-near hashes the traversal
amplifies without bound.

The measurement that falsified it, at threshold 6 over 64-bit hashes:

| n (mutually near) | Recursive striped | Scalar brute force |
| ---: | --- | ---: |
| 50 | 0.085 s | 0.048 s |
| 100 | **did not finish in 60 s** | 0.187 s |
| 150 | **did not finish in 60 s** | 0.421 s |
| 200 | **did not finish in 60 s** | 0.734 s |
| 300 | **did not finish in 60 s** | 1.681 s |

The striped implementation has been removed from the production path. No
recursive or indexing amplification remains.

---

## What the search does now

Exact chunked brute-force Hamming evaluation over distinct fixed-width hash
values. Hashes are packed into an `(n, words)` uint64 matrix; a block of left
values is XORed against a block of right values, popcounted one 64-bit word at a
time, and pairs within the radius are kept. Intra-dataset evaluates the upper
triangle; cross-dataset evaluates the complete Cartesian product. The full
all-pairs matrix is never allocated.

## Complexity — stated, not implied

| Property | Value |
| --- | --- |
| Cross-dataset search | **O(N × M)** exact distance evaluations |
| Intra-dataset search | **O(N² / 2)** exact distance evaluations |
| Output-sensitive | **No** |
| Peak working memory | Bounded by the chunk size, independent of input size |
| Chunk pair budget | 1,048,576 pairs |

**This is not subquadratic and does not claim to be.** No claim of bounded total
work appears anywhere in this report or in the code.

### Four properties that are easy to confuse

- **Output-sensitive methods** do work proportional to what they find. They can
  be fast on sparse data and degrade unpredictably when the output is large or
  the input is adversarially structured. The withdrawn implementation was of this
  kind, and its failure mode was exactly that degradation.
- **Exact full evaluation** does a fixed amount of work determined only by the
  input size. It is more work on easy inputs and cannot blow up on hard ones.
- **Predictable runtime** follows: the evaluation count is knowable before the
  run, from `N` and `M` alone.
- **Bounded peak memory** is a separate property from complexity. It is set by
  the chunk size, so 50 million pairs cost the same working set as 500 thousand.

## Completeness

There is no completeness argument to get wrong, which is the point. Nothing is
pruned and no candidate set is built, so every possible distinct-hash pair
receives an exact popcount. The invariant is arithmetic rather than structural:

```
n_distance_evaluations == n_possible_pairs
```

`candidate_search_audit_fields` refuses any summary where those disagree, so a
regression toward pruning cannot publish itself as complete. Correctness is
additionally checked against a scalar oracle (`brute_force_duplicates`) that
shares no code with the implementation — Python ints and `int.bit_count`, not
numpy words and chunking — so parity is evidence rather than a tautology.

## Benchmark

Deterministic operation counters and the peak chunk size are the regression
criterion; elapsed time is informational and is never persisted.

```console
./.venv/bin/python -m ica26.leakage.phash \
  --benchmark --benchmark-fixture dense-band-near-empty \
  --benchmark-sizes 1000,10000 --threshold 6
./.venv/bin/python -m ica26.leakage.phash \
  --benchmark --benchmark-fixture dense-true-output \
  --benchmark-sizes 300 --threshold 6
```

| Fixture | n | Possible pairs | Exact evaluations | Output pairs | Chunks | Chunk dims | Peak chunk pairs | Est. peak bytes | Seconds |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| sparse (dense-band-near-empty) | 1,000 | 499,500 | 499,500 | 0 | 1 | 1000×1000 | 1,000,000 | 56,000,000 | 0.02 |
| sparse (dense-band-near-empty) | 10,000 | 49,995,000 | 49,995,000 | 0 | 55 | 1024×1024 | 1,048,576 | 58,720,256 | 0.46 |
| dense true-output | 300 | 44,850 | 44,850 | 44,850 | 1 | 300×300 | 90,000 | 5,040,000 | 1.75 |
| acquired corpus (real) | 54,305 × 2,578 | 136,847,443 | 136,847,443 | 16 | 162 | 1024×1024 | 1,048,576 | 58,720,256 | 1.1 |
| Core corpus (real) | 54,305 × 2,561 | 136,630,311 | 136,630,311 | 16 | 162 | 1024×1024 | 1,048,576 | 58,720,256 | 1.1 |

Two things to read off this table. The 300-item dense cluster — the case the
withdrawn implementation could not finish — returns all 44,850 true pairs in
1.75 s, and 44,850 is both the output count and the complete possible-pair count
for 300 items. And a hundredfold increase in pairs (1,000 → 10,000 sparse) leaves
the peak chunk unchanged, which is what chunking is for.

## Live invariance

Recomputing the acquired corpus (PlantVillage 54,305 × PlantDoc 2,578) returns
**0 exact** and **16 near** pairs whose identities are byte-identical to the 16
recorded human decisions. The Core corpus (× 2,561) was computed independently
and also returns 0 exact and 16 near, with an identical near-pair identity set:
none of the 16 involved a conservatively excluded record.

No pair decision, exclusion, image, label, split, or scientific artifact was
changed by the search rewrite or by this benchmark.
