FAQ and troubleshooting
=======================

- `Do I need a config file?`_
- `Can I run without a FreeSurfer license?`_
- `What if I don't have a compatible GPU?`_
- `How do I align container resources with Nextflow?`_
- `My pipeline run is hanging.`_

----

Do I need a config file?
------------------------

No. Built-in defaults are used for all pipeline steps. To customise the pipeline you have two options:

1. **Config file (recommended):** Generate a YAML config file with the :doc:`configuration` page's interactive generator, mount it into the container, and pass ``--config /path/to/config.yaml``.
2. **Command-line arguments:** Pass common options directly in the ``docker run`` command (e.g. ``--anat_only``, ``--output_space "NMT2Sym:res-1"``). See :ref:`command-line-reference`.

Can I run without a FreeSurfer license?
----------------------------------------

Anatomical and functional preprocessing will still run, but surface reconstruction will be skipped. The container will warn if the license is missing.

Get a free license at https://surfer.nmr.mgh.harvard.edu/registration.html, then mount it with ``-v <path>:/fs_license.txt`` and pass ``--freesurfer-license /fs_license.txt``.

What if I don't have a compatible GPU?
---------------------------------------

You can run the pipeline without a GPU; it will use the CPU. Omit ``--gpus`` from your ``docker run`` command—no other options are needed. 

If you do have an NVIDIA GPU and want to use it, add ``--gpus all`` and ensure the `NVIDIA Container Toolkit <https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html>`_ is installed on the host. See :doc:`installation` for setup steps.

How do I align container resources with Nextflow?
--------------------------------------------------

The container defaults to 8 CPUs and 20 GB for Nextflow (controlled by ``NXF_MAX_CPUS`` and ``NXF_MAX_MEMORY``). To change these:

- Pass ``-e NXF_MAX_CPUS=<n>`` and ``-e NXF_MAX_MEMORY=<n>g`` to ``docker run``.
- Use ``-profile minimal`` (4 CPUs, 16 GB) or ``-profile recommended`` (8+ CPUs, 32 GB) for preset profiles.

See :ref:`command-line-reference` for the full resource options.

My pipeline run is hanging.
----------------------------

This typically happens when Nextflow runs out of memory. Try one or more of the following:

- Increase the RAM available to Docker.
- Use ``-profile minimal`` to reduce resource usage.
- Set ``-e NXF_MAX_CPUS`` and ``-e NXF_MAX_MEMORY`` to match your available resources.
- Resume from the last checkpoint by re-running the same command (Nextflow resume is enabled by default).
