Installation
============

Docker
------

The recommended way to run brainana is with Docker. The image includes neuroimaging toolkits (FSL, ANTs, AFNI, FreeSurfer), Nextflow, and a pre-configured Python environment.

System requirements
~~~~~~~~~~~~~~~~~~~

.. warning::

   - **OS:** Linux (e.g. Ubuntu ≥ 20.04)
   - **RAM + swap:** ≥ 16 GB (recommended 20 GB+ for full pipeline)
   - **Disk:** ≥ 20 GB (recommended 50 GB+ for multiple subjects)
   - **CPU:** ≥ 4 logical cores (recommended 8+)
   - **GPU (optional):** ≥ 6 GB VRAM (recommended ≥ 10 GB for production)
   - **NVIDIA Driver (optional):** ≥ 520.61.05 if using GPU
   - **CUDA (optional):** ≥ 11.8 if using GPU

Resource guidelines:

- **Minimal:** 16 GB RAM, 4 CPUs, 20 GB disk
- **Recommended:** 20 GB RAM, 8 CPUs, 50 GB disk, 1 GPU with ≥ 6 GB VRAM
- **Production:** 32 GB RAM, 8+ CPUs, 100 GB+ disk, 1 GPU with ≥ 10 GB VRAM

Set up Docker
~~~~~~~~~~~~~

1. **Install Docker** if you do not have it (`Docker Installation <https://docs.docker.com/get-docker/>`_).

2. **Test Docker** with the hello-world image:

   .. code-block:: bash

      docker run -it --rm hello-world

   You should see a message indicating that Docker is working correctly.

3. **Check GPU access** (optional, if you have GPUs on the host):

   .. code-block:: bash

      docker run -it --rm --gpus all hello-world

   If you see an error about ``nvidia-container-cli`` or ``libnvidia-ml.so``, ensure the NVIDIA Container Toolkit and drivers are installed. Without ``--gpus all``, the container uses only CPU.

4. **Pull the brainana image:**

   .. code-block:: bash

      docker pull liuxingyu987/brainana:latest

Once the image is ready, see :doc:`usage_notes` to run the pipeline and :doc:`faq` for GPU and resource tuning.
