# Exact pHash Search Scalability Evidence

This report records the deterministic R2B.1 Finding 1 adversary.  It is a
technical benchmark, not a scientific decision or approval.

## Implementation and completeness

The near search operates on distinct fixed-width hash values.  At each task it
stripes every unresolved bit position across `threshold + 1` non-empty disjoint
blocks.  A pair whose Hamming distance is at most `threshold` must agree on at
least one complete block; otherwise every block would contain a mismatch and
the distance would be at least `threshold + 1`.  Equal-block buckets recurse
after removing the bits known equal.  Only pair products of at most 512 reach
exact popcount verification.  If at most `threshold` unresolved bits remain,
every enumerated pair is a true output.  Thus the recursion has complete recall,
and quadratic enumeration is either explicitly bounded or output-required.

The index does not build a BK-tree, a global candidate-pair set, or an unbounded
bucket pair list.  `n_distance_evaluations` is incremented at the only full
Hamming-popcount call site.

## Reproduction

```console
./.venv/bin/python -m ica26.leakage.phash \
  --benchmark --benchmark-fixture dense-band-near-empty \
  --benchmark-sizes 1000,10000 --threshold 6
```

The fixture applies SplitMix64 deterministically, clears the same contiguous
9-bit band in every value, and removes any post-mask collision until the exact
requested distinct count is reached.  It has zero output pairs at both sizes.

| Items | All possible pairs | Candidate checks | Exact distance evaluations | Partition tasks | Partition memberships | Output pairs | Elapsed seconds |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1,000 | 499,500 | 15,652 | 15,652 | 1,510 | 7,000 | 0 | 0.017 |
| 10,000 | 49,995,000 | 196,854 | 196,854 | 73,478 | 512,715 | 0 | 0.677 |

Elapsed time is informational; deterministic operation counters are the
regression criterion.  At 10,000 items, exact distance evaluation covers about
0.394% of all possible pairs.

The complementary dense-output command uses 32 unique hashes mutually within
radius 6.  It returns all 496 true pairs and performs exactly 496 distance
evaluations (0.041 seconds), demonstrating that the exact search does not prune
quadratic output when that output is real.

## Live R2A invariance

A read-only run over the current 54,305-record PlantVillage index and
2,578-record PlantDoc index returns 0 exact pairs and the same 16 near-pair
identities as the authenticated pair CSV.  It performs 655,317 exact distance
evaluations, 1,184 recursive partitions, and 2,043,552 partition memberships.
No pair decision, exclusion, image, label, split, or scientific artifact was
changed by this benchmark.
