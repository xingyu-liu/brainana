# %%
import sys
import logging
from pathlib import Path
import shutil

# Add src/ to path for nhp_mri_prep, fastsurfer_nn imports (tests/ -> brainana -> src)
_src_dir = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

# Show pipeline progress in console (otherwise it looks stuck – logs only go to file)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s]: %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("fastsurfer_surfrecon").setLevel(logging.INFO)

from fastsurfer_surfrecon.pipeline import ReconSurfPipeline
from fastsurfer_surfrecon.config import ReconSurfConfig
from nhp_mri_prep.utils.nextflow import load_config
from nhp_mri_prep.steps.qc import qc_surf_recon_tissue_seg, qc_cortical_surf_and_measures

# %%
# UNC-Wisconsin: anat at session level (sub-XX/ses-YY/anat/); FastSurfer subjects are sub-XX_ses-YY
dataset_root = Path('/mnt/DataDrive2/macaque/data_preproc/macaque_mri')
site_list = [dataset_root / 'UNC-Wisconsin_need_to_fix_surf']
# True = re-run surface recon even when fastsurfer/sub-XX_ses-YY already exists; False = skip existing
overwrite_existing = False

# %%
# # 1. back up the existing surface reconstruction results (per-session dirs: sub-XX_ses-YY)
# for site_dir in site_list:
#     site_dir = Path(site_dir)
#     site_name = site_dir.name
#     print(f'Processing {site_name}...')

#     fastsurfer_dir = site_dir / 'fastsurfer'
#     if not fastsurfer_dir.exists():
#         print(f"fastsurfer dir not found, skipping")
#         continue

#     sub_list = [p for p in site_dir.glob('sub-*') if p.is_dir()]
#     sub_list.sort()
#     for sub_dir in sub_list:
#         sub_dir = Path(sub_dir)
#         sub = sub_dir.name
#         ses_list = [p for p in sub_dir.glob('ses-*') if p.is_dir()]
#         ses_list.sort()
#         for ses_dir in ses_list:
#             ses = ses_dir.name
#             fs_sub_id = f"{sub}_{ses}"
#             fs_sub_dir = fastsurfer_dir / fs_sub_id
#             if not fs_sub_dir.exists():
#                 print(f"  --> {site_name} / {fs_sub_id} not found")
#             else:
#                 shutil.move(fs_sub_dir, fs_sub_dir.parent / f'{fs_sub_id}_todelete')

# %%
# 2. prepare and run surface recon per session (anat under sub-XX/ses-YY/anat/)
for site_dir in site_list:
    site_dir = Path(site_dir)
    site_name = site_dir.name
    print(f'Processing {site_name}...')

    config_file = site_dir / 'nextflow_reports' / 'config.yaml'
    if not config_file.exists():
        config_file = site_dir / 'config.yaml'
    if not config_file.exists():
        print(f"  config not found, skipping site")
        continue
    config = load_config(config_file)

    fastsurfer_dir = site_dir / 'fastsurfer'
    if not fastsurfer_dir.exists():
        print(f"fastsurfer dir not found")
        continue

    sub_list = [p for p in site_dir.glob('sub-*') if p.is_dir()]
    sub_list.sort()
    for sub_dir in sub_list[::1]:
        sub_dir = Path(sub_dir)
        sub = sub_dir.name
        ses_list = [p for p in sub_dir.glob('ses-*') if p.is_dir()]
        ses_list.sort()
        for ses_dir in ses_list:
            ses = ses_dir.name
            fs_sub_id = f"{sub}_{ses}"
            fs_sub_dir = fastsurfer_dir / fs_sub_id

            fs_sub_touch_dir = fs_sub_dir / 'touch'
            if fs_sub_touch_dir.exists() and not overwrite_existing:
                print(f"  --> existing {site_name} / {fs_sub_id} found, skipping")
                continue
            fs_sub_dir.mkdir(parents=True, exist_ok=True)

            # anat at session level: sub-XX/ses-YY/anat/*_desc-preproc_T1w.nii.gz (exclude space-NMT2Sym)
            anat_files = list(ses_dir.glob('anat/*_desc-preproc_T1w.nii.gz'))
            anat_files = [f for f in anat_files if 'space-NMT2Sym' not in str(f)]
            if len(anat_files) == 0:
                print(f"  Skipping {fs_sub_id}: no anat found")
                continue
            if len(anat_files) > 1:
                print(f"  Skipping {fs_sub_id}: multiple anat files")
                continue
            anat_file = anat_files[0]

            # 1. copy mri from backup
            bak_fs_sub_dir = fs_sub_dir.parent / f'{fs_sub_id}_todelete'
            if not bak_fs_sub_dir.exists():
                raise ValueError(f"backup {bak_fs_sub_dir} not found")
            mri_dest = fs_sub_dir / 'mri'
            if mri_dest.exists():
                shutil.rmtree(mri_dest)
            shutil.copytree(bak_fs_sub_dir / 'mri', mri_dest)

            # 2. run surface reconstruction (subject_id = sub_XX_ses_YY)
            try:
                threads = config.get("processing", {}).get("threads", 8)
                atlas_name = config.get("anat", {}).get("skullstripping_segmentation", {}).get("atlas_name", "ARM2")
                recon_config = ReconSurfConfig.with_defaults(
                    subject_id=fs_sub_id,
                    subjects_dir=str(fastsurfer_dir),
                    atlas={"name": atlas_name},
                    processing={"threads": threads, "skip_cc": True, "skip_talairach": True},
                    verbose=1,
                )
                pipeline = ReconSurfPipeline(recon_config)
                pipeline.run()
                print()
            except Exception as e:
                print(f"Error for {site_name} / {fs_sub_id}: {e}")
                raise e

            # 3. QC images under sub-XX/figures/ (anat filename already includes ses)
            (sub_dir / "figures").mkdir(parents=True, exist_ok=True)
            qc_stem = anat_file.name.replace("_desc-preproc_T1w.nii.gz", "")
            try:
                qc_surf_recon_tissue_seg(
                    fs_subject_dir=fs_sub_dir,
                    output_path=sub_dir / 'figures' / f'{qc_stem}_desc-surfReconTissueSeg_T1w.png',
                    modality='anat',
                    config=config
                )
            except Exception as e:
                print(f"Error QC tissue seg {site_name} / {fs_sub_id}: {e}")
                continue
            try:
                qc_cortical_surf_and_measures(
                    fs_subject_dir=fs_sub_dir,
                    output_path=sub_dir / 'figures' / f'{qc_stem}_desc-corticalSurfAndMeasures_T1w.png',
                    modality='anat',
                    config=config
                )
                volsurf_work = sub_dir / 'figures' / 'volsurf_work'
                if volsurf_work.exists():
                    shutil.rmtree(volsurf_work)
            except Exception as e:
                print(f"Error QC cortical surf {site_name} / {fs_sub_id}: {e}")
                continue

# %%
