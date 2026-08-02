#!/usr/bin/env python
"""Phase-1 closeout: validate the returned human-review decisions (READ-ONLY).

Deterministic, stdlib-only validator for the Phase-1 human-review packet. It
reads the reviewed artifacts and the authoritative pipeline outputs, checks every
row, and emits a machine-readable finding table plus a summary.

    python scripts/validate_phase1_review.py

Outputs (overwritten; nothing else is touched):
    data/interim/phase1_review_validation.csv
    data/interim/phase1_review_validation_summary.json

Guarantees:
  * NO reviewed source file is modified, moved, or reinterpreted.
  * NO decision is inferred, defaulted, or filled in. A blank decision is
    reported as a blocker -- never resolved.
  * NO duplicate status is inferred from filenames; pair identity comes from the
    authoritative pHash pair table and the recorded SHA-256 values.
  * Output row order is fully sorted, so repeated runs are byte-identical
    (the summary JSON carries the only timestamp, and it is metadata only).

Exit codes: 0 = no blockers, 1 = blockers present, 2 = a required input is absent.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# --------------------------------------------------------------------------- #
# Authoritative vocabularies. Mirrored from src/ica26/schemas.py and from the
# review guides; duplicated here ONLY so this validator runs without the package
# installed. Any divergence is itself reported (check MAP-SCHEMA-VOCAB).
# --------------------------------------------------------------------------- #
ACTION_CLASSES = ("fungicide", "copper_sanitation", "remove_vector", "monitor")
FORBIDDEN_ACTION_CLASSES = frozenset({"abiotic_correction"})
REVIEW_STATUSES = ("pending", "needs_review", "approved", "excluded")
TERMINAL_REVIEW_STATUSES = ("approved", "excluded")  # a human has decided
MAPPING_CONFIDENCES = ("low", "medium", "high")
PATHOGEN_TYPES = ("fungal", "bacterial", "viral", "oomycete", "mite", "abiotic", "unknown")
EVIDENCE_FIELDS_REQUIRED_FOR_APPROVAL = (
    "pathogen_type", "action_class", "action_summary", "source_name",
    "source_url", "source_identifier", "evidence_summary", "evidence_checked_at",
)
#: The review CSV names the action column `candidate_action_class`; the canonical
#: mapping table (src/ica26/schemas.py:MAPPING_COLUMNS) names it `action_class`.
#: `scripts/apply_action_mapping_review.py` is the one-way bridge between them.
REVIEW_ACTION_COLUMN = "candidate_action_class"
CANONICAL_ACTION_COLUMN = "action_class"

#: Narrow healthy-class exemption -- mirrors src/ica26/schemas.py.
#: A healthy class is a NEGATIVE diagnosis class: there is no pathogen, so the
#: pathogen-specific evidence fields are exempt and must stay blank rather than
#: be fabricated. Everything else about the gate is unchanged.
HEALTHY_CANONICAL_DISEASE = "healthy"
HEALTHY_ACTION_CLASS = "monitor"
HEALTHY_POLICY_ID = "policy:healthy-monitor-v1"
HEALTHY_EVIDENCE_FIELDS_REQUIRED_FOR_APPROVAL = (
    "action_class", "action_summary", "evidence_summary", "evidence_checked_at",
)
HEALTHY_FORBIDDEN_FIELDS = ("pathogen_name", "pathogen_type")

#: Arthropod-pest scope decision -- mirrors configs/evaluation_scope.yaml.
ARTHROPOD_POLICY_ID = "policy:arthropod-pest-scope-v1"
ARTHROPOD_SCOPE_REASON = "arthropod_pest_out_of_disease_scope"

#: Allowed human values, from reports/NEAR_DUPLICATE_HUMAN_REVIEW.md.
NDP_DECISIONS = ("same_source_image", "same_scene_different_crop",
                 "visually_similar_but_independent", "clearly_different", "uncertain")
NDP_DISPOSITIONS = ("exclude_evaluation", "keep", "needs_secondary_review")
#: Decisions that may NOT terminate review -- they still need a human follow-up.
NDP_NON_TERMINAL_DECISIONS = ("uncertain",)
NDP_NON_TERMINAL_DISPOSITIONS = ("needs_secondary_review",)

#: Pathogen types that are arthropod pests, not plant pathogens. A row carrying
#: one of these is out of scope for a *plant-disease* class and needs an explicit
#: human scope decision; it is never silently included.
ARTHROPOD_PEST_TYPES = frozenset({"mite"})

PHASH_THRESHOLD = 6

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
NDP_REVIEW = Path("data/exclusions/cross_dataset_near_duplicate_review.csv")
REVIEWED_EXCL = Path("data/exclusions/cross_dataset_reviewed_exclusions.csv")
EXACT_EXCL = Path("data/exclusions/cross_dataset_exact_exclusions.csv")
MAP_REVIEW = Path("data/mapping/action_mapping_review.csv")
MAP_TEMPLATE = Path("data/mapping/action_mapping_template.csv")
MAP_APPROVED = Path("data/mapping/action_mapping_approved.csv")
MAP_APPLY_SCRIPT = Path("scripts/apply_action_mapping_review.py")
MAP_CHECKLIST = Path("reports/ACTION_MAPPING_HUMAN_CHECKLIST.md")
SCOPE_CONFIG = Path("configs/evaluation_scope.yaml")
LEAKAGE_PAIRS = Path("reports/leakage_plantvillage_vs_plantdoc_pairs.csv")
PD_MANIFEST = Path("data/manifests/plantdoc_manifest.csv")
PV_MANIFEST = Path("data/manifests/plantvillage_manifest.csv")

OUT_CSV = Path("data/interim/phase1_review_validation.csv")
OUT_JSON = Path("data/interim/phase1_review_validation_summary.json")

OUT_COLUMNS = ("artifact", "row_identifier", "check_id", "validation_status",
               "reason", "severity", "source_reference")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def blank(v) -> bool:
    return v is None or str(v).strip() == ""


def read_csv(path: Path) -> list[dict]:
    with open(REPO / path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(REPO / path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Findings:
    """Accumulates validation findings. Never mutates any input."""

    def __init__(self) -> None:
        self.rows: list[dict] = []

    def add(self, artifact, row_id, check_id, status, reason, severity, ref) -> None:
        self.rows.append({
            "artifact": artifact, "row_identifier": row_id, "check_id": check_id,
            "validation_status": status, "reason": reason,
            "severity": severity, "source_reference": ref,
        })

    def blocker(self, *a) -> None:
        self.add(*a[:4], a[4], "blocker", a[5])

    @property
    def blockers(self) -> list[dict]:
        return [r for r in self.rows if r["severity"] == "blocker"]

    @property
    def warnings(self) -> list[dict]:
        return [r for r in self.rows if r["severity"] == "warning"]


# --------------------------------------------------------------------------- #
# Artifact A -- cross-dataset near-duplicate review
# --------------------------------------------------------------------------- #
def validate_near_duplicate_review(F: Findings) -> dict:
    art = str(NDP_REVIEW)
    rows = read_csv(NDP_REVIEW)
    pairs = read_csv(LEAKAGE_PAIRS)
    reviewed_excl = read_csv(REVIEWED_EXCL)
    exact_excl = read_csv(EXACT_EXCL)

    # Authoritative pair identity: (training_relpath, evaluation_relpath) from the
    # pHash pair table. NOT inferred from filenames.
    auth = {(p["training_relpath"], p["evaluation_relpath"]): p
            for p in pairs if p.get("classification") == "near"}
    # Manifest membership -- a reviewed pair must still exist in both manifests.
    pd_paths = {r["relpath"] for r in read_csv(PD_MANIFEST)}
    pv_paths = {r["relpath"] for r in read_csv(PV_MANIFEST)}

    seen_ids: set[str] = set()
    seen_keys: set[tuple] = set()
    decided = excluded = kept = unresolved = invalid = 0

    for r in rows:
        pid = (r.get("pair_id") or "").strip()
        rid = pid or "<blank pair_id>"
        key = (r.get("training_relative_path", ""), r.get("evaluation_relative_path", ""))

        # -- identifiers
        if blank(pid):
            F.add(art, rid, "NDP-ID-PRESENT", "invalid_value",
                  "pair_id is blank; the row cannot be referenced", "blocker", art)
            invalid += 1
        elif pid in seen_ids:
            F.add(art, rid, "NDP-ID-UNIQUE", "invalid_value",
                  f"duplicate pair_id '{pid}'", "blocker", art)
            invalid += 1
        seen_ids.add(pid)
        if key in seen_keys:
            F.add(art, rid, "NDP-KEY-UNIQUE", "inconsistent",
                  "duplicate (training_relative_path, evaluation_relative_path)", "blocker", art)
        seen_keys.add(key)

        # -- source / target records
        for col in ("training_dataset", "training_relative_path", "training_class",
                    "training_sha256", "evaluation_dataset", "evaluation_relative_path",
                    "evaluation_class", "evaluation_sha256"):
            if blank(r.get(col)):
                F.add(art, rid, "NDP-RECORD-COMPLETE", "invalid_value",
                      f"required record field '{col}' is blank", "blocker", art)
        for col in ("training_sha256", "evaluation_sha256"):
            v = (r.get(col) or "").strip()
            if v and not re.fullmatch(r"[0-9a-f]{64}", v):
                F.add(art, rid, "NDP-SHA-FORMAT", "invalid_value",
                      f"{col} is not a lowercase 64-hex SHA-256", "blocker", art)

        # -- pair must still exist in the authoritative pHash pair table
        if key not in auth:
            F.add(art, rid, "NDP-PAIR-AUTHORITATIVE", "inconsistent",
                  "reviewed pair is absent from the authoritative pHash pair table "
                  "(reviewed pair disappeared, or was never flagged)",
                  "blocker", str(LEAKAGE_PAIRS))
        else:
            a = auth[key]
            try:
                d_rev = int(str(r.get("phash_distance", "")).strip())
            except ValueError:
                d_rev = None
                F.add(art, rid, "NDP-DIST-NUMERIC", "invalid_value",
                      f"phash_distance '{r.get('phash_distance')}' is not an integer",
                      "blocker", art)
            if d_rev is not None:
                if d_rev != int(a["hamming_distance"]):
                    F.add(art, rid, "NDP-DIST-MATCH", "inconsistent",
                          f"phash_distance {d_rev} != authoritative "
                          f"{a['hamming_distance']}", "blocker", str(LEAKAGE_PAIRS))
                if not (0 < d_rev <= PHASH_THRESHOLD):
                    F.add(art, rid, "NDP-DIST-RANGE", "invalid_value",
                          f"phash_distance {d_rev} outside the near band "
                          f"(0 < d <= {PHASH_THRESHOLD})", "blocker", art)

        # -- both endpoints must still be present in their manifests
        if r.get("training_relative_path") and r["training_relative_path"] not in pv_paths:
            F.add(art, rid, "NDP-TRAIN-IN-MANIFEST", "inconsistent",
                  "training image is not in plantvillage_manifest.csv", "blocker", str(PV_MANIFEST))
        if r.get("evaluation_relative_path") and r["evaluation_relative_path"] not in pd_paths:
            F.add(art, rid, "NDP-EVAL-IN-MANIFEST", "inconsistent",
                  "evaluation image is not in plantdoc_manifest.csv", "blocker", str(PD_MANIFEST))

        # -- contact sheet must exist (the human's visual evidence)
        cs = (r.get("contact_sheet") or "").strip()
        if blank(cs):
            F.add(art, rid, "NDP-SHEET-PRESENT", "invalid_value",
                  "contact_sheet is blank", "blocker", art)
        elif not (REPO / cs).exists():
            F.add(art, rid, "NDP-SHEET-EXISTS", "inconsistent",
                  f"contact sheet '{cs}' does not exist on disk", "blocker", art)

        # -- THE HUMAN DECISION (never inferred, never defaulted)
        dec = (r.get("human_decision") or "").strip()
        disp = (r.get("final_disposition") or "").strip()

        if blank(dec):
            F.add(art, rid, "NDP-DECISION-PRESENT", "missing_decision",
                  "human_decision is blank -- the pair has not been adjudicated",
                  "blocker", str(Path("reports/NEAR_DUPLICATE_HUMAN_REVIEW.md")))
            unresolved += 1
        elif dec not in NDP_DECISIONS:
            F.add(art, rid, "NDP-DECISION-ENUM", "unsupported",
                  f"human_decision '{dec}' is not one of {list(NDP_DECISIONS)}",
                  "blocker", str(Path("reports/NEAR_DUPLICATE_HUMAN_REVIEW.md")))
            invalid += 1
        elif dec in NDP_NON_TERMINAL_DECISIONS:
            F.add(art, rid, "NDP-DECISION-TERMINAL", "unresolved",
                  f"human_decision '{dec}' does not resolve the pair; the leakage "
                  "gate cannot pass while any pair is uncertain",
                  "blocker", str(Path("reports/LEAKAGE_GATE_EXCLUSION_POLICY.md")))
            unresolved += 1
        else:
            decided += 1

        if blank(disp):
            F.add(art, rid, "NDP-DISPOSITION-PRESENT", "missing_decision",
                  "final_disposition is blank -- no disposition to apply",
                  "blocker", str(Path("reports/NEAR_DUPLICATE_HUMAN_REVIEW.md")))
        elif disp not in NDP_DISPOSITIONS:
            F.add(art, rid, "NDP-DISPOSITION-ENUM", "unsupported",
                  f"final_disposition '{disp}' is not one of {list(NDP_DISPOSITIONS)}",
                  "blocker", str(Path("reports/NEAR_DUPLICATE_HUMAN_REVIEW.md")))
            invalid += 1
        else:
            if disp == "exclude_evaluation":
                excluded += 1
            elif disp == "keep":
                kept += 1
            if disp in NDP_NON_TERMINAL_DISPOSITIONS:
                F.add(art, rid, "NDP-DISPOSITION-TERMINAL", "unresolved",
                      f"final_disposition '{disp}' defers the decision", "blocker", art)

        # -- attribution is required once a decision exists
        if not blank(dec) or not blank(disp):
            for col in ("reviewer", "reviewed_at"):
                if blank(r.get(col)):
                    F.add(art, rid, "NDP-ATTRIBUTION", "invalid_value",
                          f"'{col}' is blank although a decision was recorded "
                          "(provenance is required)", "blocker", art)
            if not blank(r.get("reviewed_at")) and not re.fullmatch(
                    r"\d{4}-\d{2}-\d{2}([T ].*)?", r["reviewed_at"].strip()):
                F.add(art, rid, "NDP-REVIEWED-AT-FORMAT", "invalid_value",
                      f"reviewed_at '{r['reviewed_at']}' is not ISO-8601", "warning", art)

        # -- an exclusion decision must be carried into the reviewed-exclusions file
        if disp == "exclude_evaluation":
            hit = [x for x in reviewed_excl
                   if x.get("training_relative_path") == key[0]
                   and x.get("evaluation_relative_path") == key[1]]
            if not hit:
                F.add(art, rid, "NDP-EXCL-PROPAGATED", "inconsistent",
                      "decided exclude_evaluation but the pair is absent from "
                      "cross_dataset_reviewed_exclusions.csv", "blocker", str(REVIEWED_EXCL))

        # -- fully clean row
        if not any(f["row_identifier"] == rid and f["artifact"] == art for f in F.rows):
            F.add(art, rid, "NDP-ROW", "pass", "all checks passed", "info", art)

    # ---- global: no unreviewed pair may be treated as resolved, and no
    #      authoritative pair may vanish from the review file.
    for key, p in auth.items():
        if key not in seen_keys:
            F.add(art, f"{key[0]} -> {key[1]}", "NDP-COVERAGE", "inconsistent",
                  "authoritative near pair has no row in the review file "
                  "(unreviewed pair)", "blocker", str(LEAKAGE_PAIRS))

    for i, x in enumerate(reviewed_excl, 1):
        k = (x.get("training_relative_path"), x.get("evaluation_relative_path"))
        src = [r for r in rows if (r.get("training_relative_path"),
                                   r.get("evaluation_relative_path")) == k]
        if not src:
            F.add(str(REVIEWED_EXCL), f"row {i}", "REXCL-TRACEABLE", "inconsistent",
                  "reviewed exclusion does not correspond to any reviewed pair",
                  "blocker", str(REVIEWED_EXCL))
        elif (src[0].get("final_disposition") or "").strip() != "exclude_evaluation":
            F.add(str(REVIEWED_EXCL), f"row {i}", "REXCL-DECIDED", "inconsistent",
                  "pair appears in the reviewed-exclusions file without a "
                  "final_disposition=exclude_evaluation decision", "blocker", str(REVIEWED_EXCL))

    # ---- global: the exact file must never hold a near (d>0) pair
    for i, x in enumerate(exact_excl, 1):
        try:
            d = int(str(x.get("hamming_distance", "")).strip())
        except ValueError:
            d = None
        if d is not None and d > 0:
            F.add(str(EXACT_EXCL), f"row {i}", "EEXCL-EXACT-ONLY", "inconsistent",
                  f"exact-exclusion file contains a near pair (d={d})",
                  "blocker", str(Path("reports/LEAKAGE_GATE_EXCLUSION_POLICY.md")))

    return {"total": len(rows), "decided": decided, "excluded": excluded,
            "kept": kept, "unresolved": unresolved, "invalid": invalid,
            "authoritative_near_pairs": len(auth),
            "reviewed_exclusion_rows": len(reviewed_excl),
            "exact_exclusion_rows": len(exact_excl)}


# --------------------------------------------------------------------------- #
# Artifact B -- action-mapping review
# --------------------------------------------------------------------------- #
def validate_action_mapping(F: Findings) -> dict:
    art = str(MAP_REVIEW)
    rows = read_csv(MAP_REVIEW)
    # Raw text of the scope config. Substring containment is enough here: this
    # validator stays stdlib-only, and configs/evaluation_scope.yaml is parsed and
    # schema-checked properly by ica26.evaluation.scope + tests/test_evaluation_scope.py.
    scope_text = ((REPO / SCOPE_CONFIG).read_text(encoding="utf-8")
                  if (REPO / SCOPE_CONFIG).exists() else "")

    approved = excluded = pending = invalid = 0
    healthy_actions: dict[str, set[str]] = {}
    seen: set[tuple] = set()

    for r in rows:
        ds = (r.get("dataset") or "").strip()
        dc = (r.get("dataset_class") or "").strip()
        rid = f"{ds}/{dc}" if (ds or dc) else "<blank identity>"

        if blank(ds) or blank(dc):
            F.add(art, rid, "MAP-IDENTITY", "invalid_value",
                  "dataset and dataset_class must both be non-blank "
                  "(the original label is the join key)", "blocker", art)
            invalid += 1
        if (ds, dc) in seen:
            F.add(art, rid, "MAP-IDENTITY-UNIQUE", "inconsistent",
                  "duplicate (dataset, dataset_class)", "blocker", art)
        seen.add((ds, dc))

        # -- canonical class / crop / condition
        for col in ("canonical_crop", "canonical_disease"):
            if blank(r.get(col)):
                F.add(art, rid, "MAP-CANONICAL", "invalid_value",
                      f"'{col}' is blank", "blocker", art)

        # -- action label
        action = (r.get(REVIEW_ACTION_COLUMN) or "").strip()
        if action in FORBIDDEN_ACTION_CLASSES:
            F.add(art, rid, "MAP-ACTION-FORBIDDEN", "unsupported",
                  f"forbidden action class '{action}'", "blocker",
                  str(Path("configs/action_taxonomy.yaml")))
            invalid += 1
        elif blank(action):
            F.add(art, rid, "MAP-ACTION-PRESENT", "missing_decision",
                  f"'{REVIEW_ACTION_COLUMN}' is blank", "blocker", art)
        elif action not in ACTION_CLASSES:
            F.add(art, rid, "MAP-ACTION-ENUM", "unsupported",
                  f"unknown action class '{action}' (allowed: {list(ACTION_CLASSES)})",
                  "blocker", str(Path("configs/action_taxonomy.yaml")))
            invalid += 1

        # -- pathogen type
        ptype = (r.get("pathogen_type") or "").strip()
        if not blank(ptype) and ptype not in PATHOGEN_TYPES:
            F.add(art, rid, "MAP-PATHOGEN-ENUM", "unsupported",
                  f"unrecognised pathogen_type '{ptype}'", "blocker", art)
            invalid += 1

        conf = (r.get("mapping_confidence") or "").strip()
        if conf not in MAPPING_CONFIDENCES:
            F.add(art, rid, "MAP-CONFIDENCE-ENUM", "unsupported",
                  f"invalid mapping_confidence '{conf}'", "blocker", art)
            invalid += 1

        # -- THE HUMAN DECISION
        status = (r.get("review_status") or "").strip()
        if status not in REVIEW_STATUSES:
            F.add(art, rid, "MAP-STATUS-ENUM", "unsupported",
                  f"invalid review_status '{status}' (allowed: {list(REVIEW_STATUSES)})",
                  "blocker", art)
            invalid += 1
        elif status not in TERMINAL_REVIEW_STATUSES:
            F.add(art, rid, "MAP-STATUS-TERMINAL", "missing_decision",
                  f"review_status is '{status}' -- no terminal human decision "
                  "(approved / excluded) was recorded",
                  "blocker", str(MAP_CHECKLIST))
            pending += 1
        elif status == "approved":
            approved += 1
        else:
            excluded += 1

        # -- evidence gate. Evaluated for every row, because it determines whether
        #    an `approve` decision is even *expressible* for that row.
        is_healthy = (r.get("canonical_disease") or "").strip().lower() == HEALTHY_CANONICAL_DISEASE
        if is_healthy:
            # Narrow exemption (policy:healthy-monitor-v1): a healthy class is a
            # NEGATIVE diagnosis, so there is no pathogen to cite. Action prose,
            # evidence prose, the date, `monitor`, and a policy citation are all
            # still mandatory -- and pathogen fields must stay BLANK, so the
            # exemption can never be used to smuggle in a fabricated pathogen.
            missing_evidence = [
                fld for fld in HEALTHY_EVIDENCE_FIELDS_REQUIRED_FOR_APPROVAL
                if blank(r.get(REVIEW_ACTION_COLUMN if fld == CANONICAL_ACTION_COLUMN else fld))
            ]
            cites_policy = any(
                HEALTHY_POLICY_ID in (r.get(c) or "")
                for c in ("source_identifier", "review_notes")
            )
            if status == "approved":
                if action != HEALTHY_ACTION_CLASS:
                    F.add(art, rid, "MAP-HEALTHY-ACTION", "invalid_value",
                          f"approved healthy row must map to '{HEALTHY_ACTION_CLASS}' "
                          f"({HEALTHY_POLICY_ID}), not '{action}'", "blocker",
                          str(Path("reports/HEALTHY_CLASS_ACTION_POLICY.md")))
                if not cites_policy:
                    F.add(art, rid, "MAP-HEALTHY-POLICY-REF", "invalid_value",
                          f"approved healthy row must cite '{HEALTHY_POLICY_ID}' in "
                          "source_identifier or review_notes", "blocker",
                          str(Path("reports/HEALTHY_CLASS_ACTION_POLICY.md")))
                for fld in HEALTHY_FORBIDDEN_FIELDS:
                    if not blank(r.get(fld)):
                        F.add(art, rid, "MAP-HEALTHY-NO-PATHOGEN", "invalid_value",
                              f"healthy row must leave '{fld}' blank -- a healthy "
                              "negative class has no pathogen and none may be "
                              "fabricated", "blocker",
                              str(Path("reports/HEALTHY_CLASS_ACTION_POLICY.md")))
        else:
            missing_evidence = [
                fld for fld in EVIDENCE_FIELDS_REQUIRED_FOR_APPROVAL
                if blank(r.get(REVIEW_ACTION_COLUMN if fld == CANONICAL_ACTION_COLUMN else fld))
            ]
        if missing_evidence:
            st = "invalid_value" if status == "approved" else "evidence_gate_unsatisfiable"
            gate = ("healthy-class evidence gate" if is_healthy else "evidence gate")
            F.add(art, rid, "MAP-EVIDENCE-GATE", st,
                  f"{gate} cannot be satisfied: missing "
                  f"{missing_evidence}; src/ica26/mapping/validation.py rejects an "
                  "approved row lacking any of these fields", "blocker",
                  str(Path("src/ica26/schemas.py")))

        # -- out-of-scope (arthropod pest) rows need an explicit human scope call
        if ptype in ARTHROPOD_PEST_TYPES:
            cites_scope = ARTHROPOD_POLICY_ID in (r.get("review_notes") or "")
            in_scope_config = dc and dc in scope_text and ARTHROPOD_SCOPE_REASON in scope_text
            if status in TERMINAL_REVIEW_STATUSES and (cites_scope or in_scope_config):
                F.add(art, rid, "MAP-SCOPE-ARTHROPOD", "pass",
                      f"arthropod-pest class carries an explicit human scope "
                      f"decision (review_status='{status}'"
                      + (f", cites {ARTHROPOD_POLICY_ID}" if cites_scope else "")
                      + (f", recorded in {SCOPE_CONFIG}" if in_scope_config else "")
                      + ")", "info", str(SCOPE_CONFIG))
            else:
                F.add(art, rid, "MAP-SCOPE-ARTHROPOD", "missing_decision",
                      f"pathogen_type '{ptype}' is an arthropod pest, not a plant "
                      "pathogen; an explicit human in-scope/out-of-scope decision is "
                      "required before this class may enter a plant-disease dataset",
                      "blocker", str(MAP_CHECKLIST))

        # -- healthy-class treatment consistency
        if is_healthy:
            healthy_actions.setdefault(action or "<blank>", set()).add(rid)

        if not any(f["row_identifier"] == rid and f["artifact"] == art for f in F.rows):
            F.add(art, rid, "MAP-ROW", "pass", "all checks passed", "info", art)

    # ---- healthy-class consistency across the table
    if len(healthy_actions) > 1:
        F.add(art, "<healthy classes>", "MAP-HEALTHY-CONSISTENT", "inconsistent",
              "healthy classes do not all map to the same action: "
              + "; ".join(f"{a} -> {sorted(v)}" for a, v in sorted(healthy_actions.items())),
              "blocker", art)
    elif healthy_actions:
        a = next(iter(healthy_actions))
        F.add(art, "<healthy classes>", "MAP-HEALTHY-CONSISTENT", "pass",
              f"all {sum(len(v) for v in healthy_actions.values())} healthy classes "
              f"map consistently to '{a}'", "info", art)

    # ---- schema divergence: review CSV vs canonical mapping table.
    #      The two columns SHOULD differ (candidate proposal vs ratified fact);
    #      what matters is that an audited transcription step exists and that its
    #      output actually reflects the recorded decisions.
    if rows and CANONICAL_ACTION_COLUMN not in rows[0]:
        if not (REPO / MAP_APPLY_SCRIPT).exists():
            F.add(art, "<schema>", "MAP-SCHEMA-VOCAB", "inconsistent",
                  f"review CSV carries '{REVIEW_ACTION_COLUMN}' but the canonical "
                  f"mapping schema requires '{CANONICAL_ACTION_COLUMN}'; decisions "
                  "are not consumable by ica26.mapping.validation without a "
                  "transcription step, and no such script exists in scripts/",
                  "blocker", str(Path("src/ica26/schemas.py")))
        elif not (REPO / MAP_APPROVED).exists():
            F.add(art, "<schema>", "MAP-SCHEMA-VOCAB", "inconsistent",
                  f"{MAP_APPLY_SCRIPT} exists but has not been run: "
                  f"{MAP_APPROVED} is absent, so no canonical mapping carries the "
                  f"'{CANONICAL_ACTION_COLUMN}' column",
                  "blocker", str(MAP_APPLY_SCRIPT))
        else:
            canon = read_csv(MAP_APPROVED)
            approved_ids = {(r.get("dataset", ""), r.get("dataset_class", ""))
                            for r in rows if (r.get("review_status") or "").strip() == "approved"}
            canon_ids = {(r.get("dataset", ""), r.get("dataset_class", "")) for r in canon}
            missing = sorted(approved_ids - canon_ids)
            extra = sorted(canon_ids - approved_ids)
            bad_action = [f"{r.get('dataset')}/{r.get('dataset_class')}"
                          for r in canon
                          if (r.get(CANONICAL_ACTION_COLUMN) or "").strip() not in ACTION_CLASSES]
            if missing or extra or bad_action:
                F.add(art, "<schema>", "MAP-SCHEMA-VOCAB", "inconsistent",
                      f"{MAP_APPROVED} is out of sync with the review decisions: "
                      f"missing={missing} unexpected={extra} bad_action={bad_action}; "
                      f"re-run `python {MAP_APPLY_SCRIPT}`",
                      "blocker", str(MAP_APPLY_SCRIPT))
            else:
                F.add(art, "<schema>", "MAP-SCHEMA-VOCAB", "pass",
                      f"'{REVIEW_ACTION_COLUMN}' is transcribed to "
                      f"'{CANONICAL_ACTION_COLUMN}' by {MAP_APPLY_SCRIPT}; "
                      f"{MAP_APPROVED} carries {len(canon_ids)} approved row(s) "
                      "and matches the review file", "info", str(MAP_APPLY_SCRIPT))

    # ---- checklist: every entry must carry a human choice
    if (REPO / MAP_CHECKLIST).exists():
        text = (REPO / MAP_CHECKLIST).read_text(encoding="utf-8")
        entries = re.findall(r"^- \*\*Human choice\*\*.*$", text, flags=re.M)
        undecided = [e for e in entries if re.search(r":\s*_{3,}\s*$", e)]
        if undecided:
            F.add(str(MAP_CHECKLIST), "<all entries>", "CHECKLIST-DECIDED",
                  "missing_decision",
                  f"{len(undecided)} of {len(entries)} 'Human choice' fields are "
                  "still blank (`______`)", "blocker", str(MAP_CHECKLIST))

    # ---- coverage: which datasets have mapping rows at all
    covered = {(r.get("dataset") or "").strip() for r in rows}
    pv_classes = sorted({r["class_label"] for r in read_csv(PV_MANIFEST)})
    if "PlantVillage" not in covered:
        F.add(art, "<coverage:PlantVillage>", "MAP-COVERAGE-DATASET", "inconsistent",
              f"PlantVillage contributes {len(pv_classes)} classes to Dataset V1 but "
              "has 0 rows in the action-mapping review; action-mapping coverage for "
              "the training set would be 0%", "blocker", str(PV_MANIFEST))

    pd_classes = sorted({r["class_label"] for r in read_csv(PD_MANIFEST)})
    mapped_pd = {(r.get("dataset_class") or "").strip()
                 for r in rows if (r.get("dataset") or "").strip() == "PlantDoc"}
    for c in pd_classes:
        if c not in mapped_pd:
            F.add(art, f"<coverage:PlantDoc/{c}>", "MAP-COVERAGE-CLASS", "inconsistent",
                  "PlantDoc class present in the manifest has no mapping row",
                  "blocker", str(PD_MANIFEST))

    return {"total": len(rows), "approved": approved, "excluded": excluded,
            "pending": pending, "invalid": invalid,
            "plantdoc_classes": len(pd_classes), "plantdoc_mapped": len(mapped_pd),
            "plantvillage_classes": len(pv_classes), "plantvillage_mapped": 0,
            "healthy_rows": sum(len(v) for v in healthy_actions.values())}


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> int:
    required = [NDP_REVIEW, REVIEWED_EXCL, EXACT_EXCL, MAP_REVIEW, LEAKAGE_PAIRS,
                PD_MANIFEST, PV_MANIFEST]
    missing = [str(p) for p in required if not (REPO / p).exists()]
    if missing:
        print("[validate] required input(s) absent: " + ", ".join(missing))
        return 2

    F = Findings()
    ndp = validate_near_duplicate_review(F)
    mapping = validate_action_mapping(F)

    rows = sorted(F.rows, key=lambda r: (r["artifact"], r["row_identifier"], r["check_id"]))
    (REPO / OUT_CSV).parent.mkdir(parents=True, exist_ok=True)
    with open(REPO / OUT_CSV, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(OUT_COLUMNS))
        w.writeheader()
        w.writerows(rows)

    checksums = {}
    for p in (NDP_REVIEW, REVIEWED_EXCL, EXACT_EXCL, MAP_REVIEW, MAP_TEMPLATE,
              MAP_APPROVED, MAP_APPLY_SCRIPT, SCOPE_CONFIG,
              MAP_CHECKLIST, LEAKAGE_PAIRS, PD_MANIFEST, PV_MANIFEST,
              Path("reports/NEAR_DUPLICATE_HUMAN_REVIEW.md"),
              Path("reports/HEALTHY_CLASS_ACTION_POLICY.md"),
              Path("reports/ARTHROPOD_PEST_EVALUATION_SCOPE.md"),
              Path("reports/PHASE1_HUMAN_DECISIONS_2026-08-02.md"),
              Path("phase1_return_package.zip")):
        if (REPO / p).exists():
            checksums[str(p)] = sha256_of(p)

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "_timestamp_note": "metadata only; excluded from deterministic content hashes",
        "near_duplicate_review": ndp,
        "action_mapping_review": mapping,
        "findings": {
            "total": len(rows),
            "blockers": len(F.blockers),
            "warnings": len(F.warnings),
            "by_check": {k: sum(1 for r in rows if r["check_id"] == k)
                         for k in sorted({r["check_id"] for r in rows})},
        },
        "verdict": "BLOCKED" if F.blockers else "CLEAR",
        "reviewed_artifact_sha256": checksums,
    }
    with open(REPO / OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, sort_keys=False)
        fh.write("\n")

    print(f"[validate] findings={len(rows)} blockers={len(F.blockers)} "
          f"warnings={len(F.warnings)} -> {OUT_CSV}")
    for r in F.blockers[:20]:
        print(f"  BLOCKER {r['artifact']} [{r['row_identifier']}] "
              f"{r['check_id']}: {r['reason'][:110]}")
    if len(F.blockers) > 20:
        print(f"  ... and {len(F.blockers) - 20} more blocker(s)")
    print(f"[validate] verdict: {summary['verdict']}")
    return 1 if F.blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
