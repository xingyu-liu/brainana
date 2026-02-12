#!/bin/bash

# export PATH="$(conda info --base)/envs/fireants/bin:$PATH"
# which fireantsRegistration   # should show .../envs/fireants/bin/fireantsRegistration
# which python                 # should show .../envs/fireants/bin/python
# fireantsRegistration

cd /mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/fireants

fireantsRegistration \
  --output results/registration \
  --device cuda:0 \
  --winsorize-image-intensities [0.005,0.995] \
  --initial-moving-transform [fixed.nii.gz,moving.nii.gz,2] \
  --transform Rigid[0.03] \
  --metric MI[fixed.nii.gz,moving.nii.gz,gaussian,16] \
  --convergence [100x50x25x10,1e-6,10] \
  --shrink-factors 8x4x2x1 \
  --transform Affine[0.03] \
  --metric CC[fixed.nii.gz,moving.nii.gz,5] \
  --convergence [100x50x25x10,1e-4,10] \
  --shrink-factors 8x4x2x1 \
  --transform SyN[0.2] \
  --metric MSE[fixed.nii.gz,moving.nii.gz] \
  --convergence [100x70x50x20,1e-4,10] \
  --shrink-factors 8x4x2x1 \
  --verbose