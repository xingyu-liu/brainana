bids_dir=/mnt/DataDrive2/macaque/data_raw/macaque_mri/monkey_for_faruk/raw
output_dir=/mnt/DataDrive2/macaque/data_raw/macaque_mri/monkey_for_faruk/preproc

fs_license=/mnt/DataDrive3/xliu/prep_test/freesurfer_license.txt

docker run --rm -t --gpus all \
    -v "$bids_dir":/input \
    -v "$output_dir":/output \
    -v "$fs_license":/fs_license.txt \
    brainana:latest \
    /input /output/preprocessed \
    -w /output/preprocessed_wd \
    --config /output/config_faruk.yaml \
    --freesurfer-license /fs_license.txt
