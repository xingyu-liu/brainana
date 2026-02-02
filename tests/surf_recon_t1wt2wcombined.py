# %%
import nibabel as nib
import numpy as np
import matplotlib.pyplot as plt

import sys
from pathlib import Path


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
dataset_dir = '/mnt/DataDrive2/macaque/data_preproc/macaque_mri/UNC-Wisconsin_brainana'
sub_ses_list = [['sub-004', 'ses-16months'], 
                ['sub-004', 'ses-20months'],
                ['sub-004', 'ses-24months'],
                ['sub-004', 'ses-28months'],
                ['sub-004', 'ses-32months'],
                ['sub-032', 'ses-02weeks'],
                ['sub-032', 'ses-03months'],
                ['sub-032', 'ses-06months'],
                ['sub-032', 'ses-09months'],
                ['sub-032', 'ses-12months']]

anat_type = 'T1w'  # 'T1w' or 'T1wT2wCombined'
working_dir = Path(dataset_dir) / f'fastsurfer_{anat_type}'
lut_file = Path(working_dir) / 'lut.tsv'
config_file = Path(dataset_dir) / 'nextflow_reports' / 'config.yaml'
config = load_config(config_file)

figure_dir = Path(working_dir) / 'figures'

# %%
# # generate the t1wt2wcombined image
# if anat_type == 'T1wT2wCombined':
#     for sub_ses in sub_ses_list:
#         sub, ses = sub_ses
#         sub_dir = Path(dataset_dir) / sub / ses / 'anat'
        
#         seg_file = sub_dir / f'{sub}_{ses}_desc-brain_atlasARM2.nii.gz'
#         mask_file = sub_dir / f'{sub}_{ses}_desc-brain_mask.nii.gz'
#         t1w_file = sub_dir / f'{sub}_{ses}_desc-preproc_T1w.nii.gz'
#         t2w_file = sub_dir / f'{sub}_{ses}_desc-preproc_T2w.nii.gz'

#         t1wt2wcombined_file = sub_dir / f'{sub}_{ses}_desc-preproc_T1wT2wCombined.nii.gz'
#         anat_t1wt2wcombined(
#             t1w_file=t1w_file,
#             t2w_file=t2w_file,
#             segmentation_file=seg_file,
#             segmentation_lut_file=lut_file,
#             output_file=t1wt2wcombined_file
#         )

# %%
# post preproc t1wt2wcombined, mask and seg to freesurfer recon_all input
for sub_ses in sub_ses_list:
    sub, ses = sub_ses
    sub_dir = Path(dataset_dir) / sub / ses / 'anat'
    
    seg_file = sub_dir / f'{sub}_{ses}_desc-brain_atlasARM2.nii.gz'
    mask_file = sub_dir / f'{sub}_{ses}_desc-brain_mask.nii.gz'
    anat_file = sub_dir / f'{sub}_{ses}_desc-preproc_{anat_type}.nii.gz'
    try:
        print(f"Processing {sub_ses}")
        anat_surface_reconstruction(
            input=StepInput(
                input_file=anat_file,
                working_dir=working_dir,
                config=config,
                metadata={
                    'subject_id': sub,
                    'session_id': ses,
                    'session_count': 5
                }
            ),
            t1w_file=anat_file,
            segmentation_file=seg_file,
            brain_mask=mask_file
        )
    except Exception as e:
        print(f"Error for {sub_ses}: {e}")
        continue

# %%
# generate the qc images (QC_SURF_RECON_TISSUE_SEG and QC_CORTICAL_SURF_AND_MEASURES)
for sub_ses in sub_ses_list:
    sub, ses = sub_ses
    fs_subject_dir = Path(working_dir) / 'fastsurfer' / f'{sub}_{ses}'
    try:
        qc_surf_recon_tissue_seg(
            fs_subject_dir=fs_subject_dir,
            output_path=figure_dir / f'{sub}_{ses}_desc-surfReconTissueSeg_T1w.png',
            modality='anat',
            config=config
        )
    except Exception as e:
        print(f"Error for {sub_ses}: {e}")
        continue
    try:
        qc_cortical_surf_and_measures(
            fs_subject_dir=fs_subject_dir,
            output_path=figure_dir / f'{sub}_{ses}_desc-corticalSurfAndMeasures_T1w.png',
            modality='anat',
            config=config
        )
    except Exception as e:
        print(f"Error for {sub_ses}: {e}")
        continue
    
# %%
