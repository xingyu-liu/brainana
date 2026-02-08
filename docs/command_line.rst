Command-line reference
=====================

This page documents the interface when running brainana via Docker (or directly via ``run_brainana.sh run main.nf``).

Container invocation
--------------------

When using Docker, the entrypoint expects:

.. code-block:: text

   docker run ... xxxlab/brainana:latest [input_dir] [output_dir] [extra args...]

- **input_dir** — BIDS input directory (default: ``/input``). Must be mounted if using default.
- **output_dir** — Output directory (default: ``/output``). Must be mounted if using default.
- **extra args** — Passed to the Nextflow pipeline (see below).

Optional Docker/pipeline arguments (examples):

- ``--config /path/to/config.yaml`` — Use a custom YAML config (otherwise built-in defaults are used).
- ``bash`` or ``sh`` — Start an interactive shell instead of running the pipeline.

Pipeline arguments (Nextflow / config)
---------------------------------------

These can be passed after ``[output_dir]`` when running the container, or to ``run_brainana.sh run main.nf`` when running from source.

Required
~~~~~~~~

- ``--bids_dir`` — Path to BIDS root (inside container often ``/input``).
- ``--output_dir`` — Path for outputs (inside container often ``/output``).
- ``--config_file`` — Path to config YAML (container uses a built-in default if not overridden via ``--config`` in the entrypoint).

Optional (filtering and workflow)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- ``--subjects`` — Restrict to specific subject IDs (space-separated or comma-separated, depending on config).
- ``--sessions`` — Restrict to specific session IDs.
- ``--tasks`` — Restrict to specific task names (functional).
- ``--runs`` — Restrict to specific run indices.
- ``--anat_only`` — Run only anatomical pipeline (no functional).
- ``--output_space`` — Template space for outputs (e.g. ``NMT2Sym:res-1``, ``NMT2Sym:res-05``). See config/defaults for allowed values.
- ``--skip_bids_validation`` — Skip BIDS validation of the input dataset.
- ``-profile minimal`` — Use minimal resource profile (e.g. 4 CPUs, 16 GB).
- ``-profile recommended`` — Use recommended resource profile (e.g. 32 GB).

Optional (Nextflow / container environment)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- ``NXF_MAX_CPUS`` — Max CPUs for Nextflow (e.g. ``-e NXF_MAX_CPUS=8``).
- ``NXF_MAX_MEMORY`` — Max memory (e.g. ``-e NXF_MAX_MEMORY=20g``).

These override the container defaults (8 CPUs, 20 GB). Align with Docker ``--cpus`` and ``--memory`` when capping the container.

Summary table
-------------

+--------------------------+------------------+------------------------------------------+
| Argument / option        | Default          | Description                               |
+==========================+==================+==========================================+
| input_dir                | /input           | BIDS directory (positional)               |
+--------------------------+------------------+------------------------------------------+
| output_dir               | /output          | Output directory (positional)             |
+--------------------------+------------------+------------------------------------------+
| --config                 | (built-in)       | Custom config file path                   |
+--------------------------+------------------+------------------------------------------+
| --anat_only              | false            | Anatomical pipeline only                  |
+--------------------------+------------------+------------------------------------------+
| --output_space           | (from config)    | Template space, e.g. NMT2Sym:res-1         |
+--------------------------+------------------+------------------------------------------+
| --subjects / --sessions  | (all)            | Limit to specific subjects/sessions       |
+--------------------------+------------------+------------------------------------------+
| --skip_bids_validation   | false            | Skip BIDS validation                      |
+--------------------------+------------------+------------------------------------------+
| -profile                 | (default)        | minimal | recommended for resources        |
+--------------------------+------------------+------------------------------------------+

For full config options (templates, registration, etc.), see the YAML config schema and ``src/nhp_mri_prep/config/defaults.yaml`` in the repository. To build a config interactively, see :doc:`configuration`.
