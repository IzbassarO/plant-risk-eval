"""Manifest-driven datasets for the ICA 2026 paper experiments.

Every sample list originates in a committed manifest CSV, never in a directory
walk. The class index is derived deterministically (sorted label order) so that
an index built on one machine equals the index built on another.

PlantVillage carries ``leaf_id``: several images can photograph the same
physical leaf. A random train/validation split would place sibling images of one
leaf on both sides and inflate validation scores. Because this paper is about
leakage control, the validation carve-out is grouped by ``leaf_id``.
"""
from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import pandas as pd
from PIL import Image, UnidentifiedImageError
from torch.utils.data import Dataset

PLANTVILLAGE_ROOT = "data/raw/plantvillage/extracted"
PLANTDOC_ROOT = "data/raw/plantdoc"

PLANTVILLAGE_MANIFEST = "data/manifests/plantvillage_manifest.csv"
PLANTDOC_CORE_MANIFEST = "data/manifests/plantdoc_core_effective_manifest.csv"

# A class with fewer groups than this contributes nothing to validation.
MIN_GROUPS_FOR_VALIDATION = 3

# Bounded retry for transient OS-level read failures. See ManifestImageDataset._read.
PIXEL_READ_ATTEMPTS = 5
PIXEL_READ_BACKOFF_SECONDS = 0.25


class MissingPixelsError(RuntimeError):
    """Raised when a manifest row has no readable file on disk."""


def build_class_index(labels: Sequence[str]) -> dict[str, int]:
    """Deterministic label -> index map: sorted unique labels, 0-based."""
    return {label: i for i, label in enumerate(sorted(set(str(x) for x in labels)))}


def class_index_digest(class_to_idx: dict[str, int]) -> str:
    """Stable digest of a class index, independent of dict insertion order."""
    payload = "\n".join(f"{k}\t{v}" for k, v in sorted(class_to_idx.items()))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def split_assignment_digest(df: pd.DataFrame) -> str:
    """Stable digest binding every record identity to its split and label.

    Sorted by relpath so row order in the CSV cannot change the value.
    """
    rows = sorted(
        f"{r.relpath}\t{r.split}\t{r.class_label}\t{r.sha256}"
        for r in df.itertuples(index=False)
    )
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DatasetSpec:
    """A resolved corpus: manifest rows plus the root their relpaths hang from."""

    name: str
    manifest_path: str
    root: str
    frame: pd.DataFrame

    @property
    def classes(self) -> list[str]:
        return sorted(set(str(x) for x in self.frame["class_label"]))


