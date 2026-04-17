#!/bin/bash

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
bids_dir=/mnt/DataDrive3/xliu/prep_test/brainana_test/dataset_easy_downsampled_multianat
output_dir=/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/dataset_easy_downsampled_multianat_v4
config_f="/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/config_res-1.yaml"

working_dir=${output_dir}_wd

# Validate paths
echo "============================================"
echo "Nextflow Pipeline Test (No Docker)"
echo "============================================"
echo "BIDS directory: $bids_dir"
echo "Output directory: $output_dir"
echo "Working directory: $working_dir"
if [ -n "$config_f" ]; then
    echo "Config file: $config_f"
else
    echo "Config file: default (not overridden)"
fi
echo "============================================"

# Check if BIDS directory exists
if [ ! -d "$bids_dir" ]; then
    echo "Error: BIDS directory not found: $bids_dir" >&2
    exit 1
fi

# Check config file if explicitly provided
if [ -n "$config_f" ] && [ ! -f "$config_f" ]; then
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

if [ -n "$config_f" ]; then
    "$PROJECT_ROOT/run_brainana.sh" run main.nf \
        --no-docker \
        --bids_dir "$bids_dir" \
        --output_dir "$output_dir" \
        --work_dir "$working_dir" \
        --config_file "$config_f" \
        $RESUME_FLAG
else
    "$PROJECT_ROOT/run_brainana.sh" run main.nf \
        --no-docker \
        --bids_dir "$bids_dir" \
        --output_dir "$output_dir" \
        --work_dir "$working_dir" \
        $RESUME_FLAG
fi

echo ""
echo "============================================"
echo "Pipeline completed successfully!"
echo "Output directory: $output_dir"
echo "============================================"

