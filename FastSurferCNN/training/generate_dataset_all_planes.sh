#!/bin/bash

#==============================================================================
# Generate HDF5 Datasets for All Three Planes
#==============================================================================

# Set PYTHONPATH
export PYTHONPATH="/home/star/github/others:$PYTHONPATH"

YAML_CONFIG_CORONAL=/home/star/github/others/FastSurferCNN/config/FastSurferVINN_ARM2_coronal.yaml
YAML_CONFIG_AXIAL=${YAML_CONFIG_CORONAL/coronal/axial}
YAML_CONFIG_SAGITTAL=${YAML_CONFIG_CORONAL/coronal/sagittal}


echo ""
echo "======================================================================"
echo "1/3: Generating CORONAL Data"
echo "======================================================================"
python3 train_2_create_hdf5_dataset.py \
    --config $YAML_CONFIG_CORONAL \
    --split_type train

python3 train_2_create_hdf5_dataset.py \
    --config $YAML_CONFIG_CORONAL \
    --split_type val


echo ""
echo "======================================================================"
echo "2/3: Generating AXIAL Data"
echo "======================================================================"
python3 train_2_create_hdf5_dataset.py \
    --config $YAML_CONFIG_AXIAL \
    --split_type train

python3 train_2_create_hdf5_dataset.py \
    --config $YAML_CONFIG_AXIAL \
    --split_type val


echo ""
echo "======================================================================"
echo "3/3: Generating SAGITTAL Data (Hemisphere-Merged)"
echo "======================================================================"
python3 train_2_create_hdf5_dataset.py \
    --config $YAML_CONFIG_SAGITTAL \
    --split_type train

python3 train_2_create_hdf5_dataset.py \
    --config $YAML_CONFIG_SAGITTAL \
    --split_type val
