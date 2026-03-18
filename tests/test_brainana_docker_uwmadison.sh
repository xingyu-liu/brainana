fs_license=/mnt/DataDrive3/xliu/prep_test/freesurfer_license.txt

site=site-uwmadison
bids_dir=/mnt/DataDrive2/macaque/data_raw/macaque_mri/PRIME-DE/${site}
output_dir=/mnt/DataDrive2/macaque/data_preproc/macaque_mri/PRIME-DE_brainana/${site}
config_f=${output_dir}/config.yaml

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