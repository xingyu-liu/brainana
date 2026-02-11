#!/bin/bash
#
# brainana Docker entrypoint
#
# Starts as root, detects the UID/GID of /output, and drops privileges
# to a matching user via gosu. This ensures output files are owned by
# the same user who owns the output directory on the host.
#
# Usage (production):
#   docker run --rm --gpus all \
#     -v <bids_dir>:/input \
#     -v <output_dir>:/output \
#     -v <license.txt>:/fs_license.txt \
#     xxxlab/brainana:latest
#
# With custom config:
#   docker run ... xxxlab/brainana:latest /input /output --config /path/to/config.yaml
#
# For interactive shell:
#   docker run -it ... xxxlab/brainana:latest bash
#

set -e

##############################################################################
# UID/GID detection and privilege drop
#
# Three scenarios:
#   1. User passed -u UID:GID  -> we're already that user, just fix HOME
#   2. Running as root (default) -> detect /output owner, drop via gosu
#   3. Running as root, /output is root-owned -> run as root (no drop)
##############################################################################

setup_runtime_user() {
    local target_uid="$1"
    local target_gid="$2"

    # If target is root, nothing to set up
    if [ "$target_uid" = "0" ]; then
        return 0
    fi

    # Ensure a writable HOME for the target user
    export HOME="/tmp/home"
    mkdir -p "$HOME" 2>/dev/null || true

    # Redirect Nextflow temp files to /tmp (not the read-only project dir)
    export NXF_TEMP=/tmp
}

# Check if we were started as non-root (user passed -u UID:GID)
if [ "$(id -u)" != "0" ]; then
    # Already running as the target user -- just fix HOME and proceed
    setup_runtime_user "$(id -u)" "$(id -g)"
else
    # Running as root (default). Detect UID/GID from the /output mount point
    # (always exists since Docker creates it), not from $2 which may be a subpath.
    if [ -d "/output" ]; then
        TARGET_UID=$(stat -c '%u' /output)
        TARGET_GID=$(stat -c '%g' /output)
    else
        # No /output mount; fall back to built-in neuro user (1000)
        TARGET_UID=1000
        TARGET_GID=1000
    fi

    if [ "$TARGET_UID" != "0" ]; then
        # Create a runtime group/user matching the target UID/GID if needed
        if ! getent group "$TARGET_GID" >/dev/null 2>&1; then
            groupadd -g "$TARGET_GID" runtimegrp 2>/dev/null || true
        fi
        if ! getent passwd "$TARGET_UID" >/dev/null 2>&1; then
            useradd -l -u "$TARGET_UID" -g "$TARGET_GID" -M -d /tmp/home -s /bin/bash runtimeusr 2>/dev/null || true
        fi

        setup_runtime_user "$TARGET_UID" "$TARGET_GID"
        # So the dropped user can write to NXF_HOME and work dirs
        chown -R "$TARGET_UID:$TARGET_GID" "$HOME" 2>/dev/null || true

        # Re-exec this script as the target user via gosu
        exec gosu "$TARGET_UID:$TARGET_GID" "$0" "$@"
    fi
    # If TARGET_UID is 0 (root-owned output), continue as root
fi

##############################################################################
# From here on we run as the target user (or root if output is root-owned)
##############################################################################

# FreeSurfer license: only set when --freesurfer-license is passed (see arg parsing below).

# FreeSurfer license validity probe (runs when surface recon enabled and --freesurfer-license given).
# This runs a lightweight mri_convert on a small built-in average file to trigger
# FreeSurfer's own license checks without touching user data.
freesurfer_license_probe() {
    # Only run if the core FreeSurfer average file exists (defensive against
    # unexpected install layouts or future image changes).
    local probe_input="${FREESURFER_HOME:-/usr/local/freesurfer}/average/pons.mni152.2mm.mgz"
    local probe_output="/tmp/brainana_fs_license_test.nii.gz"
    local probe_log="/tmp/brainana_fs_license_probe.log"

    if [ ! -f "$probe_input" ]; then
        # If the reference file is missing, don't block the pipeline here;
        # FreeSurfer will fail later in a more obvious way.
        return 0
    fi

    # Run a small conversion to trigger license validation. Capture all output
    # so we can surface FreeSurfer's own error message if the license is bad.
    if ! mri_convert "$probe_input" "$probe_output" >"$probe_log" 2>&1; then
        echo "ERROR: FreeSurfer license check failed for FS_LICENSE=$FS_LICENSE" >&2
        if [ -s "$probe_log" ]; then
            # Echo the underlying FreeSurfer error (e.g. license missing/invalid)
            cat "$probe_log" >&2
        fi
        rm -f "$probe_output" "$probe_log"
        exit 1
    fi

    rm -f "$probe_output" "$probe_log"
}

