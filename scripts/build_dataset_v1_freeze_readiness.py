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
AUDIT_SIGNOFF = Path("reports/DATASET_V1_AUDIT_SIGNOFF.json")
FREEZE_APPROVAL = Path("data/manifests/dataset_v1_freeze_approval.json")
FREEZE_ARTIFACT = Path("data/manifests/dataset_v1_freeze.json")

OUT_JSON = Path("reports/dataset_v1_freeze_readiness.json")
OUT_MD = Path("reports/DATASET_V1_FREEZE_READINESS.md")

#: Audit findings that must be closed before a freeze. Closure is asserted by a
#: human sign-off artifact, never inferred from the presence of a report.
REQUIRED_CLOSED_FINDINGS = ("AUD-EC-005", "AUD-EC-006", "AUD-EC-007")


@dataclass
class Condition:
    id: str
    title: str
    kind: str          # "machine" | "human"
    status: str        # "satisfied" | "blocked"
    detail: str
    evidence: str = ""

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


def _c(cid, title, kind, ok, detail, evidence="") -> Condition:
    return Condition(cid, title, kind, "satisfied" if ok else "blocked", detail, evidence)


# --------------------------------------------------------------------------- #
# Conditions
# --------------------------------------------------------------------------- #
def evaluate(repo: Path, *, verify_pixels: bool) -> list[Condition]:
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
    out.append(_c("anonymity", "No machine-specific or personal identifier in paper artifacts",
                  "machine", port.ok,
                  port.summary() if port.ok else
                  f"{len(port.errors)} finding(s), first: {port.errors[0].message}",
                  "src/ica26/portability.py"))

    # --- mapping review (human) ---------------------------------------------- #
    mapping = read_csv(repo / MAPPING_REVIEW) if (repo / MAPPING_REVIEW).exists() else []
    needs = [r for r in mapping if (r.get("review_status") or "").strip() == "needs_review"]
    out.append(_c("disease_action_mapping_reviewed",
                  "Every disease->action mapping row carries a terminal human decision",
                  "human", bool(mapping) and not needs,
                  f"{len(needs)} of {len(mapping)} row(s) still needs_review"
                  if mapping else "no mapping review file",
                  str(MAPPING_REVIEW)))

    pv_classes = {r["class_label"] for r in read_csv(repo / PLANTVILLAGE_MANIFEST)} if (
        repo / PLANTVILLAGE_MANIFEST).exists() else set()
    pv_mapped = {(r.get("dataset_class") or "").strip() for r in mapping
                 if (r.get("dataset") or "").strip() == "PlantVillage"}
    covered = pv_classes & pv_mapped
    out.append(_c("plantvillage_action_mapping_coverage",
                  "Every PlantVillage class has an action mapping",
                  "human", bool(pv_classes) and covered == pv_classes,
                  f"coverage {len(covered)}/{len(pv_classes)} PlantVillage class(es)",
                  str(MAPPING_REVIEW)))

    # --- harm matrix (human) -------------------------------------------------- #
    try:
        from ica26.evaluation import harm
        m = harm.load_reviewed_matrix(repo / HARM_TEMPLATE)
        ready = m.is_production_ready()
        detail = (f"matrix '{m.matrix_id}' review_status='{m.review_status}', "
                  f"is_example={m.is_example}")
    except Exception as exc:                                  # noqa: BLE001
        ready, detail = False, f"could not load a reviewed harm matrix: {exc}"
    out.append(_c("harm_matrix_approved", "A human-approved harm matrix exists",
                  "human", ready, detail, str(HARM_TEMPLATE)))

    # --- audit sign-off (human) ------------------------------------------------ #
    signoff = read_json(repo / AUDIT_SIGNOFF)
    closed = {str(x) for x in (signoff or {}).get("closed_findings", [])}
    missing = [f for f in REQUIRED_CLOSED_FINDINGS if f not in closed]
    remediation_audited = bool((signoff or {}).get("r2b_remediation_independently_audited"))
    out.append(_c("open_audit_findings_closed",
                  "Open audit findings are closed by an independent re-audit",
                  "human", bool(signoff) and not missing,
                  f"no sign-off artifact; {list(REQUIRED_CLOSED_FINDINGS)} remain open"
                  if signoff is None else
                  (f"still open: {missing}" if missing else f"closed: {sorted(closed)}"),
                  str(AUDIT_SIGNOFF)))
    out.append(_c("remediation_independently_audited",
                  "The R2B duplicate remediation has itself been independently audited",
                  "human", remediation_audited,
                  "not recorded in any sign-off artifact" if not remediation_audited
                  else "recorded in the audit sign-off",
                  str(AUDIT_SIGNOFF)))

    # --- the freeze decision itself (human) ------------------------------------ #
    approval = read_json(repo / FREEZE_APPROVAL)
    approved = bool((approval or {}).get("approved"))
    out.append(_c("freeze_approval_recorded",
                  "A human has recorded an explicit Dataset V1 freeze approval",
                  "human", approved,
                  "no approval artifact; the freeze decision has not been taken"
                  if approval is None else f"approved={approved}",
                  str(FREEZE_APPROVAL)))

    return out


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
    L += ["", "## What a human must produce", "",
          "A `machine` condition is evaluated here from artifacts, digests, and a fresh "
          "rebuild. A `human` condition is a scientific judgement and is satisfied **only** by "
          "an explicit decision artifact — its absence is a blocker, never a default.", "",
          f"| Artifact | Satisfies |", "|---|---|",
          f"| `{AUDIT_SIGNOFF}` | `open_audit_findings_closed` — JSON with "
          f"`closed_findings` listing at least {list(REQUIRED_CLOSED_FINDINGS)}; and "
          "`r2b_remediation_independently_audited: true` for "
          "`remediation_independently_audited` |",
          f"| `{FREEZE_APPROVAL}` | `freeze_approval_recorded` — JSON with `approved: true`, "
          "an anonymous reviewer id, and an ISO-8601 timestamp with offset |",
          f"| `{MAPPING_REVIEW}` | the two mapping conditions, once every row carries a "
          "terminal decision and PlantVillage coverage is complete |",
          f"| `{HARM_TEMPLATE}` | `harm_matrix_approved`, once a non-example matrix is "
          "approved with complete weights |", "",
          "## Re-deriving this assessment", "",
          "```", "python scripts/build_dataset_v1_freeze_readiness.py",
          "python scripts/build_dataset_v1_freeze_readiness.py --check", "```", "",
          "No wall-clock field, so repeated runs are byte-identical and the assessment can be "
          "compared across commits.", ""]
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

    conditions = evaluate(REPO, verify_pixels=not args.skip_pixel_verification)
    blockers = [c.id for c in conditions if not c.ok]

    digests = {}
    for name, p in (("plantdoc_manifest", PLANTDOC_MANIFEST),
                    ("effective_manifest", EFFECTIVE),
                    ("duplicate_resolution", RESOLUTION),
                    ("leakage_gate", LEAKAGE_GATE),
                    ("internal_duplicate_gate", INTERNAL_GATE),
                    ("action_mapping_review", MAPPING_REVIEW),
                    ("human_review_evidence", EVIDENCE_MANIFEST)):
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
