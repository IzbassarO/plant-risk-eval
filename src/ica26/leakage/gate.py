"""Leakage-clearance gate: a persisted, manifest-bound prerequisite that
**technically blocks** cross-dataset evaluation until leakage is cleared.

A gate is valid only when it (a) exists, (b) still matches the current training
and evaluation manifests by SHA-256, (c) has ``status == pass``, (d) leaves zero
unresolved train/eval duplicate pairs, and (e) is not ``incomplete``. Any
cross-dataset evaluation entry point calls :func:`require_valid_gate` first and
fails closed otherwise. A development-only override exists, is disabled by
default, prints a prominent warning, and must never appear in paper commands.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..schemas import ValidationResult
from ..datasets.manifest import sha256_of_file
from .phash import find_duplicates, index_from_manifest, PHASH_ALGORITHM

SCHEMA_VERSION = "1.0"
GATE_STATUSES = ("pass", "fail", "incomplete")
DEFAULT_THRESHOLD = 6  # brief §8.4: perceptual-hash dedup at Hamming <= 6


class LeakageGateError(RuntimeError):
    """Raised when a required leakage gate is missing, stale, or not passing."""


@dataclass
class LeakageGate:
    schema_version: str
    generated_at: str
    training_dataset: str
    evaluation_dataset: str
    training_manifest_sha256: str
    evaluation_manifest_sha256: str
    phash_algorithm: str
    threshold: int
    exact_duplicate_count: int
    near_duplicate_count: int
    excluded_pair_count: int
    unresolved_pair_count: int
    status: str
    provenance: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "LeakageGate":
        known = {f: d.get(f) for f in LeakageGate.__annotations__}
        return LeakageGate(**known)

    def write(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2))
        return path

    @staticmethod
    def read(path: str | Path) -> "LeakageGate":
        return LeakageGate.from_dict(json.loads(Path(path).read_text()))


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def compute_gate(
    *,
    training_manifest: str | Path,
    training_root: str | Path,
    training_dataset: str,
    evaluation_manifest: str | Path,
    evaluation_root: str | Path,
    evaluation_dataset: str,
    threshold: int = DEFAULT_THRESHOLD,
    excluded_pair_count: int = 0,
    generated_at: Optional[str] = None,
    provenance: Optional[dict] = None,
) -> tuple[LeakageGate, "object"]:
    """Run the cross-dataset pHash check and build a gate. Returns (gate, result).

    ``status`` = ``incomplete`` if any image could not be hashed;
    ``pass`` if unresolved (detected − excluded) pairs == 0; else ``fail``.
    """
    idx_t, skip_t = index_from_manifest(training_manifest, training_root, training_dataset)
    idx_e, skip_e = index_from_manifest(evaluation_manifest, evaluation_root, evaluation_dataset)
    res = find_duplicates(idx_t, idx_e, threshold=threshold)
    exact = res["summary"]["n_exact_pairs"]
    near = res["summary"]["n_near_pairs"]
    detected = exact + near
    unresolved = max(0, detected - excluded_pair_count)
    skipped = len(skip_t) + len(skip_e)
    if skipped > 0:
        status = "incomplete"
    elif unresolved == 0:
        status = "pass"
    else:
        status = "fail"

    prov = dict(provenance or {})
    prov.setdefault("phash_algorithm", PHASH_ALGORITHM)
    prov.setdefault("skipped_training", len(skip_t))
    prov.setdefault("skipped_evaluation", len(skip_e))
    try:
        from .. import __version__ as _v
        prov.setdefault("ica26_version", _v)
    except Exception:
        pass

    gate = LeakageGate(
        schema_version=SCHEMA_VERSION,
        generated_at=generated_at or _utc_now(),
        training_dataset=training_dataset,
        evaluation_dataset=evaluation_dataset,
        training_manifest_sha256=sha256_of_file(training_manifest),
        evaluation_manifest_sha256=sha256_of_file(evaluation_manifest),
        phash_algorithm=PHASH_ALGORITHM,
        threshold=threshold,
        exact_duplicate_count=exact,
        near_duplicate_count=near,
        excluded_pair_count=excluded_pair_count,
        unresolved_pair_count=unresolved,
        status=status,
        provenance=prov,
    )
    return gate, res


def validate_gate(
    gate: LeakageGate,
    training_manifest: str | Path,
    evaluation_manifest: str | Path,
) -> ValidationResult:
    """Fail-closed validation. Truthy result == the gate authorises evaluation."""
    res = ValidationResult()
    if gate is None:
        res.add("error", "gate", "leakage gate is missing")
        return res
    if gate.schema_version != SCHEMA_VERSION:
        res.add("error", "schema_version", f"unsupported gate schema '{gate.schema_version}'")
    if gate.status not in GATE_STATUSES:
        res.add("error", "status", f"invalid status '{gate.status}'")
    # manifest binding: hashes must match the CURRENT manifests
    for label, man, recorded in [
        ("training", training_manifest, gate.training_manifest_sha256),
        ("evaluation", evaluation_manifest, gate.evaluation_manifest_sha256),
    ]:
        p = Path(man)
        if not p.exists():
            res.add("error", f"{label}_manifest", f"{label} manifest not found: {man}")
            continue
        current = sha256_of_file(p)
        if current != recorded:
            res.add("error", f"{label}_manifest_sha256",
                    f"{label} manifest changed since gate was generated (stale gate)")
    if gate.status == "incomplete":
        res.add("error", "status", "leakage check was incomplete")
    if gate.unresolved_pair_count > 0:
        res.add("error", "unresolved_pair_count",
                f"{gate.unresolved_pair_count} unresolved train/eval duplicate pair(s)")
    if gate.status != "pass":
        res.add("error", "status", f"gate status is '{gate.status}', not 'pass'")
    return res


_OVERRIDE_BANNER = (
    "\n" + "!" * 72 +
    "\n!!  DEV-ONLY OVERRIDE: leakage gate bypassed. Cross-dataset numbers"
    "\n!!  produced now are NOT valid and MUST NOT appear in the paper."
    "\n" + "!" * 72 + "\n"
)


def require_valid_gate(
    gate_path: str | Path,
    training_manifest: str | Path,
    evaluation_manifest: str | Path,
    *,
    allow_missing_leakage_gate: bool = False,
) -> LeakageGate:
    """Return the gate if valid; otherwise raise LeakageGateError.

    ``allow_missing_leakage_gate`` is a development-only escape hatch: disabled by
    default, prints a prominent warning, and must never be set in paper commands.
    """
    if allow_missing_leakage_gate:
        import sys
        print(_OVERRIDE_BANNER, file=sys.stderr)
        return None  # explicit, dev-only bypass
    gp = Path(gate_path)
    if not gp.exists():
        raise LeakageGateError(
            f"no leakage gate at {gate_path}. Cross-dataset evaluation is blocked "
            f"until a passing gate is generated (ica26-leakage-gate)."
        )
    gate = LeakageGate.read(gp)
    res = validate_gate(gate, training_manifest, evaluation_manifest)
    if not res.ok:
        msgs = "; ".join(i.message for i in res.errors)
        raise LeakageGateError(f"leakage gate invalid: {msgs}")
    return gate


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ica26-leakage-gate", description="Compute + persist a cross-dataset leakage gate.")
    ap.add_argument("--training-manifest", required=True)
    ap.add_argument("--training-root", required=True)
    ap.add_argument("--training-dataset", required=True)
    ap.add_argument("--evaluation-manifest", required=True)
    ap.add_argument("--evaluation-root", required=True)
    ap.add_argument("--evaluation-dataset", required=True)
    ap.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
    ap.add_argument("--excluded-pairs", type=int, default=0)
    ap.add_argument("--out", default="reports/leakage_gate.json")
    args = ap.parse_args(argv)

    gate, _ = compute_gate(
        training_manifest=args.training_manifest, training_root=args.training_root,
        training_dataset=args.training_dataset,
        evaluation_manifest=args.evaluation_manifest, evaluation_root=args.evaluation_root,
        evaluation_dataset=args.evaluation_dataset,
        threshold=args.threshold, excluded_pair_count=args.excluded_pairs,
        provenance={"command": "ica26-leakage-gate"},
    )
    gate.write(args.out)
    print(f"[leakage-gate] status={gate.status} exact={gate.exact_duplicate_count} "
          f"near={gate.near_duplicate_count} unresolved={gate.unresolved_pair_count}")
    print(f"[leakage-gate] wrote {args.out}")
    return 0 if gate.status == "pass" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
