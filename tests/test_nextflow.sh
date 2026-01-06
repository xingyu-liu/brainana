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
BIDS_DIR="/mnt/DataDrive3/xliu/prep_test/banana_test/dataset_easy"
OUTPUT_DIR="/mnt/DataDrive3/xliu/prep_test/banana_test/preproc/dataset_easy_nextflow_v1"
# BIDS_DIR="/mnt/DataDrive3/xliu/prep_test/banana_test/dataset_2pass"
# OUTPUT_DIR="/mnt/DataDrive3/xliu/prep_test/banana_test/preproc/dataset_2pass_nextflow"
# BIDS_DIR="/mnt/DataDrive3/xliu/prep_test/banana_test/dataset_classic_plus_2pass"
# OUTPUT_DIR="/mnt/DataDrive3/xliu/prep_test/banana_test/preproc/dataset_classic_plus_2pass_nextflow"

CONFIG_FILE="/mnt/DataDrive3/xliu/prep_test/banana_test/preproc/config_2pass.yaml"
# CONFIG_FILE="/mnt/DataDrive3/xliu/prep_test/banana_test/preproc/config_nextflow.yaml"

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
echo ""

"$PROJECT_ROOT/run_nextflow.sh" run main.nf \
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

