# Healthy-Class Action Policy

**Policy identifier:** `policy:healthy-monitor-v1`
**Decided by:** `human_reviewer_1`
**Decided at:** `2026-08-02T21:10:00+05:00`
**Status:** active — encoded in `src/ica26/schemas.py` and enforced by `src/ica26/mapping/validation.py`

_Governance document. It does not approve any disease mapping, does not add or remove an
action class, and does not weaken the general evidence gate._

## 1. What a healthy class is

A healthy class is a **negative diagnosis class**: the leaf shows no disease. It is *not* a
disease of unknown aetiology, and it is *not* a pathogen whose identity is merely unrecorded.
There is nothing to cite because there is nothing to diagnose.

This matters because the general evidence gate
(`EVIDENCE_FIELDS_REQUIRED_FOR_APPROVAL` in `src/ica26/schemas.py`) requires
`pathogen_type`, `source_name`, `source_url` and `source_identifier`. For a healthy class those
fields are **unsatisfiable by construction**. Before this policy, the only ways to approve a
healthy row were to fabricate a pathogen and a citation, or to weaken the gate for everyone.
Both are unacceptable, so the exemption below is deliberately narrow instead.

## 2. Diagnosis-level status

Healthy classes **remain fully included** in diagnosis-level classification and evaluation.
No image is removed, no manifest row is deleted, no class is dropped. This policy concerns the
mapping table only.

## 3. Action assignment

Healthy classes map to exactly one action class:

```
canonical_disease = healthy  ->  action_class = monitor
```

This is definitional, not empirical: `monitor` is the action taxonomy's "no immediate chemical
intervention; continue observation" category (`configs/action_taxonomy.yaml`), which is precisely
the correct response to healthy tissue. No other action class may be assigned to a healthy row.

## 4. What is exempted — and what is not

An approved healthy row is exempt from the **pathogen-specific** evidence fields only:

| Field | Healthy row | Rationale |
|---|---|---|
| `pathogen_name` | **must be blank** | no pathogen exists; a value could only be fabricated |
| `pathogen_type` | **must be blank** | same |
| `source_url` | may be blank | there is no pathogen page to cite |
| `source_identifier` | may carry `policy:healthy-monitor-v1` | the policy *is* the provenance |
| `source_name` | may be definitional | e.g. `(definitional: healthy class, no pathogen)` |
| `action_class` | **required, must be `monitor`** | §3 |
| `action_summary` | **required, non-empty** | the row must still say what to do |
| `evidence_summary` | **required, non-empty** | the row must still say why |
| `evidence_checked_at` | **required, non-empty** | the row must still be dated |
| policy citation | **required** | in `source_identifier` or `review_notes` |

Note the first two rows: the exemption does not merely *permit* blank pathogen fields, it
**forbids** populated ones. The exemption therefore cannot be used as a route to smuggle a
fabricated pathogen past the gate — attempting it fails validation.

**No external pathogen source, URL, DOI, or scientific citation is fabricated for any healthy
row.** None was fetched, invented, or inferred.

## 5. Scope of the exemption — exact conditions

The exemption applies to a mapping row if and only if **all** of the following hold:

1. `canonical_disease` is exactly `healthy` (case- and whitespace-insensitive);
2. `review_status` is `approved` (a non-approved row is not gated at all);
3. `action_class` is exactly `monitor`;
4. `action_summary` is non-empty;
5. `evidence_summary` is non-empty;
6. `evidence_checked_at` is non-empty;
7. `source_identifier` or `review_notes` contains the literal string `policy:healthy-monitor-v1`;
8. `pathogen_name` and `pathogen_type` are both blank.

The exemption **must not** apply to any diseased, ambiguous, unknown, abiotic, or pest class.
Those rows retain every original evidence requirement, unchanged. A class whose
`canonical_disease` is anything other than `healthy` — including blank, `unknown`, `abiotic`, or
an arthropod pest — is validated by the general gate exactly as before.

## 6. Implementation

| Concern | Location |
|---|---|
| Constants (`HEALTHY_*`), `is_healthy_disease()` | `src/ica26/schemas.py` |
| Validator branch `_check_healthy_approval()`, `cites_healthy_policy()` | `src/ica26/mapping/validation.py` |
| Closeout re-check (stdlib mirror) | `scripts/validate_phase1_review.py` |
| Tests | `tests/test_healthy_policy.py` |

The general evidence gate is untouched: `validate_mapping()` branches on the healthy predicate
and otherwise runs the original `EVIDENCE_FIELDS_REQUIRED_FOR_APPROVAL` loop verbatim.

## 7. Rows approved under this policy

Ten PlantDoc healthy classes, all `monitor`, recorded `2026-08-02T21:10:00+05:00` by
`human_reviewer_1`:

`Apple leaf` · `Bell_pepper leaf` · `Blueberry leaf` · `Cherry leaf` · `Peach leaf` ·
`Raspberry leaf` · `Soyabean leaf` · `Strawberry leaf` · `Tomato leaf` · `grape leaf`

They appear in `data/mapping/action_mapping_review.csv` (`review_status=approved`) and are
transcribed to `data/mapping/action_mapping_approved.csv` by
`scripts/apply_action_mapping_review.py`.

No PlantVillage row is approved under this policy yet — the 38-class PlantVillage action mapping
has not been authored. The policy is written generically and will apply to PlantVillage healthy
classes unchanged when that mapping is reviewed.

## 8. Audit trail

Every approved healthy row carries `reviewer`, `reviewed_at`, the policy identifier, and a
`review_notes` sentence naming this document. `scripts/apply_action_mapping_review.py` copies all
four into the canonical mapping, so the exemption is traceable from any downstream metric back to
the human who granted it.
