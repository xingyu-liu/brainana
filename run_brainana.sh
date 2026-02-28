#!/bin/bash
#
# Wrapper script for Nextflow
# In Docker: launches from NXF_LAUNCH_DIR (work dir) so .nextflow/ persists for resume.
# Locally:   launches from the project directory.
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

# Launch directory — where Nextflow creates .nextflow/ (history + cache for resume).
#   Docker: NXF_LAUNCH_DIR is set by entrypoint.sh (persistent work dir).
#   Local:  Derived from --work_dir or --work-dir arg if present, else SCRIPT_DIR.
if [ -z "$NXF_LAUNCH_DIR" ]; then
    _prev=""
    for _arg in "$@"; do
        if [ "$_prev" = "--work_dir" ] || [ "$_prev" = "--work-dir" ]; then
            NXF_LAUNCH_DIR="$_arg"
            break
        fi
        _prev="$_arg"
    done
fi
if [ -n "$NXF_LAUNCH_DIR" ]; then
    mkdir -p "$NXF_LAUNCH_DIR" 2>/dev/null || true
fi
cd "${NXF_LAUNCH_DIR:-$SCRIPT_DIR}"

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

# Default config when --config_file / --config not provided (same as Nextflow default)
DEFAULT_CONFIG="$SCRIPT_DIR/src/nhp_mri_prep/config/defaults.yaml"

# Function to run BIDS discovery before Nextflow
run_bids_discovery() {
    local args=("$@")
    
    # Extract required parameters (config_file has default)
    local bids_dir=$(extract_param "bids_dir" "${args[@]}")
    local output_dir=$(extract_param "output_dir" "${args[@]}")
    local config_file=$(extract_param "config_file" "${args[@]}")
    [ -z "$config_file" ] && config_file="$DEFAULT_CONFIG"
    
    # Check if required path parameters are present
    if [ -z "$bids_dir" ] || [ -z "$output_dir" ]; then
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
    local discovery_script="$SCRIPT_DIR/src/nhp_mri_prep/nextflow_scripts/discover_bids_for_nextflow.py"
    
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
    
    if [ $# -gt 1 ] && [ -f "$SCRIPT_DIR/$2" ]; then
        # Workflow file found relative to project dir
        workflow_file="$SCRIPT_DIR/$2"
        remaining_args=("${@:3}")
    elif [ $# -gt 1 ] && [ -f "$2" ]; then
        # Absolute path to workflow file
        workflow_file="$2"
        remaining_args=("${@:3}")
    elif [ $# -gt 1 ] && [[ "$2" == *.nf ]]; then
        # User specified a .nf file name — resolve relative to project
        workflow_file="$SCRIPT_DIR/$2"
        remaining_args=("${@:3}")
    else
        # No workflow file specified, use project's main.nf
        workflow_file="$SCRIPT_DIR/main.nf"
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
    
    # For main.nf: normalize config (--config and --config_file are aliases; default to DEFAULT_CONFIG) and work-dir (--work-dir → --work_dir)
    if [[ "$workflow_file" == "main.nf" ]] || [[ "$workflow_file" == */main.nf ]]; then
        effective_config=$(extract_param "config_file" "${remaining_args[@]}")
        [ -z "$effective_config" ] && effective_config=$(extract_param "config" "${remaining_args[@]}")
        [ -z "$effective_config" ] && effective_config="$DEFAULT_CONFIG"
        
        # Build normalized args: drop --config/--config_file and their values; map --work-dir → --work_dir; append --config_file
        normalized_args=()
        i=0
        while [ $i -lt ${#remaining_args[@]} ]; do
            arg="${remaining_args[$i]}"
            if [[ "$arg" == --config=* ]]; then
                ((i++))
                continue
            fi
            if [[ "$arg" == --config ]]; then
                ((i++))
                [ $i -lt ${#remaining_args[@]} ] && ((i++))
                continue
            fi
            if [[ "$arg" == --config_file=* ]]; then
                ((i++))
                continue
            fi
            if [[ "$arg" == --config_file ]]; then
                ((i++))
                [ $i -lt ${#remaining_args[@]} ] && ((i++))
                continue
            fi
            if [[ "$arg" == --work-dir ]]; then
                normalized_args+=("--work_dir")
                ((i++))
                [ $i -lt ${#remaining_args[@]} ] && normalized_args+=("${remaining_args[$i]}") && ((i++))
                continue
            fi
            if [[ "$arg" == --work-dir=* ]]; then
                normalized_args+=("--work_dir=${arg#--work-dir=}")
                ((i++))
                continue
            fi
            normalized_args+=("$arg")
            ((i++))
        done
        normalized_args+=("--config_file" "$effective_config")
        
        # Run BIDS discovery with normalized args (always has --config_file)
        run_bids_discovery "${normalized_args[@]}"
    fi
    
    # Use normalized_args for Nextflow if we built them (main.nf), else remaining_args
    if [ -n "${normalized_args+x}" ]; then
        exec "$NEXTFLOW" "${CMD_ARGS[@]}" run "$workflow_file" "${normalized_args[@]}"
    else
        exec "$NEXTFLOW" "${CMD_ARGS[@]}" run "$workflow_file" "${remaining_args[@]}"
    fi
else
    # Other Nextflow commands (info, clean, etc.) - pass through as-is
    # But still run from RUN_DIR to keep project clean
    exec "$NEXTFLOW" "${CMD_ARGS[@]}" "$@"
fi


