# How to review this packet

_This directory is a decision-neutral review packet for the byte-exact duplicate records inside PlantDoc (R1-CRIT-002). Nothing in it has been decided._

## Files

| File | Purpose |
|---|---|
| `PLANTDOC_EXACT_DUPLICATE_HUMAN_REVIEW.md` | The checklist. Read this first. |
| `plantdoc_exact_duplicate_groups.csv` | One row per group. **Write decisions here.** |
| `plantdoc_exact_duplicate_members.csv` | Two immutable evidence rows per group. Do not edit. |
| `contact_sheet_*.png` | Full uncropped images of both members. Derived review aids, regenerated locally; not tracked. |
| `packet_manifest.json` | SHA-256 of every tracked artifact above, for integrity checking. |

## Steps

1. Open the contact sheets and look at each pair. The bytes are already proved identical; you are judging what that means scientifically.
2. For each group, fill in these columns of `plantdoc_exact_duplicate_groups.csv`:
   `group_handling_decision`, `canonical_label_decision`, `split_handling_decision`, `decision_reason`, `reviewer`, `reviewed_at`.
3. Use an anonymous reviewer identifier (e.g. `human_reviewer_1`) — the submission is double-blind. Never write a real name, email, or account.
4. `reviewed_at` must be strict ISO-8601 **with a timezone offset**, e.g. `2026-08-03T14:30:00+05:00`. Blank, naive, or future timestamps are rejected.
5. Leave `plantdoc_exact_duplicate_members.csv` untouched; it is evidence, not a form.
6. Re-run `python scripts/build_plantdoc_internal_duplicate_gate.py` to see the status move from `incomplete` toward `pass`.

## Rules

- All **12** groups need a terminal decision; a partially decided packet stays `incomplete`.
- `needs_further_review` is allowed but resolves nothing.
- Do not delete, relabel, or move any record by hand. Record the decision here; the pipeline applies it in a later, separately audited step.

## Regenerating

`python scripts/build_plantdoc_duplicate_packet.py` is deterministic and preserves any decisions already recorded in the groups CSV. `--check` verifies the packet is current without writing.
