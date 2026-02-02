#!/bin/bash

#==============================================================================
# Complete Pipeline for nhp_skullstrip_nn Training with HDF5 Dataset Preparation
#==============================================================================
# This script handles:
#   1. Data splitting (train/val/test)
#   2. HDF5 generation (preprocessed slices for faster training)
#   3. Model training using pretrained model (optional)
#==============================================================================

# Note: No 'set -e' - script continues even if steps fail
# This allows you to resume from any step manually

# ============================================================================
# CONFIGURATION - Source centralized config
# ============================================================================

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# If running from the project root directory, use it directly
# This handles cases where script is run from /home/star/github/banana
CURRENT_DIR="$(pwd)"
if [ -d "$CURRENT_DIR/src/nhp_skullstrip_nn" ] && [ -f "$CURRENT_DIR/src/nhp_skullstrip_nn/scripts/run_training_pipeline.sh" ]; then
    PROJECT_ROOT="$CURRENT_DIR"
fi

# Set PYTHONPATH to include src/ for module imports
export PYTHONPATH="$PROJECT_ROOT/src:$PYTHONPATH"

# YAML config file (SINGLE SOURCE OF TRUTH)
# YAML_CONFIG="$PROJECT_ROOT/src/nhp_skullstrip_nn/config_example/T1w_brainmask.yaml"
YAML_CONFIG="$PROJECT_ROOT/src/nhp_skullstrip_nn/config_example/EPI_brainmask.yaml"

# # ============================================================================
# # STEP 1: Split Data into Train/Val/Test
# # ============================================================================

echo ""
echo "================================================================================"
echo "STEP 1: Splitting Data into Train/Val/Test Sets"
echo "================================================================================"
echo ""

# Note: Split script will read data path and seed from YAML
python3 "$PROJECT_ROOT/src/nhp_skullstrip_nn/train/step1_split_data.py" \
    --config "$YAML_CONFIG"

if [ $? -eq 0 ]; then
    echo "✓ Data split completed successfully"
else
    echo "⚠️  Data split had errors, but continuing..."
fi

# ============================================================================
# STEP 2: Generate HDF5 Datasets
# ============================================================================

echo ""
echo "================================================================================"
echo "STEP 2: Generating HDF5 Datasets (Preprocessed Slices)"
echo "================================================================================"
echo ""
echo "Note: This will convert 3D volumes to 2D slices for CNN training"
echo "      Each subject may produce multiple training slices from 3 orientations"
echo ""

# All parameters read from YAML!
echo "Generating training HDF5..."
python3 "$PROJECT_ROOT/src/nhp_skullstrip_nn/train/step2_create_hdf5.py" \
    --config "$YAML_CONFIG" \
    --split_type train

if [ $? -eq 0 ]; then
    echo "✓ Training HDF5 created successfully"
else
    echo "⚠️  Training HDF5 had errors, but continuing..."
fi

echo ""
echo "Generating validation HDF5..."
python3 "$PROJECT_ROOT/src/nhp_skullstrip_nn/train/step2_create_hdf5.py" \
    --config "$YAML_CONFIG" \
    --split_type val

if [ $? -eq 0 ]; then
    echo "✓ Validation HDF5 created successfully"
else
    echo "⚠️  Validation HDF5 had errors, but continuing..."
fi

# ============================================================================
# STEP 3: Model Training
# ============================================================================

echo ""
echo "================================================================================"
echo "STEP 3: Training Model"
echo "================================================================================"
echo ""
echo "Note: Training will automatically use HDF5 datasets if available"
echo "      All training parameters are read from the YAML config file"
echo ""

# Use the nhp_skullstrip_nn training script
# All parameters are already in the YAML!
python3 "$PROJECT_ROOT/src/nhp_skullstrip_nn/train/step3_train_model.py" \
    --config "$YAML_CONFIG"
