Installation
============

Docker
------

The recommended way to run Brainana is with Docker. The image includes neuroimaging toolkits (FSL, ANTs, AFNI, FreeSurfer), Nextflow, and a pre-configured Python environment.

System requirements
~~~~~~~~~~~~~~~~~~~

.. warning::

   - **Host:** Any OS supported by Docker (Linux, macOS, Windows with WSL2). 
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

3. **Check GPU access** (optional — skip this step if you have no GPU):

   .. note::

      **No GPU?** Skip this step. When you run the pipeline, omit ``--gpus all``; it will run on CPU with no other changes.

   If you do have an NVIDIA GPU, verify Docker can access it:

   .. code-block:: bash

      docker run -it --rm --gpus all hello-world

   If you see an error about ``nvidia-container-cli`` or ``libnvidia-ml.so``, ensure the `NVIDIA Container Toolkit <https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html>`_ and drivers are installed.

4. **Pull the Brainana image:**

   .. code-block:: bash

      docker pull liuxingyu987/brainana:latest

Once the image is ready, see :doc:`usage_notes` to run the pipeline.
