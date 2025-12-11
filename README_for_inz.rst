=============
banana
=============

A Python package for preprocessing and registration of macaque neuroimaging data with BIDS dataset support.

---
Installation
------------

Python Requirements:
    - Python >= 3.11
    - Install package: ``pip install -e .`` (from project root)
    - Python dependencies are automatically installed via pyproject.toml:
      * nibabel, numpy, scipy, matplotlib, pandas
      * torch, torchvision (for FastSurferCNN)
      * pyyaml, joblib, tqdm, packaging

External Dependencies:
    Required:
    - FSL (>=6.0): Set FSLDIR environment variable
    - ANTs (>=2.3): Set ANTSPATH environment variable  
    - AFNI (>=20.0): Set AFNI_HOME environment variable
    - FreeSurfer (>=7.4.1): Set FREESURFER_HOME environment variable

Environment Setup:
    export FSLDIR=/usr/local/fsl
    export AFNI_HOME=/usr/local/afni
    export ANTSPATH=/usr/local/ants/bin/
    export FREESURFER_HOME=/usr/local/freesurfer
    export PATH=$FSLDIR/bin:$AFNI_HOME:$ANTSPATH:$FREESURFER_HOME/bin:$PATH

---
Usage
-----

**Step 1: Generate Configuration File (optional)**

The configuration file is optional, it will use the default config if not provided. 
But it is recommended to generate one using the config generator:

.. code-block:: bash

    python -m macacaMRIprep.config.config_generator_cli --dataset-dir /path/to/bids_dataset

This launches a web-based config generator that will help you create a customized configuration file. 
Alternatively, you can copy and modify the default config from ``macacaMRIprep/config/defaults.yaml``.

**Step 2: Run Preprocessing Pipeline**

Basic usage:

.. code-block:: bash

    macacaMRIprep-preproc /path/to/bids_dataset /path/to/output_dir --config /path/to/config_file

--------------
Code Structure
--------------

Important files and directories:

banana/
├── macacaMRIprep/              # Main package
│   ├── cli/
│   │   └── preproc.py          # Main CLI entry point (macacaMRIprep-preproc command)
│   ├── config/
│   │   ├── defaults.yaml       # Default configuration parameters
│   │   ├── config_generator_cli.py  # Web-based config generator
│   │   └── config.py           # Configuration loading and validation
│   ├── workflow/
│   │   ├── bids_processor.py   # BIDS dataset processor (coordinates entire dataset processing)
│   │   ├── anat2template.py    # Anatomical preprocessing workflow (bias correction, skull stripping, registration)
│   │   ├── func2target.py      # Functional preprocessing workflow (slice timing, motion correction, registration)
│   │   └── base.py             # Base workflow class
│   ├── operations/
│   │   ├── preprocessing.py    # Core preprocessing operations (slice timing, motion correction, despike)
│   │   ├── registration.py     # ANTs-based registration operations
│   │   └── pipeline.py         # Pipeline orchestration
│   ├── utils/
│   │   ├── bids.py             # BIDS file parsing and metadata handling
│   │   ├── templates.py       # Template resolution and management
│   │   └── mri.py              # MRI file utilities
│   └── quality_control/
│       ├── reports.py          # QC report generation
│       └── snapshots.py        # QC snapshot creation
├── FastSurferCNN/              # Skull stripping CNN models
│   ├── inference/
│   │   └── skullstripping.py   # FastSurferCNN skull stripping implementation
│   └── models/
│       └── networks.py         # U-Net architecture
├── FastSurferRecon/            # Surface reconstruction (FreeSurfer-based)
└── templatezoo/                # Template files (NMT2Sym at various resolutions)

**Key Workflow:**
1. ``bids_processor.py``: Discovers BIDS files, creates processing jobs, manages dependencies
2. ``anat2template.py``: Processes T1w images (bias correction → skull stripping → registration to template)
3. ``func2target.py``: Processes BOLD images (slice timing → motion correction → despike → registration)
4. Two-phase processing: All anatomical jobs first, then all functional jobs (handles cross-session dependencies)

**Processing Pipelines that specify how the registration is performed:**
- ``func2anat2template`` (default): Functional → Anatomical → Template
- ``anat2template``: Anatomical → Template only
- ``func2template``: Functional → Template (direct registration)

---
Test Dataset
------------

Test dataset, config file, and preprocessed data are available at: 
``macacaMRI/testing_dataset`` on Hugging Face.

---
TODO
----

1. Dockerize: Create Docker container with all dependencies
2. Resource management: Memory, CPU, disk, network monitoring and limits
3. Workflow optimization: Enhanced parallel processing, caching, resumption (refer to deepprep style using workflow)