fs_license=/mnt/DataDrive3/xliu/prep_test/freesurfer_license.txt

# # # 1. prime-de
# # site=site-amu      

# bids_dir=/mnt/DataDrive2/macaque/data_raw/macaque_mri/PRIME-DE/${site}
# output_dir=/mnt/DataDrive2/macaque/data_preproc/macaque_mri/PRIME-DE_brainana/${site}

# bids_dir=/mnt/DataDrive3/xliu/prep_test/brainana_test/dataset_easy_downsampled_multianat
# output_dir=/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/dataset_easy_downsampled_multianat_v4

bids_dir=/mnt/DataDrive2/macaque/data_raw/macaque_mri/new_livingstone_test/bids_func
output_dir=/mnt/DataDrive2/macaque/data_raw/macaque_mri/new_livingstone_test/preproc/bids_func

docker run --rm -t --gpus all \
    -v "$bids_dir":/input \
    -v "$output_dir":/output \
    -v "$fs_license":/fs_license.txt \
    brainana:latest \
    /input /output/preprocessed \
    -w /output/preprocessed_wd \
    --freesurfer-license /fs_license.txt
