FAQ and troubleshooting
=======================

Common questions and fixes when running brainana (especially with Docker).

General
-------

**Do I need to provide a config file?**  
No. In production Docker mode, built-in defaults are used. For custom settings, generate a config with the config generator (GUI), save it, mount it (e.g. ``-v /path/to/config.yaml:/config.yaml``), and pass ``--config /config.yaml`` as an extra argument.

**Can I run without a FreeSurfer license?**  
Anatomical and functional preprocessing will run, but surface reconstruction will fail. The container will warn if the license is missing. Get a free license from https://surfer.nmr.mgh.harvard.edu/registration.html and mount it with ``-v <path>:/fs_license.txt``.

Docker and GPU
--------------

**How do I enable GPU acceleration?**  
Add ``--gpus all`` to your ``docker run`` command. You need the `NVIDIA Container Toolkit <https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html>`_ installed on the host.

**How do I align Docker limits with Nextflow?**  
The container defaults to 8 CPUs and 20 GB for Nextflow. To cap the container to match: ``--memory 20g --cpus 8``. To give Nextflow more resources (e.g. for a larger run): ``-e NXF_MAX_CPUS=16 -e NXF_MAX_MEMORY=32g`` or use ``-profile recommended`` (e.g. 32 GB). See :doc:`usage_local` and :doc:`command_line`.

**“Cannot connect to X server” when running GUI tools.**  
On the host, run ``xhost +local:root``. Over SSH, use X11 forwarding (e.g. ``ssh -X`` or ``-Y``).

File permissions and user
-------------------------

**Output files are owned by root.**  
Run the container as your user so outputs match your host UID/GID:

.. code-block:: bash

   docker run ... --user $(id -u):$(id -g) \
       -e NXF_WORK=/tmp/nextflow-work \
       -e NXF_HOME=/tmp/nextflow-home \
       ...

See :doc:`usage_local` for the full example.

Pipeline and config
-------------------

**Where are logs?**  
Under ``output_dir/nextflow_reports/`` (e.g. ``nextflow_trace.txt``). Check that path for failed or aborted tasks.

**How do I run only a subset of subjects?**  
Use ``--subjects`` (and optionally ``--sessions``) when invoking the container or ``run_brainana.sh run main.nf``. Example: ``... /input /output --subjects sub-001 sub-002`` (syntax may depend on config; see :doc:`command_line`).

For more details on resources and tuning, see the internal doc ``docs/RESOURCE_CALIBRATION.md`` in the repository.
