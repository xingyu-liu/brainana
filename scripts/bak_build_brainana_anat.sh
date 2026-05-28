#!/bin/bash
# Build brainana_anat.zip — NHP Anatomical Volume Processing
# Extracts models, templates, and atlases from the Brainana Docker image.
# Conform step uses antsAI (ships with ANTs/antspyx) — no FSL required.
# Run this script from whatever directory you want the zip created in.

set -e

# ════════════════════════════════════════════════════════════════
# USER SETTINGS
# ════════════════════════════════════════════════════════════════
BRAINANA_VERSION="1.0.0"
# ════════════════════════════════════════════════════════════════

DOCKER_IMAGE="liuxingyu987/brainana:${BRAINANA_VERSION}"
CONTAINER_NAME="brainana_extract"
OUTPUT_DIR="brainana_anat"

# ────────────────────────────────────────────────────────────────
echo "Pulling Docker image: ${DOCKER_IMAGE}..."
docker pull $DOCKER_IMAGE

# Clean up any previous run
docker rm -f $CONTAINER_NAME 2>/dev/null || true
rm -rf $OUTPUT_DIR brainana_anat.zip

echo "Creating container..."
docker create --name $CONTAINER_NAME $DOCKER_IMAGE

echo "Creating folder structure..."
mkdir -p $OUTPUT_DIR/src
mkdir -p $OUTPUT_DIR/templates
mkdir -p $OUTPUT_DIR/atlases

# ────────────────────────────────────────────────────────────────
# Source modules
# ────────────────────────────────────────────────────────────────
echo "Extracting source modules..."
docker cp $CONTAINER_NAME:opt/brainana/src/nhp_skullstrip_nn  $OUTPUT_DIR/src/nhp_skullstrip_nn
docker cp $CONTAINER_NAME:opt/brainana/src/nhp_mri_prep       $OUTPUT_DIR/src/nhp_mri_prep
docker cp $CONTAINER_NAME:opt/brainana/src/fastsurfer_nn      $OUTPUT_DIR/src/fastsurfer_nn
docker cp $CONTAINER_NAME:opt/brainana/src/brainana.egg-info  $OUTPUT_DIR/src/brainana.egg-info

# fastsurfer_surfrecon — stub only (surface recon not included)
mkdir -p $OUTPUT_DIR/src/fastsurfer_surfrecon
echo '__version__ = "0.1.0"' > $OUTPUT_DIR/src/fastsurfer_surfrecon/__init__.py

# ────────────────────────────────────────────────────────────────
# Templates
# ────────────────────────────────────────────────────────────────
echo "Extracting templates..."

docker cp $CONTAINER_NAME:opt/brainana/template_zoo/template/NMT2Sym/tpl-NMT2Sym_res-05_T1w_brain.nii.gz         $OUTPUT_DIR/templates/NMT2Sym/
docker cp $CONTAINER_NAME:opt/brainana/template_zoo/template/NMT2Asym  $OUTPUT_DIR/templates/NMT2Asym
docker cp $CONTAINER_NAME:opt/brainana/template_zoo/template/MEBRAINS   $OUTPUT_DIR/templates/MEBRAINS
docker cp $CONTAINER_NAME:opt/brainana/template_zoo/template/Yerkes19   $OUTPUT_DIR/templates/Yerkes19
docker cp $CONTAINER_NAME:opt/brainana/template_zoo/template/D99        $OUTPUT_DIR/templates/D99

# ────────────────────────────────────────────────────────────────
# Atlases — all available template spaces
# ────────────────────────────────────────────────────────────────
echo "Extracting atlases..."

# ARM1-6 — full directory includes all template spaces
docker cp $CONTAINER_NAME:opt/brainana/template_zoo/atlas $OUTPUT_DIR/atlases

# ────────────────────────────────────────────────────────────────
echo "Cleaning up container..."
docker rm $CONTAINER_NAME

echo "Creating zip..."
zip -r brainana_anat.zip $OUTPUT_DIR/

echo ""
echo "Done. Created brainana_anat.zip"
echo ""
echo "Contents:"
du -sh $OUTPUT_DIR/*/