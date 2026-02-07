Installation
============

Docker (recommended)
-------------------

The easiest way to run brainana is with the official Docker image. It includes neuroimaging toolkits (FSL, ANTs, AFNI, FreeSurfer, Connectome Workbench), Nextflow, and a pre-configured Python environment.

**Build the image** (from the project root):

.. code-block:: bash

   docker build \
       --build-arg USER_ID=$(id -u) \
       --build-arg GROUP_ID=$(id -g) \
       -t xxxlab/brainana:latest .

**System requirements (rough guide):**

- **Minimal:** 16 GB RAM, 4 CPUs, 20 GB disk (anat-only, 1–2 subjects)
- **Recommended:** 20 GB RAM, 8 CPUs, 50 GB disk, 1 GPU with ≥6 GB VRAM
- **Production:** 32 GB RAM, 8+ CPUs, 100 GB+ disk, 1 GPU with ≥10 GB VRAM

See :doc:`usage_local` for how to run the container and :doc:`faq` for GPU and resource tuning.

Install from source
------------------

If you prefer to run without Docker (e.g. on a cluster):

1. Install system dependencies: Nextflow, FSL, ANTs, AFNI, FreeSurfer, Connectome Workbench (see project README or Dockerfile for versions).
2. Clone the repository and install the Python package:

   .. code-block:: bash

      git clone https://github.com/yourusername/brainana.git
      cd brainana
      uv pip install -e .   # or: pip install -e .

3. Ensure the FreeSurfer license is set (e.g. ``FS_LICENSE`` or ``/path/to/license.txt``).
4. Run the pipeline via ``./run_brainana.sh run main.nf --bids_dir <path> --output_dir <path> --config_file <path>`` (see :doc:`command_line`).

For full usage and Docker details, continue to :doc:`usage_local`.
