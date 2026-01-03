# [OUTDATED] This script uses the old CLI which no longer exists. Use Nextflow instead.
# See README_NEXTFLOW.md for current usage.
source ~/macacaMRIprep/bin/activate

dataset_dir=/mnt/DataDrive2/macaque/data_raw/macaque_mri/PRIME-DE
output_dir=/mnt/DataDrive2/macaque/data_preproc/macaque_mri/PRIME-DE_res-1
# output_dir=/mnt/DataDrive2/macaque/data_preproc/macaque_mri/PRIME-DE_anatonly_res-05
config_dir=${output_dir}/configs

# ------------------------------------------------------------
site=site-amu
pipeline=func2anat2template
python3 -m macacaMRIprep.cli.preproc \
    ${dataset_dir}/${site} \
    ${output_dir}/${site} \
    --pipeline ${pipeline} --config ${config_dir}/${pipeline}_${site}.json \
    --n-procs 3 \
    --participant-label 032213

dataset_dir=/mnt/DataDrive2/macaque/data_raw/macaque_mri/arcaro
output_dir=/mnt/DataDrive2/macaque/data_preproc/macaque_mri/arcaro_res-1
config_f=${output_dir}/config
pipeline=func2anat2template
python3 -m macacaMRIprep.cli.preproc \
    ${dataset_dir} \
    ${output_dir} \
    --pipeline ${pipeline} --config ${config_f}.json \
    --n-procs 3 \
    --participant-label baby4 baby5

site=site-bordeaux
pipeline=func2anat2template
python3 -m macacaMRIprep.cli.preproc \
    ${dataset_dir}/${site} \
    ${output_dir}/${site} \
    --pipeline ${pipeline} --config ${config_dir}/${pipeline}_${site}.json \
    --n-procs 3 \
    --participant-label m01

site=site-caltech
pipeline=func2template
python3 -m macacaMRIprep.cli.preproc \
    ${dataset_dir}/${site} \
    ${output_dir}/${site} \
    --pipeline ${pipeline} --config ${config_dir}/${pipeline}.json \
    --n-procs 3 \
    --participant-label 032183 --sessions 001 --runs 1

site=site-ds003989
pipeline=func2anat2template
python3 -m macacaMRIprep.cli.preproc \
    ${dataset_dir}/${site} \
    ${output_dir}/${site} \
    --pipeline ${pipeline} --config ${config_dir}/${pipeline}.json \
    --n-procs 3 \
    --participant-label 02 --sessions 03 --runs 401

site=site-ecnu
pipeline=func2anat2template
python3 -m macacaMRIprep.cli.preproc \
    ${dataset_dir}/${site} \
    ${output_dir}/${site} \
    --pipeline ${pipeline} --config ${config_dir}/${pipeline}.json \
    --n-procs 3 \
    --participant-label 032210 --sessions 001

site=site-ecnuChen
pipeline=func2anat2template
python3 -m macacaMRIprep.cli.preproc \
    ${dataset_dir}/${site} \
    ${output_dir}/${site} \
    --pipeline ${pipeline} --config ${config_dir}/${pipeline}.json \
    --n-procs 3 \
    --participant-label 032279 --sessions 001

site=site-ion
pipeline=func2anat2template
python3 -m macacaMRIprep.cli.preproc \
    ${dataset_dir}/${site} \
    ${output_dir}/${site} \
    --pipeline ${pipeline} --config ${config_dir}/${pipeline}.json \
    --n-procs 3 \
    --participant-label 032198 --sessions 001 --runs 1

site=site-iscmj
# pipeline=func2anat2template
pipeline=func2template
python3 -m macacaMRIprep.cli.preproc \
    ${dataset_dir}/${site} \
    ${output_dir}/${site} \
    --pipeline ${pipeline} --config ${config_dir}/${pipeline}_${site}.json \
    --n-procs 3 \
    --participant-label 032312 --sessions 001 --runs 1

