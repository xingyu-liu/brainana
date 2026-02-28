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
dataset_root = Path('/mnt/DataDrive2/macaque/data_preproc/macaque_mri/PRIME-DE_brainana')
# True = re-run surface recon even when fastsurfer/sub-XX already exists; False = skip existing
overwrite_existing = False

# %%
site_list = list(dataset_root.glob('site-*'))
site_list = [i for i in site_list if i.is_dir()]
site_list.sort()
# print(site_list)

# %%
# # 1. back up the existing surface reconstruction results
# for site_dir in site_list:
#     site_dir = Path(site_dir)
#     site_name = site_dir.name
#     print(f'Processing {site_name}...')

#     # create a working directory for the site
#     fastsurfer_dir = site_dir / 'fastsurfer'
    
#     if not fastsurfer_dir.exists():
#         print(f"fastsurfer dir not found, skipping")
#         continue

#     # loop through all the subjects in the site
#     sub_list = site_dir.glob('sub-*')
#     sub_list = [i for i in sub_list if i.is_dir()]
#     sub_list.sort()
#     for sub_dir in sub_list:
#         sub_dir = Path(sub_dir)
#         sub = sub_dir.name
#         print(f'  Processing {site_name} / {sub}...')

#         fs_sub_dir = fastsurfer_dir / sub
#         if not fs_sub_dir.exists():
#             print(f"  --> {site_name} / {sub} subject dir not found")
#         else:
#             # move the subject dir to the working directory
#             shutil.move(fs_sub_dir, fs_sub_dir.parent / f'{sub}_todelete')

# %%
# 2. prepare the surface input files
for site_dir in site_list[::-1]:
    site_dir = Path(site_dir)
    site_name = site_dir.name
    print(f'Processing {site_name}...')

    # load the config file
    config_file = Path(site_dir) / 'nextflow_reports' / 'config.yaml'
    if not config_file.exists():
        print(f"  config not found: {config_file}, skipping site")
        continue
    config = load_config(config_file)

    # create a working directory for the site
    fastsurfer_dir = site_dir / 'fastsurfer'
    if not fastsurfer_dir.exists():
        print(f"fastsurfer dir not found")
        continue

    # loop through all the subjects in the site ([:1] = first subject only, remove for full run)
    sub_list = site_dir.glob('sub-*')
    sub_list = [i for i in sub_list if i.is_dir()]
    sub_list.sort()
    for sub_dir in sub_list:
        sub_dir = Path(sub_dir)
        sub = sub_dir.name
        print(f'Processing {site_name} / {sub}...')

        fs_sub_dir = fastsurfer_dir / sub
        # skip if the fastsurfer sub dir exists
        fs_sub_touch_dir = fs_sub_dir / 'touch'
        if fs_sub_touch_dir.exists() and not overwrite_existing:
            print(f"  --> existing {site_name} / {sub} fastsurfer sub dir found, skipping")
            continue
        fs_sub_dir.mkdir(parents=True, exist_ok=True)

        # remove file with 'space-NMT2Sym' in file name
        anat_file = list(sub_dir.glob('**/anat/*_desc-preproc_T1w.nii.gz'))
        anat_file = [f for f in anat_file if 'space-NMT2Sym' not in str(f)]

        if len(anat_file) == 0:
            print(f"Skipping {sub} because files not found")
            continue
        if len(anat_file) > 1:
            print(f"Skipping {sub} because multiple files found")
            continue
        anat_file = anat_file[0]

        # 1. cp the mri dir from the _todelete dir to the fastsurfer dir
        bak_fs_sub_dir = fs_sub_dir.parent / f'{sub}_todelete'
        if not bak_fs_sub_dir.exists():
            raise ValueError(f"backup {bak_fs_sub_dir} not found")
        mri_dest = fs_sub_dir / 'mri'
        if mri_dest.exists():
            shutil.rmtree(mri_dest)
        shutil.copytree(bak_fs_sub_dir / 'mri', mri_dest)

        # 2. run the surface reconstruction (surface-only: mri/ already has orig, aparc+aseg)
        try:
            threads = config.get("processing", {}).get("threads", 8)
            atlas_name = config.get("anat", {}).get("skullstripping_segmentation", {}).get("atlas_name", "ARM2")
            recon_config = ReconSurfConfig.with_defaults(
                subject_id=sub,
                subjects_dir=str(fastsurfer_dir),
                atlas={"name": atlas_name},
                processing={"threads": threads, "skip_cc": True, "skip_talairach": True},
                verbose=1,
            )
            pipeline = ReconSurfPipeline(recon_config)
            pipeline.run()
            print()

        except Exception as e:
            print(f"Error for {site_name} / {sub}: {e}")
            # stop there, don't continue
            raise e

        # 3. generate the qc images (QC_SURF_RECON_TISSUE_SEG and QC_CORTICAL_SURF_AND_MEASURES)
        (sub_dir / "figures").mkdir(parents=True, exist_ok=True)
        try:
            qc_surf_recon_tissue_seg(
                fs_subject_dir=fs_sub_dir,
                output_path=sub_dir / 'figures' / f'{str(anat_file.name).replace("_desc-preproc_T1w.nii.gz", "_desc-surfReconTissueSeg_T1w.png")}',
                modality='anat',
                config=config
            )
        except Exception as e:
            print(f"Error for {site_name} / {sub}: {e}")
            continue
        try:
            qc_cortical_surf_and_measures(
                fs_subject_dir=fs_sub_dir,
                output_path=sub_dir / 'figures' / f'{str(anat_file.name).replace("_desc-preproc_T1w.nii.gz", "_desc-corticalSurfAndMeasures_T1w.png")}',
                modality='anat',
                config=config
            )
            # remove the temp volsurf_work directory if present
            volsurf_work = sub_dir / 'figures' / 'volsurf_work'
            if volsurf_work.exists():
                shutil.rmtree(volsurf_work)
        except Exception as e:
            print(f"Error for {site_name} / {sub}: {e}")
            continue
        
# %%
