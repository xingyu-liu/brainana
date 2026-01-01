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
      * Core: nibabel, numpy, scipy, matplotlib, pandas, packaging
      * Deep learning: torch, torchvision, torchio (for FastSurferCNN and NHPskullstripNN)
      * Image processing: Pillow, scikit-image, SimpleITK
      * FastSurferCNN: yacs, h5py
      * FastSurferRecon: pydantic, lapy
      * BIDS support: pybids
      * Utilities: pyyaml, joblib, tqdm, psutil

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
│   │   ├── defaults.yaml       # Default configuration parameters (YAML format)
│   │   ├── config_generator_cli.py  # Web-based config generator
│   │   ├── config.py           # Configuration loading and validation
│   │   ├── config_io.py        # Configuration I/O operations
│   │   ├── config_validation.py # Configuration validation
│   │   └── bids_adapter.py    # BIDS metadata adapter
│   ├── workflow/
│   │   ├── bids_processor.py   # BIDS dataset processor (coordinates entire dataset processing)
│   │   ├── anat2template.py    # Anatomical preprocessing workflow (bias correction, skull stripping, registration)
│   │   ├── func2target.py      # Functional preprocessing workflow (slice timing, motion correction, registration)
│   │   └── base.py             # Base workflow class
│   ├── operations/
│   │   ├── preprocessing.py    # Core preprocessing operations (slice timing, motion correction, despike, skull stripping)
│   │   ├── registration.py     # ANTs-based registration operations
│   │   ├── validation.py      # Input/output validation
│   │   └── pipeline.py         # Pipeline orchestration
│   ├── utils/
│   │   ├── bids.py             # BIDS file parsing and metadata handling
│   │   ├── templates.py        # Template resolution and management
│   │   ├── mri.py              # MRI file utilities
│   │   ├── logger.py           # Logging utilities
│   │   └── system.py           # System utilities
│   ├── quality_control/
│   │   ├── reports.py          # QC report generation
│   │   ├── snapshots.py        # QC snapshot creation
│   │   └── mri_plotting.py     # MRI plotting utilities
│   ├── scripts/                # Utility scripts
│   │   ├── generate_snapshots_for_subject.py
│   │   └── [various utility scripts]
│   └── environment.py          # Environment and dependency checking
├── FastSurferCNN/              # Segmentation CNN models (for anatomical segmentation)
│   ├── inference/
│   │   ├── segmentation.py     # FastSurferCNN segmentation implementation
│   │   └── api.py              # Inference API
│   ├── models/
│   │   └── networks.py         # U-Net architecture
│   ├── atlas/                  # Atlas management (ARM2, ARM3)
│   ├── postprocessing/         # Post-segmentation processing
│   └── seg_statistics/        # Segmentation statistics and QC
├── NHPskullstripNN/           # Skull stripping neural network (for brain extraction)
│   ├── inference/
│   │   └── prediction.py       # Skull stripping prediction API
│   ├── model/
│   │   └── unet.py             # UNet2d model for brain extraction
│   ├── train/                  # Training pipeline
│   └── pretrained_model/      # Pretrained models (T1w, EPI, T2w)
├── FastSurferRecon/            # Surface reconstruction (FreeSurfer-based)
│   └── fastsurfer_recon/      # Surface reconstruction pipeline
└── templatezoo/                # Template files (NMT2Sym at various resolutions)

**Key Workflow:**
1. ``bids_processor.py``: Discovers BIDS files, creates processing jobs, manages dependencies, handles caching and resumption
2. ``anat2template.py``: Processes T1w images (reorient → conform → bias correction → skull stripping → registration to template)
3. ``func2target.py``: Processes BOLD images (slice timing → motion correction → despike → bias correction → skull stripping → registration)
4. Two-phase processing: All anatomical jobs first, then all functional jobs (handles cross-session dependencies)
5. Caching and resumption: Jobs are cached immediately upon completion, allowing safe resumption after interruptions

**Processing Pipelines that specify how the registration is performed:**
- ``func2anat2template`` (default): Functional → Anatomical → Template
- ``anat2template``: Anatomical → Template only
- ``func2template``: Functional → Template (direct registration)

**Skull Stripping Methods:**
- **FastSurferCNN**: Used for anatomical segmentation (multi-class segmentation)
- **NHPskullstripNN**: Used for brain extraction (binary mask generation) in functional data and conform step

---
Docker Usage
------------

We provide a pre-configured Docker image containing all external dependencies (FSL, ANTs, AFNI, FreeSurfer).

**Run Interactive Environment:**

.. code-block:: bash

    docker run -it --rm \
        --gpus all \
        --network host \
        --name macaca_dev \
        --user $(id -u):$(id -g) \
        --env="DISPLAY=$DISPLAY" \
        --env="QT_X11_NO_MITSHM=1" \
        --volume="/tmp/.X11-unix:/tmp/.X11-unix:rw" \
        --volume="$(pwd):/opt/banana" \
        --volume="$HOME/.cache/uv:/home/neuro/.cache/uv" \
        --volume="/home/yinzi/dataset/testing_dataset:/data" \
        --volume="/nvmessd/yinzi/banana/license.txt:/opt/freesurfer/license.txt" \
        --workdir="/opt/banana" \
        macacamriprep

For detailed Docker instructions, please refer to ``README_Docker.md``.

---
TODO
----

1. [Done] Dockerize: Create Docker container with all dependencies
2. Resource management: Memory, CPU, disk, network monitoring and limits
3. Workflow optimization: Enhanced parallel processing, caching, resumption (refer to deepprep style using workflow)