#!/bin/bash
#SBATCH --job-name=macacaMRIprep
#SBATCH --output=/mnt/DataDrive2/macaque/data_raw/macaque_mri/new_livingstone_test/preproc/macacaMRIprep_%j.out
#SBATCH --error=/mnt/DataDrive2/macaque/data_raw/macaque_mri/new_livingstone_test/preproc/macacaMRIprep_%j.err
#SBATCH --time=24:00:00
#SBATCH --mem=64G
#SBATCH --cpus-per-task=24
#SBATCH --gres=gpu:1
#SBATCH --partition=main  # main partition has GPUs (gpu:2 per node)

# ================================================
# test new livingstone
# ================================================

# Activate environment (adjust path as needed)
source ~/macacaMRIprep/bin/activate

# Set up paths
dataset_root=/mnt/DataDrive2/macaque/data_raw/macaque_mri/new_livingstone_test
dataset_name=bids_reorient_upright

dataset_dir=${dataset_root}/${dataset_name}
output_dir=${dataset_root}/preproc/${dataset_name}
config_f=${dataset_root}/config.yaml

python3 -m macacaMRIprep.cli.preproc ${dataset_dir} ${output_dir} \
    --config ${config_f}