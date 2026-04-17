"""Rerun FastSurfer surface reconstruction and QC for all PRIME-DE sites.

This script is designed for bulk reruns after segmentation-related updates
(for example, claustrum fixes). It supports idempotent backup of existing
FastSurfer outputs and emits a final run summary for quick audit.
"""

# %%
import sys
from collections import defaultdict
from pathlib import Path
import shutil

# Add src/ to path for nhp_mri_prep, fastsurfer_nn imports (tests/ -> brainana -> src)
_src_dir = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from nhp_mri_prep.steps.types import StepInput
from nhp_mri_prep.steps.anatomical import anat_surface_reconstruction
from nhp_mri_prep.utils.nextflow import load_config
from nhp_mri_prep.steps.qc import qc_surf_recon_tissue_seg, qc_cortical_surf_and_measures

# %%
dataset_root = Path("/mnt/DataDrive2/macaque/data_preproc/macaque_mri/PRIME-DE_brainana")

# Run controls
rerun_all = True
dry_run = False
overwrite = False

# %%
def list_sites(root):
    """Return sorted site directories matching site-*."""
    site_dirs = [path for path in root.glob("site-*") if path.is_dir()]
    site_dirs.sort()
    return site_dirs


def list_subjects(site_dir):
    """Return sorted subject directories matching sub-* for one site."""
    subject_dirs = [path for path in site_dir.glob("sub-*") if path.is_dir()]
    subject_dirs.sort()
    return subject_dirs


def get_filtered_matches(sub_dir, pattern):
    """Collect glob matches, excluding NMT2Sym-space derivatives."""
    return [path for path in sub_dir.glob(pattern) if "space-NMT2Sym" not in str(path)]


def pick_single(sub_dir, pattern, required=True):
    """Resolve one input file and return (path, status)."""
    matches = get_filtered_matches(sub_dir, pattern)
    if len(matches) == 1:
        return matches[0], None
    if len(matches) == 0:
        return None, "missing" if required else None
    return None, f"multiple({len(matches)})"


def backup_subject_dir(fs_sub_dir, do_dry_run):
    """Backup an existing FastSurfer subject directory to <sub>_todelete."""
    if not fs_sub_dir.exists():
        return None

    backup_dir = fs_sub_dir.parent / f"{fs_sub_dir.name}_todelete"
    if backup_dir.exists():
        return "SKIP_ALREADY_BACKED_UP"

    if do_dry_run:
        return f"DRY_RUN move {fs_sub_dir} -> {backup_dir}"

    shutil.move(fs_sub_dir, backup_dir)
    return f"Moved {fs_sub_dir} -> {backup_dir}"


def has_subject_backup(fs_sub_dir):
    """Return whether a backup copy already exists for this subject."""
    return (fs_sub_dir.parent / f"{fs_sub_dir.name}_todelete").exists()


def backup_png_if_exists(png_path, do_dry_run):
    """Move an existing QC png to *_todelete.png before rewriting it."""
    if not png_path.exists():
        return None

    backup_png = png_path.with_name(f"{png_path.stem}_todelete{png_path.suffix}")
    if do_dry_run:
        return f"DRY_RUN move {png_path} -> {backup_png}"

    if backup_png.exists():
        return "SKIP_ALREADY_BACKED_UP"

    shutil.move(png_path, backup_png)
    return f"Moved {png_path} -> {backup_png}"

# %%
# 0. prepare run state and site list
stats = defaultdict(int)
site_list = list_sites(dataset_root)[::1]

