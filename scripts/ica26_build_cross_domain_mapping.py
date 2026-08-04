#!/usr/bin/env python3
"""Build the frozen PlantVillage <-> PlantDoc shared-class mapping.

Deterministic and evidence-bound: it derives pairs from the repository's own
label normaliser and from one recorded human policy, and it excludes everything
else with a stated reason. Re-running it on the same inputs rewrites the same
bytes.

    python scripts/ica26_build_cross_domain_mapping.py           # write
    python scripts/ica26_build_cross_domain_mapping.py --check   # verify only

Exit codes: 0 written/current, 1 --check found a difference.
"""
from __future__ import annotations

import argparse
import csv
import io
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

import pandas as pd  # noqa: E402

from ica26.experiments.mapping import (  # noqa: E402
    EVIDENCE_HEALTHY_POLICY,
    EVIDENCE_NORMALIZER,
    MAPPING_COLUMNS,
    MAPPING_CSV,
)
from ica26.mapping.crosswalk import normalize_crop, normalize_disease  # noqa: E402

PLANTVILLAGE_MANIFEST = REPO / "data/manifests/plantvillage_manifest.csv"
PLANTDOC_CORE_MANIFEST = REPO / "data/manifests/plantdoc_core_effective_manifest.csv"
ACTION_MAPPING_REVIEW = REPO / "data/mapping/action_mapping_review.csv"
EVALUATION_SCOPE = REPO / "configs/evaluation_scope.yaml"

HEALTHY_POLICY_ID = "policy:healthy-monitor-v1"

# Recorded human decision: both spider-mite classes denote Tetranychus urticae,
# an arthropod pest rather than a plant pathogen, and both are out of scope.
# See reports/ARTHROPOD_PEST_EVALUATION_SCOPE.md and configs/evaluation_scope.yaml.
ARTHROPOD_PEST_CLASSES = {
    "PlantDoc": "Tomato two spotted spider mites leaf",
    "PlantVillage": "Tomato___Spider_mites Two-spotted_spider_mite",
}


def canonical_id(crop: str, disease: str) -> str:
    return f"{crop}__{disease}".replace(" ", "_").replace(",", "").lower()


