#!/usr/bin/env python3
"""Derive the additional-seed experiment configs from the seed-42 originals.

    python scripts/ica26_make_seed_configs.py                 # write the configs
    python scripts/ica26_make_seed_configs.py --check         # verify, write nothing

A seed repetition is only evidence about variance if the seed is the *only*
thing that changed. Hand-copying twelve YAML files invites a silent divergence —
a stray learning rate, a dropped class-weighting flag — that would turn a
variance estimate into a comparison of two different protocols.

So the seed configs are derived mechanically from the seed-42 files, and the
derivation is checked semantically after the fact: the parsed config must differ
from its source in exactly ``experiment_id`` and ``seed``, and in nothing else.
``--check`` re-runs that comparison against what is already on disk, so a config
edited by hand after generation is caught.

The generated ``experiment_id`` carries the seed (``pv_resnet50_s1337``), which
is what keeps ``experiments/ica26/runs/<experiment_id>`` from colliding: a new
seed can never overwrite an existing run's checkpoint.

Exit codes: 0 written / verified, 1 a config diverges from its source protocol.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
CONFIGS = REPO / "experiments/ica26/configs"

BASE_SEED = 42
# Chosen arbitrarily and fixed before the runs; recorded here so the choice is
# reproducible rather than remembered. Nothing about either value is special.
ADDITIONAL_SEEDS = [1337, 2026]

BASE_IDS = [
    "pv_resnet50", "pv_efficientnet_b0", "pv_mobilenet_v3_small",
    "pdc_resnet50", "pdc_efficientnet_b0", "pdc_mobilenet_v3_small",
]
# The only two keys a seed repetition may change.
ALLOWED_DIFFERENCES = {"experiment_id", "seed"}

DERIVATION_NOTE = (
    "# Derived from {source} by scripts/ica26_make_seed_configs.py.\n"
    "# Seed repetition: `seed` and `experiment_id` differ from the source; every\n"
    "# other protocol value is identical and is verified to be so by --check.\n"
)


def derive_text(source_text: str, source_name: str, stem: str, seed: int) -> str:
    """Rewrite the two seed-bearing lines, leaving all other bytes untouched."""
    out = re.sub(
        r"^experiment_id:.*$", f"experiment_id: {stem}_s{seed}",
        source_text, count=1, flags=re.MULTILINE,
    )
    out, n = re.subn(r"^seed:.*$", f"seed: {seed}", out, count=1, flags=re.MULTILINE)
    if n != 1:
        raise RuntimeError(f"{source_name}: expected exactly one `seed:` line, found {n}")
    return DERIVATION_NOTE.format(source=source_name) + out


def compare(source: Path, derived: Path, seed: int) -> list[str]:
    """Semantic check: only experiment_id and seed may differ."""
    a = yaml.safe_load(source.read_text())
    b = yaml.safe_load(derived.read_text())
    problems = []
    for key in sorted(set(a) | set(b)):
        if a.get(key) != b.get(key) and key not in ALLOWED_DIFFERENCES:
            problems.append(f"{derived.name}: {key} diverges from {source.name} "
                            f"({a.get(key)!r} -> {b.get(key)!r})")
    if b.get("seed") != seed:
        problems.append(f"{derived.name}: seed is {b.get('seed')!r}, expected {seed}")
    expected_id = f"{source.stem[:-len(f'_s{BASE_SEED}')]}_s{seed}"
    if b.get("experiment_id") != expected_id:
        problems.append(f"{derived.name}: experiment_id is {b.get('experiment_id')!r}, "
                        f"expected {expected_id!r}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="verify existing configs, write nothing")
    args = ap.parse_args()

    problems: list[str] = []
    written = verified = 0

    for stem in BASE_IDS:
        source = CONFIGS / f"{stem}_s{BASE_SEED}.yaml"
        if not source.exists():
            problems.append(f"missing source config {source.name}")
            continue
        for seed in ADDITIONAL_SEEDS:
            derived = CONFIGS / f"{stem}_s{seed}.yaml"
            if not args.check:
                derived.write_text(derive_text(source.read_text(), source.name, stem, seed))
                written += 1
            elif not derived.exists():
                problems.append(f"missing derived config {derived.name}")
                continue
            problems.extend(compare(source, derived, seed))
            verified += 1

    print(f"base runs         : {len(BASE_IDS)}")
    print(f"additional seeds  : {ADDITIONAL_SEEDS}")
    if not args.check:
        print(f"configs written   : {written}")
    print(f"configs verified  : {verified}")

    if problems:
        print(f"FAILED            : {len(problems)} problem(s)")
        for p in problems:
            print(f"  {p}")
        return 1
    print("OK                : every derived config differs only in experiment_id and seed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
