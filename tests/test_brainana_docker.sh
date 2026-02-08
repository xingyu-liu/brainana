bids_dir=/mnt/DataDrive3/xliu/prep_test/brainana_test/dataset_easy_downsampled_multianat
output_dir=/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/dataset_easy_downsampled_multianat_docker
config_file=/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/config_easy_generated.yaml

fs_license=/mnt/DataDrive3/xliu/prep_test/freesurfer_license.txt

docker run --rm -t --gpus all \
    -v "$bids_dir":/input \
    -v "$output_dir":/output \
    -v "$config_file":/config.yaml \
    -v "$fs_license":/fs_license.txt \
    brainana:latest \
    /input /output/preprocessed \
    -w /output/preprocessed_wd \
    --config /config.yaml \
    --freesurfer-license /fs_license.txt