# %%
# 1. back up (or delete) existing fastsurfer subject dirs
if rerun_all:
    print("Step 1: Backing up existing fastsurfer subject dirs...")
    for site_dir in site_list:
        site_name = site_dir.name
        fastsurfer_dir = site_dir / "fastsurfer"
        if not fastsurfer_dir.exists():
            print(f"Skipping {site_name}: fastsurfer dir not found")
            stats["site_missing_fastsurfer"] += 1
            continue

        for sub_dir in list_subjects(site_dir):
            sub = sub_dir.name
            fs_sub_dir = fastsurfer_dir / sub
            try:
                # "already_reran" means we have both a complete current output and
                # an archival backup (<sub>_todelete), so this subject was processed before.
                already_reran = fs_sub_dir.exists() and has_subject_backup(fs_sub_dir)
                if already_reran and not overwrite:
                    print(f"{site_name} / {sub}: skip backup, rerun output and backup already exist")
                    stats["backup_skipped_already_reran"] += 1
                    continue

                if already_reran and overwrite:
                    # Preserve existing backup history in overwrite mode.
                    print(f"{site_name} / {sub}: overwrite=True, keeping existing backup {sub}_todelete")
                    stats["backup_preserved_overwrite"] += 1
                    continue

                # For subjects without a prior backup, create one exactly once.
                action = backup_subject_dir(fs_sub_dir, dry_run)
                if action is None:
                    stats["backup_not_found"] += 1
                    continue
                if action == "SKIP_ALREADY_BACKED_UP":
                    print(f"{site_name} / {sub}: skip backup, {sub}_todelete already exists")
                    stats["backup_skipped_already_exists"] += 1
                    continue
                print(f"{site_name} / {sub}: {action}")
                stats["backup_done"] += 1
            except Exception as exc:
                print(f"Backup error for {site_name} / {sub}: {exc}")
                stats["backup_errors"] += 1
else:
    print("Step 1 skipped: rerun_all is False.")

