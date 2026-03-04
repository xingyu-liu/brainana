Installation
============

Docker
------

The recommended way to run brainana is with Docker. The image includes neuroimaging toolkits (FSL, ANTs, AFNI, FreeSurfer), Nextflow, and a pre-configured Python environment.

.. list-table::
   :header-rows: 1
   :widths: 15 12 45 28

   * - Image
     - Version
     - Download / build command
     - User guide
   * - Docker
     - latest
     - ``docker pull liuxingyu987/brainana:latest`` (or build from source, see below)
     - :doc:`usage_local` (Docker guide)

If no pre-built image is available, build the Docker image from the project root (see **Run with Docker (step-by-step)** below).

Run with Docker (step-by-step)
------------------------------

brainana provides a Docker image as the recommended way to get started.

.. warning::
   **Required environment**

   - **OS:** Linux (e.g. Ubuntu ≥ 20.04)
   - **RAM + swap:** ≥ 16 GB (recommended 20 GB+ for full pipeline)
   - **Disk:** ≥ 20 GB (recommended 50 GB+ for multiple subjects)
   - **CPU:** ≥ 4 logical cores (recommended 8+)
   - **GPU (optional):** ≥ 6 GB VRAM (recommended ≥ 10 GB for production)
   - **NVIDIA Driver (optional):** ≥ 520.61.05 if using GPU
   - **CUDA (optional):** ≥ 11.8 if using GPU

1. **Install Docker** if you do not have it (`Docker Installation <https://docs.docker.com/get-docker/>`_).

2. **Test Docker** with the hello-world image:

   .. code-block:: bash

      docker run -it --rm hello-world

   You should see a message indicating that Docker is working correctly.

3. **Check GPU access** (optional, if you have GPUs on the host):

   .. code-block:: bash

      docker run -it --rm --gpus all hello-world

   The same hello-world output is expected. If you see an error about ``nvidia-container-cli`` or ``libnvidia-ml.so``, ensure the NVIDIA Container Toolkit and drivers are installed. Without ``--gpus all``, the container uses only CPU.

4. **Pull or build the image:**

   **Option A — Pull from Docker Hub (if available):**

   .. code-block:: bash

      docker pull liuxingyu987/brainana:latest

   **Option B — Build from source** (from the project root):

   .. code-block:: bash

      docker build \
          --build-arg USER_ID=$(id -u) \
          --build-arg GROUP_ID=$(id -g) \
          -t liuxingyu987/brainana:latest .

5. **Run the container:**

   .. code-block:: bash

      docker run --rm liuxingyu987/brainana:latest

   For a full run with BIDS input, output, and FreeSurfer license, see :doc:`usage_local`.

**Resource guidelines:**

- **Minimal:** 16 GB RAM, 4 CPUs, 20 GB disk (anat-only, 1–2 subjects)
- **Recommended:** 20 GB RAM, 8 CPUs, 50 GB disk, 1 GPU with ≥ 6 GB VRAM
- **Production:** 32 GB RAM, 8+ CPUs, 100 GB+ disk, 1 GPU with ≥ 10 GB VRAM

See :doc:`usage_local` for how to run the container with your data and :doc:`faq` for GPU and resource tuning.

Install from source
-------------------

If you prefer to run without Docker (e.g. on a cluster):

1. Install system dependencies: Nextflow, FSL, ANTs, AFNI, FreeSurfer, Connectome Workbench (see project README or Dockerfile for versions).
2. Clone the repository and install the Python package:

   .. code-block:: bash

      git clone https://github.com/xingyu-liu/brainana.git
      cd brainana
      uv pip install -e .   # or: pip install -e .

3. Ensure the FreeSurfer license is set (e.g. ``FS_LICENSE`` or ``/path/to/license.txt``).
4. Run the pipeline via ``./run_brainana.sh run main.nf --bids_dir <path> --output_dir <path>`` (optionally ``--config_file <path>`` or ``--config <path>``; see :doc:`usage_local`).

For full usage and Docker details, continue to :doc:`usage_local`.
