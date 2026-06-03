fs_license=/mnt/DataDrive3/xliu/prep_test/freesurfer_license.txt

# # # 1. prime-de
# # site=site-amu      

# bids_dir=/mnt/DataDrive2/macaque/data_raw/macaque_mri/PRIME-DE/${site}
# output_dir=/mnt/DataDrive2/macaque/data_preproc/macaque_mri/PRIME-DE_brainana/${site}
version=1.1.0

bids_dir=/mnt/DataDrive3/xliu/prep_test/brainana_test/dataset_devtest
output_dir=/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/dataset_devtest_${version}
config_f=/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/config_res-1.yaml

# bids_dir=/mnt/DataDrive3/xliu/prep_test/brainana_test/dataset_example
# output_dir=/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/dataset_example_v2

# pet cropped
# bids_dir=/mnt/DataDrive3/xliu/prep_test/brainana_test/dataset_pet_cropped
# output_dir=/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/dataset_pet_cropped_noss_cpu
# config_f=/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/config_pet_noss_cpu.yaml

# run docker
docker run --rm -t --gpus all \
    -v "$bids_dir":/input \
    -v "$output_dir":/output \
    -v "$fs_license":/fs_license.txt \
    liuxingyu987/brainana:${version} \
    /input /output/preprocessed \
    -w /output/preprocessed_wd \
    --freesurfer-license /fs_license.txt

# # run docker
# docker run --rm -t --gpus all \
#     -v "$bids_dir":/input \
#     -v "$output_dir":/output \
#     -v "$fs_license":/fs_license.txt \
#     -v "$config_f":/config.yaml \
#     brainana:latest \
#     /input /output/preprocessed \
#     -w /output/preprocessed_wd \
#     --config /config.yaml \
#     --freesurfer-license /fs_license.txt