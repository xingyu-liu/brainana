Usage notes (local)
===================

The brainana workflow takes a BIDS-formatted dataset as input and writes preprocessed outputs to a directory you specify. This section covers running brainana locally with Docker (recommended).

The BIDS format
---------------

The input dataset must be in valid `BIDS <https://bids-specification.readthedocs.io/>`_ format. We recommend validating your dataset with the free online `BIDS Validator <https://bids-standard.github.io/bids-validator/>`_.

The FreeSurfer license
----------------------

brainana uses FreeSurfer (and related tools) for surface reconstruction. A valid FreeSurfer license is required for those steps.

- Obtain a free license: https://surfer.nmr.mgh.harvard.edu/registration.html
- Mount the license file into the container: ``-v <path/to/license.txt>:/fs_license.txt``

Example (if the license is at ``$HOME/freesurfer/license.txt`` on the host):

.. code-block:: bash

   -v $HOME/freesurfer/license.txt:/fs_license.txt

Without a valid license, anatomical and functional preprocessing can still run, but surface reconstruction will fail. The container will warn if the license is missing.

Docker user guide
-----------------

Mandatory mounts
~~~~~~~~~~~~~~~~

- **Input (BIDS):** ``-v <bids_dir>:/input``
- **Output:** ``-v <output_dir>:/output``
- **FreeSurfer license:** ``-v <path/to/license.txt>:/fs_license.txt``

Sample Docker command
~~~~~~~~~~~~~~~~~~~~~

**Default (recommended resources: 8 CPUs, 20 GB inside container):**

.. code-block:: bash

   docker run -it --rm --gpus all \
       -v <bids_dir>:/input \
       -v <output_dir>:/output \
       -v <path/to/license.txt>:/fs_license.txt \
       xxxlab/brainana:latest

**Example with real paths:**

.. code-block:: bash

   docker run -it --rm --gpus all \
       -v /data/my_bids_dataset:/input \
       -v /data/preprocessed:/output \
       -v /home/user/license.txt:/fs_license.txt \
       xxxlab/brainana:latest

**With optional arguments** (e.g. anat-only, custom output space, or resource profile):

.. code-block:: bash

   docker run -it --rm --gpus all \
       -v /data/bids:/input \
       -v /data/output:/output \
       -v /path/to/license.txt:/fs_license.txt \
       xxxlab/brainana:latest /input /output --anat_only --output_space "NMT2Sym:res-1"

**Hard-cap container resources** (e.g. on a shared host):

.. code-block:: bash

   docker run -it --rm --gpus all \
       --memory 20g --cpus 8 \
       -v <bids_dir>:/input \
       -v <output_dir>:/output \
       -v <path/to/license.txt>:/fs_license.txt \
       xxxlab/brainana:latest

**Minimal resources** (anat-only, 1–2 subjects) with profile:

.. code-block:: bash

   docker run -it --rm --gpus all \
       --memory 16g --cpus 4 \
       -e NXF_MAX_CPUS=4 -e NXF_MAX_MEMORY=16g \
       -v <bids_dir>:/input \
       -v <output_dir>:/output \
       -v <path/to/license.txt>:/fs_license.txt \
       xxxlab/brainana:latest /input /output -profile minimal

Quick start
~~~~~~~~~~~

1. Prepare a BIDS dataset and an output directory on your host.
2. Get a FreeSurfer license and note its path.
3. Run the command above (with your paths). The container will run the full pipeline with built-in defaults; no config file is required.

For all supported command-line options (e.g. ``--anat_only``, ``--output_space``, ``--config``, ``--subjects``), see :doc:`command_line`.

Running as host user (file permissions)
----------------------------------------

To have output files owned by your host user, pass ``--user`` and set writable Nextflow directories:

.. code-block:: bash

   docker run -it --rm --gpus all \
       --user $(id -u):$(id -g) \
       -e NXF_WORK=/tmp/nextflow-work \
       -e NXF_HOME=/tmp/nextflow-home \
       -v <bids_dir>:/input \
       -v <output_dir>:/output \
       -v <path/to/license.txt>:/fs_license.txt \
       xxxlab/brainana:latest

When using ``--user``, the default Nextflow work directory (``~/.nextflow/work``) may not be writable; ``NXF_WORK`` and ``NXF_HOME`` set it to ``/tmp`` so the run can complete.

Interactive / development mode
------------------------------

For debugging or running the config generator GUI:

1. Enable X11 on the host: ``xhost +local:root``
2. Run an interactive shell with display and repo mounted:

   .. code-block:: bash

      docker run -it --rm --gpus all \
          --network host \
          --user $(id -u):$(id -g) \
          -e NXF_WORK=/tmp/nextflow-work \
          -e NXF_HOME=/tmp/nextflow-home \
          -e DISPLAY=$DISPLAY \
          -e QT_X11_NO_MITSHM=1 \
          -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
          -v $(pwd):/opt/brainana \
          -v /path/to/your/data:/data \
          -v /path/to/license.txt:/fs_license.txt \
          --workdir /opt/brainana \
          xxxlab/brainana:latest bash

   Inside the container you can:

   - Open the config generator: see :doc:`configuration` (Generate your own config) or open ``docs/_static/config_generator.html`` in the repo in a browser.
   - Run the pipeline manually: ``./run_brainana.sh run main.nf --bids_dir /data --output_dir /output --config_file /opt/brainana/src/nhp_mri_prep/config/defaults.yaml``

For common issues (X server, GPU, config file, license), see :doc:`faq`.
