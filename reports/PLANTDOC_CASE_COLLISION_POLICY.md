# PlantDoc Case-Collision Policy

**Policy identifier:** `policy:plantdoc-casefold-safe-v1`
**Status:** active — enforced by `src/ica26/datasets/plantdoc.py` and `scripts/restore_plantdoc_collisions.py`
**Addresses:** AUD-EC-003 (`reports/PHASE1_CODEX_AUDIT_EC482333.md` §H)

_Data-integrity policy. It does not decide any duplicate, exclusion, split, or scientific
label._

## 1. The defect

The upstream PlantDoc tree at the pinned commit `5467f601` is **case-sensitive** and contains
paths that differ only by letter case:

```
train/Apple rust leaf/CAR1.jpg      sha ff8e8450…  249,767 B  498x841
train/Apple rust leaf/car1.jpg      sha da3a9af4…   43,509 B  320x320
```

Extracted onto a **case-insensitive** filesystem (macOS APFS, NTFS) the second member
overwrites the first. The loss is silent: the extractor reports success, the tree looks healthy,
and the manifest — built by scanning that tree — simply never sees the lost image.

Six such groups exist, so 12 upstream records collapsed to 6 files and the active manifest held
**2,572** of **2,578** upstream images.

**This is an artifact of the extraction filesystem, not a property of the data.** The audit
compared every group member directly against the pinned archive: within every group the members
differ in bytes, in file size, in pixel dimensions, and in decoded RGB pixel hash. They are not
duplicates, not re-encodings, and not near-duplicates.

## 2. Policy

1. **A case-insensitive filename collision never justifies dropping a distinct source record.**
   Losing an image because *another file's name differs only in capitalisation* is a filesystem
   accident, not a data decision.
2. **Every distinct upstream SHA-256 must remain representable** in the active,
   model-consumable dataset — not merely recoverable from a side directory.
3. **The original archive-member path is retained as provenance** for every record, in
   `data/manifests/plantdoc_source_inventory.csv` and
   `data/manifests/plantdoc_case_collision_mapping.csv`.
4. **Active filesystem paths must be deterministic and unique** under Unicode-NFC casefold, so
   the same tree materialises identically on case-sensitive and case-insensitive systems.
5. **The policy applies before manifest generation.** A manifest may never be built from a tree
   that has not been asserted collision-safe.
6. **No scientific label changes.** Split and class come from upstream provenance, untouched.

## 3. Mechanism

Every member of a colliding group — not just the loser — receives a content-disambiguated
filename:

```
<stem>__<first 12 hex of its own SHA-256><ext>
```

```
train/Apple rust leaf/CAR1.jpg  ->  train/Apple rust leaf/CAR1__ff8e845061e3.jpg
train/Apple rust leaf/car1.jpg  ->  train/Apple rust leaf/car1__da3a9af451c8.jpg
```

Casefolded, these are `car1__ff8e845061e3.jpg` and `car1__da3a9af451c8.jpg` — distinct, because
the members' SHA-256 values differ, which is exactly what makes them distinct records.

Disambiguating **all** members rather than only the overwritten one is deliberate: it removes any
notion of a member "winning" the natural path by extraction order, so the layout is a pure
function of content and upstream name, with no dependence on iteration order, locale, or
filesystem. Non-colliding files (2,566 of 2,578) keep their upstream names untouched.

Directory and extension are never altered, so class and split remain exactly where upstream put
them.

## 4. Authority and safety

- The **pinned source archive** is the authority for bytes. Every restored file is read from
  `data/raw/plantdoc/_archive/plantdoc-5467f6012d78.tar.gz` and its SHA-256 and byte size verified
  against the inventory *before* being written. Nothing is copied out of the possibly-clobbered
  active tree.
- The **inventory** is the authority for which records exist. Collision groups are recomputed
  from casefold keys and cross-checked against the recorded `collision_group` labels; disagreement
  aborts.
- **Distinctness is re-proved at restore time.** If two members of a group shared a SHA-256, or
  shared a decoded-pixel hash, the script refuses to restore them — that would be a true duplicate
  or a re-encoding, and the correct response would be a human duplicate decision, not a rename.
- **No source image is deleted.** An ambiguous natural-path file is removed only after *both*
  members of its group are verified present at collision-safe paths, and the independent
  `data/raw/plantdoc/_collisions/` copies are left untouched.
- Writes are atomic (temp file + `os.replace`); any verification failure aborts before writing.

## 5. Result

| Quantity | Before | After |
|---|---:|---:|
| Upstream records (inventory) | 2,578 | 2,578 |
| Active manifest records | 2,572 | **2,578** |
| Distinct SHA-256 in manifest | 2,560 | **2,566** |
| Train / test | 2,336 / 236 | **2,342 / 236** |
| Train / test classes | 28 / 27 | 28 / 27 |
| Casefold path collisions | 6 | **0** |
| Corrupt / zero-byte | 0 / 0 | 0 / 0 |

The manifest SHA-256 multiset is now **identical** to the inventory's: every upstream record is
represented exactly once, with no surplus and nothing dropped.

Restored images:

| Group | Upstream path | SHA-256 prefix | Active path |
|---|---|---|---|
| cg01 | `train/Apple rust leaf/CAR1.jpg` | `ff8e845061e3` | `train/Apple rust leaf/CAR1__ff8e845061e3.jpg` |
| cg02 | `train/Blueberry leaf/blueberry-leaf.jpg` | `a488765c32aa` | `train/Blueberry leaf/blueberry-leaf__a488765c32aa.jpg` |
| cg03 | `train/Blueberry leaf/blueberry-leaves.jpg` | `2e99aae9cb26` | `train/Blueberry leaf/blueberry-leaves__2e99aae9cb26.jpg` |
| cg04 | `train/Corn leaf blight/northern-corn-leaf-blight.jpg` | `2c2cc7cec2c4` | `train/Corn leaf blight/northern-corn-leaf-blight__2c2cc7cec2c4.jpg` |
| cg05 | `train/Peach leaf/peach-leaf.jpg` | `0571261a682b` | `train/Peach leaf/peach-leaf__0571261a682b.jpg` |
| cg06 | `train/Potato leaf early blight/…-a60hxn.jpg` | `0ea1317f5e20` | `train/Potato leaf early blight/…-a60hxn__0ea1317f5e20.jpg` |

Full per-member detail, including the six members that were already present, is in
`data/manifests/plantdoc_case_collision_mapping.csv`.

## 6. Out of scope — pre-existing upstream byte duplicates

Separately from case collisions, the upstream tree contains **12 SHA-256 values that each appear
at two different paths** (2,578 records over 2,566 distinct digests). Several cross split *and*
class, for example:

```
test/Corn leaf blight/2015070295153021.jpg
train/Corn Gray leaf spot/2015070295153021.jpg      <- same bytes, different class
```

These are genuine upstream duplicates, they were present in the 2,572-image manifest too, and
restoring the six collision images neither created nor removed any of them. **This policy does
not decide them.** They are recorded here because a train/test byte duplicate carrying two
different class labels is a real scientific issue for any future split or evaluation, and it needs
a human decision that has not been made. Deleting them here would be exactly the kind of
unreviewed data decision this policy exists to prevent.
