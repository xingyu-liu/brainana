site=site-ion  
# site-ecnu
# site-ion 
# site-princeton
# site-ecnuChen  
# site-iscmj            
# site-mcgill       
# site-mountsinaiS

# site-ds003989, site-oxford, site-uwo, site-mountsinaiP, site-nin, site-nki
# site-ohsu, site-rochester, site-sbri, site-uminn, site-caltech, site-carmenlyon
# site-amu, site-ucdavis
# bad QC: site-rockefeller, site-neurospin

bids_dir=/mnt/DataDrive2/macaque/data_raw/macaque_mri/PRIME-DE/${site}
output_dir=/mnt/DataDrive2/macaque/data_preproc/macaque_mri/PRIME-DE_brainana/${site}

# bids_dir=/mnt/DataDrive3/xliu/prep_test/brainana_test/dataset_easy_downsampled
# output_dir=/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/dataset_easy_downsampled_docker_v1

fs_license=/mnt/DataDrive3/xliu/prep_test/freesurfer_license.txt

docker run --rm -t --gpus all \
    -v "$bids_dir":/input \
    -v "$output_dir":/output \
    -v "$fs_license":/fs_license.txt \
    brainana:latest \
    /input /output/preprocessed \
    -w /output/preprocessed_wd \
    --freesurfer-license /fs_license.txt

# # with config file
# config_f=/mnt/DataDrive2/macaque/data_preproc/macaque_mri/PRIME-DE_brainana/config_neurospin.yaml
# docker run --rm -t --gpus all \
#     -v "$bids_dir":/input \
#     -v "$output_dir":/output \
#     -v "$config_f":/config.yaml \
#     -v "$fs_license":/fs_license.txt \
#     brainana:latest \
#     /input /output/preprocessed \
#     -w /output/preprocessed_wd \
#     --config /config.yaml \
#     --freesurfer-license /fs_license.txt