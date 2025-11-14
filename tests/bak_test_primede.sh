source ~/macacaMRIprep/bin/activate

dataset_dir=/mnt/DataDrive2/macaque/data_raw/macaque_mri/PRIME-DE/func_tmean_version
output_dir=/mnt/DataDrive3/xliu/prep_test/PRIME-DE/results_tmean
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

site=site-arcaro
pipeline=func2anat2template
python3 -m macacaMRIprep.cli.preproc \
    ${dataset_dir}/${site} \
    ${output_dir}/${site} \
    --pipeline ${pipeline} --config ${config_dir}/${pipeline}_${site}.json \
    --n-procs 3 \
    --participant-label baby1

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
    ${output_dir}/${site}_test \
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
    --participant-label 032275 --sessions 001 --runs 1

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


