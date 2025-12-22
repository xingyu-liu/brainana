#!/bin/bash

#==============================================================================
# Complete Pipeline for Brain Segmentation with Transfer Learning
#==============================================================================
# This script handles:
#   1. Data splitting (train/val)
#   2. HDF5 generation
#   3. Transfer learning training using pretrained human model
#==============================================================================

# Note: No 'set -e' - script continues even if steps fail
# This allows you to resume from any step manually

# ============================================================================
# CONFIGURATION - Source centralized config
# ============================================================================

# YAML config file (SINGLE SOURCE OF TRUTH - like macacaMRINN!)
export PYTHONPATH="/home/star/github/banana:$PYTHONPATH"
YAML_CONFIG=/home/star/github/banana/FastSurferCNN/config/T1w_ARM2_axial_lia.yaml
# YAML_CONFIG=/home/star/github/banana/FastSurferCNN/config/T1w_brainmask_mixed.yaml
# YAML_CONFIG=/home/star/github/banana/FastSurferCNN/config/EPI_brainmask_mixed.yaml

# # ============================================================================
# # STEP 1: Split Data into Train/Val
# # ============================================================================

# # Note: Split script will read data path and seed from YAML
# python3 FastSurferCNN/training/step1_split_data.py \
#     --config "$YAML_CONFIG"

# if [ $? -eq 0 ]; then
#     echo "Data split completed successfully"
# else
#     echo "Data split had errors, but continuing..."
# fi

# ============================================================================
# STEP 2: Generate HDF5 Datasets
# ============================================================================

echo ""
echo "Note: This will convert 3D volumes to 2D slices for CNN training"
echo "      Each subject may produce multiple training slices"

# All parameters read from YAML!
echo "Generating training HDF5..."
python3 FastSurferCNN/training/step2_create_hdf5.py \
    --config "$YAML_CONFIG" \
    --split_type train

if [ $? -eq 0 ]; then
    echo "Training HDF5 created successfully"
else
    echo "Training HDF5 had errors, but continuing..."
fi

echo ""
echo "Generating validation HDF5..."
python3 FastSurferCNN/training/step2_create_hdf5.py \
    --config "$YAML_CONFIG" \
    --split_type val

if [ $? -eq 0 ]; then
    echo "Validation HDF5 created successfully"
else
    echo "Validation HDF5 had errors, but continuing..."
fi

# ============================================================================
# STEP 3: Transfer Learning Training
# ============================================================================
# Use the native FastSurferCNN training script
# All parameters are already in the YAML!
# Need to set PYTHONPATH so imports work correctly
python3 FastSurferCNN/training/step3_train_model.py \
    --cfg "$YAML_CONFIG"

if [ $? -eq 0 ]; then
    echo "Training completed successfully"
else
    echo "Training had errors or was interrupted"
fi
