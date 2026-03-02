Usage notes (local)
===================

The brainana workflow takes a BIDS-formatted dataset as input and writes preprocessed outputs to a directory you specify. This section covers running brainana locally with Docker (recommended).

The BIDS format
---------------

The input dataset must be in valid `BIDS <https://bids-specification.readthedocs.io/>`_ format. We recommend validating your dataset with the free online `BIDS Validator <https://bids-standard.github.io/bids-validator/>`_.

Minimal example layout (dataset root with one subject, one session, anat + func)::

   ./   # dataset root
   └── sub-aaa
       ├── ses-bbb
       │   ├── anat
       │   │   ├── sub-aaa_ses-bbb_run-ccc_T1w.nii.gz
       │   │   └── sub-aaa_ses-bbb_run-ccc_T1w.json   # optional
       │   └── func
       │       ├── sub-aaa_ses-bbb_task-ddd_run-eee_bold.nii.gz
       │       └── sub-aaa_ses-bbb_task-ddd_run-eee_bold.json   # optional

If you start with DICOM, you can either (1) use `dcm2niix <https://github.com/rordenlab/dcm2niix>`_ to convert DICOM to NIfTI and then manually reorganise and rename files to BIDS, or (2) use `dcm2bids <https://unfmontgomery.github.io/Dcm2Bids/>`_, which converts DICOM to NIfTI and organises output into BIDS for you.

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
- **FreeSurfer license:** ``-v <path/to/license.txt>:/fs_license.txt`` (and pass ``--freesurfer-license /fs_license.txt`` when surface recon is enabled)

Sample Docker command
~~~~~~~~~~~~~~~~~~~~~

**Default (recommended resources: 8 CPUs, 20 GB inside container):**

.. code-block:: bash

   docker run -it --rm --gpus all \
       -v <bids_dir>:/input \
       -v <output_dir>:/output \
       -v <path/to/license.txt>:/fs_license.txt \
       xxxlab/brainana:latest /input /output --freesurfer-license /fs_license.txt

**Example with real paths:**

.. code-block:: bash

   docker run -it --rm --gpus all \
       -v /data/my_bids_dataset:/input \
       -v /data/preprocessed:/output \
       -v /home/user/license.txt:/fs_license.txt \
       xxxlab/brainana:latest /input /output --freesurfer-license /fs_license.txt

**With optional arguments** (e.g. anat-only, custom output space, or resource profile):

.. code-block:: bash

   docker run -it --rm --gpus all \
       -v /data/bids:/input \
       -v /data/output:/output \
       -v /path/to/license.txt:/fs_license.txt \
       xxxlab/brainana:latest /input /output --freesurfer-license /fs_license.txt --anat_only --output_space "NMT2Sym:res-1"

**Hard-cap container resources** (e.g. on a shared host):

.. code-block:: bash

   docker run -it --rm --gpus all \
       --memory 20g --cpus 8 \
       -v <bids_dir>:/input \
       -v <output_dir>:/output \
       -v <path/to/license.txt>:/fs_license.txt \
       xxxlab/brainana:latest /input /output --freesurfer-license /fs_license.txt

**Minimal resources** (anat-only, 1–2 subjects) with profile:

.. code-block:: bash

   docker run -it --rm --gpus all \
       --memory 16g --cpus 4 \
       -e NXF_MAX_CPUS=4 -e NXF_MAX_MEMORY=16g \
       -v <bids_dir>:/input \
       -v <output_dir>:/output \
       -v <path/to/license.txt>:/fs_license.txt \
       xxxlab/brainana:latest /input /output --freesurfer-license /fs_license.txt -profile minimal

Quick start
~~~~~~~~~~~

1. Prepare a BIDS dataset and an output directory on your host.
2. Get a FreeSurfer license and note its path.
3. Run the command above (with your paths). The container will run the full pipeline with built-in defaults; no config file is required.

The full list of options is in :ref:`command-line-reference` below.

Input arguments: Docker vs local
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **Docker:** After the image name you can pass *positional* paths and *pipeline* options. Positionals are optional and default to ``/input`` and ``/output`` (so your mounts must use those names if you omit them). Pipeline options (e.g. ``--anat_only``, ``--output_space``, ``-profile minimal``) are passed through to the workflow. The entrypoint also accepts ``--config``, ``-w`` / ``--work-dir``, ``--no-resume``, and ``--freesurfer-license`` (see below). Example: ``xxxlab/brainana:latest /input /output --anat_only``.
- **Local (run_brainana.sh):** No positionals. Use *named* arguments: ``--bids_dir``, ``--output_dir`` (required); ``--config_file`` or ``--config`` (optional; built-in defaults used when omitted); plus any optional pipeline options. Example: ``./run_brainana.sh run main.nf --bids_dir /data/bids --output_dir /data/out``.

When surface reconstruction is enabled (default), you must pass ``--freesurfer-license <path>`` so the container sets ``FS_LICENSE``; use the same path you mounted (e.g. ``--freesurfer-license /fs_license.txt``). If you only mount the file and do not pass this flag, surface recon will fail.

