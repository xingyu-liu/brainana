#!/usr/bin/env python3
"""Clean up atlas-only FastSurfer subject directories.

A target directory is removed only when all conditions are true:
1) it matches site-*/fastsurfer/sub-*
2) it is a directory
3) its only direct child entry is a directory named "atlas"
"""

from __future__ import annotations

import argparse
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass
class ScanResult:
    checked_subject_dirs: int = 0
    atlas_only_dirs: int = 0
    removed_dirs: int = 0
    remove_errors: int = 0


def iter_fastsurfer_subject_dirs(dataset_root: Path) -> Iterable[Path]:
    """Yield site-*/fastsurfer/sub-* subject directories in sorted order."""
    for site_dir in sorted(p for p in dataset_root.glob("site-*") if p.is_dir()):
        fastsurfer_dir = site_dir / "fastsurfer"
        if not fastsurfer_dir.is_dir():
            continue
        for sub_dir in sorted(p for p in fastsurfer_dir.glob("sub-*") if p.is_dir()):
            yield sub_dir


def is_atlas_only_subject_dir(sub_dir: Path) -> bool:
    """Return True when sub_dir contains only one child named atlas (directory)."""
    children = list(sub_dir.iterdir())
    if len(children) != 1:
        return False
    only_child = children[0]
    return only_child.is_dir() and only_child.name == "atlas"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Remove fastsurfer/sub-* directories that only contain atlas/."
    )
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=Path("/mnt/DataDrive2/macaque/data_preproc/macaque_mri/PRIME-DE_brainana"),
        help="Root directory containing site-* folders (default: PRIME-DE_brainana path).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be removed without deleting anything.",
    )
    args = parser.parse_args()

    dataset_root = args.dataset_root.expanduser().resolve()
    if not dataset_root.is_dir():
        print(f"ERROR: dataset root does not exist or is not a directory: {dataset_root}")
        return 2

    result = ScanResult()
    atlas_only_dirs: list[Path] = []

    for sub_dir in iter_fastsurfer_subject_dirs(dataset_root):
        result.checked_subject_dirs += 1
        if is_atlas_only_subject_dir(sub_dir):
            result.atlas_only_dirs += 1
            atlas_only_dirs.append(sub_dir)

    mode = "DRY RUN" if args.dry_run else "DELETE"
    print(f"Mode: {mode}")
    print(f"Dataset root: {dataset_root}")
    print(f"Checked subject dirs: {result.checked_subject_dirs}")
    print(f"Atlas-only dirs found: {result.atlas_only_dirs}")

    for sub_dir in atlas_only_dirs:
        if args.dry_run:
            print(f"WOULD_REMOVE {sub_dir}")
            continue
        try:
            shutil.rmtree(sub_dir)
            result.removed_dirs += 1
            print(f"REMOVED {sub_dir}")
        except Exception as exc:  # pragma: no cover - operational error reporting
            result.remove_errors += 1
            print(f"ERROR removing {sub_dir}: {exc}")

    if not args.dry_run:
        print(f"Removed dirs: {result.removed_dirs}")
        print(f"Remove errors: {result.remove_errors}")
        return 1 if result.remove_errors else 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
