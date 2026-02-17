site=site-ohsu
# site-nki
# site-ohsu
# site-princeton
# site-rochester
# site-rockefeller
# site-sbri
# site-ucdavis
# site-uminn
# site-uwo

# site-ds003989, site-oxford, site-uwo, site-mountsinaiP, site-nin
# site-neurospin

# bids_dir=/mnt/DataDrive2/macaque/data_raw/macaque_mri/PRIME-DE/${site}
# output_dir=/mnt/DataDrive2/macaque/data_preproc/macaque_mri/PRIME-DE_brainana/${site}

bids_dir=/mnt/DataDrive3/xliu/prep_test/brainana_test/dataset_easy_downsampled
output_dir=/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/dataset_easy_downsampled_docker_cpu

fs_license=/mnt/DataDrive3/xliu/prep_test/freesurfer_license.txt

docker run --rm -t \
    -v "$bids_dir":/input \
    -v "$output_dir":/output \
    -v "$fs_license":/fs_license.txt \
    brainana:latest \
    /input /output/preprocessed \
    -w /output/preprocessed_wd \
    --freesurfer-license /fs_license.txt