# We are inside the container - do NOT spawn nested Docker for Nextflow processes
export NXF_NO_DOCKER=1

# Use colored ANSI output (override with -e NXF_ANSI_LOG=false if piping to file)
export NXF_ANSI_LOG="${NXF_ANSI_LOG:-true}"

# Default executor resources (recommended: 8 CPUs, 20 GB) - override with -e NXF_MAX_CPUS / NXF_MAX_MEMORY
export NXF_MAX_CPUS="${NXF_MAX_CPUS:-8}"
export NXF_MAX_MEMORY="${NXF_MAX_MEMORY:-20g}"

# Default config (built-in defaults, no user config required)
DEFAULT_CONFIG="/opt/brainana/src/nhp_mri_prep/config/defaults.yaml"
PROJECT_ROOT="/opt/brainana"

# Resolve input/output paths first (needed for default work dir)
INPUT_DIR="${1:-/input}"
OUTPUT_DIR="${2:-/output}"

# Parse args from position 3: --config, -w/--work-dir, --no-resume; rest go to EXTRA_ARGS
# Work dir: -w PATH or --work-dir PATH. Default: ${OUTPUT_DIR}_wd (persists, visible for cleanup).
# Resume: on by default; use --no-resume to run from scratch.
CONFIG="$DEFAULT_CONFIG"
WORK_DIR=""   # empty = use default after OUTPUT_DIR is validated
RESUME_BY_DEFAULT=1
EXTRA_ARGS=()
FS_LICENSE_PATH=""
i=3
while [ $i -le $# ]; do
    arg="${!i}"
    if [[ "$arg" == --config=* ]]; then
        CONFIG="${arg#*=}"
    elif [[ "$arg" == --config ]]; then
        ((i++))
        [ $i -le $# ] && CONFIG="${!i}"
    elif [[ "$arg" == -w ]] || [[ "$arg" == --work-dir ]]; then
        ((i++))
        [ $i -le $# ] && WORK_DIR="${!i}"
    elif [[ "$arg" == --no-resume ]]; then
        RESUME_BY_DEFAULT=0
    elif [[ "$arg" == --freesurfer-license=* ]]; then
        FS_LICENSE_PATH="${arg#*=}"
        EXTRA_ARGS+=("$arg")
    elif [[ "$arg" == --freesurfer-license ]]; then
        EXTRA_ARGS+=("$arg")
        ((i++))
        [ $i -le $# ] && FS_LICENSE_PATH="${!i}" && EXTRA_ARGS+=("${!i}")
    else
        EXTRA_ARGS+=("$arg")
    fi
    ((i++))
done

# FS_LICENSE is only set when --freesurfer-license is passed; otherwise unset (no default).
if [ -n "$FS_LICENSE_PATH" ]; then
    export FS_LICENSE="$FS_LICENSE_PATH"
else
    unset FS_LICENSE
fi

# Allow interactive shell override
if [ $# -gt 0 ]; then
    case "$1" in
        bash|sh|-bash|-sh)
            exec "$@"
            exit 0
            ;;
    esac
fi

# Validate
if [ ! -d "$INPUT_DIR" ]; then
    echo "ERROR: Input directory not found: $INPUT_DIR" >&2
    echo "Usage: docker run ... xxxlab/brainana:latest [input_dir] [output_dir]" >&2
    echo "       Default: /input /output (must be mounted with -v)" >&2
    exit 1
fi

# Create output directory if it doesn't exist (like fmriprep does)
if [ ! -d "$OUTPUT_DIR" ]; then
    mkdir -p "$OUTPUT_DIR" || {
        echo "ERROR: Cannot create output directory: $OUTPUT_DIR" >&2
        echo "Check that the parent mount is writable." >&2
        exit 1
    }
fi
if ! [ -w "$OUTPUT_DIR" ]; then
    echo "ERROR: Output directory is not writable: $OUTPUT_DIR" >&2
    echo "This is unexpected (entrypoint should have matched your UID)." >&2
    echo "Try: mkdir -p \$output_dir  (on host, before docker run)" >&2
    exit 1
fi

# Nextflow work dir and resume: default <output_dir>_wd so it persists and is visible for cleanup
if [ -z "$WORK_DIR" ]; then
    WORK_DIR="${OUTPUT_DIR}_wd"
fi
export NXF_HOME="$WORK_DIR"
export NXF_WORK="${WORK_DIR}/work"
# run_brainana.sh CDs here so Nextflow's .nextflow/ (history + cache) persists for resume
export NXF_LAUNCH_DIR="$WORK_DIR"
mkdir -p "$NXF_HOME" "$NXF_WORK" 2>/dev/null || true
# Symlink pre-cached framework JAR so Nextflow doesn't re-download at runtime
if [ -d /opt/nextflow/framework ] && [ ! -e "$NXF_HOME/framework" ]; then
    ln -s /opt/nextflow/framework "$NXF_HOME/framework" 2>/dev/null || true
fi
if [ "$RESUME_BY_DEFAULT" -eq 1 ]; then
    EXTRA_ARGS+=("-resume")
fi

# Determine whether surface reconstruction is enabled in the config.
# We prefer the user config file, falling back to defaults.yaml if needed.
SURF_RECON_ENABLED="$(
python3 - "$CONFIG" "$DEFAULT_CONFIG" << 'PY'
import sys
from pathlib import Path

try:
    import yaml  # type: ignore
except Exception:
    # If PyYAML is somehow unavailable, be conservative: assume enabled.
    print("true")
    sys.exit(0)

user_cfg_path = Path(sys.argv[1])
default_cfg_path = Path(sys.argv[2])

def load_yaml(p: Path):
    if not p.is_file():
        return {}
    try:
        with p.open("r") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}

cfg = load_yaml(default_cfg_path)
user_cfg = load_yaml(user_cfg_path)

# Shallow-merge anat.surface_reconstruction.enabled if present in user config.
anat = cfg.get("anat") or {}
user_anat = user_cfg.get("anat") or {}
surf = anat.get("surface_reconstruction") or {}
user_surf = user_anat.get("surface_reconstruction") or {}

enabled = surf.get("enabled", True)
if "enabled" in user_surf:
    enabled = bool(user_surf["enabled"])

print("true" if enabled else "false")
PY
)"

# FreeSurfer license policy:
# - Surface reconstruction DISABLED -> no license handling.
# - Surface reconstruction ENABLED -> must pass --freesurfer-license; then check file exists and run probe.
if [ "$SURF_RECON_ENABLED" = "true" ]; then
    if [ -z "$FS_LICENSE_PATH" ]; then
        echo "ERROR: Surface reconstruction is enabled but --freesurfer-license was not provided." >&2
        echo "       Pass --freesurfer-license /path/to/license.txt (mount with -v /host/license.txt:/path/to/license.txt)" >&2
        exit 1
    fi
    if [ ! -f "$FS_LICENSE" ]; then
        echo "ERROR: Surface reconstruction is enabled but FreeSurfer license file was not found at $FS_LICENSE." >&2
        echo "       Ensure the license file is mounted and the path matches --freesurfer-license." >&2
        exit 1
    fi
    freesurfer_license_probe
fi

cd "$PROJECT_ROOT"

echo "============================================"
echo "brainana pipeline"
echo "  Input:   $INPUT_DIR"
echo "  Output:  $OUTPUT_DIR"
echo "  Config:  $CONFIG"
echo "  Work:    $NXF_HOME (resume: $([ "$RESUME_BY_DEFAULT" -eq 1 ] && echo on || echo off))"
echo "  User:    $(id -u):$(id -g)"
echo "============================================"

# Virtual display for headless QC snaps (wb_command -show-scene)
export DISPLAY="${DISPLAY:-:99}"
Xvfb "$DISPLAY" -screen 0 1024x768x24 -ac +extension GLX +render -noreset &
XVFB_PID=$!
sleep 1
if ! kill -0 "$XVFB_PID" 2>/dev/null; then
    echo "WARNING: Xvfb failed to start; QC snapshots may fail." >&2
fi

exec ./run_brainana.sh run main.nf \
    --bids_dir "$INPUT_DIR" \
    --output_dir "$OUTPUT_DIR" \
    --config_file "$CONFIG" \
    "${EXTRA_ARGS[@]}"