def load_manifest(manifest_path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(manifest_path)
    required = {"split", "class_label", "relpath", "sha256"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{manifest_path}: manifest missing columns {sorted(missing)}")
    return df


def load_plantvillage(repo_root: str | Path = ".") -> DatasetSpec:
    repo_root = Path(repo_root)
    return DatasetSpec(
        name="plantvillage",
        manifest_path=str(repo_root / PLANTVILLAGE_MANIFEST),
        root=str(repo_root / PLANTVILLAGE_ROOT),
        frame=load_manifest(repo_root / PLANTVILLAGE_MANIFEST),
    )


def load_plantdoc_core(repo_root: str | Path = ".") -> DatasetSpec:
    repo_root = Path(repo_root)
    return DatasetSpec(
        name="plantdoc_core",
        manifest_path=str(repo_root / PLANTDOC_CORE_MANIFEST),
        root=str(repo_root / PLANTDOC_ROOT),
        frame=load_manifest(repo_root / PLANTDOC_CORE_MANIFEST),
    )


def grouped_validation_split(
    train_df: pd.DataFrame,
    val_fraction: float,
    seed: int,
    group_column: Optional[str] = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Carve a validation set out of a training frame.

    When ``group_column`` is given (PlantVillage ``leaf_id``), whole groups move
    together so no leaf appears on both sides. Selection walks classes in sorted
    order with a seeded RNG, so the result depends only on (frame, fraction,
    seed) and not on row order or platform.

    Rows with no group value are treated as singleton groups keyed by relpath.
    """
    if not 0.0 < val_fraction < 1.0:
        raise ValueError(f"val_fraction must be in (0,1), got {val_fraction}")

    df = train_df.reset_index(drop=True).copy()
    if group_column and group_column in df.columns:
        groups = df[group_column].astype("string")
        groups = groups.where(groups.notna() & (groups != ""), other=pd.NA)
        df["_group"] = [
            g if pd.notna(g) else f"__singleton__{rp}"
            for g, rp in zip(groups, df["relpath"])
        ]
    else:
        df["_group"] = df["relpath"].astype(str)

    rng = np.random.default_rng(seed)
    val_groups: set[str] = set()

    # Stratify at the group level: for each class, hold out `val_fraction` of
    # that class's groups. A group is attributed to the class of its first row
    # in sorted-relpath order (PlantVillage leaves are single-class in practice).
    group_class = (
        df.sort_values("relpath")
        .groupby("_group", sort=True)["class_label"]
        .first()
    )
    for label in sorted(set(group_class.values)):
        members = sorted(group_class[group_class == label].index.tolist())
        # A class too small to spare a group keeps every example in training.
        # PlantDoc Core's arthropod-pest class has two training images; taking
        # one for validation would halve an already unusable class.
        if len(members) < MIN_GROUPS_FOR_VALIDATION:
            continue
        n_val = int(round(len(members) * val_fraction))
        n_val = max(1, min(n_val, len(members) - 1))
        if n_val:
            picked = rng.choice(len(members), size=n_val, replace=False)
            val_groups.update(members[i] for i in sorted(picked.tolist()))

    is_val = df["_group"].isin(val_groups)
    val = df[is_val].drop(columns=["_group"]).reset_index(drop=True)
    train = df[~is_val].drop(columns=["_group"]).reset_index(drop=True)
    if len(val) == 0 or len(train) == 0:
        raise ValueError("validation carve-out produced an empty side")
    return train, val


class ManifestImageDataset(Dataset):
    """Images listed by a manifest frame, labelled through a fixed class index.

    ``label_column`` allows cross-domain evaluation to label PlantDoc rows by
    their canonical shared-class id instead of their native PlantDoc label.
    """

    def __init__(
        self,
        frame: pd.DataFrame,
        root: str | Path,
        class_to_idx: dict[str, int],
        transform=None,
        label_column: str = "class_label",
    ) -> None:
        self.frame = frame.reset_index(drop=True)
        self.root = Path(root)
        self.class_to_idx = dict(class_to_idx)
        self.transform = transform
        self.label_column = label_column

        unknown = sorted(
            set(str(x) for x in self.frame[label_column]) - set(self.class_to_idx)
        )
        if unknown:
            raise ValueError(f"labels absent from the class index: {unknown[:5]}")

        self.paths = [str(self.root / r) for r in self.frame["relpath"]]
        self.targets = [self.class_to_idx[str(x)] for x in self.frame[label_column]]

    def __len__(self) -> int:
        return len(self.frame)

    def _read(self, path: str, index: int) -> Image.Image:
        """Decode one image, retrying only errors that can plausibly be transient.

        A sustained multi-worker read of a macOS ``~/Documents`` subtree
        occasionally returns EACCES for a file that is present, owned by the
        user, and readable a moment later; one such failure killed a training run
        at epoch 6 after roughly 218,000 successful opens. Retrying briefly
        absorbs that without hiding anything real:

        - a genuinely absent file raises immediately, no retry;
        - a corrupt or unidentifiable image raises immediately, no retry;
        - a transient OS error that never clears still raises, with the attempt
          count and the underlying error in the message.

        Image content is pinned by the manifest digests bound in the experiment
        lock, so a retry cannot substitute different pixels for the right ones.
        """
        last: Exception | None = None
        for attempt in range(1, PIXEL_READ_ATTEMPTS + 1):
            try:
                with Image.open(path) as im:
                    return im.convert("RGB")
            except FileNotFoundError as exc:
                raise MissingPixelsError(
                    f"manifest row {index} has no file at {path}"
                ) from exc
            except UnidentifiedImageError as exc:
                raise MissingPixelsError(
                    f"manifest row {index} is not a decodable image: {path}"
                ) from exc
            except OSError as exc:
                last = exc
                if attempt < PIXEL_READ_ATTEMPTS:
                    time.sleep(PIXEL_READ_BACKOFF_SECONDS * attempt)
        raise MissingPixelsError(
            f"manifest row {index} could not be read after {PIXEL_READ_ATTEMPTS} "
            f"attempts: {path} ({type(last).__name__}: {last})"
        ) from last

    def __getitem__(self, i: int):
        img = self._read(self.paths[i], i)
        if self.transform is not None:
            img = self.transform(img)
        return img, self.targets[i]


def assert_pixels_present(spec: DatasetSpec, sample: Optional[int] = None) -> int:
    """Check manifest rows resolve to files. Returns the number checked.

    ``sample=None`` checks every row. Raises on the first missing file so the
    caller sees a real path, not a count.
    """
    relpaths = list(spec.frame["relpath"])
    if sample is not None and sample < len(relpaths):
        step = max(1, len(relpaths) // sample)
        relpaths = relpaths[::step][:sample]
    root = Path(spec.root)
    for rp in relpaths:
        if not os.path.exists(root / rp):
            raise MissingPixelsError(
                f"{spec.name}: manifest row has no file on disk: {root / rp}"
            )
    return len(relpaths)
