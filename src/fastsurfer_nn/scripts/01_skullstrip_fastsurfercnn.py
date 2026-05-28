#!/usr/bin/env python3
"""Notebook-style test script mirroring the ANAT_SKULLSTRIPPING step."""

import logging
import sys
from pathlib import Path

# Add src/ to path (scripts/ -> fastsurfer_nn -> src)
_src_dir = Path(__file__).resolve().parent.parent.parent
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from nhp_mri_prep.steps.anatomical import anat_skullstripping
from nhp_mri_prep.steps.types import StepInput
from nhp_mri_prep.config.config_io import load_config


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# %%
# Edit these values before running this cell.
input_file = Path(
    "/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/surf_recon/sub-032310_nofixV1/others/T1w.nii.gz"
)
modality = "anat"  # "anat" | "func"
config_file = None

subject_id = "test"
session_id = ""  # Set "" if no session is used.

fix_V1_WM = False

# %%
working_dir = input_file.parent / "work"
working_dir.mkdir(parents=True, exist_ok=True)
output_name = "brain.nii.gz"

# %%
# Match the workflow logic: load config, detect modality, build StepInput, run step.
if not input_file.exists():
    raise FileNotFoundError(f"Input file not found: {input_file}")
if config_file is not None and not Path(config_file).exists():
    raise FileNotFoundError(f"Config file not found: {config_file}")

config = load_config(config_file)

# Set fix_V1_WM in config
config["anat"]["skullstripping_segmentation"]["fastSurferCNN"]["fix_V1_WM"] = fix_V1_WM

# Build StepInput
input_obj = StepInput(
    input_file=input_file,
    working_dir=working_dir,
    config=config,
    output_name=output_name,
    metadata={
        "subject_id": subject_id,
        "session_id": session_id,
    },
)

logger.info("Running anat_skullstripping")
logger.info("input_file=%s", input_file)
logger.info("modality=%s", modality)
logger.info("working_dir=%s", working_dir)

result = anat_skullstripping(input_obj)

logger.info("Completed.")
logger.info("output_file=%s", result.output_file)
logger.info("metadata=%s", result.metadata)
if result.additional_files:
    for key, value in result.additional_files.items():
        logger.info("additional_file[%s]=%s", key, value)
else:
    logger.info("additional_files=None")
