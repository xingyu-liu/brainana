#!/bin/bash

# Set paths
root_dir=/mnt/DataDrive3/xliu/monkey_training_groundtruth/FastSurferCNN_training
fastsurfer_dir=/home/star/github/banana

# Input options (uncomment one):
    # --t1 ${root_dir}/training_data/T1w_images/site-uwmadison_sub-1003_T1w.nii.gz \
    # --output_dir ${root_dir}/test_prediction_output/test_monkey_001 \
    # --t1 ${root_dir}/training_data/T1w_images/site-UNCWisconsin_sub-001_ses-28months_T1w.nii.gz \
    # --output_dir ${root_dir}/test_prediction_output/test_monkey_002 \
    # --t1 /home/star/github/atlas/macaque/NMT2Sym/volume/tpl-NMT2Sym_res-05_T1w.nii.gz \
    # --output_dir ${root_dir}/test_prediction_output/NMT2Sym
    # --t1 ${root_dir}/training_data/T1w_images/site-ucdavis_sub-032130_ses-001_run-1_T1w.nii.gz \
    # --output_dir ${root_dir}/test_prediction_output/test_monkey_unseen \
    # --plane_weight_coronal 0.4 --plane_weight_axial 0.4 --plane_weight_sagittal 0.2 \

    # --t1 ${root_dir}/test_prediction_output/test_2pass_seg.nii.gz \
    # --output_dir ${root_dir}/test_prediction_output/test_2pass_seg \
    # --plane_weight_coronal 0 --plane_weight_axial 1 --plane_weight_sagittal 0 \

cd ${fastsurfer_dir} && export PYTHONPATH=${fastsurfer_dir}:$PYTHONPATH && \
python3 FastSurferCNN/inference/freesurfer_subfolder_prepare.py \
    --t1 ${root_dir}/training_data/T1w_images/site-UNCWisconsin_sub-001_ses-28months_T1w.nii.gz \
    --output_dir ${root_dir}/test_prediction_output/test_monkey_002_freesurfer \
    --plane_weight_coronal 0.4 --plane_weight_axial 0.4 --plane_weight_sagittal 0.2 \
    --ckpt_cor ${fastsurfer_dir}/FastSurferCNN/pretrained_model/T1w_seg-ARM2_coronal.pkl \
    --ckpt_ax ${fastsurfer_dir}/FastSurferCNN/pretrained_model/T1w_seg-ARM2_axial.pkl \
    --ckpt_sag ${fastsurfer_dir}/FastSurferCNN/pretrained_model/T1w_seg-ARM2_sagittal.pkl \
    --viewagg_device cuda \
    --batch_size 8 \
    --fixv1





