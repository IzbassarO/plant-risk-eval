#!/usr/bin/env python3
"""Build the ICA 2026 paper experiment dataset lock.

    python scripts/ica26_build_experiment_lock.py            # write the lock
    python scripts/ica26_build_experiment_lock.py --check    # rebuild and compare

This lock is NOT the repository's formal governance freeze. It records no human
audit signature, closes no finding, and approves no freeze. It binds digests.

`--check` rebuilds the lock from the on-disk corpus and compares it to the
committed file, carrying over only ``created_at_utc`` and ``repository_commit``
from the existing file. Those two are provenance of the moment the lock was
written; recomputing them would make an unchanged corpus look changed (the
commit necessarily advances when the lock itself is committed).

Exit codes: 0 written / current, 1 --check found a difference.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from ica26.experiments import lock as L  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="rebuild and compare, write nothing")
    args = ap.parse_args()

    out = REPO / L.LOCK_PATH
    existing = json.loads(out.read_text()) if out.exists() else None

    if args.check:
        if existing is None:
            print(f"MISSING {out}", file=sys.stderr)
            return 1
        created = existing.get("created_at_utc")
    else:
        created = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()

    payload = L.build_lock(REPO, created_at=created)

    if args.check:
        # Provenance-of-writing fields are carried over, not recomputed.
        payload["repository_commit"] = existing.get("repository_commit")

    payload["lock_digest"] = L.lock_digest(payload)
    text = L.canonical_json(payload)

    print(f"schema                : {payload['schema']}")
    print(f"is_governance_freeze  : {payload['is_formal_governance_freeze']}")
    print(f"dataset_owner         : {payload['dataset_owner']}")
    print(f"repository_commit     : {payload['repository_commit']}")
    print(f"lock_digest           : {payload['lock_digest']}")
    n_art = sum(len(v) for v in payload["artifacts"].values())
    print(f"bound artifacts       : {n_art} across {len(payload['artifacts'])} roles")
    print(f"plantvillage          : {payload['corpora']['plantvillage']['n_records']} "
          f"{payload['corpora']['plantvillage']['split_counts']}")
    print(f"plantdoc_core         : {payload['corpora']['plantdoc_core']['n_records']} "
          f"{payload['corpora']['plantdoc_core']['split_counts']}")
    print(f"shared classes        : {payload['cross_domain_mapping']['n_shared_classes']} "
          f"({payload['cross_domain_mapping']['n_evaluable_plantdoc_core_images']} images)")

    if args.check:
        if L.canonical_json(existing) != text:
            print(f"DIFFERS {out}", file=sys.stderr)
            old, new = json.loads(L.canonical_json(existing)), payload
            for k in sorted(set(old) | set(new)):
                if old.get(k) != new.get(k):
                    print(f"  changed key: {k}", file=sys.stderr)
            return 1
        print("check OK: lock is byte-identical to a fresh rebuild")
        return 0

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
