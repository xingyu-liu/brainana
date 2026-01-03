#!/bin/bash
#
# Wrapper script for Nextflow that keeps project directory clean
# Runs Nextflow from a temporary directory to prevent .nextflow/ creation in project
#

# Set Nextflow home directory (for global cache, history, etc.)
export NXF_HOME="${NXF_HOME:-$HOME/.nextflow}"

# Set log file location (outside project)
export NXF_LOG="${NXF_LOG:-$HOME/.nextflow/logs/nextflow.log}"

# Create directories if they don't exist
mkdir -p "$(dirname "$NXF_LOG")"
mkdir -p "$NXF_HOME"

# Get the directory where this script is located (project root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Find Nextflow executable
if [ -f "$SCRIPT_DIR/nextflow" ] && [ -x "$SCRIPT_DIR/nextflow" ]; then
    NEXTFLOW="$SCRIPT_DIR/nextflow"
elif command -v nextflow &> /dev/null; then
    NEXTFLOW="nextflow"
else
    echo "Error: Nextflow not found" >&2
    exit 1
fi

# Note: Nextflow creates .nextflow/ in the directory containing the workflow file
# Since we reference main.nf in the project, .nextflow/ will be created there
# However, it's gitignored and we redirect logs and work directory elsewhere
# To completely avoid .nextflow/ in project, you'd need to run from a different location
# and copy all workflow files, which breaks relative paths. This is a reasonable compromise.

# Change to project directory (required for relative paths in workflow)
cd "$SCRIPT_DIR"

# Build the command
# Always use -log to redirect log files and -C to specify config
CMD_ARGS=(-log "$NXF_LOG" -C "$SCRIPT_DIR/nextflow.config")

# Function to extract parameter value from arguments
# Handles both --param=value and --param value formats
extract_param() {
    local param_name="$1"
    local args=("${@:2}")
    local i=0
    while [ $i -lt ${#args[@]} ]; do
        local arg="${args[$i]}"
        # Check for --param=value format
        if [[ "$arg" == --${param_name}=* ]]; then
            echo "${arg#*=}"
            return 0
        fi
        # Check for --param value format
        if [[ "$arg" == --${param_name} ]]; then
            # Check if next argument exists (not empty and not another flag)
            if [ $((i + 1)) -lt ${#args[@]} ] && [[ "${args[$((i + 1))]}" != -* ]]; then
                echo "${args[$((i + 1))]}"
                return 0
            fi
        fi
        ((i++))
    done
    return 1  # Not found
}

# Function to check if --config_file is provided in arguments
check_config_file() {
    extract_param "config_file" "$@" > /dev/null
}

# Function to run BIDS discovery before Nextflow
run_bids_discovery() {
    local args=("$@")
    
    # Extract required parameters
    local bids_dir=$(extract_param "bids_dir" "${args[@]}")
    local output_dir=$(extract_param "output_dir" "${args[@]}")
    local config_file=$(extract_param "config_file" "${args[@]}")
    
    # Check if all required parameters are present
    if [ -z "$bids_dir" ] || [ -z "$output_dir" ] || [ -z "$config_file" ]; then
        return 0  # Skip discovery if params not available (Nextflow will error later)
    fi
    
    # Extract optional parameters
    local skip_validation=""
    if echo "${args[@]}" | grep -q -- "--skip_bids_validation"; then
        skip_validation="--skip_bids_validation"
    fi
    
    local subjects=$(extract_param "subjects" "${args[@]}")
    local sessions=$(extract_param "sessions" "${args[@]}")
    local tasks=$(extract_param "tasks" "${args[@]}")
    local runs=$(extract_param "runs" "${args[@]}")
    
    # Build discovery command
    local discovery_script="$SCRIPT_DIR/macacaMRIprep/scripts/discover_bids_for_nextflow.py"
    
    if [ ! -f "$discovery_script" ]; then
        echo "Warning: Discovery script not found: $discovery_script" >&2
        return 1
    fi
    
    echo "============================================"
    echo "Running BIDS Discovery"
    echo "============================================"
    
    # Build command
    local cmd=("python3" "$discovery_script")
    cmd+=("--bids_dir" "$bids_dir")
    cmd+=("--output_dir" "$output_dir")
    cmd+=("--config_file" "$config_file")
    
    [ -n "$skip_validation" ] && cmd+=("$skip_validation")
    [ -n "$subjects" ] && cmd+=("--subjects" "$subjects")
    [ -n "$sessions" ] && cmd+=("--sessions" "$sessions")
    [ -n "$tasks" ] && cmd+=("--tasks" "$tasks")
    [ -n "$runs" ] && cmd+=("--runs" "$runs")
    
    # Run discovery
    if ! "${cmd[@]}"; then
        echo "ERROR: BIDS discovery failed" >&2
        exit 1
    fi
    
    echo "============================================"
    echo ""
}

# Handle different Nextflow commands
if [ $# -eq 0 ]; then
    # No arguments - show help
    exec "$NEXTFLOW" "${CMD_ARGS[@]}" "$@"
elif [ "$1" = "run" ]; then
    # Determine workflow file and remaining arguments
    workflow_file=""
    remaining_args=()
    
    if [ $# -gt 1 ] && [ -f "$2" ]; then
        # User provided a workflow file (might be relative or absolute)
        workflow_file="$2"
        remaining_args=("${@:3}")
    elif [ $# -gt 1 ] && [[ "$2" == *.nf ]]; then
        # User provided a workflow file name (relative to project)
        workflow_file="$2"
        remaining_args=("${@:3}")
    else
        # No workflow file specified, use project's main.nf
        workflow_file="main.nf"
        remaining_args=("${@:2}")
    fi
    
    # Filter out --no-docker flag and set environment variable if present
    filtered_args=()
    for arg in "${remaining_args[@]}"; do
        if [[ "$arg" == --no-docker ]]; then
            # Set environment variable to disable Docker
            export NXF_NO_DOCKER=1
            # Skip this argument
        else
            # Keep this argument
            filtered_args+=("$arg")
        fi
    done
    remaining_args=("${filtered_args[@]}")
    
    # Check if --config_file is provided (required for main.nf)
    if [[ "$workflow_file" == "main.nf" ]] || [[ "$workflow_file" == */main.nf ]]; then
        if ! check_config_file "${remaining_args[@]}"; then
            echo "Error: --config_file is required when running main.nf" >&2
            echo "" >&2
            echo "Usage: $0 run main.nf --config_file /path/to/config.yaml [other options...]" >&2
            echo "" >&2
            echo "Example:" >&2
            echo "  $0 run main.nf --config_file /path/to/config.yaml --bids_dir /data --output_dir /output --output_space \"NMT2Sym:res-1\"" >&2
            exit 1
        fi
        
        # Run BIDS discovery before Nextflow
        run_bids_discovery "${remaining_args[@]}"
    fi
    
    # Execute Nextflow
    exec "$NEXTFLOW" "${CMD_ARGS[@]}" run "$workflow_file" "${remaining_args[@]}"
else
    # Other Nextflow commands (info, clean, etc.) - pass through as-is
    # But still run from RUN_DIR to keep project clean
    exec "$NEXTFLOW" "${CMD_ARGS[@]}" "$@"
fi


