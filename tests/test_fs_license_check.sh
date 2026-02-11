#!/usr/bin/env bash
set -euo pipefail

IMAGE="brainana:latest"
BIDS_DIR=/some/small/test_bids
OUT_DIR=/tmp/brainana_fs_test
CONFIG=/path/to/config_surf_on.yaml

mkdir -p "$OUT_DIR"

echo "=== Case 1: surf recon enabled, NO license ==="
if docker run --rm -t \
    -v "$BIDS_DIR":/input \
    -v "$OUT_DIR":/output \
    -v "$CONFIG":/config.yaml \
    "$IMAGE" \
    /input /output \
    --config /config.yaml \
    --freesurfer-license /fs_license.txt \
    2>err_no_license.log; then
  echo "Expected failure, but command succeeded" >&2
  exit 1
fi
grep -q "Surface reconstruction is enabled but FreeSurfer license file was not found" err_no_license.log

echo "=== Case 2: surf recon enabled, INVALID license ==="
if docker run --rm -t \
    -v "$BIDS_DIR":/input \
    -v "$OUT_DIR":/output \
    -v "$CONFIG":/config.yaml \
    -v "$INVALID_LICENSE":/fs_license.txt \
    "$IMAGE" \
    /input /output \
    --config /config.yaml \
    --freesurfer-license /fs_license.txt \
    2>err_invalid_license.log; then
  echo "Expected failure, but command succeeded" >&2
  exit 1
fi
# Check that our probe wrapper fired and FreeSurfer complained
grep -q "FreeSurfer license check failed for FS_LICENSE" err_invalid_license.log
grep -q -E "license file .* not found|Invalid FreeSurfer license key" err_invalid_license.log

echo "=== Case 3: surf recon enabled, VALID license ==="
docker run --rm -t \
    -v "$BIDS_DIR":/input \
    -v "$OUT_DIR":/output_valid \
    -v "$CONFIG":/config.yaml \
    -v "$VALID_LICENSE":/fs_license.txt \
    "$IMAGE" \
    /input /output_valid \
    --config /config.yaml \
    --freesurfer-license /fs_license.txt

echo "All FS license gate tests passed."