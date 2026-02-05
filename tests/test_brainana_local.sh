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
BIDS_DIR=/mnt/DataDrive3/xliu/prep_test/brainana_test/dataset_easy_downsampled_multianat
OUTPUT_DIR=/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/dataset_easy_downsampled_multianat_v4
# BIDS_DIR="/mnt/DataDrive3/xliu/prep_test/brainana_test/dataset_easy_downsampled"
# OUTPUT_DIR="/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/dataset_easy_downsampled_v6"
# BIDS_DIR="/mnt/DataDrive3/xliu/prep_test/brainana_test/dataset_2pass"
# OUTPUT_DIR="/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/dataset_2pass_nextflow"
# BIDS_DIR="/mnt/DataDrive3/xliu/prep_test/brainana_test/dataset_multiple"
# OUTPUT_DIR="/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/dataset_multiple_v5"
# BIDS_DIR="/mnt/DataDrive2/macaque/data_raw/macaque_mri/new_livingstone_test/bids_baby31"
# OUTPUT_DIR="/mnt/DataDrive2/macaque/data_raw/macaque_mri/new_livingstone_test/preproc/bids_baby31_nextflow"

# BIDS_DIR=/mnt/DataDrive3/xliu/prep_test/brainana_test/dataset_UNC_batch1
# OUTPUT_DIR=/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/dataset_UNC_batch1
# BIDS_DIR=/mnt/DataDrive2/macaque/data_raw/macaque_mri/MEBRAIN/bids
# OUTPUT_DIR=/mnt/DataDrive2/macaque/data_preproc/macaque_mri/MEBRAIN/
# BIDS_DIR=/mnt/DataDrive2/macaque/data_raw/macaque_mri/ElectrodeLocalization/bids
# OUTPUT_DIR=/mnt/DataDrive2/macaque/data_raw/macaque_mri/ElectrodeLocalization/bids_preproc
# BIDS_DIR=/mnt/DataDrive2/macaque/data_raw/macaque_mri/PRIME-DE/site-newcastle
# OUTPUT_DIR=/mnt/DataDrive2/macaque/data_preproc/macaque_mri/PRIME-DE_brainana/site-newcastle

CONFIG_FILE="/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/config_easy.yaml"
# CONFIG_FILE="/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/config_UNC.yaml"
# CONFIG_FILE="/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/config_MEBRAIN.yaml"
# CONFIG_FILE="/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/config_common.yaml"

WORKING_DIR=${OUTPUT_DIR}_wd

# Check if .ymal exists (user typo), use it if .yaml doesn't exist
if [ ! -f "$CONFIG_FILE" ] && [ -f "${CONFIG_FILE%.yaml}.ymal" ]; then
    CONFIG_FILE="${CONFIG_FILE%.yaml}.ymal"
    echo "Note: Using ${CONFIG_FILE} (found .ymal instead of .yaml)"
fi

# Validate paths
echo "============================================"
echo "Nextflow Pipeline Test (No Docker)"
echo "============================================"
echo "BIDS directory: $BIDS_DIR"
echo "Output directory: $OUTPUT_DIR"
echo "Working directory: $WORKING_DIR"
echo "Config file: $CONFIG_FILE"
echo "============================================"

# Check if BIDS directory exists
if [ ! -d "$BIDS_DIR" ]; then
    echo "Error: BIDS directory not found: $BIDS_DIR" >&2
    exit 1
fi

# Check if config file exists
if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: Config file not found: $CONFIG_FILE" >&2
    exit 1
fi

# Create output and working directories if they don't exist
mkdir -p "$OUTPUT_DIR"
mkdir -p "$WORKING_DIR"

# Change to project root
cd "$PROJECT_ROOT"

# Run Nextflow pipeline (--no-docker flag disables Docker)
echo ""
echo "Starting Nextflow pipeline..."
if [ -n "$RESUME_FLAG" ]; then
    echo "Resume enabled: $RESUME_FLAG"
    echo "Work directory: $WORKING_DIR"
    if [ -d "$WORKING_DIR" ] && [ "$(ls -A $WORKING_DIR 2>/dev/null)" ]; then
        echo "Work directory contains previous tasks (resume should work)"
    else
        echo "Work directory is empty (no previous run to resume)"
    fi
fi
echo ""

"$PROJECT_ROOT/run_brainana.sh" run main.nf \
    --no-docker \
    --bids_dir "$BIDS_DIR" \
    --output_dir "$OUTPUT_DIR" \
    --work_dir "$WORKING_DIR" \
    --config_file "$CONFIG_FILE" \
    $RESUME_FLAG

echo ""
echo "============================================"
echo "Pipeline completed successfully!"
echo "Output directory: $OUTPUT_DIR"
echo "============================================"

