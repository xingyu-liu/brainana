# %%
from pathlib import Path
import shutil
import tempfile
import traceback

from nhp_mri_prep.steps.anatomical import anat_backproject_atlases
from nhp_mri_prep.utils.nextflow import load_config
from tqdm.auto import tqdm

# %%
# Parameters
dataset_root = Path("/mnt/DataDrive2/macaque/data_preproc/macaque_mri/PRIME-DE_brainana")
config_file = Path("/home/star/github/brainana/src/nhp_mri_prep/config/defaults.yaml")
template_dir = Path("/home/star/github/brainana/template_zoo")

overwrite = False
dry_run = False

# Optional filters (empty list means all)
include_subjects = []
include_sessions = []

# Hardcoded to match your historical preprocessing setup
inverse_xfm_pattern = "*from-NMT2Sym_to-T1w_mode-image_xfm*"

# %%
def parse_subject_session(anat_dir: Path):
    subject_id = None
    session_id = None
    for parent in anat_dir.parents:
        if parent.name.startswith("sub-") and subject_id is None:
            subject_id = parent.name.replace("sub-", "")
        if parent.name.startswith("ses-") and session_id is None:
            session_id = parent.name.replace("ses-", "")
    return subject_id, session_id


def iter_subject_dirs(site_dir: Path):
    return sorted(p for p in site_dir.glob("sub-*") if p.is_dir())


def _is_t1w_preproc_in_t1w_space(path: Path) -> bool:
    name = path.name
    if not name.endswith("desc-preproc_T1w.nii.gz"):
        return False
    # Current pipeline: space-T1w_desc-preproc_T1w
    if "_space-T1w_desc-preproc_" in name:
        return True
    # Legacy outputs without space entity
    return "space-" not in name


def find_required_inputs_for_subject(subject_dir: Path, site_name: str):
    subject_id = subject_dir.name.replace("sub-", "")
    anat_dirs = sorted(
        p for p in subject_dir.glob("**/anat") if p.is_dir() and p.parent.name.startswith(("sub-", "ses-"))
    )
    record = {
        "anat_dir": None,
        "site": site_name,
        "subject_id": subject_id,
        "session_id": None,
        "status": "pending",
        "reason": "",
        "bids_name": None,
        "t1w_reference": None,
        "inverse_reg_xfm": None,
        "out_dir_t1w": None,
    }

    if not anat_dirs:
        record["status"] = "skip_missing_inputs"
        record["reason"] = "missing_anat_dir_under_subject"
        return record

    t1w_candidates = []
    for anat_dir in anat_dirs:
        t1w_candidates.extend(
            p for p in anat_dir.glob("*desc-preproc_T1w.nii.gz") if _is_t1w_preproc_in_t1w_space(p)
        )
    t1w_candidates = sorted(t1w_candidates)
    if len(t1w_candidates) == 0:
        record["status"] = "skip_missing_inputs"
        record["reason"] = "missing_desc-preproc_T1w_without_space_at_subject_level"
        return record
    if len(t1w_candidates) > 1:
        record["status"] = "failed_input_ambiguity"
        record["reason"] = "multiple_desc-preproc_T1w_without_space_at_subject_level"
        record["t1w_candidates"] = [str(p) for p in t1w_candidates]
        return record

    t1w_path = t1w_candidates[0]
    anat_dir = t1w_path.parent
    _, session_id = parse_subject_session(anat_dir)
    record["session_id"] = session_id
    record["anat_dir"] = anat_dir
    record["out_dir_t1w"] = anat_dir / "atlas_space-T1w"

    inverse_candidates = sorted(anat_dir.glob(inverse_xfm_pattern))
    if len(inverse_candidates) == 0:
        record["status"] = "skip_missing_inputs"
        record["reason"] = "missing_inverse_xfm_from-NMT2Sym_to-T1w_for_selected_t1w"
        return record
    if len(inverse_candidates) > 1:
        record["status"] = "failed_input_ambiguity"
        record["reason"] = "multiple_inverse_xfm_from-NMT2Sym_to-T1w_for_selected_t1w"
        record["inverse_candidates"] = [str(p) for p in inverse_candidates]
        return record

    # Keep preproc image as spatial reference, but remove desc-preproc from atlas filename template.
    bids_name_no_preproc = (
        t1w_path.name.replace("_space-T1w_desc-preproc_T1w.nii.gz", "_T1w.nii.gz")
        .replace("_desc-preproc_T1w.nii.gz", "_T1w.nii.gz")
    )
    record["bids_name"] = Path(bids_name_no_preproc)
    record["t1w_reference"] = t1w_path
    record["inverse_reg_xfm"] = inverse_candidates[0]

    existing_outputs = sorted(record["out_dir_t1w"].glob("*.nii.gz")) if record["out_dir_t1w"].exists() else []
    if existing_outputs and not overwrite:
        record["status"] = "skip_exists"
        record["reason"] = f"atlas_space-T1w_exists_n={len(existing_outputs)}"
    else:
        record["status"] = "ready"
    return record


def pass_filters(record):
    if include_subjects and record["subject_id"] not in include_subjects:
        return False
    if include_sessions and (record["session_id"] not in include_sessions):
        return False
    return True