def build_rows() -> list[dict]:
    pv_labels = sorted(set(pd.read_csv(PLANTVILLAGE_MANIFEST)["class_label"].astype(str)))
    pd_labels = sorted(set(pd.read_csv(PLANTDOC_CORE_MANIFEST)["class_label"].astype(str)))

    review = pd.read_csv(ACTION_MAPPING_REVIEW)
    healthy_pd = {
        str(r.dataset_class): str(r.canonical_crop)
        for r in review.itertuples(index=False)
        if str(getattr(r, "canonical_disease", "")).strip().lower() == "healthy"
        and str(getattr(r, "review_status", "")).strip().lower() == "approved"
    }

    pv_key = {c: (normalize_crop(c), normalize_disease(c)) for c in pv_labels}
    pd_key = {c: (normalize_crop(c), normalize_disease(c)) for c in pd_labels}
    pv_by_key: dict[tuple[str, str], list[str]] = {}
    for c, k in pv_key.items():
        pv_by_key.setdefault(k, []).append(c)
    pv_healthy_by_crop = {
        normalize_crop(c): c for c in pv_labels if normalize_disease(c) == "healthy"
    }

    rows: list[dict] = []
    paired_pv: set[str] = set()
    paired_pd: set[str] = set()

    # --- source 1: deterministic normaliser key collisions --------------------
    for pdl in pd_labels:
        if pdl in ARTHROPOD_PEST_CLASSES.values():
            continue
        key = pd_key[pdl]
        if key[1] == "healthy":
            continue
        for pvl in sorted(pv_by_key.get(key, [])):
            crop, disease = key
            rows.append({
                "canonical_class_id": canonical_id(crop, disease),
                "plantvillage_label": pvl,
                "plantdoc_label": pdl,
                "crop": crop,
                "disease_state": disease,
                "mapping_evidence": (
                    "ica26.mapping.crosswalk.normalize_crop/normalize_disease applied "
                    f"unchanged to both labels yields the identical key ({crop!r}, {disease!r})"
                ),
                "evidence_source": EVIDENCE_NORMALIZER,
                "inclusion_status": "included",
                "exclusion_reason": "",
            })
            paired_pv.add(pvl)
            paired_pd.add(pdl)

    # --- source 2: human-approved healthy policy ------------------------------
    for pdl, crop in sorted(healthy_pd.items()):
        pvl = pv_healthy_by_crop.get(crop)
        if not pvl:
            continue
        rows.append({
            "canonical_class_id": canonical_id(crop, "healthy"),
            "plantvillage_label": pvl,
            "plantdoc_label": pdl,
            "crop": crop,
            "disease_state": "healthy",
            "mapping_evidence": (
                f"{HEALTHY_POLICY_ID}: data/mapping/action_mapping_review.csv records "
                f"canonical_disease=healthy, review_status=approved for {pdl!r}; the "
                f"PlantVillage label {pvl!r} carries the literal 'healthy' token"
            ),
            "evidence_source": EVIDENCE_HEALTHY_POLICY,
            "inclusion_status": "included",
            "exclusion_reason": "",
        })
        paired_pv.add(pvl)
        paired_pd.add(pdl)

    # --- everything else is excluded, with a reason ---------------------------
    pd_crops = {normalize_crop(c) for c in pd_labels} - {""}
    pv_crops = {normalize_crop(c) for c in pv_labels} - {""}

    for pvl in pv_labels:
        if pvl in paired_pv:
            continue
        crop, disease = pv_key[pvl]
        if pvl == ARTHROPOD_PEST_CLASSES["PlantVillage"]:
            reason = "arthropod_pest_out_of_disease_scope"
        elif crop in pd_crops:
            reason = "no_equivalent_plantdoc_class_under_available_evidence"
        else:
            reason = "crop_absent_from_plantdoc"
        rows.append({
            "canonical_class_id": "",
            "plantvillage_label": pvl,
            "plantdoc_label": "",
            "crop": crop,
            "disease_state": disease,
            "mapping_evidence": "",
            "evidence_source": "",
            "inclusion_status": "excluded",
            "exclusion_reason": reason,
        })

    for pdl in pd_labels:
        if pdl in paired_pd:
            continue
        crop, disease = pd_key[pdl]
        if pdl == ARTHROPOD_PEST_CLASSES["PlantDoc"]:
            reason = "arthropod_pest_out_of_disease_scope"
        elif crop in pv_crops:
            reason = "no_equivalent_plantvillage_class_under_available_evidence"
        else:
            reason = "crop_absent_from_plantvillage"
        rows.append({
            "canonical_class_id": "",
            "plantvillage_label": "",
            "plantdoc_label": pdl,
            "crop": crop,
            "disease_state": disease,
            "mapping_evidence": "",
            "evidence_source": "",
            "inclusion_status": "excluded",
            "exclusion_reason": reason,
        })

    rows.sort(key=lambda r: (
        r["inclusion_status"] != "included",
        r["canonical_class_id"],
        r["plantvillage_label"],
        r["plantdoc_label"],
    ))
    return rows


def render(rows: list[dict]) -> str:
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=MAPPING_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="verify without writing")
    args = ap.parse_args()

    rows = build_rows()
    text = render(rows)
    out = REPO / MAPPING_CSV

    included = [r for r in rows if r["inclusion_status"] == "included"]
    canonical = sorted({r["canonical_class_id"] for r in included})
    print(f"shared canonical classes : {len(canonical)}")
    print(f"included pair rows       : {len(included)}")
    print(f"excluded rows            : {len(rows) - len(included)}")
    by_source: dict[str, int] = {}
    for r in included:
        by_source[r["evidence_source"]] = by_source.get(r["evidence_source"], 0) + 1
    for k, v in sorted(by_source.items()):
        print(f"  evidence {k}: {v}")

    if args.check:
        if not out.exists():
            print(f"MISSING {out}", file=sys.stderr)
            return 1
        if out.read_text(encoding="utf-8") != text:
            print(f"DIFFERS {out}", file=sys.stderr)
            return 1
        print("check OK: mapping is byte-identical to a fresh rebuild")
        return 0

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
