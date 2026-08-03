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
#      binding, and a byte-deterministic artifact.
# 2.1: canonical pair identities, fresh-vs-persisted identity-SET equality (not
#      count equality), authenticated display ids, and strict ISO-8601 review
#      timestamps.
# A gate from an older schema is rejected, never reinterpreted -- its counts do
# not mean the same thing.
SCHEMA_VERSION = "2.1"
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
#
# A pair's scientific identity is its two endpoints and their relationship --
# never its label and never its position in a file. `pair_id` is a DISPLAY name
# for humans; it authorises nothing (R1-HIGH-001). The authority is
# `canonical_pair_id`, the digest of an explicitly versioned serialization of
# every immutable field, so the same pair yields the same id on any machine, in
# any row order, in any file.
#
# The serialization is versioned because changing it changes every id. Bump
# CANONICAL_PAIR_SCHEMA rather than editing the field list in place.
# --------------------------------------------------------------------------- #
CANONICAL_PAIR_SCHEMA = "ica26.leakage.pair/1"

#: Hex digits of the identity digest kept in a canonical id. 16 hex = 64 bits.
CANONICAL_ID_HEX = 16


@dataclass(frozen=True)
class PairIdentity:
    """Immutable identity of one detected cross-dataset duplicate pair.

    Endpoint digests and class labels come from the CURRENT manifests, never from
    a review or pair-table row, so editing either cannot make a forgery
    authenticate.
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
    phash_algorithm: str = PHASH_ALGORITHM
    phash_bits: int = 64

    @property
    def key(self) -> tuple[str, str]:
        """Path key. Convenient for lookup; NOT sufficient for authorization."""
        return (self.training_relpath, self.evaluation_relpath)

    def canonical_serialization(self) -> str:
        """Deterministic, versioned serialization of every immutable field.

        Only serialization is normalised (key order, separators, integer typing);
        no scientific value is altered, trimmed, case-folded, or defaulted.
        """
        return json.dumps({
            "schema": CANONICAL_PAIR_SCHEMA,
            "pair_type": self.classification,
            "training_dataset": self.training_dataset,
            "training_relpath": self.training_relpath,
            "training_class": self.training_class,
            "training_sha256": self.training_sha256,
            "evaluation_dataset": self.evaluation_dataset,
            "evaluation_relpath": self.evaluation_relpath,
            "evaluation_class": self.evaluation_class,
            "evaluation_sha256": self.evaluation_sha256,
            "phash_distance": int(self.phash_distance),
            "phash_algorithm": self.phash_algorithm,
            "phash_bits": int(self.phash_bits),
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @property
    def canonical_pair_id(self) -> str:
        """Namespaced identity digest, e.g. ``near-1a2b3c4d5e6f7a8b``.

        The pair type is in the prefix AND inside the serialization, so an exact
        pair and a near pair over the same endpoints can never collide.
        """
        digest = hashlib.sha256(
            self.canonical_serialization().encode("utf-8")).hexdigest()
        return f"{self.classification}-{digest[:CANONICAL_ID_HEX]}"

    def as_dict(self) -> dict:
        d = asdict(self)
        d["canonical_pair_id"] = self.canonical_pair_id
        return d


def display_pair_ids(pairs: Iterable[PairIdentity]) -> dict[str, str]:
    """Authoritative ``canonical_pair_id -> display id`` map (``ndp-01`` …).

    Display ids are assigned from a canonical SORT of the identities, so they are
    reproducible and independent of file order. They exist for human legibility
    only; :func:`authenticate_near_review` verifies a review row's display id
    against this map but never authorises on it.
    """
    ordered = sorted(pairs, key=lambda p: (p.classification, p.phash_distance,
                                           p.training_relpath, p.evaluation_relpath))
    prefix = {"near": "ndp", "exact": "xdp"}
    counters: dict[str, int] = {}
    out: dict[str, str] = {}
    for p in ordered:
        n = counters.get(p.classification, 0) + 1
        counters[p.classification] = n
        out[p.canonical_pair_id] = f"{prefix.get(p.classification, p.classification)}-{n:02d}"
    return out


def _read_csv(path: str | Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _manifest_sha_index(manifest_csv: str | Path) -> dict[str, str]:
    return {r["relpath"]: r["sha256"] for r in _read_csv(manifest_csv)}


def _manifest_class_index(manifest_csv: str | Path) -> dict[str, str]:
    return {r["relpath"]: r["class_label"] for r in _read_csv(manifest_csv)}


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

        # The table may DECLARE endpoint digests. The manifest is the authority,
        # so a declared digest is never used -- but it must not be allowed to
        # assert something false, or a reader (or a later tool) could trust it.
        for col, want in (("training_sha256", tr_sha[t_rel]),
                          ("evaluation_sha256", ev_sha[e_rel])):
            declared = (r.get(col) or "").strip()
            if declared and declared != want:
                violations.append(
                    f"{where}: table declares {col} '{declared}' but the manifest "
                    f"records '{want}'")
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


def build_fresh_pairs(
    result: dict,
    training_manifest: str | Path,
    evaluation_manifest: str | Path,
    *,
    training_dataset: str,
    evaluation_dataset: str,
    hash_bits: int = 64,
) -> dict[str, PairIdentity]:
    """Canonical identities derived DIRECTLY from a fresh detection result.

    Class labels and endpoint digests are taken from the manifests, so a fresh
    identity cannot inherit a forged value from any persisted table. Keyed by
    ``canonical_pair_id``.
    """
    tr_sha = _manifest_sha_index(training_manifest)
    ev_sha = _manifest_sha_index(evaluation_manifest)
    tr_cls = _manifest_class_index(training_manifest)
    ev_cls = _manifest_class_index(evaluation_manifest)

    out: dict[str, PairIdentity] = {}
    for classification in ("exact", "near"):
        frame = result.get(classification)
        if frame is None:
            continue
        for _, r in frame.iterrows():
            t_rel, e_rel = str(r["path_a"]), str(r["path_b"])
            pair = PairIdentity(
                training_dataset=training_dataset,
                training_relpath=t_rel,
                training_class=tr_cls.get(t_rel, ""),
                training_sha256=tr_sha.get(t_rel, ""),
                evaluation_dataset=evaluation_dataset,
                evaluation_relpath=e_rel,
                evaluation_class=ev_cls.get(e_rel, ""),
                evaluation_sha256=ev_sha.get(e_rel, ""),
                phash_distance=int(r["distance"]),
                classification=classification,
                phash_bits=hash_bits,
            )
            out[pair.canonical_pair_id] = pair
    return out


def reconcile_pair_sets(
    fresh: dict[str, PairIdentity],
    persisted: dict[tuple[str, str], PairIdentity],
) -> tuple[list[str], dict]:
    """Require EXACT canonical identity-set equality, not equal counts.

    Counting was the R1-CRIT-001 hole: a forged table naming unrelated endpoints
    with the right row count authorised an unrelated exclusion. Equality of the
    canonical id sets makes every substitution -- changed endpoint, class, path,
    distance, or exact/near type -- a mismatch, even when the counts agree.

    Returns ``(violations, report)``.
    """
    persisted_by_id: dict[str, PairIdentity] = {}
    duplicates: list[str] = []
    for p in persisted.values():
        cid = p.canonical_pair_id
        if cid in persisted_by_id:
            duplicates.append(cid)
        persisted_by_id[cid] = p

    fresh_only = sorted(set(fresh) - set(persisted_by_id))
    persisted_only = sorted(set(persisted_by_id) - set(fresh))

    violations: list[str] = []
    for cid in fresh_only:
        p = fresh[cid]
        violations.append(
            f"freshly detected {p.classification} pair {cid} "
            f"({p.training_relpath} -> {p.evaluation_relpath}) is absent from the "
            "persisted pair table")
    for cid in persisted_only:
        p = persisted_by_id[cid]
        violations.append(
            f"persisted pair table lists {p.classification} pair {cid} "
            f"({p.training_relpath} -> {p.evaluation_relpath}) which fresh detection "
            "did not produce")
    for cid in sorted(set(duplicates)):
        violations.append(f"persisted pair table contains duplicate identity {cid}")

    report = {
        "schema": CANONICAL_PAIR_SCHEMA,
        "fresh_count": len(fresh),
        "persisted_count": len(persisted_by_id),
        "equal": not violations,
        "fresh_only": fresh_only,
        "persisted_only": persisted_only,
        "duplicates": sorted(set(duplicates)),
    }
    return violations, report


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


def parse_review_timestamp(value: str, *, now: Optional[datetime] = None) -> tuple[Optional[datetime], Optional[str]]:
    """Strict ISO-8601 with an explicit UTC offset. Returns ``(dt, error)``.

    A review timestamp is provenance, so it must actually be a timestamp. R1
    accepted any non-blank string -- ``tomorrow`` authenticated. Requirements:
    parseable ISO-8601, a real calendar date, an explicit timezone offset (a
    naive stamp is ambiguous across reviewers), and not in the future.
    """
    raw = (value or "").strip()
    if not raw:
        return None, "reviewed_at is blank"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None, (f"reviewed_at '{raw}' is not a valid ISO-8601 timestamp "
                      "(expected e.g. 2026-08-02T21:10:00+05:00)")
    if dt.tzinfo is None or dt.utcoffset() is None:
        return None, (f"reviewed_at '{raw}' has no timezone offset; an explicit "
                      "offset is required so the instant is unambiguous")
    reference = now or datetime.now(timezone.utc)
    if dt > reference:
        return None, f"reviewed_at '{raw}' is in the future"
    return dt, None


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

    # Authoritative display-id map, derived from the identities themselves.
    display = display_pair_ids(authoritative_near.values())

    seen_ids: dict[str, int] = {}
    seen_canonical: dict[str, int] = {}
    seen_keys: dict[tuple[str, str], int] = {}
    credited: set[tuple[str, str]] = set()

    for i, r in enumerate(rows, start=2):
        pid = (r.get("pair_id") or "").strip()
        cid = (r.get("canonical_pair_id") or "").strip()
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
        if cid and cid in seen_canonical:
            auth.violations.append(
                f"{where}: duplicate canonical_pair_id '{cid}', first seen at row "
                f"{seen_canonical[cid]}")
            continue
        if cid:
            seen_canonical[cid] = i
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

        # The canonical id is the authority; the display id is only a label and
        # must match the map derived from the identities (R1-HIGH-001).
        expected_cid = pair.canonical_pair_id
        if not cid:
            auth.violations.append(
                f"{where}: missing canonical_pair_id (expected '{expected_cid}'); "
                "a display pair_id authorises nothing")
            continue
        if cid != expected_cid:
            auth.violations.append(
                f"{where}: canonical_pair_id '{cid}' does not match the identity-derived "
                f"'{expected_cid}'")
            continue
        expected_display = display.get(expected_cid)
        if expected_display and pid != expected_display:
            auth.violations.append(
                f"{where}: display pair_id '{pid}' does not match the authoritative "
                f"display id '{expected_display}' for {expected_cid}")
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

        _, ts_error = parse_review_timestamp(r.get("reviewed_at"))
        if ts_error:
            auth.violations.append(f"{where}: {ts_error}")
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
            "training_sha256": pair.training_sha256,
            "evaluation_dataset": pair.evaluation_dataset,
            "evaluation_class": pair.evaluation_class,
            "evaluation_sha256": pair.evaluation_sha256,
            "hamming_distance": str(pair.phash_distance),
            "canonical_pair_id": pair.canonical_pair_id,
        }
        for col, want in expected.items():
            got = (r.get(col) or "").strip()
            if not got:
                auth.violations.append(
                    f"{where}: required identity column '{col}' is missing or blank "
                    f"(expected '{want}')")
            elif got != want:
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

    # The persisted table must describe the SAME pairs we just detected -- by
    # IDENTITY, not by count. Counting was R1-CRIT-001: a forged table naming
    # unrelated endpoints with the right row count authorised an unrelated
    # exclusion. Compare the canonical id sets instead (R1-CRIT-001).
    fresh_pairs = build_fresh_pairs(
        res, training_manifest, evaluation_manifest,
        training_dataset=training_dataset, evaluation_dataset=evaluation_dataset,
    )
    set_violations, identity_report = reconcile_pair_sets(fresh_pairs, pairs)
    table_violations = list(table_violations) + set_violations

    # Identity-set equality is a PRECONDITION. If it fails we are authenticating
    # against the wrong identities, so review/exclusion arithmetic is meaningless
    # and is not run at all.
    if table_violations:
        review = ReviewAuthorization(unresolved=len(authoritative_near))
        exact = ExactAuthorization(detected=exact_detected)
        violations = sorted(table_violations)
        unresolved = exact_detected + len(authoritative_near)
        status = "incomplete"
    else:
        review = authenticate_near_review(near_review, authoritative_near, reviewed_exclusions)
        exact = authenticate_exact_exclusions(exact_exclusions, authoritative_exact)
        violations = sorted(review.violations + exact.violations)
        unresolved = max(0, (exact_detected - exact.excluded) + review.unresolved)
        if skipped > 0:
            status = "incomplete"
        elif violations or unresolved > 0:
            status = "fail"
        else:
            status = "pass"
    if skipped > 0:
        status = "incomplete"

    prov = dict(provenance or {})
    prov.setdefault("phash_algorithm", PHASH_ALGORITHM)
    prov.setdefault("skipped_training", len(skip_t))
    prov.setdefault("skipped_evaluation", len(skip_e))
    prov.setdefault("near_review_counts", review.as_dict())
    prov.setdefault("exact_exclusion_counts", exact.as_dict())
    prov.setdefault("pair_identity_reconciliation", identity_report)
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