site=site-lyon
pipeline=func2anat2template
python3 -m macacaMRIprep.cli.preproc \
    ${dataset_dir}/${site} \
    ${output_dir}/${site} \
    --pipeline ${pipeline} --config ${config_dir}/${pipeline}_${site}.json \
    --n-procs 3 \
    --participant-label 032277 032278

site=site-mcgill
pipeline=func2anat2template
python3 -m macacaMRIprep.cli.preproc \
    ${dataset_dir}/${site} \
    ${output_dir}/${site} \
    --pipeline ${pipeline} --config ${config_dir}/${pipeline}.json \
    --n-procs 3 \
    --participant-label 032207 --sessions 003

site=site-mountsinaiP
pipeline=func2anat2template
python3 -m macacaMRIprep.cli.preproc \
    ${dataset_dir}/${site} \
    ${output_dir}/${site} \
    --pipeline ${pipeline} --config ${config_dir}/${pipeline}.json \
    --n-procs 3 \
    --participant-label 032146 --sessions 001 --runs 1

site=site-mountsinaiS
pipeline=func2anat2template
python3 -m macacaMRIprep.cli.preproc \
    ${dataset_dir}/${site} \
    ${output_dir}/${site} \
    --pipeline ${pipeline} --config ${config_dir}/${pipeline}_${site}.json \
    --n-procs 3 \
    --participant-label 032155 --sessions 001

site=site-neurospin
pipeline=func2template
python3 -m macacaMRIprep.cli.preproc \
    ${dataset_dir}/${site} \
    ${output_dir}/${site} \
    --pipeline ${pipeline} --config ${config_dir}/${pipeline}.json \
    --n-procs 3 \
    --participant-label 032219 --sessions 001 --runs 1

site=site-newcastle
pipeline=func2anat2template
python3 -m macacaMRIprep.cli.preproc \
    ${dataset_dir}/${site} \
    ${output_dir}/${site} \
    --pipeline ${pipeline} --config ${config_dir}/${pipeline}.json \
    --n-procs 3 \
    --participant-label 032097 --sessions 002 --runs 1

site=site-nin
pipeline=func2anat2template
python3 -m macacaMRIprep.cli.preproc \
    ${dataset_dir}/${site} \
    ${output_dir}/${site} \
    --pipeline ${pipeline} --config ${config_dir}/${pipeline}_${site}.json \
    --n-procs 3 \
    --participant-label 032222 --sessions 001 --runs 1

site=site-nki
pipeline=func2anat2template
python3 -m macacaMRIprep.cli.preproc \
    ${dataset_dir}/${site} \
    ${output_dir}/${site} \
    --pipeline ${pipeline} --config ${config_dir}/${pipeline}_${site}.json \
    --n-procs 3 \
    --participant-label 032144 --sessions 002 --runs 1

site=site-ohsu
pipeline=func2anat2template
python3 -m macacaMRIprep.cli.preproc \
    ${dataset_dir}/${site} \
    ${output_dir}/${site} \
    --pipeline ${pipeline} --config ${config_dir}/${pipeline}_${site}.json \
    --n-procs 3 \
    --participant-label 032217 --sessions 002

site=site-princeton
pipeline=func2anat2template
python3 -m macacaMRIprep.cli.preproc \
    ${dataset_dir}/${site} \
    ${output_dir}/${site} \
    --pipeline ${pipeline} --config ${config_dir}/${pipeline}_${site}.json \
    --n-procs 3 \
    --participant-label 032144 --sessions 004 --runs 1

site=site-rochester
pipeline=func2anat2template
python3 -m macacaMRIprep.cli.preproc \
    ${dataset_dir}/${site} \
    ${output_dir}/${site} \
    --pipeline ${pipeline} --config ${config_dir}/${pipeline}.json \
    --n-procs 3 \
    --participant-label 1234570 --sessions 001

site=site-rockefeller
pipeline=func2anat2template
python3 -m macacaMRIprep.cli.preproc \
    ${dataset_dir}/${site} \
    ${output_dir}/${site} \
    --pipeline ${pipeline} --config ${config_dir}/${pipeline}_${site}.json \
    --n-procs 3 \
    --participant-label 032116 --sessions 001 --runs 1

