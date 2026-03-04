#!/bin/bash
#
# brainana Docker entrypoint
#
# Starts as root and runs as root so GPU access works on any host.
# Output files may be root-owned; chown the output dir on the host if needed.
#
# Usage (production):
#   docker run --rm --gpus all \
#     -v <bids_dir>:/input \
#     -v <output_dir>:/output \
#     -v <license.txt>:/fs_license.txt \
#     liuxingyu987/brainana:latest
#
# With custom config:
#   docker run ... liuxingyu987/brainana:latest /input /output --config /path/to/config.yaml
#
# For interactive shell:
#   docker run -it ... liuxingyu987/brainana:latest bash
#

set -e

##############################################################################
# Runtime user setup
#
# If the user passed -u UID:GID we run as that user and fix HOME.
# Otherwise we run as root so GPU access works on any host (no gosu drop).
##############################################################################

setup_runtime_user() {
    local target_uid="$1"
    local target_gid="$2"

    if [ "$target_uid" = "0" ]; then
        return 0
    fi
    export HOME="/tmp/home"
    mkdir -p "$HOME" 2>/dev/null || true
    export NXF_TEMP=/tmp
}

if [ "$(id -u)" != "0" ]; then
    setup_runtime_user "$(id -u)" "$(id -g)"
fi
# When started as root we do not drop to /output owner; stay root for GPU.

##############################################################################
# From here on we run as root (or as the user if -u was passed)
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
    echo "Usage: docker run ... liuxingyu987/brainana:latest [input_dir] [output_dir]" >&2
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
import io
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
        raw = p.read_text()
        raw = raw.replace("\t", " " * 4)  # YAML disallows tabs
        return yaml.safe_load(io.StringIO(raw)) or {}
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

# GPU count (0 if nvidia-smi missing or no GPUs)
GPU_COUNT=0
if command -v nvidia-smi &>/dev/null && nvidia-smi --list-gpus &>/dev/null; then
    GPU_COUNT=$(nvidia-smi --list-gpus 2>/dev/null | wc -l)
fi

echo "============================================"
echo "brainana pipeline"
echo "  Input:   $INPUT_DIR"
echo "  Output:  $OUTPUT_DIR"
echo "  Config:  $CONFIG"
echo "  Work:    $NXF_HOME (resume: $([ "$RESUME_BY_DEFAULT" -eq 1 ] && echo on || echo off))"
echo "  User:    $(id -u):$(id -g)"
echo "  GPUs:    $GPU_COUNT"
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
