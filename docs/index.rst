Brainana
========

**Brainana** is a preprocessing and registration pipeline for non-human primate (NHP) neuroimaging data. It provides anatomical, functional processing, and surface reconstruction.

.. note::
   For a quick start with Docker (recommended):

   .. code-block:: bash

      docker run -it --rm --gpus all \
        -v <bids_dir>:/input \
        -v <output_dir>:/output \
        -v <work_dir>:/output_wd \
        -v <path/to/license.txt>:/fs_license.txt \
        liuxingyu987/brainana:<version> /input /output --freesurfer-license /fs_license.txt

   **No compatible GPU?** First, determine whether you have a compatible GPU in :ref:`Check GPU access <installation-check-gpu-access>`. If you do not, omit ``--gpus all``; the pipeline runs on CPU with no other changes.

Contents
--------

.. toctree::
   :maxdepth: 1
   :caption: INSTALLATION

   installation

.. toctree::
   :maxdepth: 1
   :caption: USER GUIDE

   usage_notes

.. toctree::
   :maxdepth: 1
   :caption: PROCESS AND OUTPUTS

   processing
   outputs
   anat_selection_for_func
   spaces_and_transforms

.. toctree::
   :maxdepth: 1
   :caption: TEMPLATE AND ATLAS

   template_atlas_zoo

.. toctree::
   :maxdepth: 1
   :caption: OTHER INFO

   faq