# %%
# 2. run surface reconstruction and regenerate QC images
print("Step 2: Running surface reconstruction and QC...")
# Iterate in reverse order to keep behavior consistent with earlier rerun batches.
for site_dir in site_list[::-1]:
    site_name = site_dir.name
    print(f"Processing {site_name}...")

    config_file = site_dir / "nextflow_reports" / "config.yaml"
    if not config_file.exists():
        print(f"Skipping {site_name}: config not found at {config_file}")
        stats["site_config_missing"] += 1
        continue

    try:
        config = load_config(config_file)
    except Exception as exc:
        print(f"Skipping {site_name}: failed to load config: {exc}")
        stats["site_config_errors"] += 1
        continue

    # Force hemisphere-parallel surface stages for this rerun script only.
    processing_cfg = config.setdefault("processing", {})
    processing_cfg["parallel_hemis"] = True
    processing_cfg["threads"] = "auto"

    fastsurfer_dir = site_dir / "fastsurfer"
    if not fastsurfer_dir.exists():
        print(f"Skipping {site_name}: fastsurfer dir not found")
        stats["site_missing_fastsurfer"] += 1
        continue

    for sub_dir in list_subjects(site_dir)[::-1]:
        sub = sub_dir.name
        fs_sub_dir = fastsurfer_dir / sub
        print(f"Processing {site_name} / {sub}...")

        # wmparc.mgz is used as the marker for a completed FastSurfer subject run.
        wmparc_file = fs_sub_dir / "mri" / "wmparc.mgz"
        output_complete = wmparc_file.exists()
        already_reran = output_complete and has_subject_backup(fs_sub_dir)
        if already_reran and not overwrite:
            print("  --> output and backup already exist (already reran), skipping")
            stats["skipped_already_reran"] += 1
            continue
        if already_reran and overwrite:
            print("  --> output and backup already exist, overwrite=True so forcing fresh rerun")
            stats["overwrite_runs"] += 1
            # Overwrite mode refreshes ONLY current output; backup archive is preserved.
            if dry_run:
                print(f"  --> DRY_RUN would remove current fastsurfer dir: {fs_sub_dir}")
            elif fs_sub_dir.exists():
                print(f"  --> removing current fastsurfer dir before rerun: {fs_sub_dir}")
                shutil.rmtree(fs_sub_dir)
            stats["removed_existing_for_overwrite"] += 1

        # Clean up partial runs so reconstruction starts from a clean directory.
        if fs_sub_dir.exists() and not output_complete:
            if dry_run:
                print(f"  --> incomplete fastsurfer dir (missing wmparc.mgz), would remove: {fs_sub_dir}")
            else:
                print(f"  --> incomplete fastsurfer dir (missing wmparc.mgz), removing: {fs_sub_dir}")
                shutil.rmtree(fs_sub_dir)
            stats["removed_incomplete_output"] += 1

        if output_complete and not rerun_all:
            print("  --> complete fastsurfer output found (wmparc.mgz), skipping")
            stats["skipped_existing_output"] += 1
            continue

        # Enforce exactly one valid input per required artifact before launching recon.
        seg_file, seg_status = pick_single(sub_dir, "**/anat/*_desc-brain_atlasARM2.nii.gz", required=True)
        mask_file, mask_status = pick_single(sub_dir, "**/anat/*_desc-brain_mask.nii.gz", required=True)
        anat_file, anat_status = pick_single(sub_dir, "**/anat/*_desc-preproc_T1w.nii.gz", required=True)
        arm6_atlas, arm6_status = pick_single(sub_dir, "**/anat/atlas_space-T1w/atlas-ARM6*.nii.gz", required=True)

        missing_or_multiple = {
            "seg": seg_status,
            "mask": mask_status,
            "anat": anat_status,
            "arm6": arm6_status,
        }
        if any(status is not None for status in missing_or_multiple.values()):
            print(f"Skipping {site_name} / {sub} due to file selection: {missing_or_multiple}")
            if any(status == "missing" for status in (seg_status, mask_status, anat_status, arm6_status)):
                stats["skipped_missing_input"] += 1
            else:
                stats["skipped_ambiguous_input"] += 1
            continue

        if dry_run:
            print(f"DRY_RUN would run recon for {site_name} / {sub}")
            stats["dry_run_candidates"] += 1
            continue

        # Run FastSurfer reconstruction first; QC generation depends on its outputs.
        try:
            anat_surface_reconstruction(
                input=StepInput(
                    input_file=anat_file,
                    working_dir=fastsurfer_dir.parent,
                    config=config,
                    metadata={"subject_id": sub, "session_count": 1},
                ),
                t1w_file=anat_file,
                segmentation_file=seg_file,
                brain_mask=mask_file,
                arm6_atlas=arm6_atlas,
            )
        except Exception as exc:
            print(f"Reconstruction error for {site_name} / {sub}: {exc}")
            stats["recon_errors"] += 1
            continue

        figures_dir = sub_dir / "figures"
        figures_dir.mkdir(parents=True, exist_ok=True)
        tissue_qc_png = figures_dir / anat_file.name.replace(
            "_desc-preproc_T1w.nii.gz", "_desc-surfReconTissueSeg_T1w.png"
        )
        cortical_qc_png = figures_dir / anat_file.name.replace(
            "_desc-preproc_T1w.nii.gz", "_desc-corticalSurfAndMeasures_T1w.png"
        )

        # 2.1 back up original QC png files to *_todelete.png before rewriting
        backup_tissue_msg = backup_png_if_exists(tissue_qc_png, dry_run)
        if backup_tissue_msg is not None:
            print(f"{site_name} / {sub}: {backup_tissue_msg}")
            stats["qc_png_backups"] += 1
        backup_cortical_msg = backup_png_if_exists(cortical_qc_png, dry_run)
        if backup_cortical_msg is not None:
            print(f"{site_name} / {sub}: {backup_cortical_msg}")
            stats["qc_png_backups"] += 1

        # 2.2 generate QC_SURF_RECON_TISSUE_SEG image
        try:
            qc_surf_recon_tissue_seg(
                fs_subject_dir=fs_sub_dir,
                output_path=tissue_qc_png,
                modality="anat",
                config=config,
            )
        except Exception as exc:
            print(f"QC tissue seg error for {site_name} / {sub}: {exc}")
            stats["qc_errors"] += 1
            continue

        # 2.3 generate QC_CORTICAL_SURF_AND_MEASURES image
        try:
            qc_cortical_surf_and_measures(
                fs_subject_dir=fs_sub_dir,
                output_path=cortical_qc_png,
                modality="anat",
                config=config,
            )
        except Exception as exc:
            print(f"QC cortical error for {site_name} / {sub}: {exc}")
            stats["qc_errors"] += 1
            continue

        # Remove temporary surface/volume QC workspace to keep subject directory tidy.
        shutil.rmtree(figures_dir / "volsurf_work", ignore_errors=True)
        stats["processed_ok"] += 1

# %%
# 3. print run summary
print("\nRun summary")
for key in sorted(stats.keys()):
    print(f"- {key}: {stats[key]}")
