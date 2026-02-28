#!/bin/bash
#
# Test script for Nextflow pipeline
# Runs without Docker for local development testing
#
# Usage:
#   bash tests/test_nextflow.sh           # Resume from previous run (default)
#   bash tests/test_nextflow.sh --no-resume  # Start fresh, reprocess all steps
#

set -e  # Exit on error

# Resume is enabled by default
# Use --no-resume to start fresh
RESUME_FLAG="-resume"
if [ "$1" == "--no-resume" ] || [ "$1" == "-no-resume" ]; then
    RESUME_FLAG=""
    echo "Starting fresh: Will reprocess all steps (resume disabled)"
else
    echo "Resume mode: Will continue from previous run (use --no-resume to start fresh)"
fi

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Test parameters
# bids_dir=/mnt/DataDrive2/macaque/data_raw/macaque_mri/princeton_2025/bids_wrong_orient
# output_dir=/mnt/DataDrive2/macaque/data_preproc/macaque_mri/PRIME-DE_brainana/site-princetonWu
# bids_dir=/mnt/DataDrive3/xliu/prep_test/brainana_test/dataset_easy
# output_dir=/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/dataset_easy_v2
bids_dir=/mnt/DataDrive3/xliu/prep_test/brainana_test/dataset_easy_downsampled_multianat
output_dir=/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/dataset_easy_downsampled_multianat_v2
# bids_dir="/mnt/DataDrive3/xliu/prep_test/brainana_test/dataset_easy_downsampled"
# output_dir="/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/dataset_easy_downsampled_v6"
# bids_dir="/mnt/DataDrive3/xliu/prep_test/brainana_test/dataset_2pass"
# output_dir="/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/dataset_2pass_nextflow"
# bids_dir="/mnt/DataDrive3/xliu/prep_test/brainana_test/dataset_multiple"
# output_dir="/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/dataset_multiple_v5"
# bids_dir="/mnt/DataDrive2/macaque/data_raw/macaque_mri/new_livingstone_test/bids_baby31"
# output_dir="/mnt/DataDrive2/macaque/data_raw/macaque_mri/new_livingstone_test/preproc/bids_baby31_nextflow"

# bids_dir=/mnt/DataDrive3/xliu/prep_test/brainana_test/dataset_UNC_batch1
# output_dir=/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/dataset_UNC_batch1
# bids_dir=/mnt/DataDrive2/macaque/data_raw/macaque_mri/MEBRAIN/bids
# output_dir=/mnt/DataDrive2/macaque/data_preproc/macaque_mri/MEBRAIN/
# bids_dir=/mnt/DataDrive2/macaque/data_raw/macaque_mri/ElectrodeLocalization/bids
# output_dir=/mnt/DataDrive2/macaque/data_raw/macaque_mri/ElectrodeLocalization/bids_preproc
# bids_dir=/mnt/DataDrive2/macaque/data_raw/macaque_mri/PRIME-DE/site-newcastle
# output_dir=/mnt/DataDrive2/macaque/data_preproc/macaque_mri/PRIME-DE_brainana/site-newcastle

# config_f=/mnt/DataDrive2/macaque/data_raw/macaque_mri/princeton_2025/preproc/config.yaml
# config_f="/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/config_res-1.yaml"
# config_f="/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/config_easy.yaml"
# config_f="/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/config_UNC.yaml"
# config_f="/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/config_MEBRAIN.yaml"
# config_f="/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/config_common.yaml"
config_f=/home/star/github/brainana/src/nhp_mri_prep/config/defaults.yaml

working_dir=${output_dir}_wd

# Check if .ymal exists (user typo), use it if .yaml doesn't exist
if [ ! -f "$config_f" ] && [ -f "${config_f%.yaml}.ymal" ]; then
    config_f="${config_f%.yaml}.ymal"
    echo "Note: Using ${config_f} (found .ymal instead of .yaml)"
fi

# Validate paths
echo "============================================"
echo "Nextflow Pipeline Test (No Docker)"
echo "============================================"
echo "BIDS directory: $bids_dir"
echo "Output directory: $output_dir"
echo "Working directory: $working_dir"
echo "Config file: $config_f"
echo "============================================"

# Check if BIDS directory exists
if [ ! -d "$bids_dir" ]; then
    echo "Error: BIDS directory not found: $bids_dir" >&2
    exit 1
fi

# Check if config file exists
if [ ! -f "$config_f" ]; then
    echo "Error: Config file not found: $config_f" >&2
    exit 1
fi

# Create output and working directories if they don't exist
mkdir -p "$output_dir"
mkdir -p "$working_dir"

# Change to project root
cd "$PROJECT_ROOT"

# Run Nextflow pipeline (--no-docker flag disables Docker)
echo ""
echo "Starting Nextflow pipeline..."
if [ -n "$RESUME_FLAG" ]; then
    echo "Resume enabled: $RESUME_FLAG"
    echo "Work directory: $working_dir"
    if [ -d "$working_dir" ] && [ "$(ls -A $working_dir 2>/dev/null)" ]; then
        echo "Work directory contains previous tasks (resume should work)"
    else
        echo "Work directory is empty (no previous run to resume)"
    fi
fi
echo ""

"$PROJECT_ROOT/run_brainana.sh" run main.nf \
    --no-docker \
    --bids_dir "$bids_dir" \
    --output_dir "$output_dir" \
    --work_dir "$working_dir" \
    --config_file "$config_f" \
    $RESUME_FLAG

echo ""
echo "============================================"
echo "Pipeline completed successfully!"
echo "Output directory: $output_dir"
echo "============================================"