site=site-sbri
pipeline=func2anat2template
python3 -m macacaMRIprep.cli.preproc \
    ${dataset_dir}/${site} \
    ${output_dir}/${site} \
    --pipeline ${pipeline} --config ${config_dir}/${pipeline}.json \
    --n-procs 3 \
    --participant-label 032309 --sessions 001 --runs 1

site=site-ucdavis
pipeline=func2anat2template
python3 -m macacaMRIprep.cli.preproc \
    ${dataset_dir}/${site} \
    ${output_dir}/${site} \
    --pipeline ${pipeline} --config ${config_dir}/${pipeline}_${site}.json \
    --n-procs 3 \
    --participant-label 032126 --sessions 001

site=site-uminn
pipeline=func2anat2template
python3 -m macacaMRIprep.cli.preproc \
    ${dataset_dir}/${site} \
    ${output_dir}/${site} \
    --pipeline ${pipeline} --config ${config_dir}/${pipeline}_${site}.json \
    --n-procs 3 \
    --participant-label 032122 --sessions 001 --runs 1

site=site-uwmadison
pipeline=func2anat2template
python3 -m macacaMRIprep.cli.preproc \
    ${dataset_dir}/${site} \
    ${output_dir}/${site} \
    --pipeline ${pipeline} --config ${config_dir}/${pipeline}_${site}.json \
    --n-procs 3 \
    --participant-label 1003

site=site-uwo
pipeline=func2anat2template
python3 -m macacaMRIprep.cli.preproc \
    ${dataset_dir}/${site} \
    ${output_dir}/${site} \
    --pipeline ${pipeline} --config ${config_dir}/${pipeline}.json \
    --n-procs 3 \
    --participant-label 032191 --sessions 001 --runs 1

site=ds003989
pipeline=func2anat2template
python3 -m macacaMRIprep.cli.preproc \
    ${dataset_dir}/${site} \
    ${output_dir}/${site} \
    --pipeline ${pipeline} --config ${config_dir}/${pipeline}.json \
    --n-procs 3 \
    --participant-label 01

# ------------------------------------------------------------
# cayo
# ------------------------------------------------------------
dataset_dir=/home/star/Downloads/cayo
output_dir=/home/star/Downloads/cayo_preproc
config_f=/home/star/Downloads/config_cayo.json

pipeline=func2anat2template
python3 -m macacaMRIprep.cli.preproc \
    ${dataset_dir} \
    ${output_dir} \
    --pipeline ${pipeline} --config ${config_f} \
    --n-procs 3 

# ------------------------------------------------------------
# unc
# ------------------------------------------------------------
dataset_dir=/mnt/DataDrive2/macaque/data_raw/macaque_mri/UNC-Wisconsine/bids
output_dir=/mnt/DataDrive2/macaque/data_preproc/macaque_mri/UNC-Wisconsine_res-05
config_f=${output_dir}/config.json

pipeline=func2anat2template
python3 -m macacaMRIprep.cli.preproc \
    ${dataset_dir} \
    ${output_dir} \
    --pipeline ${pipeline} --config ${config_f} \
    --n-procs 3 \
    --participant-label 001 --sessions 12months

# 2nd round
dataset_dir=/mnt/DataDrive2/macaque/data_raw/macaque_mri/UNC-Wisconsin/bids_skullstripped
output_dir=/mnt/DataDrive2/macaque/data_preproc/macaque_mri/UNC-Wisconsin_res-05_v2
config_f=${output_dir}/config.json

pipeline=func2anat2template
python3 -m macacaMRIprep.cli.preproc \
    ${dataset_dir} \
    ${output_dir} \
    --pipeline ${pipeline} --config ${config_f} \
    --n-procs 3 \
    --participant-label 001 --sessions 12months

# ================================================
# preproc pet
# ================================================
dataset_dir=/mnt/DataDrive2/macaque/data_raw/macaque_pet/dustin_SV2A/bids_skullstripped
output_dir=/mnt/DataDrive2/macaque/data_raw/macaque_pet/dustin_SV2A/preproc_test_skullstripped
config_f=${output_dir}/config.json

