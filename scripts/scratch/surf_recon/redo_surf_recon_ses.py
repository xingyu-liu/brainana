"""Rerun FastSurfer surface reconstruction and QC at session level.

This script targets datasets with session-organized anatomy under each subject,
for example:
    <site>/sub-*/ses-*/anat/

It preserves the same backup/idempotent behavior used by redo_surf_recon.py and
emits a final run summary for audit.
"""

# %%
import sys
from collections import defaultdict
from pathlib import Path
import shutil

# Add src/ to path for nhp_mri_prep imports (tests/ -> brainana -> src)
_src_dir = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from nhp_mri_prep.steps.types import StepInput
from nhp_mri_prep.steps.anatomical import anat_surface_reconstruction
from nhp_mri_prep.utils.nextflow import load_config
from nhp_mri_prep.steps.qc import (
    qc_surf_recon_tissue_seg,
    qc_cortical_surf_and_measures,
)

# %%
dataset_root = Path("/mnt/DataDrive2/macaque/data_preproc/macaque_mri/UNC-Wisconsin")

# Run controls
rerun_all = True
dry_run = False
overwrite = False


# %%
def list_sites(root):
    """Return sorted site directories matching site-* (if present)."""
    site_dirs = [path for path in root.glob("site-*") if path.is_dir()]
    site_dirs.sort()
    return site_dirs


def list_subjects(parent_dir):
    """Return sorted subject directories matching sub-*."""
    subject_dirs = [path for path in parent_dir.glob("sub-*") if path.is_dir()]
    subject_dirs.sort()
    return subject_dirs


def list_sessions(sub_dir):
    """Return sorted session directories matching ses-*."""
    session_dirs = [path for path in sub_dir.glob("ses-*") if path.is_dir()]
    session_dirs.sort()
    return session_dirs


def get_filtered_matches(search_dir, pattern):
    """Collect glob matches, excluding NMT2Sym-space derivatives."""
    return [
        path for path in search_dir.glob(pattern) if "space-NMT2Sym" not in str(path)
    ]


def pick_single(search_dir, pattern, required=True):
    """Resolve one input file and return (path, status)."""
    matches = get_filtered_matches(search_dir, pattern)
    if len(matches) == 1:
        return matches[0], None
    if len(matches) == 0:
        return None, "missing" if required else None
    return None, f"multiple({len(matches)})"


def backup_subject_dir(fs_sub_dir, do_dry_run):
    """Backup an existing FastSurfer subject/session dir to <name>_todelete."""
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
    """Return whether a backup copy already exists for this session output."""
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


def load_site_config(site_dir):
    """Load site nextflow config.yaml, returning (config, status_msg)."""
    config_file = site_dir / "nextflow_reports" / "config.yaml"
    if not config_file.exists():
        return None, f"config not found at {config_file}"

    try:
        return load_config(config_file), None
    except Exception as exc:
        return None, f"failed to load config: {exc}"


def get_site_subject_pairs(root):
    """Return (site_name, site_dir, sub_dir) triples for iteration."""
    site_dirs = list_sites(root)
    if site_dirs:
        pairs = []
        for site_dir in site_dirs:
            for sub_dir in list_subjects(site_dir):
                pairs.append((site_dir.name, site_dir, sub_dir))
        return pairs

    # Fallback: no site-* layout, treat root as a single pseudo-site.
    return [("root", root, sub_dir) for sub_dir in list_subjects(root)]


# %%
# 0. prepare run state and subject list
stats = defaultdict(int)
site_subject_pairs = get_site_subject_pairs(dataset_root)

