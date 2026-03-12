FAQ and troubleshooting
=======================

**Setup and configuration**

- `Do I need a config file?`_
- `Can I run without a FreeSurfer license?`_
- `What if I don't have a compatible GPU?`_

**Running on your system**

- `Can I use a network drive for input or output?`_
- `I'm on Windows — how do I write paths?`_

**Resources and troubleshooting**

- `How do I align container resources with Nextflow?`_
- `My pipeline run is hanging.`_

----

Setup and configuration
------------------------

Do I need a config file?
~~~~~~~~~~~~~~~~~~~~~~~~

No. Built-in defaults are used for all pipeline steps. To customise the pipeline you have two options:

1. **Config file (recommended):** Generate a YAML config file with the :ref:`generating-config-file` interactive generator (in :doc:`usage_notes`), mount it into the container (e.g. ``-v <path/to/config.yaml>:/config.yaml``), and pass ``--config /config.yaml``.
2. **Command-line arguments:** Pass common options directly in the ``docker run`` command (e.g. ``--anat_only``, ``--output_space "NMT2Sym:res-1"``). See :ref:`command-line-arguments`.

Can I run without a FreeSurfer license?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Anatomical and functional preprocessing will still run, but surface reconstruction will be skipped. The container will warn if the license is missing.

Get a free license at https://surfer.nmr.mgh.harvard.edu/registration.html, then mount it with ``-v <path/to/license.txt>:/fs_license.txt`` and pass ``--freesurfer-license /fs_license.txt``.

What if I don't have a compatible GPU?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

You can run the pipeline without a GPU; it will use the CPU. Omit ``--gpus`` from your ``docker run`` command—no other options are needed.

If you do have an NVIDIA GPU and want to use it, add ``--gpus all`` and ensure the `NVIDIA Container Toolkit <https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html>`_ is installed on the host. See :doc:`installation` for setup steps.

----

Running on your system
----------------------

Can I use a network drive for input or output?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**We recommend keeping the output directory and work directory on local storage.** Writing to a network drive (NFS, SMB, etc.) can cause permission errors, copy failures in early stages, or poor I/O performance and timeouts. If you see failures that look like permission or copy issues soon after the run starts, try pointing the output and work-directory mounts to local paths.

**Input on a network drive is fine.** You can leave your BIDS dataset on a network share and set the output (and work directory) to a local path. For example: mount the network BIDS root with ``-v <path/on/network/bids_dir>:/input`` and use local paths for ``-v <path/on/local/output_dir>:/output`` and ``-v <path/on/local/work_dir>:/output_wd``. The pipeline reads from the network and writes only to local disk.

.. _windows-paths:

I'm on Windows — how do I write paths?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Docker volume mounts (``-v``) require the **host** path (the part before ``:``) to use
**forward slashes**, regardless of which Windows terminal you use.
The paths **inside** the container (after ``:``) are always Linux paths and never change.

**PowerShell or Command Prompt**

Replace backslashes with forward slashes in the host path:

.. code-block:: text

   # Replace this:                    C:\Users\me\bids:/input
   # With this:
   -v C:/Users/me/bids:/input

Full example:

.. code-block:: powershell

   docker run -it --rm `
       -v C:/Users/me/bids:/input `
       -v C:/Users/me/output:/output `
       -v C:/Users/me/work:/output_wd `
       liuxingyu987/brainana:<version> /input /output `
       --work-dir /output_wd

.. note::

   PowerShell uses a backtick `` ` `` for line continuation instead of ``\``.

**WSL2 (Windows Subsystem for Linux)**

Use the ``/mnt/c/`` prefix to reference Windows drives:

.. code-block:: bash

   docker run -it --rm \
       -v /mnt/c/Users/me/bids:/input \
       -v /mnt/c/Users/me/output:/output \
       -v /mnt/c/Users/me/work:/output_wd \
       liuxingyu987/brainana:<version> /input /output \
       --work-dir /output_wd

----

Resources and troubleshooting
-----------------------------

How do I align container resources with Nextflow?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The container defaults to 8 CPUs and 20 GB for Nextflow (controlled by ``NXF_MAX_CPUS`` and ``NXF_MAX_MEMORY``). To change these:

- Pass ``-e NXF_MAX_CPUS=<n>`` and ``-e NXF_MAX_MEMORY=<n>g`` to ``docker run``.
- Use ``-profile minimal`` (4 CPUs, 16 GB) or ``-profile recommended`` (8+ CPUs, 32 GB) for preset profiles.

See :ref:`command-line-arguments` for the full resource options.

My pipeline run is hanging.
~~~~~~~~~~~~~~~~~~~~~~~~~~

This typically happens when Nextflow runs out of memory. Try one or more of the following:

- Increase the RAM available to Docker.
- Use ``-profile minimal`` to reduce resource usage.
- Set ``-e NXF_MAX_CPUS`` and ``-e NXF_MAX_MEMORY`` to match your available resources.
- Resume from the last checkpoint by re-running the same command (Nextflow resume is enabled by default, provided the work directory is mounted — see :ref:`usage-docker-guide`).
