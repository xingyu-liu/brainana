site=site-uwo
# site-mountsinaiP
# site-nki
# site-nin
# site-neurospin
# site-ohsu
# site-princeton
# site-rochester
# site-rockefeller
# site-sbri
# site-ucdavis
# site-uminn
# site-uwo

# site-ds003989, site-oxford

# bids_dir=/mnt/DataDrive2/macaque/data_raw/macaque_mri/PRIME-DE/${site}
# output_dir=/mnt/DataDrive2/macaque/data_preproc/macaque_mri/PRIME-DE_brainana/${site}

bids_dir=/mnt/DataDrive3/xliu/prep_test/brainana_test/dataset_easy
output_dir=/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/dataset_easy_docker_v1

fs_license=/mnt/DataDrive3/xliu/prep_test/freesurfer_license.txt

docker run --rm -t --gpus all \
    -v "$bids_dir":/input \
    -v "$output_dir":/output \
    -v "$fs_license":/fs_license.txt \
    brainana:latest \
    /input /output/preprocessed \
    -w /output/preprocessed_wd \
    --freesurfer-license /fs_license.txt
