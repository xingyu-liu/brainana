Brainana
========

**Brainana** is a preprocessing and registration pipeline for Non-human primate (NHP) neuroimaging data. It provides anatomical, functional processing, and surface reconstruction.

.. note::
   For a quick start with Docker (recommended):

   .. code-block:: bash

      docker run -it --rm --gpus all \
        -v <bids_dir>:/input \
        -v <output_dir>:/output \
        -v <path/to/license.txt>:/fs_license.txt \
        liuxingyu987/brainana:latest /input /output --freesurfer-license /fs_license.txt

   **No GPU?** Omit ``--gpus all``; the pipeline runs on CPU with no other changes.

Contents
--------

.. toctree::
   :maxdepth: 2
   :caption: User guide

   installation
   usage_notes
   configuration
   outputs
   processing
   spaces_and_transforms
   faq
