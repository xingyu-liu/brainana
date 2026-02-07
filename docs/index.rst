brainana
=======

**brainana** is a preprocessing and registration pipeline for macaque neuroimaging data with BIDS dataset support. It provides anatomical and (optionally) functional processing, surface reconstruction (FreeSurfer/FastSurfer), and template registration.

.. note::
   For a quick start with Docker (recommended):

   .. code-block:: bash

      docker run -it --rm --gpus all \
        -v <bids_dir>:/input \
        -v <output_dir>:/output \
        -v <path/to/license.txt>:/fs_license.txt \
        xxxlab/brainana:latest

Contents
--------

.. toctree::
   :maxdepth: 2
   :caption: User guide

   installation
   usage_local
   command_line
   outputs
   processing
   faq

.. toctree::
   :maxdepth: 1
   :caption: Other

   other_docs

Indices and tables
------------------

* :ref:`genindex`
* :ref:`search`
