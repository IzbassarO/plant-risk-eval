#!/usr/bin/env python
"""Separate Core Dataset V1 readiness from Risk Evaluation Layer V1 (R2B.2 Part 7).

    python scripts/build_core_and_risk_readiness.py
    python scripts/build_core_and_risk_readiness.py --check

One readiness assessment covered two different things, and the stricter of them
was holding the other hostage. Whether a leaf image is correctly identified,
deduplicated and split is a **dataset** question. Which treatment a diagnosis
implies, and what it costs to get that wrong, is a **risk-modelling** question.
The action mappings and harm matrix are genuinely unfinished -- and they have
nothing to do with whether the pixels, labels and splits are sound.

Conflating them had a real cost: baseline computer-vision training was blocked
on a harm matrix it does not use. It also carried a real risk in the other
direction, because "Dataset V1 is not ready" invited the reading that the
dataset itself was defective, which the machine evidence does not support.

So this writes two assessments with separate statuses:

    reports/core_dataset_v1_readiness.json / CORE_DATASET_V1_READINESS.md
    reports/risk_evaluation_layer_v1_readiness.json / RISK_EVALUATION_LAYER_V1_READINESS.md

**Core Dataset V1** covers image identities, labels, splits, provenance,
duplicate and conservative exclusions, leakage decisions, effective manifests
and dataset fingerprints. It depends on none of the risk artifacts.

**Risk Evaluation Layer V1** covers disease-to-action mappings, PlantVillage
action mappings, the harm matrix, error costs, risk-aware metrics, and the
optional independent scientific diagnostic reviews. It is not ready, and its
being unfinished says nothing about the Core dataset's validity.

Neither assessment freezes anything, approves anything, or authorises training.
`ready_for_independent_audit` is the strongest thing Core can say here, and it
means only that the machine evidence is complete enough for someone who did not
do the work to start checking it.

The combined `dataset_v1_freeze_readiness` assessment is left in place and
unchanged; it remains the authority for the technical freeze workflow.

Exit codes: 0 ok, 1 not ready, 2 missing input, 3 stale (--check).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

SCHEMA_VERSION = "1.0"

CORE_JSON = Path("reports/core_dataset_v1_readiness.json")
CORE_MD = Path("reports/CORE_DATASET_V1_READINESS.md")
RISK_JSON = Path("reports/risk_evaluation_layer_v1_readiness.json")
RISK_MD = Path("reports/RISK_EVALUATION_LAYER_V1_READINESS.md")

CORE_MANIFEST = Path("data/manifests/plantdoc_core_effective_manifest.csv")
CONSERVATIVE_DECISION = Path("data/exclusions/core_dataset_v1_conservative_exclusions.csv")
TWO_POPULATION_REPORT = Path("reports/leakage_two_population_report.json")
PLANTVILLAGE_MANIFEST = Path("data/manifests/plantvillage_manifest.csv")
PLANTVILLAGE_RECONSTRUCTION = Path("reports/plantvillage_manifest_reconstruction.json")

#: Conditions from the combined assessment that are about the DATA.
CORE_INHERITED = (
    "plantdoc_acquired",
    "plantvillage_materialized",
    "cross_dataset_leakage_gate",
    "internal_duplicate_gate",
    "effective_dataset_current",
    "effective_dataset_integrity",
    "effective_dataset_pixels_verified",
    "human_review_evidence_intact",
    "anonymity",
    # Both remain BLOCKED here, deliberately: an independent audit and a freeze
    # approval are exactly the two decisions this task must not take.
    "open_audit_findings_closed",
    "freeze_approval_recorded",
)

#: Conditions that are about RISK MODELLING, not about the dataset.
RISK_INHERITED = (
    "disease_action_mapping_reviewed",
    "plantvillage_action_mapping_coverage",
    "harm_matrix_approved",
    # The G07/G08/G10 scientific review. Core no longer depends on it because
    # those records are conservatively excluded; if the Risk Layer ever wants
    # them back, this is the decision that has to be taken first.
    "relabel_second_scientific_review",
)

#: The Core decisions that remain open. Core can be ready FOR these, never ready
#: DESPITE them.
CORE_DECISION_CONDITIONS = ("open_audit_findings_closed", "freeze_approval_recorded")

#: What may be trained once Core Dataset V1 is audited and frozen, and what may
#: not until the Risk Layer is frozen too. Recorded as data so the boundary is
#: machine-readable rather than a paragraph someone has to remember.
TRAINING_BOUNDARY = {
    "permitted_after_core_freeze": [
        "plantvillage_in_domain_classification_baseline",
        "plantdoc_core_in_domain_classification_baseline",
        "model_calibration_experiments",
        "ordinary_classification_metrics",
        "dataset_loading_and_training_pipeline_validation",
    ],
    "blocked_until_risk_layer_frozen": [
        "harm_weighted_model_selection",
        "action_aware_training",
        "treatment_recommendation",
        "risk_weighted_conclusions",
        "final_risk_aware_evaluation_tables",
    ],
}


def _load_script(name: str, path: Path):
    """Import a sibling script as a module.

    Registered in ``sys.modules`` before execution because ``@dataclass`` looks
    its own module up by name while the class body is being processed.
    """
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_builder():
    return _load_script(
        "_dataset_v1_readiness_builder",
        REPO / "scripts" / "build_dataset_v1_freeze_readiness.py")


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


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- #
# Core-specific conditions
# --------------------------------------------------------------------------- #
def _conservative_exclusion_conditions(builder, repo: Path) -> list:
    """The operator decision, the Core manifest, and their reconciliation."""
    from ica26.datasets.conservative_exclusions import (
        apply_conservative_exclusions,
        parse_conservative_exclusions,
        verify_core_records,
    )

    out = []
    apply_script = repo / "scripts" / "apply_core_conservative_exclusions.py"
    if not apply_script.is_file() or not (repo / CONSERVATIVE_DECISION).is_file():
        for cid, title in (
            ("conservative_exclusions_recorded",
             "A recorded operator decision defines the Core exclusions"),
            ("core_dataset_current",
             "The Core dataset matches a fresh rebuild from the decisions"),
            ("core_dataset_integrity", "The Core dataset is internally sound"),
        ):
            out.append(builder._c(cid, title, "machine", False,
                                  f"no conservative-exclusion decision at "
                                  f"{CONSERVATIVE_DECISION}",
                                  str(CONSERVATIVE_DECISION), repo))
        return out

    module = _load_script("_core_exclusions_apply", apply_script)
    manifest, adj = module.load_adjudication(repo)
    effective = read_csv(repo / module.EFFECTIVE)
    rows = read_csv(repo / CONSERVATIVE_DECISION)
    exclusions, parse_violations = parse_conservative_exclusions(
        rows, adj, artifact_digests=module.artifact_digests(repo))
    core, apply_violations = apply_conservative_exclusions(effective, exclusions)
    verify_violations, report = verify_core_records(
        manifest, effective, core, exclusions, adj)

    authenticated = not (adj.violations or parse_violations or apply_violations)
    out.append(builder._c(
        "conservative_exclusions_recorded",
        "A recorded operator decision defines the Core exclusions",
        "machine", authenticated and bool(exclusions),
        (f"{len(exclusions)} authenticated exclusion(s) for "
         f"{report['conservatively_excluded_groups']}; each bound to the R2B "
         f"outcome it removes"
         if authenticated else
         f"{len(parse_violations + apply_violations)} violation(s): "
         f"{(parse_violations + apply_violations)[:3]}"),
        str(CONSERVATIVE_DECISION), repo))

    # Fresh rebuild equality, proved by re-running the builder's own --check.
    check = subprocess.run([sys.executable, str(apply_script), "--check"],
                           cwd=str(repo), capture_output=True, text=True)
    out.append(builder._c(
        "core_dataset_current",
        "The Core dataset matches a fresh rebuild from the decisions",
        "machine", check.returncode == 0,
        (f"fresh {report['core_records']} == persisted "
         f"{report['core_records']}, identity digest "
         f"{report['core_identity_digest'][:16]}..., byte-identical"
         if check.returncode == 0
         else f"fresh rebuild differs (exit {check.returncode})"),
        str(CORE_MANIFEST), repo))

    sound = (not verify_violations
             and report["surviving_exact_duplicate_groups"] == 0
             and report["unique_relpaths"] and report["unique_effective_identities"]
             and report["non_reviewed_records_unchanged"])
    out.append(builder._c(
        "core_dataset_integrity", "The Core dataset is internally sound",
        "machine", sound,
        (f"{report['core_records']} record(s), splits "
         f"{report['core_split_counts']}, {report['core_class_count']} class(es), "
         f"0 exact duplicates, {report['non_reviewed_records']} non-reviewed "
         f"record(s) unchanged"
         if sound else f"{len(verify_violations)} violation(s): "
                       f"{verify_violations[:3]}"),
        str(CORE_MANIFEST), repo))
    return out


def _core_leakage_condition(builder, repo: Path):
    report = read_json(repo / TWO_POPULATION_REPORT)
    if not isinstance(report, dict):
        return builder._c(
            "core_cross_dataset_leakage", "Core-corpus cross-dataset leakage is cleared",
            "machine", False,
            f"no two-population leakage report at {TWO_POPULATION_REPORT}",
            str(TWO_POPULATION_REPORT), repo)

    core = report.get("core") or {}
    acquired = report.get("acquired") or {}
    core_manifest_rows = (len(read_csv(repo / CORE_MANIFEST))
                          if (repo / CORE_MANIFEST).is_file() else -1)
    ok = (core.get("n_exact_pairs") == 0
          and report.get("core_near_pairs_all_reviewed") is True
          and not report.get("core_unresolved_near_pairs")
          and core.get("n_evaluation_indexed") == core_manifest_rows)
    return builder._c(
        "core_cross_dataset_leakage",
        "Core-corpus cross-dataset leakage is cleared",
        "machine", ok,
        (f"independently computed over PlantVillage "
         f"{core.get('n_training_indexed')} x Core PlantDoc "
         f"{core.get('n_evaluation_indexed')}: {core.get('n_exact_pairs')} exact, "
         f"{core.get('n_near_pairs')} near, all resolved, 0 unresolved "
         f"(acquired corpus separately: {acquired.get('n_exact_pairs')} exact, "
         f"{acquired.get('n_near_pairs')} near)"
         if ok else
         f"exact={core.get('n_exact_pairs')}, unresolved="
         f"{len(report.get('core_unresolved_near_pairs') or [])}, "
         f"indexed={core.get('n_evaluation_indexed')} vs manifest "
         f"{core_manifest_rows}"),
        str(TWO_POPULATION_REPORT), repo)


def _plantvillage_reconstruction_condition(builder, repo: Path):
    """Validate the persisted reconstruction evidence, not a live re-derivation.

    Re-deriving here would make the assessment depend on whether the optional
    ``hf`` extra and the Hugging Face cache happen to be present, so the same
    commit would produce different readiness artifacts in different environments
    and ``--check`` could never pass on a fresh clone. The reconstruction is
    recorded as digest-bound evidence by
    ``scripts/build_plantvillage_reconstruction.py`` and validated here like
    every other artifact -- including the binding that stops it outliving the
    manifest it describes.
    """
    from ica26.datasets.manifest import sha256_of_file

    record = read_json(repo / PLANTVILLAGE_RECONSTRUCTION)
    if not isinstance(record, dict):
        return builder._c(
            "plantvillage_manifest_reconstructed",
            "The PlantVillage manifest is exactly reconstructed from pinned sources",
            "machine", False,
            f"no reconstruction record at {PLANTVILLAGE_RECONSTRUCTION}; run "
            "scripts/build_plantvillage_reconstruction.py with the pinned sources",
            str(PLANTVILLAGE_RECONSTRUCTION), repo)

    manifest = repo / PLANTVILLAGE_MANIFEST
    current = sha256_of_file(manifest) if manifest.is_file() else "<absent>"
    stale = record.get("manifest_sha256") != current
    clean = (record.get("equal") is True
             and not record.get("problems")
             and record.get("missing_records") == 0
             and record.get("extra_records") == 0
             and record.get("duplicated_identities") == 0
             and record.get("value_mismatches") == 0
             and record.get("order_matches") is True
             and record.get("expected_records") == record.get("persisted_records"))
    return builder._c(
        "plantvillage_manifest_reconstructed",
        "The PlantVillage manifest is exactly reconstructed from pinned sources",
        "machine", clean and not stale,
        (f"{record.get('expected_records')} record(s) re-derived from the pinned "
         f"sources ({record.get('expected_train')} train / "
         f"{record.get('expected_test')} test); 0 missing, 0 extra, 0 duplicated, "
         f"0 value mismatch(es), order matches"
         if clean and not stale else
         ("reconstruction record is stale: it describes manifest "
          f"{str(record.get('manifest_sha256'))[:12]}..., current is "
          f"{current[:12]}..." if stale
          else f"reconstruction reported problem(s): {record.get('problems')[:3]}")),
        str(PLANTVILLAGE_RECONSTRUCTION), repo)


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #
def evaluate(repo: Path, *, skip_pixel_verification: bool = False):
    builder = _load_builder()
    combined = builder.evaluate(repo, verify_pixels=not skip_pixel_verification)
    by_id = {c.id: c for c in combined}

    core = [by_id[cid] for cid in CORE_INHERITED if cid in by_id]
    core.append(_plantvillage_reconstruction_condition(builder, repo))
    core.extend(_conservative_exclusion_conditions(builder, repo))
    core.append(_core_leakage_condition(builder, repo))

    risk = [by_id[cid] for cid in RISK_INHERITED if cid in by_id]

    unassigned = sorted(set(by_id) - set(CORE_INHERITED) - set(RISK_INHERITED))
    return core, risk, unassigned


def _layer_payload(name, dataset, conditions, *, extra: dict) -> dict:
    blockers = [c.id for c in conditions if not c.ok]
    return {
        "schema_version": SCHEMA_VERSION,
        "layer": name,
        "dataset": dataset,
        "satisfied": sum(1 for c in conditions if c.ok),
        "blocked": len(blockers),
        "blockers": blockers,
        "conditions": [asdict(c) for c in conditions],
        **extra,
    }


def build(repo: Path = REPO, *, skip_pixel_verification: bool = False):
    core, risk, unassigned = evaluate(
        repo, skip_pixel_verification=skip_pixel_verification)

    machine_blockers = [c.id for c in core
                        if not c.ok and c.id not in CORE_DECISION_CONDITIONS]
    decision_blockers = [c.id for c in core
                         if not c.ok and c.id in CORE_DECISION_CONDITIONS]

    if machine_blockers:
        core_status = "not_ready"
    elif decision_blockers:
        # Every mechanical check passes; what remains is exactly the two
        # decisions a machine must not take for itself.
        core_status = "ready_for_independent_audit"
    else:
        core_status = "ready_to_freeze"

    core_payload = _layer_payload(
        "Core Dataset V1", "Core Dataset V1", core,
        extra={
            "status": core_status,
            "frozen": False,
            "training_authorized": False,
            "machine_blockers": machine_blockers,
            "open_decisions": decision_blockers,
            "depends_on_risk_layer": False,
            "unassigned_conditions": unassigned,
            "training_boundary": TRAINING_BOUNDARY,
            "provenance": {
                "command": "build_core_and_risk_readiness.py",
                "freezes_nothing": True,
                "authorizes_no_training": True,
                "note": ("Core readiness is independent of action mappings, the "
                         "harm matrix, risk weights, treatment recommendations, "
                         "and risk-aware evaluation approval."),
            },
        })

    risk_blockers = [c.id for c in risk if not c.ok]
    risk_payload = _layer_payload(
        "Risk Evaluation Layer V1", "Risk Evaluation Layer V1", risk,
        extra={
            "status": "not_ready" if risk_blockers else "ready_for_independent_audit",
            "frozen": False,
            "scientific_second_review_performed": False,
            "provenance": {
                "command": "build_core_and_risk_readiness.py",
                "freezes_nothing": True,
                "note": ("This layer being unfinished does not imply the Core "
                         "dataset is invalid. They are separate questions with "
                         "separate evidence."),
            },
        })

    return (json.dumps(core_payload, indent=2, sort_keys=True) + "\n",
            render_core_markdown(core_payload),
            json.dumps(risk_payload, indent=2, sort_keys=True) + "\n",
            render_risk_markdown(risk_payload, core_payload),
            core_payload, risk_payload)


def _condition_table(conditions) -> list[str]:
    lines = ["| Condition | Kind | Status | Detail |", "|---|---|---|---|"]
    for c in conditions:
        mark = "satisfied" if c["status"] == "satisfied" else "**BLOCKED**"
        lines.append(f"| {c['title']} (`{c['id']}`) | {c['kind']} | {mark} | "
                     f"{c['detail']} |")
    return lines


def render_core_markdown(p: dict) -> str:
    L = ["# Core Dataset V1 — technical readiness", "",
         "_Generated by `scripts/build_core_and_risk_readiness.py`. **This assessment "
         "freezes nothing, approves nothing, and authorises no training.**_", "",
         f"**Status: `{p['status'].upper()}`** — {p['satisfied']} satisfied, "
         f"{p['blocked']} blocked.", "",
         "**Core Dataset V1 frozen: NO.**",
         "**Training authorized: NO** — not until Core Dataset V1 is independently "
         "audited and frozen.", ""]

    L += ["## What Core Dataset V1 is", "",
         "Immutable image identities, the labels used for classification, the "
         "train/test splits, source provenance, duplicate exclusions, conservative "
         "uncertainty exclusions, leakage decisions, effective manifests and dataset "
         "fingerprints.", "",
         "Its readiness deliberately does **not** depend on action mappings, the harm "
         "matrix, risk weights, treatment recommendations, or risk-aware evaluation "
         "approval. Those belong to the Risk Evaluation Layer, and whether a leaf is "
         "correctly identified and split is not answered by what treating it would "
         "cost.", ""]

    if p["machine_blockers"]:
        L += ["## Blocking machine conditions", ""]
        for b in p["machine_blockers"]:
            c = next(x for x in p["conditions"] if x["id"] == b)
            L.append(f"- **{c['title']}** (`{c['id']}`) — {c['detail']}")
        L.append("")

    if p["open_decisions"]:
        L += ["## Open decisions", "",
              "Every mechanical check above passes. What remains is exactly the "
              "decisions a machine must not take for itself:", ""]
        for b in p["open_decisions"]:
            c = next(x for x in p["conditions"] if x["id"] == b)
            L.append(f"- **{c['title']}** (`{c['id']}`, {c['kind']}) — {c['detail']}")
        L.append("")

    L += ["## All Core conditions", ""] + _condition_table(p["conditions"]) + [""]

    L += ["## Training authorization boundary", "",
          "Training is **not** authorized: Core Dataset V1 is not frozen. After an "
          "independent audit and a recorded freeze approval, the following become "
          "permissible, because none of them consumes the unfinished Risk Layer:", ""]
    for item in p["training_boundary"]["permitted_after_core_freeze"]:
        L.append(f"- `{item}`")
    L += ["", "These remain blocked until Risk Evaluation Layer V1 is itself frozen:",
          ""]
    for item in p["training_boundary"]["blocked_until_risk_layer_frozen"]:
        L.append(f"- `{item}`")
    L += ["", "## Re-deriving this assessment", "",
          "```", "python scripts/build_core_and_risk_readiness.py",
          "python scripts/build_core_and_risk_readiness.py --check", "```", "",
          "No wall-clock field, so repeated runs are byte-identical and the "
          "assessment can be compared across commits.", ""]
    return "\n".join(L)


def render_risk_markdown(p: dict, core: dict) -> str:
    L = ["# Risk Evaluation Layer V1 — readiness", "",
         "_Generated by `scripts/build_core_and_risk_readiness.py`. **This assessment "
         "freezes nothing and approves nothing.**_", "",
         f"**Status: `{p['status'].upper()}`** — {p['satisfied']} satisfied, "
         f"{p['blocked']} blocked.", "",
         "**Scientific second review performed: NO.**", ""]

    L += ["## What this layer is, and what its state does not mean", "",
          "Disease-to-action mappings, PlantVillage action mappings, the harm matrix, "
          "error-cost definitions, risk-aware metrics, and the optional independent "
          "scientific diagnostic reviews.", "",
          "This layer is not ready. That is a statement about risk modelling and "
          "**not** about the dataset: Core Dataset V1 reports "
          f"`{core['status']}` on its own evidence. Reading an unfinished harm matrix "
          "as evidence that the images, labels or splits are defective would be a "
          "mistake, and keeping the two assessments apart is how that mistake is "
          "prevented.", ""]

    if p["blockers"]:
        L += ["## Blocking conditions", ""]
        for b in p["blockers"]:
            c = next(x for x in p["conditions"] if x["id"] == b)
            L.append(f"- **{c['title']}** (`{c['id']}`, {c['kind']}) — {c['detail']}")
        L.append("")

    L += ["## All Risk Layer conditions", ""] + _condition_table(p["conditions"]) + [""]

    L += ["## The G07/G08/G10 relabels", "",
          "Those three records are conservatively excluded from Core Dataset V1 for "
          "insufficient independent diagnostic evidence, so Core no longer depends on "
          "adjudicating them. The scientific question is still open and is recorded "
          "here rather than closed by the exclusion. If the Risk Layer ever wants "
          "those records back, an independent second review is the decision that has "
          "to be taken first.", ""]
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="core-and-risk-readiness")
    ap.add_argument("--check", action="store_true",
                    help="verify the persisted assessments match current inputs")
    ap.add_argument("--skip-pixel-verification", action="store_true")
    args = ap.parse_args(argv)

    if not (REPO / "data/manifests/plantdoc_manifest.csv").exists():
        print("[core-risk-readiness] missing PlantDoc manifest")
        return 2

    core_json, core_md, risk_json, risk_md, core_payload, risk_payload = build(
        REPO, skip_pixel_verification=args.skip_pixel_verification)

    print(f"[core-risk-readiness] Core Dataset V1: {core_payload['status']} "
          f"({core_payload['satisfied']} satisfied, {core_payload['blocked']} blocked; "
          f"frozen={core_payload['frozen']}, "
          f"training_authorized={core_payload['training_authorized']})")
    print(f"[core-risk-readiness] Risk Evaluation Layer V1: {risk_payload['status']} "
          f"({risk_payload['satisfied']} satisfied, {risk_payload['blocked']} blocked)")
    if core_payload["unassigned_conditions"]:
        print("[core-risk-readiness] REFUSED — condition(s) belong to neither layer: "
              f"{core_payload['unassigned_conditions']}")
        return 1

    outputs = ((CORE_JSON, core_json), (CORE_MD, core_md),
               (RISK_JSON, risk_json), (RISK_MD, risk_md))
    if args.check:
        stale = [str(p) for p, t in outputs
                 if not (REPO / p).exists()
                 or (REPO / p).read_text(encoding="utf-8") != t]
        if stale:
            print("[core-risk-readiness] CHECK FAILED — out of date: "
                  + ", ".join(stale))
            return 3
        print("[core-risk-readiness] check OK — assessments match current inputs")
        return 0 if not core_payload["machine_blockers"] else 1

    for path, text in outputs:
        atomic_write_text(REPO / path, text)
    print(f"[core-risk-readiness] wrote {CORE_JSON}, {CORE_MD}, {RISK_JSON}, {RISK_MD}")
    return 0 if not core_payload["machine_blockers"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
