fs_license=/mnt/DataDrive3/xliu/prep_test/freesurfer_license.txt

bids_dir=/mnt/DataDrive3/swap/test_brainana/raw/PET_yale_cropped
output_dir=/mnt/DataDrive3/swap/test_brainana/preproc/PET_yale_cropped_v2
config_f=/mnt/DataDrive3/swap/test_brainana/config_pet.yaml

docker run --rm -t --gpus all \
    -v "$bids_dir":/input \
    -v "$output_dir":/output \
    -v "$config_f":/config.yaml \
    -v "$fs_license":/fs_license.txt \
    brainana:latest \
    /input /output/preprocessed \
    -w /output/preprocessed_wd \
    --config /config.yaml \
    --freesurfer-license /fs_license.txt