pipeline=func2anat2template
python3 -m macacaMRIprep.cli.preproc \
    ${dataset_dir} \
    ${output_dir} \
    --pipeline ${pipeline} --config ${config_f} \
    --n-procs 3

# pet
dataset_dir=/mnt/DataDrive2/macaque/data_raw/macaque_pet/dustin_SV2A/bids_skullstripped_pet
output_dir=/mnt/DataDrive2/macaque/data_raw/macaque_pet/dustin_SV2A/preproc_test_pet_bak
config_f=${output_dir}/config.json

pipeline=func2anat2template
python3 -m macacaMRIprep.cli.preproc \
    ${dataset_dir} \
    ${output_dir} \
    --pipeline ${pipeline} --config ${config_f} \
    --n-procs 3

# pet func2template
dataset_dir=/mnt/DataDrive2/macaque/data_raw/macaque_pet/dustin_SV2A/bids_correctorient_pet
output_dir=/mnt/DataDrive2/macaque/data_raw/macaque_pet/dustin_SV2A/preproc_test_pet_func2template_noss
config_f=${output_dir}/config.json

pipeline=func2template
python3 -m macacaMRIprep.cli.preproc \
    ${dataset_dir} \
    ${output_dir} \
    --pipeline ${pipeline} --config ${config_f} \
    --n-procs 3

# ================================================
# test princeton new 
# ================================================
dataset_root=/mnt/DataDrive2/macaque/data_raw/macaque_mri/princeton
dataset_dir=${dataset_root}/bids_wrong_orient
output_dir=${dataset_root}/preproc/preproc_freddie
config_f=${output_dir}/config.yaml

python3 -m macacaMRIprep.cli.preproc \
    ${dataset_dir} \
    ${output_dir} \
    --config ${config_f}

# ================================================
# test mebrain
# ================================================
dataset_dir=/mnt/DataDrive2/macaque/data_raw/macaque_mri/MEBRAIN/bids
output_dir=/mnt/DataDrive2/macaque/data_preproc/macaque_mri/MEBRAIN
config_f=${output_dir}/config.json

pipeline=func2anat2template
python3 -m macacaMRIprep.cli.preproc \
    ${dataset_dir} \
    ${output_dir} \
    --pipeline ${pipeline} --config ${config_f} \
    --n-procs 3

# ================================================
# test fastsurfercnn
# ================================================
dataset_root=/mnt/DataDrive3/xliu/prep_test/banana_test
config_f=${dataset_root}/preproc/config_linReg.yaml

# dataset_dir=${dataset_root}/dataset_2pass
# output_dir=${dataset_root}/preproc/dataset_2pass

dataset_dir=${dataset_root}/dataset_classic
output_dir=${dataset_root}/preproc/dataset_classic

pipeline=func2anat2template
python3 -m macacaMRIprep.cli.preproc ${dataset_dir} ${output_dir} \
    --config ${config_f} --n-procs 3

# ================================================
# test new livingstone
# ================================================
dataset_root=/mnt/DataDrive2/macaque/data_raw/macaque_mri/new_livingstone_test
dataset_name=bids_casper
version=v1

dataset_dir=${dataset_root}/${dataset_name}
output_dir=${dataset_root}/preproc/${dataset_name}_${version}
config_f=${dataset_root}/config_casper.yaml

python3 -m macacaMRIprep.cli.preproc ${dataset_dir} ${output_dir} \
    --config ${config_f}

# ================================================
# test banana
# ================================================
dataset_root=/mnt/DataDrive3/xliu/prep_test/banana_test
dataset_name=dataset_misorient
dataset_dir=${dataset_root}/${dataset_name}
output_dir=${dataset_root}/preproc/${dataset_name}_v5
# config_f=${dataset_root}/preproc/config.yaml
config_f=${dataset_root}/preproc/config_nosurfrecon.yaml

python3 -m macacaMRIprep.cli.preproc ${dataset_dir} ${output_dir} \
    --config ${config_f}
