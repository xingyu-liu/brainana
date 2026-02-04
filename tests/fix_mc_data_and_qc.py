# %%
"""
Fix motion parameter column names and regenerate motion QC plots for an already
preprocessed dataset. Addresses the bug where MCFLIRT .par columns were labeled
trans-first, rot-last instead of the correct rot-first, trans-last.
"""

import re
import sys
from pathlib import Path

import pandas as pd

# Add src to path for nhp_mri_prep imports
_src_dir = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(_src_dir))

from nhp_mri_prep.quality_control import create_motion_correction_qc

# %%

dataset_dir = Path(
    "/mnt/DataDrive2/macaque/data_preproc/macaque_mri/PRIME-DE_brainana/site-newcastle"
)

CORRECT_COLS = ["rot_x", "rot_y", "rot_z", "trans_x", "trans_y", "trans_z"]
WRONG_COLS = ["trans_x", "trans_y", "trans_z", "rot_x", "rot_y", "rot_z"]


def needs_fix(df: pd.DataFrame) -> bool:
    """Check if TSV has the wrong column order (trans first, rot last)."""
    cols = list(df.columns)
    return cols == WRONG_COLS or (len(cols) == 6 and cols[:3] == WRONG_COLS[:3])


def fix_confounds_tsv(tsv_path: Path) -> bool:
    """
    Fix column names in a confounds TSV. Returns True if file was modified.
    """
    df = pd.read_csv(tsv_path, sep="\t")
    if not needs_fix(df):
        return False
    df.columns = CORRECT_COLS
    df.to_csv(tsv_path, sep="\t", index=False)
    return True


def get_figures_dir(confounds_path: Path) -> Path:
    """Get sub-xxx/figures directory from a confounds file path."""
    # confounds at: .../sub-xxx/ses-xxx/func/... or .../sub-xxx/func/...
    parts = confounds_path.resolve().parts
    sub_idx = next(i for i, p in enumerate(parts) if re.match(r"sub-[a-zA-Z0-9]+", p))
    sub_dir = Path(*parts[: sub_idx + 1])
    return sub_dir / "figures"


def get_qc_output_filename(confounds_path: Path) -> str:
    """Derive QC plot filename from confounds filename."""
    stem = confounds_path.stem  # e.g. sub-01_ses-01_task-rest_run-01_desc-confounds_timeseries
    qc_stem = stem.replace("desc-confounds_timeseries", "desc-motion") + "_bold"
    return qc_stem + ".png"


# %%

def main():
    if not dataset_dir.exists():
        print(f"Dataset directory not found: {dataset_dir}")
        return 1

    confounds_globs = [
        "sub-*/func/*desc-confounds_timeseries.tsv",
        "sub-*/ses-*/func/*desc-confounds_timeseries.tsv",
    ]
    confounds_files = []
    for pattern in confounds_globs:
        confounds_files.extend(dataset_dir.glob(pattern))

    if not confounds_files:
        print(f"No *desc-confounds_timeseries.tsv files found under {dataset_dir}")
        return 0

    print(f"Found {len(confounds_files)} confounds TSV file(s)\n")

    fixed_count = 0
    qc_count = 0

    for tsv_path in sorted(confounds_files):
        # 1. Fix column names
        if fix_confounds_tsv(tsv_path):
            print(f"Fixed columns: {tsv_path.relative_to(dataset_dir)}")
            fixed_count += 1
        else:
            print(f"Already correct: {tsv_path.relative_to(dataset_dir)}")

        # 2. Regenerate motion QC plot
        figures_dir = get_figures_dir(tsv_path)
        figures_dir.mkdir(parents=True, exist_ok=True)
        qc_filename = get_qc_output_filename(tsv_path)
        qc_path = figures_dir / qc_filename

        result = create_motion_correction_qc(
            motion_params=str(tsv_path),
            save_f=str(qc_path),
        )
        if result:
            print(f"  -> QC plot: {qc_path.relative_to(dataset_dir)}")
            qc_count += 1
        else:
            print(f"  -> Failed to generate QC plot")

    # print(f"\nDone: fixed {fixed_count} TSV(s), generated {qc_count} QC plot(s)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
