#!/usr/bin/env python3
"""Pre-flight smoke tests for the ICA 2026 experiments.

Seven gates, in order. Any failure stops the run and reports which gate failed,
so the six full trainings are never started on a broken pipeline.

  1. the experiment dataset lock validates
  2. both datasets load from their manifests
  3. class indices and sample counts match the lock
  4. one mini-batch forward/backward for all three models
  5. a one-epoch experiment on a small deterministic subset
  6. checkpoint saving and metric generation
  7. cross-domain evaluation over the frozen shared classes

    python scripts/ica26_smoke.py

Exit codes: 0 all gates pass, 1 a gate failed.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

import torch  # noqa: E402

from ica26.experiments import data as dmod  # noqa: E402
from ica26.experiments import lock as L  # noqa: E402
from ica26.experiments import models as models_mod  # noqa: E402
from ica26.experiments.mapping import load_mapping  # noqa: E402

RESULTS: list[dict] = []


def gate(n: int, title: str):
    def deco(fn):
        def wrapper(*a, **kw):
            print(f"\n=== gate {n}/7: {title} ===", flush=True)
            t0 = time.perf_counter()
            try:
                detail = fn(*a, **kw)
            except Exception as exc:
                traceback.print_exc()
                RESULTS.append({"gate": n, "title": title, "passed": False,
                                "detail": f"{type(exc).__name__}: {exc}",
                                "seconds": round(time.perf_counter() - t0, 2)})
                return False
            RESULTS.append({"gate": n, "title": title, "passed": True,
                            "detail": detail,
                            "seconds": round(time.perf_counter() - t0, 2)})
            print(f"    PASS  {detail}")
            return True
        return wrapper
    return deco


@gate(1, "experiment dataset lock validates")
def gate_lock():
    report = L.require_valid_lock(REPO, check_pixels=False)
    return f"lock_digest={report['lock_digest'][:16]}…"


@gate(2, "both datasets load from their manifests")
def gate_load():
    pv = dmod.load_plantvillage(REPO)
    pdc = dmod.load_plantdoc_core(REPO)
    dmod.assert_pixels_present(pv, sample=200)
    dmod.assert_pixels_present(pdc, sample=None)
    return f"plantvillage={len(pv.frame)} plantdoc_core={len(pdc.frame)} (all Core pixels present)"


@gate(3, "class indices and sample counts match the lock")
def gate_counts():
    locked = L.load_lock(REPO)
    problems = []
    for key, spec in (("plantvillage", dmod.load_plantvillage(REPO)),
                      ("plantdoc_core", dmod.load_plantdoc_core(REPO))):
        idx = dmod.build_class_index(spec.frame["class_label"])
        want = locked["corpora"][key]
        if dmod.class_index_digest(idx) != want["class_index_digest"]:
            problems.append(f"{key}: class-index digest differs")
        if sorted(idx, key=lambda k: idx[k]) != want["classes"]:
            problems.append(f"{key}: class list differs")
        if len(spec.frame) != want["n_records"]:
            problems.append(f"{key}: {len(spec.frame)} != {want['n_records']}")
        counts = {str(k): int(v) for k, v in
                  spec.frame["split"].value_counts().sort_index().items()}
        if counts != want["split_counts"]:
            problems.append(f"{key}: split counts {counts} != {want['split_counts']}")
    if problems:
        raise AssertionError("; ".join(problems))
    return "PlantVillage 38 classes / 54,305; PlantDoc Core 28 classes / 2,561; indices match the lock"


@gate(4, "mini-batch forward/backward for all three models")
def gate_minibatch():
    hw = models_mod.select_device("auto")
    out = []
    for name in models_mod.MODEL_NAMES:
        model = models_mod.build_model(name, 38, pretrained=True).to(hw.device)
        model.train()
        x = torch.randn(4, 3, 224, 224, device=hw.device)
        y = torch.randint(0, 38, (4,), device=hw.device)
        opt = torch.optim.AdamW(model.parameters(), lr=3e-4)
        with torch.autocast(device_type=hw.device, dtype=torch.float16) if hw.device != "cpu" \
                else torch.autocast(device_type="cpu", enabled=False):
            loss = torch.nn.functional.cross_entropy(model(x), y)
        loss.backward()
        opt.step()
        lv = float(loss.detach())
        if not (lv == lv):  # NaN check; AMP underflow would show here
            raise AssertionError(f"{name}: loss is NaN under AMP on {hw.device}")
        n = models_mod.count_parameters(model)["total_parameters"]
        out.append(f"{name}(params={n:,}, loss={lv:.3f})")
        del model, opt
    return f"device={hw.device}: " + ", ".join(out)


SMOKE_RUNS = (
    "smoke_pdc_resnet50",
    "smoke_pdc_efficientnet_b0",
    "smoke_pdc_mobilenet_v3_small",
    "smoke_pv_mobilenet_v3_small",   # carries the cross-domain path
)


@gate(5, "one-epoch run on a deterministic subset (all three models)")
def gate_one_epoch():
    done = []
    for cfg_name in SMOKE_RUNS:
        cfg_path = REPO / "experiments/ica26/configs" / f"{cfg_name}.yaml"
        r = subprocess.run(
            [sys.executable, str(REPO / "scripts/ica26_train.py"),
             "--config", str(cfg_path), "--out-root", "experiments/ica26/_smoke"],
            cwd=str(REPO), capture_output=True, text=True,
        )
        if r.returncode != 0:
            raise AssertionError(f"{cfg_name} exited {r.returncode}\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}")
        done.append(cfg_name)
    return f"completed {', '.join(done)}"


@gate(6, "checkpoint saving and metric generation")
def gate_artifacts():
    root = REPO / "experiments/ica26/_smoke"
    found = []
    for eid in SMOKE_RUNS:
        ckpt = root / "runs" / eid / "best.pt"
        result = root / "metrics" / f"{eid}.json"
        history = root / "runs" / eid / "history.json"
        for p in (ckpt, result, history):
            if not p.exists():
                raise AssertionError(f"missing artifact: {p}")
        payload = json.loads(result.read_text())
        block = payload["evaluations"]["in_domain_test"]
        for field in ("accuracy", "macro_f1", "weighted_f1", "balanced_accuracy",
                      "macro_precision", "macro_recall", "per_class", "confusion_matrix"):
            if field not in block:
                raise AssertionError(f"{eid}: metric {field} absent")
        if "probabilistic" not in block or "expected_calibration_error" not in block["probabilistic"]:
            raise AssertionError(f"{eid}: probabilistic metrics absent")
        found.append(f"{eid}(ckpt={ckpt.stat().st_size // 1024}KB)")
    return ", ".join(found)


@gate(7, "cross-domain evaluation over the frozen shared classes")
def gate_cross_domain():
    mapping = load_mapping(REPO)
    payload = json.loads(
        (REPO / "experiments/ica26/_smoke/metrics/smoke_pv_mobilenet_v3_small.json").read_text()
    )
    cd = payload["evaluations"].get("cross_domain_plantdoc_core")
    if cd is None:
        raise AssertionError("cross-domain evaluation block absent from the smoke result")
    proto = cd["protocol"]
    if proto["n_shared_classes"] != len(mapping.canonical_classes):
        raise AssertionError(
            f"shared classes {proto['n_shared_classes']} != mapping {len(mapping.canonical_classes)}"
        )
    if proto["n_evaluated_samples"] + proto["n_excluded_unmapped_samples"] != proto["n_plantdoc_core_total"]:
        raise AssertionError("cross-domain sample accounting does not add up")
    return (f"{proto['n_shared_classes']} shared classes, "
            f"{proto['n_evaluated_samples']} evaluated, "
            f"{proto['n_excluded_unmapped_samples']} excluded as unmapped "
            f"(total {proto['n_plantdoc_core_total']})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="experiments/ica26/metrics/smoke_test_report.json")
    args = ap.parse_args()

    hw = models_mod.select_device("auto")
    print("=" * 78)
    print("ICA 2026 pre-flight smoke tests")
    print(f"hardware: device={hw.device} backend={hw.backend} "
          f"torch={hw.torch_version} platform={hw.platform} machine={hw.machine}")
    print("=" * 78)

    gates = [gate_lock, gate_load, gate_counts, gate_minibatch,
             gate_one_epoch, gate_artifacts, gate_cross_domain]
    ok = True
    for fn in gates:
        if not fn():
            ok = False
            break

    out = REPO / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "schema": "ica26.smoke_test_report/1",
        "all_passed": ok,
        "hardware": hw.to_dict(),
        "gates": RESULTS,
    }, indent=2, sort_keys=True) + "\n")

    print("\n" + "=" * 78)
    for r in RESULTS:
        print(f"  gate {r['gate']}/7  {'PASS' if r['passed'] else 'FAIL'}  "
              f"{r['title']}  ({r['seconds']}s)")
    print(f"ALL GATES PASSED: {ok}")
    print(f"report: {out}")
    print("=" * 78)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
