bids_dir=/mnt/DataDrive3/xliu/prep_test/brainana_test/dataset_easy_downsampled_multianat
output_dir=/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc
config_file=/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/config_easy.yaml

fs_license=/mnt/DataDrive3/xliu/prep_test/freesurfer_license.txt

# # Create output dir as current user so the container can write to it.
# # The entrypoint auto-detects the owner of /output and runs as that user.
# mkdir -p "$output_dir"

docker run --rm --gpus all \
    -v "$bids_dir":/input \
    -v "$output_dir":/output \
    -v "$config_file":/config.yaml \
    -v "$fs_license":/fs_license.txt \
    brainana:latest \
    /input /output/dataset_easy_downsampled_multianat_docker \
    --config /config.yaml \
    --freesurfer-license /fs_license.txt