.. _command-line-reference:

Command-line reference
----------------------

This section is the full reference for arguments when running brainana via Docker or via ``run_brainana.sh run main.nf``.

Container invocation (Docker)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When using Docker, the entrypoint expects:

.. code-block:: text

   docker run ... xxxlab/brainana:latest [input_dir] [output_dir] [extra args...]

- **input_dir** — BIDS input directory (default: ``/input``). Must be mounted if using default.
- **output_dir** — Output directory (default: ``/output``). Must be mounted if using default.
- **extra args** — Passed to the Nextflow pipeline (see below).

Optional Docker/entrypoint arguments (before or after positionals):

- ``--config`` / ``--config_file`` *path* — Use a custom YAML config (optional; built-in defaults used when omitted). ``--config`` is an alias for ``--config_file``.
- ``--freesurfer-license /path/to/license.txt`` — Set ``FS_LICENSE`` (required when surface reconstruction is enabled; use the path where you mounted the license, e.g. ``/fs_license.txt``).
- ``-w PATH`` / ``--work-dir PATH`` — Nextflow work directory (default: ``<output_dir>_wd``).
- ``--no-resume`` — Disable resume; run from scratch.
- ``bash`` or ``sh`` — Start an interactive shell instead of running the pipeline.

Pipeline arguments (Nextflow / config)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

These can be passed after ``[output_dir]`` when running the container, or to ``run_brainana.sh run main.nf`` when running from source.

**Required**

- ``--bids_dir`` — Path to BIDS root (inside container often ``/input``).
- ``--output_dir`` — Path for outputs (inside container often ``/output``).
- ``--config_file`` / ``--config`` — Path to config YAML (optional; built-in defaults used when omitted).

**Optional (filtering and workflow)**

- ``--subjects`` — Restrict to specific subject IDs (space-separated or comma-separated, depending on config).
- ``--sessions`` — Restrict to specific session IDs.
- ``--tasks`` — Restrict to specific task names (functional).
- ``--runs`` — Restrict to specific run indices.
- ``--anat_only`` — Run only anatomical pipeline (no functional).
- ``--output_space`` — Template space for outputs (e.g. ``NMT2Sym:res-1``, ``NMT2Sym:res-05``). See config/defaults for allowed values.
- ``--skip_bids_validation`` — Skip BIDS validation of the input dataset.
- ``-profile minimal`` — Use minimal resource profile (e.g. 4 CPUs, 16 GB).
- ``-profile recommended`` — Use recommended resource profile (e.g. 32 GB).

**Optional (Nextflow / container environment)**

- ``NXF_MAX_CPUS`` — Max CPUs for Nextflow (e.g. ``-e NXF_MAX_CPUS=8``).
- ``NXF_MAX_MEMORY`` — Max memory (e.g. ``-e NXF_MAX_MEMORY=20g``).

These override the container defaults (8 CPUs, 20 GB). Align with Docker ``--cpus`` and ``--memory`` when capping the container.

Summary table
~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 28 18 52

   * - Argument / option
     - Default
     - Description
   * - ``input_dir``
     - /input
     - BIDS directory (positional, Docker)
   * - ``output_dir``
     - /output
     - Output directory (positional, Docker)
   * - ``--config``
     - (built-in)
     - Custom config file path (Docker)
   * - ``--freesurfer-license``
     - (none)
     - Path to license in container (Docker)
   * - ``--anat_only``
     - false
     - Anatomical pipeline only
   * - ``--output_space``
     - (from config)
     - Template space, e.g. NMT2Sym:res-1
   * - ``--subjects`` / ``--sessions``
     - (all)
     - Limit to specific subjects/sessions
   * - ``--skip_bids_validation``
     - false
     - Skip BIDS validation
   * - ``-profile``
     - (default)
     - minimal | recommended for resources

For full config options (templates, registration, etc.), see the YAML config schema and ``src/nhp_mri_prep/config/defaults.yaml`` in the repository. To build a config interactively, see :doc:`configuration`.

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
       xxxlab/brainana:latest /input /output --freesurfer-license /fs_license.txt

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
          -v /path/to/your/bids:/data \
          -v /path/to/your/output:/output \
          -v /path/to/license.txt:/fs_license.txt \
          --workdir /opt/brainana \
          xxxlab/brainana:latest bash

   Replace ``/path/to/your/bids``, ``/path/to/your/output``, and ``/path/to/license.txt`` with your host paths. Inside the container you can:

   - Open the config generator: see :doc:`configuration` (Generate your own config) or open ``docs/_static/config_generator.html`` in the repo in a browser.
   - Run the pipeline manually: ``./run_brainana.sh run main.nf --bids_dir /data --output_dir /output --config_file /opt/brainana/src/nhp_mri_prep/config/defaults.yaml`` (paths are *container* paths; ``FS_LICENSE`` is already set by the image when the license is mounted at ``/fs_license.txt``).

For common issues (X server, GPU, config file, license), see :doc:`faq`.
