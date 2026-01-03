#!/bin/bash

# T1w brainmask
# finetuned 
# input=/mnt/DataDrive3/xliu/monkey_training_groundtruth/training_output/test/T1w/site-ecnuChen_sub-032281_ses-001_run-1_T1w.nii.gz
input=/mnt/DataDrive3/xliu/monkey_training_groundtruth/training_output/test/T1w/site-nin_sub-032223_ses-008_T1w.nii.gz
# input=/mnt/DataDrive3/xliu/monkey_training_groundtruth/training_output/test/T1w/site-nin_sub-032223_ses-019_run-1_T1w.nii.gz
model=/mnt/DataDrive3/xliu/monkey_training_groundtruth/training_output/T1w_brainmask_finetune_v1/checkpoints/best_model.pth
python -m macacaMRINN.scripts.run_prediction \
    --model $model \
    --input $input \
    --output ${input/.nii.gz/_pred.nii.gz} \
    --input-label ${input/.nii.gz/_brainmask.nii.gz} \
    --device cuda:0 --compute-metrics --plot-QC

input=/mnt/DataDrive2/macaque/data_preproc/macaque_mri/UNC-Wisconsin_res-05/sub-005/ses-20months/anat/sub-005_ses-20months_desc-preproc_T1w.nii.gz
model=/mnt/DataDrive3/xliu/monkey_training_groundtruth/unet_models/orig/T1w_brainmask.pth
python -m macacaMRINN.scripts.run_prediction \
    --model $model \
    --input $input \
    --output ${input/.nii.gz/_pred.nii.gz} \
    --no-save-prob-map

# EPI brainmask
input=/mnt/DataDrive3/xliu/monkey_training_groundtruth/test_prediction/func_iscmj.nii.gz
# model=/mnt/DataDrive3/xliu/monkey_training_groundtruth/unet_models/orig/EPI_brainmask.pth
model=/mnt/DataDrive3/xliu/monkey_training_groundtruth/NHPskullstripNN_training/training_output/EPI_seg-brainmask_v1/checkpoints/best_model.pth
python -m NHPskullstripNN.scripts.run_prediction \
    --model $model \
    --input $input \
    --output ${input/.nii.gz/_oldCNNmask_v2.nii.gz} \
    --no-save-prob-map

# test t2w
input=/mnt/DataDrive2/macaque/data_preproc/macaque_mri/UNC-Wisconsin_res-05/sub-034/ses-02weeks/anat/sub-034_ses-02weeks_space-T1w_desc-preproc_T2w.nii.gz
# input=/mnt/DataDrive2/macaque/data_preproc/macaque_mri/UNC-Wisconsin_res-05/sub-034/ses-03months/anat/sub-034_ses-03months_space-T1w_desc-preproc_T2w.nii.gz
model=/home/star/github/macacaMRIprep/macacaMRINN/pretrained_model/T2w_brainmask.pth
python -m macacaMRINN.scripts.run_prediction \
    --model $model \
    --input $input \
    --output ${input/.nii.gz/_mask.nii.gz} \
    --no-save-prob-map

# test T1w_neonate
input=/mnt/DataDrive2/macaque/data_raw/macaque_pet/dustin_SV2A/preproc_test/sub-pc4437/anat/sub-pc4437_desc-preproc_T1w.nii.gz
model=/mnt/DataDrive3/xliu/monkey_training_groundtruth/training_output/T1w_neonate_brainmask_finetune_v1/checkpoints/best_model.pth
python -m macacaMRINN.scripts.run_prediction \
    --model $model \
    --input $input \
    --output ${input/.nii.gz/_pred.nii.gz} \
    --device cuda:0 --compute-metrics --plot-QC

# test pet
input=/mnt/DataDrive2/macaque/data_raw/macaque_pet/dustin_SV2A/bids/sub-pc4437/func/sub-pc4437_run-005_desc-petCropReorient_bold.nii.gz
model=/home/star/github/macacaMRIprep/macacaMRINN/pretrained_model/T2w_brainmask.pth
python -m macacaMRINN.scripts.run_prediction \
    --model $model \
    --input $input \
    --output ${input/.nii.gz/_mask.nii.gz} \
    --no-save-prob-map

# test marge neonate brainmask
model=/home/star/github/banana/NHPskullstripNN/pretrained_model/T1w_brainmask.pth
# input=/mnt/DataDrive2/macaque/data_raw/macaque_mri/new_livingstone_test/preproc/bids_reorient/sub-baby31/ses-240710/anat/sub-baby31_ses-240710_T1w.nii.gz
# input=/mnt/DataDrive3/xliu/monkey_training_groundtruth/test_prediction/test_freddie_mixed/input.nii.gz
# input=/mnt/DataDrive3/xliu/monkey_training_groundtruth/test_prediction/test_mebrain.nii.gz
input="/mnt/DataDrive2/macaque/data_raw/macaque_mri/new_livingstone_test/raw/casper25083_anat_probeHz.nii.gz"

python -m NHPskullstripNN.scripts.run_prediction \
    --model $model \
    --input $input \
    --output ${input/.nii.gz/_oldCNNmask_v2.nii.gz} \
    --no-save-prob-map