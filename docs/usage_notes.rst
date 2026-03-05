Usage notes
===========

The brainana workflow takes a BIDS-formatted dataset as input and writes preprocessed outputs to a directory you specify.

Quick start
-----------

1. Prepare a valid BIDS dataset (see `The BIDS format`_ below) and an output directory.
2. For surface reconstruction, obtain a free FreeSurfer license (see `The FreeSurfer license`_ below). Otherwise, disable surface recon in your config and omit the license mount and ``--freesurfer-license``.
3. Pull the image and run:

   .. code-block:: bash

      docker pull liuxingyu987/brainana:latest

      docker run -it --rm --gpus all \
          -v <bids_dir>:/input \
          -v <output_dir>:/output \
          -v <path/to/license.txt>:/fs_license.txt \
          liuxingyu987/brainana:latest /input /output --freesurfer-license /fs_license.txt

No config file is required; built-in defaults are used. The default config can be found in the `config generator <_static/config_generator.html>`_. See :ref:`command-line-reference` below for all available options.

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
- Pass ``--freesurfer-license /fs_license.txt`` when running the pipeline.

Without a valid license, anatomical and functional preprocessing can still run, but surface reconstruction will fail. The container will warn if the license is missing.

Docker user guide
-----------------

Mandatory mounts
~~~~~~~~~~~~~~~~

- **Input (BIDS):** ``-v <bids_dir>:/input``
- **Output:** ``-v <output_dir>:/output``
- **FreeSurfer license:** ``-v <path/to/license.txt>:/fs_license.txt``

Example with real paths
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   docker run -it --rm --gpus all \
       -v /data/my_bids_dataset:/input \
       -v /data/preprocessed:/output \
       -v /home/user/license.txt:/fs_license.txt \
       liuxingyu987/brainana:latest /input /output --freesurfer-license /fs_license.txt

Customizing your run
~~~~~~~~~~~~~~~~~~~~

There are two ways to customize the pipeline beyond the defaults.

**Option A — Config file (recommended)**

Generate a full config file using the :doc:`configuration` page's interactive generator, then mount and pass it:

.. code-block:: bash

   docker run -it --rm --gpus all \
       -v /data/my_bids_dataset:/input \
       -v /data/preprocessed:/output \
       -v /home/user/license.txt:/fs_license.txt \
       -v /home/user/my_config.yaml:/config.yaml \
       liuxingyu987/brainana:latest /input /output \
       --freesurfer-license /fs_license.txt \
       --config /config.yaml

The config file gives you fine-grained control over every pipeline step (registration type, template space, slice timing, bias correction, surface reconstruction, and more). See :doc:`configuration` for details.

**Option B — Command-line arguments**

Common options can be passed directly without a config file:

.. code-block:: bash

   docker run -it --rm --gpus all \
       -v /data/bids:/input \
       -v /data/output:/output \
       -v /path/to/license.txt:/fs_license.txt \
       liuxingyu987/brainana:latest /input /output \
       --freesurfer-license /fs_license.txt \
       --anat_only \
       --output_space NMT2Sym:res-1 \
       --subjects sub-001 sub-002

See :ref:`command-line-reference` below for the full list of options.

.. _command-line-reference:

Command-line reference
----------------------

.. code-block:: text

   docker run ... liuxingyu987/brainana:latest [bids_dir] [output_dir] [options]

Positional arguments
~~~~~~~~~~~~~~~~~~~~

``bids_dir``
   BIDS root directory mounted into the container.

   Default: ``/input``

``output_dir``
   Output directory mounted into the container.

   Default: ``/output``

Entrypoint options
~~~~~~~~~~~~~~~~~~

``--freesurfer-license PATH``
   Path to the FreeSurfer license file *inside the container* (required when surface
   reconstruction is enabled). Use the same path as your volume mount,
   e.g. ``/fs_license.txt``.

   Default: (none)

``--config PATH``, ``--config_file PATH``
   Path to a custom YAML config file inside the container (optional; built-in defaults
   are used when omitted). ``--config`` is an alias for ``--config_file``.

   Default: (built-in)

``-w PATH``, ``--work-dir PATH``
   Nextflow work directory.

   Default: ``<output_dir>_wd``

``--no-resume``
   Disable Nextflow resume; restart the pipeline from scratch.

``bash``, ``sh``
   Open an interactive shell inside the container instead of running the pipeline.

Options for filtering BIDS queries
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``--subjects SUBJECT [SUBJECT ...]``
   Restrict processing to the listed subject IDs (omit the ``sub-`` prefix).

   Default: (all subjects)

``--sessions SESSION [SESSION ...]``
   Restrict to specific session IDs (omit the ``ses-`` prefix).

   Default: (all sessions)

``--tasks TASK [TASK ...]``
   Restrict to specific task names (functional data only).

   Default: (all tasks)

``--runs RUN [RUN ...]``
   Restrict to specific run indices.

   Default: (all runs)

``--skip_bids_validation``
   Assume the input dataset is BIDS compliant and skip validation.

   Default: ``False``

Workflow options
~~~~~~~~~~~~~~~~

``--anat_only``
   Run only the anatomical pipeline; skip functional processing.

   Default: ``False``

``--output_space SPACE``
   Template space for registered outputs. Format: ``TEMPLATE_NAME:DESCRIPTION``.
   Examples: ``NMT2Sym:res-1`` (1 mm), ``NMT2Sym:res-05`` (0.5 mm), ``T1w`` (native space).

   Default: ``NMT2Sym:res-05``

Resource options
~~~~~~~~~~~~~~~~

``-profile PROFILE``
   Nextflow resource profile. Choices:

   - ``minimal`` — 4 CPUs, 16 GB RAM (suitable for anat-only, 1–2 subjects)
   - ``recommended`` — 8+ CPUs, 32 GB RAM

   Default: (built-in: 8 CPUs, 20 GB)

``NXF_MAX_CPUS`` (environment variable)
   Maximum number of CPUs for Nextflow. Pass via ``-e NXF_MAX_CPUS=8``.

``NXF_MAX_MEMORY`` (environment variable)
   Maximum memory for Nextflow. Pass via ``-e NXF_MAX_MEMORY=20g``.
