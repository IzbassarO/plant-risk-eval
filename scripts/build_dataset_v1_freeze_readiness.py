#!/usr/bin/env python
"""Fail-closed readiness assessment for a Dataset V1 freeze. Freezes NOTHING.

    python scripts/build_dataset_v1_freeze_readiness.py
    python scripts/build_dataset_v1_freeze_readiness.py --check

A freeze is the point after which numbers become quotable, so the question
"may we freeze?" deserves one reproducible answer rather than a reader
assembling it from five reports. This script evaluates every precondition and
writes a single artifact:

    reports/dataset_v1_freeze_readiness.json    machine-readable, deterministic
    reports/DATASET_V1_FREEZE_READINESS.md      the same, for a human auditor

It is deliberately incapable of freezing anything. It writes no
`dataset_v1_freeze.json`, approves nothing, and changes no record. `ready` means
only that every listed precondition is satisfied and a human may now *consider*
the decision -- it is not the decision.

Every condition is one of two kinds:

  machine  evaluated here from artifacts, digests, and a fresh rebuild;
  human    a scientific judgement, satisfied ONLY by the presence of an explicit
           decision artifact. Absent means blocked. There is no default-yes, no
           count parameter, and no override.

Deterministic: no wall-clock field, so repeated runs are byte-identical.
Exit codes: 0 ready, 1 not ready, 2 missing input, 3 stale (--check).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ica26.datasets.duplicate_remediation import (  # noqa: E402
    identity_set, reconcile_identity_sets,
)
from ica26.datasets.duplicates import (  # noqa: E402
    InternalDuplicateGate, validate_internal_gate,
)
from ica26.governance import (  # noqa: E402
    APPROVAL_SCHEMA, MAPPING_READINESS_SCHEMA,
)
from ica26.schemas import IMAGE_MANIFEST_COLUMNS  # noqa: E402

SCHEMA_VERSION = "1.0"

PLANTDOC_SUMMARY = Path("data/manifests/plantdoc_summary.json")
PLANTVILLAGE_SUMMARY = Path("data/manifests/plantvillage_summary.json")
PLANTDOC_MANIFEST = Path("data/manifests/plantdoc_manifest.csv")
EFFECTIVE = Path("data/manifests/plantdoc_effective_manifest.csv")
RESOLUTION = Path("data/exclusions/plantdoc_internal_duplicate_resolution.csv")
LEAKAGE_GATE = Path("reports/leakage_gate.json")
INTERNAL_GATE = Path("reports/plantdoc_internal_duplicate_gate.json")
MAPPING_REVIEW = Path("data/mapping/action_mapping_review.csv")
PLANTVILLAGE_MANIFEST = Path("data/manifests/plantvillage_manifest.csv")
HARM_TEMPLATE = Path("configs/harm_matrix_template.yaml")
EVIDENCE_MANIFEST = Path("human_review/evidence_manifest.json")

#: Artifacts a HUMAN must produce. Their absence is a blocker, never a default.
#: Each is validated against a versioned schema in `ica26.governance.approvals`;
#: a file that merely exists, or says `{"approved": true}`, satisfies nothing.
AUDIT_SIGNOFF = Path("reports/DATASET_V1_AUDIT_SIGNOFF.json")
FREEZE_APPROVAL = Path("data/manifests/dataset_v1_freeze_approval.json")
SECOND_REVIEW = Path("human_review/plantdoc_label_second_review/second_review.json")
SECOND_REVIEW_PACKET = Path("reports/plantdoc_label_second_review")
FREEZE_ARTIFACT = Path("data/manifests/dataset_v1_freeze.json")

OUT_JSON = Path("reports/dataset_v1_freeze_readiness.json")
OUT_MD = Path("reports/DATASET_V1_FREEZE_READINESS.md")

#: Audit findings that must be closed before a freeze. Closure is asserted by a
#: validated human sign-off artifact, never inferred from the presence of a
#: report. Sourced from the approval spec so the two cannot drift apart.
from ica26.governance import AUDIT_SIGNOFF_SPEC as _SIGNOFF_SPEC  # noqa: E402

REQUIRED_CLOSED_FINDINGS = _SIGNOFF_SPEC.required_findings


#: How a condition can be settled. Collapsing these into one "human" bucket hid
#: that they need different KINDS of artifact -- a scientific judgement, a
#: governance decision, and an independent audit are not interchangeable.
CONDITION_KINDS = ("machine", "human_scientific", "governance_approval",
                   "independent_audit")


@dataclass
class Condition:
    id: str
    title: str
    kind: str          # one of CONDITION_KINDS
    status: str        # "satisfied" | "blocked"
    detail: str
    evidence: str = ""
    #: SHA-256 of the artifact this verdict was computed from, so a condition
    #: cannot keep its answer after its evidence changes. "<absent>" when the
    #: artifact does not exist -- which is itself a blocking state.
    evidence_digest: str = ""

    def __post_init__(self):
        if self.kind not in CONDITION_KINDS:
            raise ValueError(f"unknown condition kind '{self.kind}' "
                             f"(allowed: {list(CONDITION_KINDS)})")

    @property
    def ok(self) -> bool:
        return self.status == "satisfied"


@dataclass
class Readiness:
    schema_version: str
    dataset: str
    status: str
    frozen: bool
    satisfied: int
    blocked: int
    blockers: list = field(default_factory=list)
    conditions: list = field(default_factory=list)
    input_digests: dict = field(default_factory=dict)
    provenance: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    return path


def _digest_of(repo: Path, evidence: str) -> str:
    """Digest the artifact a condition was judged from. Absence is recorded."""
    if not evidence:
        return ""
    target = repo / evidence
    if target.is_dir():
        parts = []
        for f in sorted(target.rglob("*")):
            if f.is_file():
                parts.append(f"{f.relative_to(target)}:{sha256_of(f)}")
        return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
    return sha256_of(target) if target.exists() else "<absent>"


def _c(cid, title, kind, ok, detail, evidence="", repo: Path = REPO) -> Condition:
    return Condition(cid, title, kind, "satisfied" if ok else "blocked", detail,
                     evidence, _digest_of(repo, evidence))


# --------------------------------------------------------------------------- #
# Conditions
# --------------------------------------------------------------------------- #
def evaluate(repo: Path, *, verify_pixels: bool,
             head_commit: Optional[str] = None) -> list[Condition]:
    out: list[Condition] = []

    # --- acquisition ------------------------------------------------------- #
    pd_sum = read_json(repo / PLANTDOC_SUMMARY)
    complete = bool((pd_sum or {}).get("complete"))
    rec = (pd_sum or {}).get("reconciliation", {})
    out.append(_c("plantdoc_acquired", "PlantDoc is acquired to the frozen upstream snapshot",
                  "machine", complete,
                  f"complete={complete}; manifest {rec.get('manifest_count')} of "
                  f"upstream {rec.get('upstream_repository_count')}"
                  if pd_sum else "plantdoc_summary.json is absent",
                  str(PLANTDOC_SUMMARY)))

    pv_sum = read_json(repo / PLANTVILLAGE_SUMMARY)
    pv_ok = bool((pv_sum or {}).get("pixels_materialized"))
    out.append(_c("plantvillage_materialized", "PlantVillage pixels are materialized",
                  "machine", pv_ok,
                  f"pixels_materialized={pv_ok}; {(pv_sum or {}).get('n_images')} image(s)"
                  if pv_sum else "plantvillage_summary.json is absent",
                  str(PLANTVILLAGE_SUMMARY)))

    # --- cross-dataset leakage gate (R2A) ---------------------------------- #
    lg = read_json(repo / LEAKAGE_GATE)
    if lg is None:
        out.append(_c("cross_dataset_leakage_gate", "Cross-dataset leakage gate passes",
                      "machine", False, "reports/leakage_gate.json is absent",
                      str(LEAKAGE_GATE)))
    else:
        from ica26.leakage.gate import SCHEMA_VERSION as LEAK_SCHEMA
        problems = []
        if lg.get("schema_version") != LEAK_SCHEMA:
            problems.append(f"schema {lg.get('schema_version')} != {LEAK_SCHEMA}")
        if lg.get("status") != "pass":
            problems.append(f"status={lg.get('status')}")
        if lg.get("unresolved_pair_count"):
            problems.append(f"{lg['unresolved_pair_count']} unresolved pair(s)")
        if lg.get("authorization_violations"):
            problems.append(f"{len(lg['authorization_violations'])} violation(s)")
        stale = [n for n, d in (lg.get("input_digests") or {}).items()
                 if n != "leakage_config"
                 and (not (repo / _leak_input_path(n)).exists()
                      or sha256_of(repo / _leak_input_path(n)) != d)]
        if stale:
            problems.append(f"stale bound input(s): {stale}")
        out.append(_c("cross_dataset_leakage_gate", "Cross-dataset leakage gate passes",
                      "machine", not problems,
                      "; ".join(problems) or
                      f"schema {lg['schema_version']}, exact {lg['exact_duplicate_count']}, "
                      f"near {lg['near_duplicate_count']} all resolved, 0 unresolved, "
                      f"0 violations, every bound input digest current",
                      str(LEAKAGE_GATE)))

    # --- internal duplicate gate (R2B) ------------------------------------- #
    ig = read_json(repo / INTERNAL_GATE)
    if ig is None:
        out.append(_c("internal_duplicate_gate", "PlantDoc internal duplicate gate passes",
                      "machine", False, "the gate artifact is absent", str(INTERNAL_GATE)))
    else:
        errors = validate_internal_gate(InternalDuplicateGate.from_dict(ig))
        stale = [n for n, p in (("plantdoc_manifest", PLANTDOC_MANIFEST),
                                ("duplicate_resolution", RESOLUTION),
                                ("effective_manifest", EFFECTIVE))
                 if (ig.get("input_digests") or {}).get(n) !=
                 (sha256_of(repo / p) if (repo / p).exists() else "<absent>")]
        if stale:
            errors = list(errors) + [f"stale bound input(s): {stale}"]
        rem = ig.get("remediation") or {}
        out.append(_c("internal_duplicate_gate", "PlantDoc internal duplicate gate passes",
                      "machine", not errors,
                      "; ".join(errors) or
                      f"schema {ig['schema_version']}, {ig['resolved_groups']}/"
                      f"{ig['total_groups']} groups adjudicated and applied, "
                      f"{rem.get('retained_records')} retained, "
                      f"{rem.get('excluded_records')} excluded, fresh==persisted",
                      str(INTERNAL_GATE)))

    # --- effective dataset -------------------------------------------------- #
    out.extend(_effective_conditions(repo, verify_pixels=verify_pixels))

    # --- evidence integrity -------------------------------------------------- #
    em = read_json(repo / EVIDENCE_MANIFEST)
    if em is None:
        out.append(_c("human_review_evidence_intact", "Preserved human-review evidence is unaltered",
                      "machine", False, "human_review/evidence_manifest.json is absent",
                      str(EVIDENCE_MANIFEST)))
    else:
        bad = [n for n, d in em["artifacts"].items()
               if not (repo / "human_review" / n).exists()
               or sha256_of(repo / "human_review" / n) != d]
        out.append(_c("human_review_evidence_intact", "Preserved human-review evidence is unaltered",
                      "machine", not bad,
                      f"{len(bad)} artifact(s) differ from their recorded digest: {bad}" if bad
                      else f"{em['file_count']} preserved artifact(s), all digests current",
                      str(EVIDENCE_MANIFEST)))

    # --- anonymity ----------------------------------------------------------- #
    from ica26.portability import validate_portability
    port = validate_portability(repo)
    # Report WHERE, never WHAT: quoting the offending string would write the
    # identifier straight back into this artifact, which the next run would then
    # report -- a leak that feeds itself.
    leak_files = sorted({i.where for i in port.errors})
    out.append(_c("anonymity", "No machine-specific or personal identifier in paper artifacts",
                  "machine", port.ok,
                  port.summary() if port.ok else
                  f"{len(port.errors)} identifier(s) in {len(leak_files)} file(s): "
                  f"{leak_files[:5]}",
                  "src/ica26/portability.py", repo))

    # --- mapping readiness (human scientific) -------------------------------- #
    # R2B.1 Finding 1: the old predicates were `needs_review == 0` and "a row
    # exists for this class". Both fail open -- rename the status, or add an
    # empty row, and they go green. Readiness is now decided against the class
    # identity set the dataset actually has, with an allow-list of terminal
    # statuses and the full evidence gate on every approved row.
    from ica26.evaluation.scope import load_scope
    from ica26.governance import evaluate_mapping_readiness

    mapping_rows = read_csv(repo / MAPPING_REVIEW) if (repo / MAPPING_REVIEW).exists() else []
    mapping_digest = sha256_of(repo / MAPPING_REVIEW) if (repo / MAPPING_REVIEW).exists() else "<absent>"
    try:
        scope = load_scope(repo / "configs/evaluation_scope.yaml")
        out_of_action = {k[1] for k in scope.out_of_scope("include_action_evaluation")}
    except Exception:                                          # noqa: BLE001
        out_of_action = set()

    effective = read_csv(repo / EFFECTIVE) if (repo / EFFECTIVE).exists() else []
    plantdoc_classes = {r["class_label"] for r in effective}
    pd_ready = evaluate_mapping_readiness(
        mapping_rows, dataset="PlantDoc", expected_classes=plantdoc_classes,
        artifact=str(MAPPING_REVIEW), artifact_digest=mapping_digest,
        out_of_action_scope_classes=out_of_action)
    out.append(_c("disease_action_mapping_reviewed",
                  "Every PlantDoc class carries a terminal, evidence-gated mapping decision",
                  "human_scientific", pd_ready.satisfied, pd_ready.detail(),
                  str(MAPPING_REVIEW), repo))

    pv_classes = {r["class_label"] for r in read_csv(repo / PLANTVILLAGE_MANIFEST)} if (
        repo / PLANTVILLAGE_MANIFEST).exists() else set()
    pv_ready = evaluate_mapping_readiness(
        mapping_rows, dataset="PlantVillage", expected_classes=pv_classes,
        artifact=str(MAPPING_REVIEW), artifact_digest=mapping_digest,
        out_of_action_scope_classes=out_of_action)
    out.append(_c("plantvillage_action_mapping_coverage",
                  "Every PlantVillage class carries a terminal, evidence-gated mapping decision",
                  "human_scientific", pv_ready.satisfied, pv_ready.detail(),
                  str(MAPPING_REVIEW), repo))

    # --- harm matrix (human scientific) --------------------------------------- #
    try:
        from ica26.evaluation import harm
        m = harm.load_reviewed_matrix(repo / HARM_TEMPLATE)
        ready = m.is_production_ready()
        detail = (f"matrix '{m.matrix_id}' review_status='{m.review_status}', "
                  f"is_example={m.is_example}")
    except Exception as exc:                                  # noqa: BLE001
        ready, detail = False, f"could not load a reviewed harm matrix: {exc}"
    out.append(_c("harm_matrix_approved", "A human-approved harm matrix exists",
                  "human_scientific", ready, detail, str(HARM_TEMPLATE), repo))

    # --- second scientific review of the canonical relabels ------------------- #
    # R2B.1 Finding 5: three canonical labels rest on one anonymous rationale
    # with no independently citable diagnostic source.
    from ica26.governance import SECOND_REVIEW_SPEC, validate_approval_file
    second = validate_approval_file(repo / SECOND_REVIEW, SECOND_REVIEW_SPEC,
                                    repo=repo, expected_commit=head_commit)
    relabelled = _relabelled_group_ids(repo)
    out.append(_c("relabel_second_scientific_review",
                  f"The canonical relabels {relabelled} carry an independent second review",
                  "human_scientific", second.satisfied,
                  second.detail() + (f"; packet pending at {SECOND_REVIEW_PACKET}"
                                     if not second.present else ""),
                  str(SECOND_REVIEW), repo))

    # --- audit sign-off (independent audit) ----------------------------------- #
    from ica26.governance import AUDIT_SIGNOFF_SPEC
    signoff = validate_approval_file(repo / AUDIT_SIGNOFF, AUDIT_SIGNOFF_SPEC,
                                     repo=repo, expected_commit=head_commit)
    out.append(_c("open_audit_findings_closed",
                  f"An independent re-audit closes {list(REQUIRED_CLOSED_FINDINGS)}",
                  "independent_audit", signoff.satisfied, signoff.detail(),
                  str(AUDIT_SIGNOFF), repo))

    # --- the freeze decision itself (governance approval) --------------------- #
    from ica26.governance import FREEZE_APPROVAL_SPEC
    approval = validate_approval_file(repo / FREEZE_APPROVAL, FREEZE_APPROVAL_SPEC,
                                      repo=repo, expected_commit=head_commit)
    out.append(_c("freeze_approval_recorded",
                  "A human has recorded a valid, bound Dataset V1 freeze approval",
                  "governance_approval", approval.satisfied, approval.detail(),
                  str(FREEZE_APPROVAL), repo))

    return out


def _relabelled_group_ids(repo: Path) -> list[str]:
    """Groups whose retained record was given a different label. Derived, not fixed."""
    if not (repo / RESOLUTION).exists():
        return []
    sys.path.insert(0, str(repo / "scripts"))
    from build_plantdoc_second_review_packet import relabelled_groups  # noqa: E402
    return relabelled_groups(read_csv(repo / RESOLUTION))


def _leak_input_path(name: str) -> str:
    return {
        "training_manifest": "data/manifests/plantvillage_manifest.csv",
        "evaluation_manifest": "data/manifests/plantdoc_manifest.csv",
        "pair_table": "reports/leakage_plantvillage_vs_plantdoc_pairs.csv",
        "near_review": "data/exclusions/cross_dataset_near_duplicate_review.csv",
        "reviewed_exclusions": "data/exclusions/cross_dataset_reviewed_exclusions.csv",
        "exact_exclusions": "data/exclusions/cross_dataset_exact_exclusions.csv",
    }[name]


def _effective_conditions(repo: Path, *, verify_pixels: bool) -> list[Condition]:
    out: list[Condition] = []
    if not (repo / EFFECTIVE).exists():
        return [_c("effective_dataset_current",
                   "The effective dataset matches a fresh rebuild from the decisions",
                   "machine", False, "no effective manifest; the decisions are not applied",
                   str(EFFECTIVE)),
                _c("effective_dataset_integrity", "The effective dataset is internally sound",
                   "machine", False, "no effective manifest", str(EFFECTIVE)),
                _c("effective_dataset_pixels_verified",
                   "Every effective record's bytes match its recorded digest",
                   "machine", False, "no effective manifest", str(EFFECTIVE))]

    persisted = read_csv(repo / EFFECTIVE)
    sys.path.insert(0, str(repo / "scripts"))
    from apply_plantdoc_duplicate_adjudication import build as rebuild  # noqa: E402

    _, effective_text, report = rebuild(repo)
    fresh = list(csv.DictReader(effective_text.splitlines()))
    set_violations, recon = reconcile_identity_sets(fresh, persisted)
    problems = list(report.get("violations", [])) + set_violations
    if (repo / EFFECTIVE).read_text(encoding="utf-8") != effective_text:
        problems.append("the persisted effective manifest differs byte-for-byte from a rebuild")
    out.append(_c("effective_dataset_current",
                  "The effective dataset matches a fresh rebuild from the decisions",
                  "machine", not problems,
                  "; ".join(problems[:3]) or
                  f"fresh {recon['fresh_count']} == persisted {recon['persisted_count']}, "
                  f"identity digest {recon['fresh_digest'][:16]}…, byte-identical",
                  str(EFFECTIVE)))

    with open(repo / EFFECTIVE, newline="", encoding="utf-8") as fh:
        header = next(csv.reader(fh))
    by_digest: dict[str, list[dict]] = {}
    for r in persisted:
        by_digest.setdefault(r["sha256"], []).append(r)
    dupes = {d: rs for d, rs in by_digest.items() if len(rs) > 1}
    cross = sum(1 for rs in dupes.values() if len({r["split"] for r in rs}) > 1)
    issues = []
    if tuple(header) != tuple(IMAGE_MANIFEST_COLUMNS):
        issues.append("schema does not match IMAGE_MANIFEST_COLUMNS")
    if len({r["relpath"] for r in persisted}) != len(persisted):
        issues.append("duplicate relpath")
    if len(set(identity_set(persisted))) != len(persisted):
        issues.append("duplicate record identity")
    if dupes:
        issues.append(f"{len(dupes)} surviving exact-duplicate group(s), {cross} cross-split")
    if [r for r in persisted if r.get("is_corrupt") != "False"]:
        issues.append("record(s) flagged is_corrupt")
    out.append(_c("effective_dataset_integrity", "The effective dataset is internally sound",
                  "machine", not issues,
                  "; ".join(issues) or
                  f"{len(persisted)} record(s), {len(by_digest)} distinct digest(s), "
                  f"0 exact duplicates, unique relpaths and identities, "
                  f"{len({r['class_label'] for r in persisted})} class(es)",
                  str(EFFECTIVE)))

    if not verify_pixels:
        out.append(_c("effective_dataset_pixels_verified",
                      "Every effective record's bytes match its recorded digest",
                      "machine", False,
                      "skipped by --skip-pixel-verification; an unverified check is not a "
                      "passing one", str(EFFECTIVE)))
    else:
        root = repo / "data/raw/plantdoc"
        missing = bad = 0
        for r in persisted:
            p = root / r["relpath"]
            if not p.exists():
                missing += 1
            elif sha256_of(p) != r["sha256"]:
                bad += 1
        out.append(_c("effective_dataset_pixels_verified",
                      "Every effective record's bytes match its recorded digest",
                      "machine", not (missing or bad),
                      f"{missing} missing, {bad} digest mismatch" if (missing or bad)
                      else f"all {len(persisted)} record(s) re-hashed from disk and matching",
                      str(EFFECTIVE)))
    return out


# --------------------------------------------------------------------------- #
def render_markdown(r: Readiness) -> str:
    L = ["# Dataset V1 — freeze readiness", "",
         "_Generated by `scripts/build_dataset_v1_freeze_readiness.py`. **This assessment "
         "freezes nothing.** It writes no freeze artifact, approves nothing, and changes no "
         "record. `ready` means only that every precondition below is satisfied and a human "
         "may then consider the decision._", "",
         f"**Status: `{r.status.upper()}`** — {r.satisfied} satisfied, {r.blocked} blocked.",
         f"**Dataset V1 frozen: {'yes' if r.frozen else 'NO'}.**", ""]
    if r.blockers:
        L += ["## Blocking conditions", ""]
        for b in r.blockers:
            c = next(x for x in r.conditions if x["id"] == b)
            L.append(f"- **{c['title']}** (`{c['id']}`, {c['kind']}) — {c['detail']}")
        L.append("")
    L += ["## All conditions", "", "| Condition | Kind | Status | Detail |", "|---|---|---|---|"]
    for c in r.conditions:
        mark = "satisfied" if c["status"] == "satisfied" else "**BLOCKED**"
        L.append(f"| {c['title']} (`{c['id']}`) | {c['kind']} | {mark} | {c['detail']} |")
    L += ["", "## Who can settle what", "",
          "A `machine` condition is evaluated here from artifacts, bound digests, and a "
          "fresh rebuild. The other three are decisions, and they are **not** "
          "interchangeable — a governance approval cannot stand in for a scientific "
          "judgement, and neither can stand in for an independent audit. Each is satisfied "
          "only by an explicit artifact validated against a versioned schema "
          f"(`{APPROVAL_SCHEMA}`); absence, invalidity, or a stale binding all block.", "",
          "| Kind | Meaning |", "|---|---|",
          "| `machine` | The pipeline can verify it. |",
          "| `human_scientific` | A domain judgement about the data itself. |",
          "| `governance_approval` | A decision to proceed, taken by an accountable owner. |",
          "| `independent_audit` | A verdict by someone who did not do the work. |", "",
          "## What a human must produce", "",
          "| Artifact | Satisfies | Must carry |", "|---|---|---|",
          f"| `{AUDIT_SIGNOFF}` | `open_audit_findings_closed` | schema version, artifact "
          f"type `dataset_v1_audit_signoff`, scope `phase1_audit_findings`, decision, "
          f"reviewer id **and role**, ISO-8601 timestamp with offset, the repository "
          f"commit, SHA-256 bindings for the gate and effective manifest, a rationale, "
          f"`closed_findings` covering {list(REQUIRED_CLOSED_FINDINGS)}, "
          "`auditor_independent_of_implementer: true`, and an explicit `not_approved` |",
          f"| `{SECOND_REVIEW}` | `relabel_second_scientific_review` | the same core fields "
          "with artifact type `plantdoc_label_second_review`, plus `group_verdicts` and "
          f"`diagnostic_citations`. The pending packet is at `{SECOND_REVIEW_PACKET}` |",
          f"| `{FREEZE_APPROVAL}` | `freeze_approval_recorded` | the same core fields with "
          "artifact type `dataset_v1_freeze_approval` and scope `dataset_v1`, binding the "
          "effective manifest, resolution table, and both gates |",
          f"| `{MAPPING_REVIEW}` | both mapping conditions | one row per dataset class, each "
          "with a terminal status (`approved` or `excluded`), the full evidence set, a "
          "target from the approved action vocabulary, and reviewer attribution |",
          f"| `{HARM_TEMPLATE}` | `harm_matrix_approved` | a non-example matrix, approved, "
          "with complete weights |", "",
          "An approval is refused for: a missing or placeholder field, an unknown decision "
          "value, an invalid or naive timestamp, an empty reviewer, a commit that is not "
          "HEAD, a digest that no longer matches the file it binds, the wrong artifact type "
          "or scope, a duplicate approval for the same scope, or a timestamp predating the "
          "commit it claims to have reviewed. A bare `{\"approved\": true}` fails on all "
          "counts and is pinned as a test.", "",
          "## Re-deriving this assessment", "",
          "```", "python scripts/build_dataset_v1_freeze_readiness.py",
          "python scripts/build_dataset_v1_freeze_readiness.py --check", "```", "",
          "No wall-clock field, so repeated runs are byte-identical and the assessment can "
          "be compared across commits. Every condition records the SHA-256 of the artifact "
          "it was judged from, so a verdict cannot outlive its evidence.", ""]
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="dataset-v1-freeze-readiness")
    ap.add_argument("--check", action="store_true",
                    help="verify the persisted assessment matches current inputs; write nothing")
    ap.add_argument("--skip-pixel-verification", action="store_true",
                    help="skip re-hashing every effective record (that condition then BLOCKS)")
    args = ap.parse_args(argv)

    if not (REPO / PLANTDOC_MANIFEST).exists():
        print(f"[freeze-readiness] manifest not found: {PLANTDOC_MANIFEST}")
        return 2

    from ica26.governance.approvals import current_commit
    head = current_commit(REPO)
    conditions = evaluate(REPO, verify_pixels=not args.skip_pixel_verification,
                          head_commit=head)
    blockers = [c.id for c in conditions if not c.ok]

    digests = {}
    for name, p in (("plantdoc_manifest", PLANTDOC_MANIFEST),
                    ("effective_manifest", EFFECTIVE),
                    ("duplicate_resolution", RESOLUTION),
                    ("leakage_gate", LEAKAGE_GATE),
                    ("internal_duplicate_gate", INTERNAL_GATE),
                    ("action_mapping_review", MAPPING_REVIEW),
                    ("human_review_evidence", EVIDENCE_MANIFEST),
                    ("second_review_packet", SECOND_REVIEW_PACKET / "packet_manifest.json")):
        digests[name] = sha256_of(REPO / p) if (REPO / p).exists() else "<absent>"

    readiness = Readiness(
        schema_version=SCHEMA_VERSION,
        dataset="Dataset V1",
        status="ready" if not blockers else "not_ready",
        frozen=(REPO / FREEZE_ARTIFACT).exists(),
        satisfied=sum(1 for c in conditions if c.ok),
        blocked=len(blockers),
        blockers=blockers,
        conditions=[asdict(c) for c in conditions],
        input_digests=dict(sorted(digests.items())),
        provenance={"command": "build_dataset_v1_freeze_readiness.py",
                    "freezes_nothing": True,
                    "condition_kinds": list(CONDITION_KINDS),
                    "approval_schema": APPROVAL_SCHEMA,
                    "mapping_readiness_schema": MAPPING_READINESS_SCHEMA,
                    # HEAD is deliberately NOT recorded here. Approvals are
                    # validated against the LIVE commit at run time, which is
                    # what "this approval is stale" has to mean; persisting it
                    # would make this artifact stale on every commit -- including
                    # the one that stores it -- and a `--check` that can never
                    # pass teaches a reader to ignore it.
                    "commit_binding": "validated against live HEAD at run time",
                    "pixel_verification": not args.skip_pixel_verification},
    )

    text = json.dumps(readiness.to_dict(), indent=2, sort_keys=True) + "\n"
    md = render_markdown(readiness)

    print(f"[freeze-readiness] status={readiness.status} "
          f"satisfied={readiness.satisfied} blocked={readiness.blocked} "
          f"frozen={readiness.frozen}")
    for b in blockers:
        c = next(x for x in conditions if x.id == b)
        print(f"  BLOCKED [{c.kind}] {c.id}: {c.detail}")

    if args.check:
        stale = [str(p) for p, t in ((OUT_JSON, text), (OUT_MD, md))
                 if not (REPO / p).exists() or (REPO / p).read_text(encoding="utf-8") != t]
        if stale:
            print("[freeze-readiness] CHECK FAILED — out of date: " + ", ".join(stale))
            return 3
        print("[freeze-readiness] check OK — persisted assessment matches current inputs")
        return 0 if not blockers else 1

    atomic_write_text(REPO / OUT_JSON, text)
    atomic_write_text(REPO / OUT_MD, md)
    print(f"[freeze-readiness] wrote {OUT_JSON} and {OUT_MD}")
    if blockers:
        print("[freeze-readiness] Dataset V1 is NOT ready to freeze. This script freezes "
              "nothing and has taken no decision.")
    return 0 if not blockers else 1


if __name__ == "__main__":
    raise SystemExit(main())
