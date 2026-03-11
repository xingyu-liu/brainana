fs_license=/mnt/DataDrive3/xliu/prep_test/freesurfer_license.txt

dataset_root=/home/star/github/brainana/test_dataset
bids_dir=${dataset_root}/bids
output_dir=${dataset_root}/bids_preproc
work_dir=${output_dir}_wd
config_f=${dataset_root}/config.yaml

docker run --rm -t --gpus all \
    -v "$bids_dir":/input \
    -v "$output_dir":/output \
    -v "$work_dir":/output_wd \
    -v "$fs_license":/fs_license.txt \
    -v "$config_f":/config.yaml \
    brainana:latest /input /output \
    --work-dir /output_wd --freesurfer-license /fs_license.txt \
    --config /config.yaml
