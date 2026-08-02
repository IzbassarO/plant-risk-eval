"""Leakage-clearance gate: a persisted, input-bound prerequisite that
**technically blocks** cross-dataset evaluation until leakage is cleared.

A gate is valid only when it (a) exists, (b) still matches EVERY input it was
computed from by SHA-256, (c) has ``status == pass``, (d) leaves zero unresolved
train/eval duplicate pairs, (e) records zero authorization violations, and (f) is
not ``incomplete``. Any cross-dataset evaluation entry point calls
:func:`require_valid_gate` first and fails closed otherwise. A development-only
override exists, is disabled by default, prints a prominent warning, and must
never appear in paper commands.

Authorization model (schema 2.0, hardening AUD-EC-001/002/008)
--------------------------------------------------------------
Earlier revisions authorised a near pair by its two relative paths alone, and
authorised exact pairs by a caller-supplied integer. Both were forgeable: an
edited SHA-256, a duplicated pair id, a surplus review row, or
``--excluded-pairs 999`` all produced a numerical ``pass``. Schema 2.0 replaces
both with record-derived authorization over a **canonical pair identity**:

* every authoritative pair is identified by BOTH datasets, BOTH relative paths,
  BOTH class labels, BOTH endpoint SHA-256 digests (read from the current
  manifests, not from the review file), the pHash distance, and the
  exact/near classification;
* a review or exclusion row is credited only if it reproduces that identity
  field-for-field, and the review set must be in strict **bijection** with the
  authoritative set -- no missing, surplus, unknown, or duplicated rows;
* violations do not merely forfeit credit, they force the gate to ``fail``. A
  gate can therefore never certify a review set it could not authenticate.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from ..schemas import ValidationResult
from ..datasets.manifest import sha256_of_file
from .phash import find_duplicates, index_from_manifest, PHASH_ALGORITHM

# 2.0: identity-authenticated review, record-derived exact exclusions, full input
# binding, and a byte-deterministic artifact. A 1.x gate is rejected, never
# reinterpreted -- its counts do not mean the same thing.
SCHEMA_VERSION = "2.0"
GATE_STATUSES = ("pass", "fail", "incomplete")
DEFAULT_THRESHOLD = 6  # brief §8.4: perceptual-hash dedup at Hamming <= 6

# --------------------------------------------------------------------------- #
# Human near-duplicate review vocabulary. Mirrors
# reports/NEAR_DUPLICATE_HUMAN_REVIEW.md and the disposition policy in
# reports/LEAKAGE_GATE_EXCLUSION_POLICY.md.
# --------------------------------------------------------------------------- #
NEAR_REVIEW_DECISIONS = ("same_source_image", "same_scene_different_crop",
                         "visually_similar_but_independent", "clearly_different",
                         "uncertain")
NEAR_REVIEW_DISPOSITIONS = ("exclude_evaluation", "keep", "needs_secondary_review")

#: Decisions/dispositions that do NOT terminate review -- they resolve nothing.
NEAR_REVIEW_NON_TERMINAL_DECISIONS = frozenset({"uncertain"})
NEAR_REVIEW_NON_TERMINAL_DISPOSITIONS = frozenset({"needs_secondary_review"})

#: Attribution a terminal decision must carry (provenance is not optional).
NEAR_REVIEW_ATTRIBUTION_FIELDS = ("reviewer", "reviewed_at", "decision_reason")

#: Named inputs bound into the persisted gate. Every one is digested at compute
#: time and re-digested at validation time; any drift makes the gate stale.
GATE_INPUT_NAMES = (
    "training_manifest",
    "evaluation_manifest",
    "pair_table",
    "near_review",
    "reviewed_exclusions",
    "exact_exclusions",
    "leakage_config",
)


class LeakageGateError(RuntimeError):
    """Raised when a required leakage gate is missing, stale, or not passing."""


# --------------------------------------------------------------------------- #
# Canonical pair identity
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PairIdentity:
    """Immutable identity of one detected cross-dataset duplicate pair.

    Endpoint digests come from the CURRENT manifests, never from the review file,
    so editing a SHA-256 in the review CSV cannot make it authenticate.
    """

    training_dataset: str
    training_relpath: str
    training_class: str
    training_sha256: str
    evaluation_dataset: str
    evaluation_relpath: str
    evaluation_class: str
    evaluation_sha256: str
    phash_distance: int
    classification: str  # "exact" | "near"

    @property
    def key(self) -> tuple[str, str]:
        return (self.training_relpath, self.evaluation_relpath)

    def as_dict(self) -> dict:
        return asdict(self)


def _read_csv(path: str | Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _manifest_sha_index(manifest_csv: str | Path) -> dict[str, str]:
    return {r["relpath"]: r["sha256"] for r in _read_csv(manifest_csv)}


def build_authoritative_pairs(
    pair_table_csv: str | Path,
    training_manifest: str | Path,
    evaluation_manifest: str | Path,
    *,
    training_dataset: str,
    evaluation_dataset: str,
) -> tuple[dict[tuple[str, str], PairIdentity], list[str]]:
    """Assemble canonical identities for every detected pair.

    Returns ``(pairs_by_key, violations)``. A pair whose endpoint is absent from
    its manifest is a violation, not a silently skipped row: the pair table and
    the manifests must describe the same world.
    """
    violations: list[str] = []
    tr_sha = _manifest_sha_index(training_manifest)
    ev_sha = _manifest_sha_index(evaluation_manifest)

    pairs: dict[tuple[str, str], PairIdentity] = {}
    for i, r in enumerate(_read_csv(pair_table_csv), start=2):
        t_rel = (r.get("training_relpath") or "").strip()
        e_rel = (r.get("evaluation_relpath") or "").strip()
        classification = (r.get("classification") or "").strip()
        where = f"pair_table row {i} ({t_rel} -> {e_rel})"

        if not t_rel or not e_rel:
            violations.append(f"{where}: blank relpath")
            continue
        if classification not in ("exact", "near"):
            violations.append(f"{where}: unsupported classification '{classification}'")
            continue
        try:
            distance = int(str(r.get("hamming_distance", "")).strip())
        except ValueError:
            violations.append(f"{where}: non-integer hamming_distance "
                              f"'{r.get('hamming_distance')}'")
            continue
        if classification == "exact" and distance != 0:
            violations.append(f"{where}: classification 'exact' with distance {distance}")
            continue
        if classification == "near" and distance <= 0:
            violations.append(f"{where}: classification 'near' with distance {distance}")
            continue
        if t_rel not in tr_sha:
            violations.append(f"{where}: training endpoint absent from the training manifest")
            continue
        if e_rel not in ev_sha:
            violations.append(f"{where}: evaluation endpoint absent from the evaluation manifest")
            continue

        key = (t_rel, e_rel)
        if key in pairs:
            violations.append(f"{where}: duplicate pair in the authoritative table")
            continue
        pairs[key] = PairIdentity(
            training_dataset=training_dataset,
            training_relpath=t_rel,
            training_class=(r.get("training_class") or "").strip(),
            training_sha256=tr_sha[t_rel],
            evaluation_dataset=evaluation_dataset,
            evaluation_relpath=e_rel,
            evaluation_class=(r.get("evaluation_class") or "").strip(),
            evaluation_sha256=ev_sha[e_rel],
            phash_distance=distance,
            classification=classification,
        )
    return pairs, violations


# --------------------------------------------------------------------------- #
# Near-pair review authentication (AUD-EC-001)
# --------------------------------------------------------------------------- #
@dataclass
class ReviewAuthorization:
    resolved: int = 0
    kept: int = 0
    excluded: int = 0
    unresolved: int = 0
    violations: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations

    def as_dict(self) -> dict:
        return {"resolved": self.resolved, "kept": self.kept, "excluded": self.excluded,
                "unresolved": self.unresolved, "violations": sorted(self.violations)}


def _identity_mismatches(row: dict, pair: PairIdentity) -> list[str]:
    """Field-for-field comparison of a review row against canonical identity."""
    expected = {
        "training_dataset": pair.training_dataset,
        "training_relative_path": pair.training_relpath,
        "training_class": pair.training_class,
        "training_sha256": pair.training_sha256,
        "evaluation_dataset": pair.evaluation_dataset,
        "evaluation_relative_path": pair.evaluation_relpath,
        "evaluation_class": pair.evaluation_class,
        "evaluation_sha256": pair.evaluation_sha256,
        "phash_distance": str(pair.phash_distance),
    }
    out = []
    for col, want in expected.items():
        got = (row.get(col) or "").strip()
        if got != want:
            out.append(f"{col} is '{got}', authoritative value is '{want}'")
    return out


def authenticate_near_review(
    review_csv: str | Path,
    authoritative_near: dict[tuple[str, str], PairIdentity],
    reviewed_exclusions_csv: Optional[str | Path] = None,
) -> ReviewAuthorization:
    """Authenticate the near-pair review against canonical identity.

    Requires a strict bijection between review rows and authoritative near pairs.
    Credit is granted only for a row that reproduces the full canonical identity,
    carries a terminal decision and disposition from the allowed vocabulary, and
    carries reviewer/timestamp/reason attribution. An ``exclude_evaluation``
    decision additionally requires exactly one matching, identity-consistent row
    in the reviewed-exclusions file.
    """
    auth = ReviewAuthorization()
    path = Path(review_csv)
    if not path.exists():
        auth.violations.append(f"near-review file is absent: {review_csv}")
        auth.unresolved = len(authoritative_near)
        return auth

    rows = _read_csv(path)
    exclusions = _read_csv(reviewed_exclusions_csv) if (
        reviewed_exclusions_csv and Path(reviewed_exclusions_csv).exists()) else []

    seen_ids: dict[str, int] = {}
    seen_keys: dict[tuple[str, str], int] = {}
    credited: set[tuple[str, str]] = set()

    for i, r in enumerate(rows, start=2):
        pid = (r.get("pair_id") or "").strip()
        key = ((r.get("training_relative_path") or "").strip(),
               (r.get("evaluation_relative_path") or "").strip())
        where = f"near-review row {i} (pair_id '{pid or '<blank>'}')"

        if not pid:
            auth.violations.append(f"{where}: blank pair_id")
            continue
        if pid in seen_ids:
            auth.violations.append(f"{where}: duplicate pair_id, first seen at row {seen_ids[pid]}")
            continue
        seen_ids[pid] = i
        if key in seen_keys:
            auth.violations.append(
                f"{where}: duplicate pair identity, first seen at row {seen_keys[key]}")
            continue
        seen_keys[key] = i

        pair = authoritative_near.get(key)
        if pair is None:
            auth.violations.append(
                f"{where}: does not correspond to any authoritative near pair "
                "(unknown or surplus review row)")
            continue

        mismatches = _identity_mismatches(r, pair)
        if mismatches:
            auth.violations.append(f"{where}: identity mismatch -- " + "; ".join(mismatches))
            continue

        decision = (r.get("human_decision") or "").strip()
        disposition = (r.get("final_disposition") or "").strip()

        if not decision or not disposition:
            continue  # pending: no credit, no violation
        if decision not in NEAR_REVIEW_DECISIONS:
            auth.violations.append(f"{where}: unsupported human_decision '{decision}'")
            continue
        if disposition not in NEAR_REVIEW_DISPOSITIONS:
            auth.violations.append(f"{where}: unsupported final_disposition '{disposition}'")
            continue
        if (decision in NEAR_REVIEW_NON_TERMINAL_DECISIONS
                or disposition in NEAR_REVIEW_NON_TERMINAL_DISPOSITIONS):
            continue  # deferred: no credit, no violation

        missing_attr = [c for c in NEAR_REVIEW_ATTRIBUTION_FIELDS if not (r.get(c) or "").strip()]
        if missing_attr:
            auth.violations.append(
                f"{where}: terminal decision without attribution {missing_attr}")
            continue

        if disposition == "exclude_evaluation":
            hits = [x for x in exclusions
                    if ((x.get("training_relative_path") or "").strip(),
                        (x.get("evaluation_relative_path") or "").strip()) == key]
            if len(hits) != 1:
                auth.violations.append(
                    f"{where}: decided exclude_evaluation but the reviewed-exclusions "
                    f"file holds {len(hits)} matching row(s), expected exactly 1")
                continue
            x = hits[0]
            if (x.get("pair_id") or "").strip() != pid:
                auth.violations.append(
                    f"{where}: reviewed-exclusion pair_id "
                    f"'{(x.get('pair_id') or '').strip()}' does not match")
                continue
            if (x.get("phash_distance") or "").strip() != str(pair.phash_distance):
                auth.violations.append(
                    f"{where}: reviewed-exclusion phash_distance does not match "
                    f"the authoritative distance {pair.phash_distance}")
                continue
            auth.excluded += 1
        else:
            auth.kept += 1

        credited.add(key)
        auth.resolved += 1

    # Bijection: no authoritative pair may lack a review row.
    for key in sorted(set(authoritative_near) - set(seen_keys)):
        auth.violations.append(
            f"authoritative near pair {key[0]} -> {key[1]} has no review row")

    # Every reviewed exclusion must trace back to a credited exclude decision.
    for i, x in enumerate(exclusions, start=2):
        key = ((x.get("training_relative_path") or "").strip(),
               (x.get("evaluation_relative_path") or "").strip())
        src = [r for r in rows
               if ((r.get("training_relative_path") or "").strip(),
                   (r.get("evaluation_relative_path") or "").strip()) == key]
        if not src:
            auth.violations.append(
                f"reviewed-exclusions row {i}: does not correspond to any review row")
        elif (src[0].get("final_disposition") or "").strip() != "exclude_evaluation":
            auth.violations.append(
                f"reviewed-exclusions row {i}: the pair was not decided exclude_evaluation")

    auth.unresolved = len(authoritative_near) - len(credited)
    return auth


# --------------------------------------------------------------------------- #
# Exact-pair exclusion authentication (AUD-EC-002)
# --------------------------------------------------------------------------- #
@dataclass
class ExactAuthorization:
    detected: int = 0
    excluded: int = 0
    violations: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations

    def as_dict(self) -> dict:
        return {"detected": self.detected, "excluded": self.excluded,
                "violations": sorted(self.violations)}


def authenticate_exact_exclusions(
    exact_exclusions_csv: Optional[str | Path],
    authoritative_exact: dict[tuple[str, str], PairIdentity],
) -> ExactAuthorization:
    """Derive exact-exclusion credit from RECORDS, never from a supplied count.

    Requires exactly one identity-matching exclusion record per detected exact
    pair. Missing, duplicated, unknown, surplus, or mismatched records are
    violations, so no integer can waive a real overlap.
    """
    auth = ExactAuthorization(detected=len(authoritative_exact))
    rows = _read_csv(exact_exclusions_csv) if (
        exact_exclusions_csv and Path(exact_exclusions_csv).exists()) else []

    seen: dict[tuple[str, str], int] = {}
    for i, r in enumerate(rows, start=2):
        key = ((r.get("training_relpath") or "").strip(),
               (r.get("evaluation_relpath") or "").strip())
        where = f"exact-exclusions row {i} ({key[0]} -> {key[1]})"
        if key in seen:
            auth.violations.append(
                f"{where}: duplicate exclusion, first seen at row {seen[key]}")
            continue
        seen[key] = i

        pair = authoritative_exact.get(key)
        if pair is None:
            auth.violations.append(
                f"{where}: does not correspond to any detected exact pair "
                "(unknown or surplus exclusion)")
            continue

        expected = {
            "training_dataset": pair.training_dataset,
            "training_class": pair.training_class,
            "evaluation_dataset": pair.evaluation_dataset,
            "evaluation_class": pair.evaluation_class,
            "hamming_distance": str(pair.phash_distance),
        }
        for col, want in expected.items():
            got = (r.get(col) or "").strip()
            if got != want:
                auth.violations.append(
                    f"{where}: {col} is '{got}', authoritative value is '{want}'")
        auth.excluded += 1

    for key in sorted(set(authoritative_exact) - set(seen)):
        auth.violations.append(
            f"detected exact pair {key[0]} -> {key[1]} has no exclusion record")

    if auth.excluded > auth.detected:
        auth.violations.append(
            f"{auth.excluded} exclusion record(s) for {auth.detected} detected exact pair(s)")
    return auth


# --------------------------------------------------------------------------- #
# Input binding (AUD-EC-008)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class GateInputs:
    """Every file the gate result depends on. All are digested into the gate."""

    training_manifest: str | Path
    evaluation_manifest: str | Path
    pair_table: str | Path
    near_review: str | Path
    reviewed_exclusions: str | Path
    exact_exclusions: str | Path

    def paths(self) -> dict[str, Path]:
        return {n: Path(getattr(self, n)) for n in GATE_INPUT_NAMES if n != "leakage_config"}


def _config_digest(*, threshold: int, training_dataset: str, evaluation_dataset: str) -> str:
    """Digest of the leakage configuration itself, so a threshold change is stale."""
    payload = json.dumps({
        "threshold": threshold,
        "phash_algorithm": PHASH_ALGORITHM,
        "training_dataset": training_dataset,
        "evaluation_dataset": evaluation_dataset,
        "schema_version": SCHEMA_VERSION,
    }, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_input_digests(inputs: GateInputs, *, threshold: int,
                          training_dataset: str, evaluation_dataset: str) -> dict[str, str]:
    digests: dict[str, str] = {}
    for name, p in inputs.paths().items():
        digests[name] = sha256_of_file(p) if Path(p).exists() else "<absent>"
    digests["leakage_config"] = _config_digest(
        threshold=threshold, training_dataset=training_dataset,
        evaluation_dataset=evaluation_dataset)
    return dict(sorted(digests.items()))


# --------------------------------------------------------------------------- #
# The gate
# --------------------------------------------------------------------------- #
@dataclass
class LeakageGate:
    """Persisted leakage clearance.

    Deliberately carries NO wall-clock field: two identical computations must
    produce byte-identical JSON (AUD-EC-008). Execution metadata lives in a
    separate, non-authoritative run report.
    """

    schema_version: str
    training_dataset: str
    evaluation_dataset: str
    phash_algorithm: str
    threshold: int
    exact_duplicate_count: int
    exact_excluded_count: int
    near_duplicate_count: int
    near_resolved_count: int
    near_kept_count: int
    near_excluded_count: int
    unresolved_pair_count: int
    status: str
    authorization_violations: list = field(default_factory=list)
    input_digests: dict = field(default_factory=dict)
    provenance: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "LeakageGate":
        known = {f: d[f] for f in LeakageGate.__annotations__ if f in d}
        return LeakageGate(**known)

    def write(self, path: str | Path) -> Path:
        """Atomic, deterministic write: sorted keys, LF, trailing newline."""
        import os

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"
        tmp = path.with_name(path.name + ".part")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
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
    pair_table: str | Path,
    near_review: str | Path,
    reviewed_exclusions: str | Path,
    exact_exclusions: str | Path,
    threshold: int = DEFAULT_THRESHOLD,
    provenance: Optional[dict] = None,
) -> tuple[LeakageGate, "object"]:
    """Run the cross-dataset pHash check and build an input-bound gate.

    ``status``:
      * ``incomplete`` -- an image could not be hashed, or the authoritative pair
        table could not be reconciled with the manifests;
      * ``fail`` -- unresolved pairs remain, or any authorization violation was
        found;
      * ``pass`` -- zero unresolved pairs and zero violations.

    There is no ``excluded_pair_count`` parameter. Exact-exclusion credit is
    derived from ``exact_exclusions`` records and near-pair credit from
    identity-authenticated review rows; no caller-supplied integer can waive a
    detected overlap (AUD-EC-002).
    """
    idx_t, skip_t = index_from_manifest(training_manifest, training_root, training_dataset)
    idx_e, skip_e = index_from_manifest(evaluation_manifest, evaluation_root, evaluation_dataset)
    res = find_duplicates(idx_t, idx_e, threshold=threshold)
    exact_detected = int(res["summary"]["n_exact_pairs"])
    near_detected = int(res["summary"]["n_near_pairs"])
    skipped = len(skip_t) + len(skip_e)

    pairs, table_violations = build_authoritative_pairs(
        pair_table, training_manifest, evaluation_manifest,
        training_dataset=training_dataset, evaluation_dataset=evaluation_dataset,
    )
    authoritative_near = {k: v for k, v in pairs.items() if v.classification == "near"}
    authoritative_exact = {k: v for k, v in pairs.items() if v.classification == "exact"}

    # The pair table must describe the SAME computation we just ran; otherwise the
    # identities we authenticate against are not the ones that were detected.
    if len(authoritative_near) != near_detected:
        table_violations.append(
            f"pair table lists {len(authoritative_near)} near pair(s) but the fresh "
            f"computation detected {near_detected}; regenerate the leakage step")
    if len(authoritative_exact) != exact_detected:
        table_violations.append(
            f"pair table lists {len(authoritative_exact)} exact pair(s) but the fresh "
            f"computation detected {exact_detected}; regenerate the leakage step")

    review = authenticate_near_review(near_review, authoritative_near, reviewed_exclusions)
    exact = authenticate_exact_exclusions(exact_exclusions, authoritative_exact)

    violations = sorted(table_violations + review.violations + exact.violations)
    unresolved = max(0, (exact_detected - exact.excluded) + review.unresolved)

    if skipped > 0 or table_violations:
        status = "incomplete"
    elif violations or unresolved > 0:
        status = "fail"
    else:
        status = "pass"

    prov = dict(provenance or {})
    prov.setdefault("phash_algorithm", PHASH_ALGORITHM)
    prov.setdefault("skipped_training", len(skip_t))
    prov.setdefault("skipped_evaluation", len(skip_e))
    prov.setdefault("near_review_counts", review.as_dict())
    prov.setdefault("exact_exclusion_counts", exact.as_dict())
    try:
        from .. import __version__ as _v
        prov.setdefault("ica26_version", _v)
    except Exception:
        pass

    inputs = GateInputs(
        training_manifest=training_manifest, evaluation_manifest=evaluation_manifest,
        pair_table=pair_table, near_review=near_review,
        reviewed_exclusions=reviewed_exclusions, exact_exclusions=exact_exclusions,
    )
    gate = LeakageGate(
        schema_version=SCHEMA_VERSION,
        training_dataset=training_dataset,
        evaluation_dataset=evaluation_dataset,
        phash_algorithm=PHASH_ALGORITHM,
        threshold=threshold,
        exact_duplicate_count=exact_detected,
        exact_excluded_count=exact.excluded,
        near_duplicate_count=near_detected,
        near_resolved_count=review.resolved,
        near_kept_count=review.kept,
        near_excluded_count=review.excluded,
        unresolved_pair_count=unresolved,
        status=status,
        authorization_violations=violations,
        input_digests=compute_input_digests(
            inputs, threshold=threshold, training_dataset=training_dataset,
            evaluation_dataset=evaluation_dataset),
        provenance=dict(sorted(prov.items())),
    )
    return gate, res


def validate_gate(gate: LeakageGate, inputs: GateInputs) -> ValidationResult:
    """Fail-closed validation. Truthy result == the gate authorises evaluation.

    Recomputes EVERY bound input digest, so mutating the review CSV, the pair
    table, either exclusion file, or a manifest after generation makes the gate
    stale (AUD-EC-008) -- not just a manifest change.
    """
    res = ValidationResult()
    if gate is None:
        res.add("error", "gate", "leakage gate is missing")
        return res
    if gate.schema_version != SCHEMA_VERSION:
        res.add("error", "schema_version",
                f"unsupported gate schema '{gate.schema_version}' (expected {SCHEMA_VERSION}); "
                "counts from an older schema are not comparable")
        return res
    if gate.status not in GATE_STATUSES:
        res.add("error", "status", f"invalid status '{gate.status}'")

    current = compute_input_digests(
        inputs, threshold=gate.threshold, training_dataset=gate.training_dataset,
        evaluation_dataset=gate.evaluation_dataset)
    recorded = dict(gate.input_digests or {})
    if not recorded:
        res.add("error", "input_digests", "gate records no input bindings")
    for name in GATE_INPUT_NAMES:
        want = recorded.get(name)
        got = current.get(name)
        if want is None:
            res.add("error", f"input_digests.{name}", f"gate does not bind '{name}'")
        elif got == "<absent>" and want != "<absent>":
            res.add("error", f"input_digests.{name}", f"bound input '{name}' no longer exists")
        elif got != want:
            res.add("error", f"input_digests.{name}",
                    f"'{name}' changed since the gate was generated (stale gate)")

    if gate.authorization_violations:
        res.add("error", "authorization_violations",
                f"{len(gate.authorization_violations)} unresolved authorization "
                f"violation(s), first: {gate.authorization_violations[0]}")
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
    inputs: GateInputs,
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
    res = validate_gate(gate, inputs)
    if not res.ok:
        msgs = "; ".join(i.message for i in res.errors)
        raise LeakageGateError(f"leakage gate invalid: {msgs}")
    return gate


def write_run_report(gate: LeakageGate, path: str | Path, *,
                     command: str = "", generated_at: Optional[str] = None) -> Path:
    """Non-authoritative execution metadata, kept OUT of the gate artifact.

    The wall-clock timestamp lives here so that the gate itself stays
    byte-deterministic across identical runs.
    """
    import os

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "_note": "Non-authoritative execution metadata. The gate artifact "
                 "(reports/leakage_gate.json) is the authority and is "
                 "byte-deterministic; this file is not.",
        "generated_at": generated_at or _utc_now(),
        "command": command,
        "gate_schema_version": gate.schema_version,
        "gate_status": gate.status,
        "gate_sha256": hashlib.sha256(
            (json.dumps(gate.to_dict(), indent=2, sort_keys=True) + "\n").encode("utf-8")
        ).hexdigest(),
    }
    tmp = path.with_name(path.name + ".part")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ica26-leakage-gate", description="Compute + persist a cross-dataset leakage gate.")
    ap.add_argument("--training-manifest", required=True)
    ap.add_argument("--training-root", required=True)
    ap.add_argument("--training-dataset", required=True)
    ap.add_argument("--evaluation-manifest", required=True)
    ap.add_argument("--evaluation-root", required=True)
    ap.add_argument("--evaluation-dataset", required=True)
    ap.add_argument("--pair-table", required=True)
    ap.add_argument("--near-review", required=True)
    ap.add_argument("--reviewed-exclusions", required=True)
    ap.add_argument("--exact-exclusions", required=True)
    ap.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
    ap.add_argument("--out", default="reports/leakage_gate.json")
    ap.add_argument("--run-report", default="reports/leakage_gate_run.json")
    args = ap.parse_args(argv)

    gate, _ = compute_gate(
        training_manifest=args.training_manifest, training_root=args.training_root,
        training_dataset=args.training_dataset,
        evaluation_manifest=args.evaluation_manifest, evaluation_root=args.evaluation_root,
        evaluation_dataset=args.evaluation_dataset,
        pair_table=args.pair_table, near_review=args.near_review,
        reviewed_exclusions=args.reviewed_exclusions, exact_exclusions=args.exact_exclusions,
        threshold=args.threshold,
        provenance={"command": "ica26-leakage-gate"},
    )
    gate.write(args.out)
    write_run_report(gate, args.run_report, command="ica26-leakage-gate")
    print(f"[leakage-gate] status={gate.status} "
          f"exact={gate.exact_duplicate_count}/excluded={gate.exact_excluded_count} "
          f"near={gate.near_duplicate_count}/resolved={gate.near_resolved_count} "
          f"unresolved={gate.unresolved_pair_count} "
          f"violations={len(gate.authorization_violations)}")
    for v in gate.authorization_violations[:10]:
        print(f"  VIOLATION {v}")
    print(f"[leakage-gate] wrote {args.out}")
    return 0 if gate.status == "pass" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
