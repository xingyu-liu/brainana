# %%
import nibabel as nib
import numpy as np
import matplotlib.pyplot as plt

import sys
from pathlib import Path
import shutil

# Add src/ to path for nhp_mri_prep, fastsurfer_nn imports (tests/ -> brainana -> src)
_src_dir = Path(__file__).resolve().parent.parent / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from nhp_mri_prep.steps.types import StepInput
# from nhp_mri_prep.steps.anatomical import anat_t1wt2wcombined
from nhp_mri_prep.steps.anatomical import anat_surface_reconstruction
from nhp_mri_prep.utils.nextflow import load_config
from nhp_mri_prep.steps.qc import qc_surf_recon_tissue_seg, qc_cortical_surf_and_measures

# %%
dataset_root = Path('/mnt/DataDrive2/macaque/data_preproc/macaque_mri/PRIME-DE_brainana')
overwrite_existing = False

lut_file = Path('/home/star/github/brainana/src/fastsurfer_nn/atlas/atlas-ARM2/ARM2_ColorLUT.tsv')

# %%
site_list = list(dataset_root.glob('site-*'))
site_list = [i for i in site_list if i.is_dir()]
site_list.sort()
print(site_list)

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
for site_dir in site_list:
    site_dir = Path(site_dir)
    site_name = site_dir.name
    print(f'Processing {site_name}...')

    # load the config file
    config_file = Path(site_dir) / 'nextflow_reports' / 'config.yaml'
    config = load_config(config_file)

    # create a working directory for the site
    fastsurfer_dir = site_dir / 'fastsurfer'
    if not fastsurfer_dir.exists():
        print(f"fastsurfer dir not found")
        continue

    # loop through all the subjects in the site
    sub_list = site_dir.glob('sub-*')
    sub_list = [i for i in sub_list if i.is_dir()]
    sub_list.sort()
    for sub_dir in sub_list:
        sub_dir = Path(sub_dir)
        sub = sub_dir.name
        print(f'Processing {site_name} / {sub}...')

        fs_sub_dir = fastsurfer_dir / sub
        # skip if the fastsurfer sub dir exists
        if fs_sub_dir.exists() and not overwrite_existing:
            print(f"  --> exising {site_name} / {sub} fastsurfer sub dir found, skipping")
            continue
        
        # get files for surface reconstruction
        seg_file = list(sub_dir.glob('**/anat/*_desc-brain_atlasARM2.nii.gz'))
        mask_file = list(sub_dir.glob('**/anat/*_desc-brain_mask.nii.gz'))
        mask_file = [f for f in mask_file if 'space-NMT2Sym' not in str(f)]
        # remove file with 'space-NMT2Sym' in file name
        anat_file = list(sub_dir.glob('**/anat/*_desc-preproc_T1w.nii.gz'))
        anat_file = [f for f in anat_file if 'space-NMT2Sym' not in str(f)]

        if len(seg_file) == 0 or len(mask_file) == 0 or len(anat_file) == 0:
            print(f"Skipping {sub} because files not found")
            continue
        if len(seg_file) > 1 or len(mask_file) > 1 or len(anat_file) > 1:
            print(f"Skipping {sub} because multiple files found")
            continue
        seg_file = seg_file[0]
        mask_file = mask_file[0]
        anat_file = anat_file[0]

        # 2. run the surface reconstruction
        try:
            print(f"Processing {site_name} / {sub}...")
            anat_surface_reconstruction(
                input=StepInput(
                    input_file=anat_file,
                    working_dir=fastsurfer_dir.parent,
                    config=config,
                    metadata={
                        'subject_id': sub,
                        'session_count': 1
                    }
                ),
                t1w_file=anat_file,
                segmentation_file=seg_file,
                brain_mask=mask_file
            )
        except Exception as e:
            print(f"Error for {site_name} / {sub}: {e}")
            continue
    
        # 3. generate the qc images (QC_SURF_RECON_TISSUE_SEG and QC_CORTICAL_SURF_AND_MEASURES)
        try:
            qc_surf_recon_tissue_seg(
                fs_subject_dir=fs_sub_dir,
                output_path=sub_dir / 'figures' / f'{str(anat_file.name).replace("desc-preproc_T1w.nii.gz", "_desc-surfReconTissueSeg_T1w.png")}',
                modality='anat',
                config=config
            )
        except Exception as e:
            print(f"Error for {site_name} / {sub}: {e}")
            continue
        try:
            qc_cortical_surf_and_measures(
                fs_subject_dir=fs_sub_dir,
                output_path=sub_dir / 'figures' / f'{str(anat_file.name).replace("desc-preproc_T1w.nii.gz", "_desc-corticalSurfAndMeasures_T1w.png")}',
                modality='anat',
                config=config
            )
            # remove the temp volsurf_work directory
            shutil.rmtree(sub_dir / 'figures' / 'volsurf_work')
        except Exception as e:
            print(f"Error for {site_name} / {sub}: {e}")
            continue
        