# %%
# Discovery
all_records = []
site_list = sorted(p for p in dataset_root.glob("site-*") if p.is_dir())

for site_dir in site_list:
    print(f"Scanning {site_dir.name} ...")
    for subject_dir in iter_subject_dirs(site_dir):
        rec = find_required_inputs_for_subject(subject_dir, site_dir.name)
        if pass_filters(rec):
            all_records.append(rec)

status_counts = {}
for rec in all_records:
    status_counts[rec["status"]] = status_counts.get(rec["status"], 0) + 1

print(f"Found {len(all_records)} subjects")
for status in sorted(status_counts):
    print(f"  {status}: {status_counts[status]}")

not_ready_records = [rec for rec in all_records if rec["status"] != "ready"]
if not_ready_records:
    print("\nDetailed records not ready:")
    for rec in not_ready_records:
        subject_label = f"sub-{rec['subject_id']}" if rec["subject_id"] else "sub-unknown"
        session_label = f"/ses-{rec['session_id']}" if rec["session_id"] else ""
        site_label = rec["site"] if rec["site"] else "site-unknown"
        case_label = f"{site_label}:{subject_label}{session_label}"
        print(f"- {case_label}")
        print(f"  status: {rec['status']}")
        print(f"  reason: {rec['reason']}")
        print(f"  anat_dir: {rec['anat_dir']}")
        if "t1w_candidates" in rec:
            print("  t1w_candidates:")
            for path in rec["t1w_candidates"]:
                print(f"    - {path}")
        if "inverse_candidates" in rec:
            print("  inverse_candidates:")
            for path in rec["inverse_candidates"]:
                print(f"    - {path}")

# %%
# Execute T1w backprojection only
config = load_config(str(config_file))
run_results = []

# Keep non-ready bookkeeping outside the progress bar.
for rec in all_records:
    subject_label = f"sub-{rec['subject_id']}" if rec["subject_id"] else "sub-unknown"
    session_label = f"/ses-{rec['session_id']}" if rec["session_id"] else ""
    case_label = f"{subject_label}{session_label}"

    if rec["status"] != "ready":
        run_results.append(
            {
                "case": case_label,
                "status": rec["status"],
                "reason": rec["reason"],
                "written": 0,
            }
        )
        continue

ready_records = [rec for rec in all_records if rec["status"] == "ready"]
for rec in tqdm(ready_records, desc="Backprojecting atlases to T1w"):
    subject_label = f"sub-{rec['subject_id']}" if rec["subject_id"] else "sub-unknown"
    session_label = f"/ses-{rec['session_id']}" if rec["session_id"] else ""
    case_label = f"{subject_label}{session_label}"

    if dry_run:
        run_results.append(
            {
                "case": case_label,
                "status": "dry_run_ready",
                "reason": "would_run_t1w_backprojection",
                "written": 0,
            }
        )
        continue

    try:
        with tempfile.TemporaryDirectory(prefix="atlas_t1w_backfill_") as tmpdir:
            working_dir = Path(tmpdir)
            step_result = anat_backproject_atlases(
                inverse_xfm=rec["inverse_reg_xfm"],
                t1w_reference=rec["t1w_reference"],
                bids_name=rec["bids_name"],
                working_dir=working_dir,
                config=config,
                template_dir=Path(template_dir) if template_dir else None,
            )

            atlas_dir = Path(step_result.output_file)
            generated = sorted(atlas_dir.glob("*.nii.gz"))

            if not generated:
                run_results.append(
                    {
                        "case": case_label,
                        "status": "skip_no_atlases",
                        "reason": "no_atlas_outputs_generated",
                        "written": 0,
                    }
                )
                continue

            rec["out_dir_t1w"].mkdir(parents=True, exist_ok=True)
            written = 0
            for src in generated:
                dst = rec["out_dir_t1w"] / src.name
                if dst.exists() and not overwrite:
                    continue
                shutil.copy2(src, dst)
                written += 1

            run_results.append(
                {
                    "case": case_label,
                    "status": "processed",
                    "reason": "ok",
                    "written": written,
                }
            )
    except Exception as exc:
        run_results.append(
            {
                "case": case_label,
                "status": "failed",
                "reason": f"{type(exc).__name__}: {exc}",
                "written": 0,
                "traceback": traceback.format_exc(),
            }
        )

# %%
# Final report
result_counts = {}
for row in run_results:
    result_counts[row["status"]] = result_counts.get(row["status"], 0) + 1

print(f"Processed records: {len(run_results)}")
for status in sorted(result_counts):
    print(f"  {status}: {result_counts[status]}")

failed_rows = [r for r in run_results if r["status"] in {"failed", "failed_input_ambiguity"}]
if failed_rows:
    print("\nFailure / ambiguity details:")
    for row in failed_rows:
        print(f"- {row['case']}: {row['status']} ({row['reason']})")
        if "traceback" in row:
            print("  traceback_tail:")
            tb_lines = row["traceback"].strip().splitlines()
            for line in tb_lines[-6:]:
                print(f"    {line}")

