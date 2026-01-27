# # anat
# model=/home/star/github/banana/NHPskullstripNN/pretrained_model/T1w_brainmask.pth
# input=/mnt/DataDrive3/xliu/prep_test/banana_test/preproc/test_BC/anat/input_rescaled_BC4mm.nii.gz

# func
model=/home/star/github/banana/NHPskullstripNN/pretrained_model/T1w_brainmask.pth
input=/mnt/DataDrive3/xliu/prep_test/banana_test/surf_recon/sub-032_ses-02weeks_reuse/mri/T1.nii.gz

python -m NHPskullstripNN.scripts.run_prediction \
    --model $model \
    --input $input \
    --output ${input/.nii.gz/_mask.nii.gz} \
    --device auto \
    --no-save-prob-map