# %%
# 1. back up existing fastsurfer subject-session dirs
if rerun_all:
    print("Step 1: Backing up existing fastsurfer session dirs...")
    for site_name, site_dir, sub_dir in site_subject_pairs:
        sessions = list_sessions(sub_dir)
        if not sessions:
            stats["subject_missing_sessions"] += 1
            continue

        fastsurfer_dir = site_dir / "fastsurfer"
        if not fastsurfer_dir.exists():
            print(f"Skipping {site_name} / {sub_dir.name}: fastsurfer dir not found")
            stats["site_missing_fastsurfer"] += 1
            continue

        for ses_dir in sessions:
            sub = sub_dir.name
            ses = ses_dir.name
            fs_id = f"{sub}_{ses}"
            fs_sub_dir = fastsurfer_dir / fs_id
            try:
                already_reran = fs_sub_dir.exists() and has_subject_backup(fs_sub_dir)
                if already_reran and not overwrite:
                    print(
                        f"{site_name} / {sub} / {ses}: skip backup, rerun output and backup already exist"
                    )
                    stats["backup_skipped_already_reran"] += 1
                    continue

                if already_reran and overwrite:
                    print(
                        f"{site_name} / {sub} / {ses}: overwrite=True, keeping existing backup {fs_id}_todelete"
                    )
                    stats["backup_preserved_overwrite"] += 1
                    continue

                action = backup_subject_dir(fs_sub_dir, dry_run)
                if action is None:
                    stats["backup_not_found"] += 1
                    continue
                if action == "SKIP_ALREADY_BACKED_UP":
                    print(
                        f"{site_name} / {sub} / {ses}: skip backup, {fs_id}_todelete already exists"
                    )
                    stats["backup_skipped_already_exists"] += 1
                    continue
                print(f"{site_name} / {sub} / {ses}: {action}")
                stats["backup_done"] += 1
            except Exception as exc:
                print(f"Backup error for {site_name} / {sub} / {ses}: {exc}")
                stats["backup_errors"] += 1
else:
    print("Step 1 skipped: rerun_all is False.")

# %%
# 2. run surface reconstruction and regenerate QC images
print("Step 2: Running surface reconstruction and QC...")
for site_name, site_dir, sub_dir in site_subject_pairs:
    config, config_error = load_site_config(site_dir)
    if config_error is not None:
        print(f"Skipping {site_name} / {sub_dir.name}: {config_error}")
        if "config not found" in config_error:
            stats["site_config_missing"] += 1
        else:
            stats["site_config_errors"] += 1
        continue

    # Force hemisphere-parallel surface stages for this rerun script only.
    processing_cfg = config.setdefault("processing", {})
    processing_cfg["parallel_hemis"] = True
    processing_cfg["threads"] = "auto"

    fastsurfer_dir = site_dir / "fastsurfer"
    if not fastsurfer_dir.exists():
        print(f"Skipping {site_name} / {sub_dir.name}: fastsurfer dir not found")
        stats["site_missing_fastsurfer"] += 1
        continue

    sessions = list_sessions(sub_dir)
    if not sessions:
        print(f"Skipping {site_name} / {sub_dir.name}: no ses-* directories found")
        stats["subject_missing_sessions"] += 1
        continue

    for ses_dir in sessions:
        sub = sub_dir.name
        ses = ses_dir.name
        fs_id = f"{sub}_{ses}"
        fs_sub_dir = fastsurfer_dir / fs_id
        print(f"Processing {site_name} / {sub} / {ses}...")

        wmparc_file = fs_sub_dir / "mri" / "wmparc.mgz"
        output_complete = wmparc_file.exists()
        already_reran = output_complete and has_subject_backup(fs_sub_dir)
        if already_reran and not overwrite:
            print("  --> output and backup already exist (already reran), skipping")
            stats["skipped_already_reran"] += 1
            continue
        if already_reran and overwrite:
            print(
                "  --> output and backup already exist, overwrite=True so forcing fresh rerun"
            )
            stats["overwrite_runs"] += 1
            if dry_run:
                print(
                    f"  --> DRY_RUN would remove current fastsurfer dir: {fs_sub_dir}"
                )
            elif fs_sub_dir.exists():
                print(
                    f"  --> removing current fastsurfer dir before rerun: {fs_sub_dir}"
                )
                shutil.rmtree(fs_sub_dir)
            stats["removed_existing_for_overwrite"] += 1

        if fs_sub_dir.exists() and not output_complete:
            if dry_run:
                print(
                    f"  --> incomplete fastsurfer dir (missing wmparc.mgz), would remove: {fs_sub_dir}"
                )
            else:
                print(
                    f"  --> incomplete fastsurfer dir (missing wmparc.mgz), removing: {fs_sub_dir}"
                )
                shutil.rmtree(fs_sub_dir)
            stats["removed_incomplete_output"] += 1

        if output_complete and not rerun_all:
            print("  --> complete fastsurfer output found (wmparc.mgz), skipping")
            stats["skipped_existing_output"] += 1
            continue

        anat_dir = ses_dir / "anat"
        seg_file, seg_status = pick_single(
            anat_dir, "*_desc-brain_atlasARM2.nii.gz", required=True
        )
        mask_file, mask_status = pick_single(
            anat_dir, "*_desc-brain_mask.nii.gz", required=True
        )
        anat_file, anat_status = pick_single(
            anat_dir, "*_desc-preproc_T1w.nii.gz", required=True
        )
        arm6_atlas, arm6_status = pick_single(
            anat_dir, "atlas/atlas-ARM6*.nii.gz", required=True
        )

        missing_or_multiple = {
            "seg": seg_status,
            "mask": mask_status,
            "anat": anat_status,
            "arm6": arm6_status,
        }
        if any(status is not None for status in missing_or_multiple.values()):
            print(
                f"Skipping {site_name} / {sub} / {ses} due to file selection: {missing_or_multiple}"
            )
            if any(
                status == "missing"
                for status in (seg_status, mask_status, anat_status, arm6_status)
            ):
                stats["skipped_missing_input"] += 1
            else:
                stats["skipped_ambiguous_input"] += 1
            continue

        if dry_run:
            print(f"DRY_RUN would run recon for {site_name} / {sub} / {ses}")
            stats["dry_run_candidates"] += 1
            continue

        try:
            anat_surface_reconstruction(
                input=StepInput(
                    input_file=anat_file,
                    working_dir=fastsurfer_dir.parent,
                    config=config,
                    metadata={
                        "subject_id": fs_id,
                        "session_id": ses,
                        "session_count": 1,
                    },
                ),
                t1w_file=anat_file,
                segmentation_file=seg_file,
                brain_mask=mask_file,
                arm6_atlas=arm6_atlas,
            )
        except Exception as exc:
            print(f"Reconstruction error for {site_name} / {sub} / {ses}: {exc}")
            stats["recon_errors"] += 1
            continue

        # Keep QC figures at subject level across sessions.
        figures_dir = sub_dir / "figures"
        figures_dir.mkdir(parents=True, exist_ok=True)
        tissue_qc_png = figures_dir / anat_file.name.replace(
            "_desc-preproc_T1w.nii.gz", "_desc-surfReconTissueSeg_T1w.png"
        )
        cortical_qc_png = figures_dir / anat_file.name.replace(
            "_desc-preproc_T1w.nii.gz", "_desc-corticalSurfAndMeasures_T1w.png"
        )

        backup_tissue_msg = backup_png_if_exists(tissue_qc_png, dry_run)
        if backup_tissue_msg is not None:
            print(f"{site_name} / {sub} / {ses}: {backup_tissue_msg}")
            stats["qc_png_backups"] += 1
        backup_cortical_msg = backup_png_if_exists(cortical_qc_png, dry_run)
        if backup_cortical_msg is not None:
            print(f"{site_name} / {sub} / {ses}: {backup_cortical_msg}")
            stats["qc_png_backups"] += 1

        try:
            qc_surf_recon_tissue_seg(
                fs_subject_dir=fs_sub_dir,
                output_path=tissue_qc_png,
                modality="anat",
                config=config,
            )
        except Exception as exc:
            print(f"QC tissue seg error for {site_name} / {sub} / {ses}: {exc}")
            stats["qc_errors"] += 1
            continue

        try:
            qc_cortical_surf_and_measures(
                fs_subject_dir=fs_sub_dir,
                output_path=cortical_qc_png,
                modality="anat",
                config=config,
            )
        except Exception as exc:
            print(f"QC cortical error for {site_name} / {sub} / {ses}: {exc}")
            stats["qc_errors"] += 1
            continue

        shutil.rmtree(figures_dir / "volsurf_work", ignore_errors=True)
        stats["processed_ok"] += 1

# %%
# 3. print run summary
print("\nRun summary")
for key in sorted(stats.keys()):
    print(f"- {key}: {stats[key]}")
