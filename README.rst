=============
macacaMRIprep
=============

.. image:: https://img.shields.io/badge/python-3.8+-blue.svg
   :target: https://python.org
   :alt: Python 3.8+

.. image:: https://img.shields.io/badge/license-MIT-green.svg
   :target: https://github.com/yourusername/macacaMRIprep/blob/main/LICENSE
   :alt: MIT License

A comprehensive Python package for preprocessing and registration of macaque neuroimaging data. This package provides robust, reproducible preprocessing workflows specifically designed for non-human primate neuroimaging research with **BIDS dataset support** and **sophisticated dependency management**.

🚀 Key Features
---------------

**🧠 BIDS-First Approach**
* **Complete BIDS dataset processing**: Process entire datasets with automatic file discovery
* **Cross-session dependency handling**: Anatomical data in one session, functional in another
* **Multi-run T1w synthesis**: Automatic coregistration and averaging of multiple T1w acquisitions
* **Systematic output organization**: Maintains BIDS derivatives structure

**⚡ Advanced Processing Capabilities** 
* **Dependency-safe parallel processing**: Two-phase approach (anatomical first, then functional)
* **Complete preprocessing pipeline**: Slice timing correction, motion correction, despiking, skull stripping, bias field correction
* **Multi-stage registration**: Linear and non-linear registration to template spaces with ANTs
* **Flexible pipeline configurations**: func2anat2template, func2anat, func2template

**🔧 Robust Architecture**
* **Modular design**: Use individual components or complete workflows
* **Comprehensive logging**: Detailed logging with step-specific log files
* **Configuration system**: Flexible JSON-based configuration with validation
* **Quality control**: Automated generation of quality control reports and snapshots
* **Error handling**: Robust error handling with cleanup and recovery options

**🖥️ User-Friendly Interface**
* **Command-line interface**: Easy-to-use CLI with extensive BIDS filtering options
* **Python API**: Programmatic access for custom workflows
* **Cross-platform**: Works on Linux, macOS, and Windows

📋 Table of Contents
-------------------

* `Installation`_
* `Quick Start`_
* `Usage`_
* `Configuration`_
* `API Reference`_
* `Examples`_
* `Troubleshooting`_
* `Contributing`_
* `Citation`_
* `License`_

🔧 Installation
---------------

Prerequisites
~~~~~~~~~~~~~

Before installing macacaMRIprep, ensure you have the following external tools installed:

**Required External Dependencies:**

* **FSL** (≥6.0): `FSL Installation Guide <https://fsl.fmrib.ox.ac.uk/fsl/fslwiki/FslInstallation>`_
* **ANTs** (≥2.3): `ANTs Installation Guide <http://stnava.github.io/ANTs/>`_
* **AFNI** (≥20.0): `AFNI Installation Guide <https://afni.nimh.nih.gov/pub/dist/doc/htmldoc/background_install/main_toc.html>`_

**Optional Dependencies:**

* **JIP**: For enhanced registration (set ``JIP_HOME`` environment variable)
* **Macaque UNet Model**: For skull stripping (set ``MACAQUE_SS_UNET`` environment variable)

Environment Setup
~~~~~~~~~~~~~~~~~

Set the following environment variables:

.. code-block:: bash

    # Required
    export FSLDIR=/usr/local/fsl
    export AFNI_HOME=/usr/local/afni
    export ANTSPATH=/usr/local/ants/bin/
    
    # Optional
    export JIP_HOME=/usr/local/jip-Linux-x86_64
    export MACAQUE_SS_UNET=/path/to/macaque/unet/model

    # Add to PATH
    export PATH=$FSLDIR/bin:$AFNI_HOME:$ANTSPATH:$PATH

Install macacaMRIprep
~~~~~~~~~~~~~~~~~~~~

**Option 1: Install from PyPI (recommended)**

.. code-block:: bash

    pip install macacaMRIprep

**Option 2: Install from source**

.. code-block:: bash

    git clone https://github.com/yourusername/macacaMRIprep.git
    cd macacaMRIprep
    pip install -e .

**Option 3: Development installation**

.. code-block:: bash

    git clone https://github.com/yourusername/macacaMRIprep.git
    cd macacaMRIprep
    pip install -e ".[dev,docs]"

Verify Installation
~~~~~~~~~~~~~~~~~~

.. code-block:: bash

    macacaMRIprep-preproc --list-templates
    macacaMRIprep-preproc /path/to/bids /path/to/output --template NMT2Sym:res-1 --check-only

This will verify that all dependencies are correctly installed and accessible.

🚀 Quick Start
--------------

**Process entire BIDS dataset:**

.. code-block:: bash

    macacaMRIprep-preproc \
        /path/to/your/bids/dataset \
        /path/to/your/output/directory \
        --pipeline func2anat2template \
        --template NMT2Sym:res-1

**Process specific subjects with parallel processing:**

.. code-block:: bash

    macacaMRIprep-preproc \
        /path/to/your/bids/dataset \
        /path/to/your/output/directory \
        --template NMT2Sym:res-1 \
        --pipeline func2template \
        --subjects 032100 032097 \
        --n-procs 4

**Anatomical processing only:**

.. code-block:: bash

    macacaMRIprep-preproc \
        /path/to/your/bids/dataset \
        /path/to/your/output/directory \
        --template NMT2Sym:res-1 \
        --anat-only \
        --n-procs 4

**Process specific sessions and tasks:**

.. code-block:: bash

    macacaMRIprep-preproc \
        /path/to/your/bids/dataset \
        /path/to/your/output/directory \
        --template NMT2Sym:res-1 \
        --sessions 001 002 \
        --tasks resting auditory

📖 Usage
--------

Command Line Interface
~~~~~~~~~~~~~~~~~~~~~

The main command-line tool is ``macacaMRIprep-preproc`` for BIDS dataset processing:

.. code-block:: bash

    macacaMRIprep-preproc <dataset_dir> <output_dir> [OPTIONS]

**Required Arguments:**

* ``dataset_dir``: Path to BIDS dataset root directory
* ``output_dir``: Path to output derivatives directory

**Template Specification:**

* ``--template``: Template specification (e.g., 'NMT2Sym:res-1' or 'NMT2Sym:res-1:brainWoCerebellumBrainstem')

**BIDS Entity Filtering:**

* ``--subjects``: List of subject IDs to process (e.g., 032100 032097)
* ``--sessions``: List of session IDs to process (e.g., 001 002)
* ``--tasks``: List of task names to process (e.g., resting auditory)
* ``--runs``: List of run numbers to process (e.g., 01 02)

**Processing Modes:**

* ``--anat-only``: Process anatomical data only
* ``--func-only``: Process functional data only (requires anatomical dependencies)
* ``--n-procs``: Number of parallel processes (uses dependency-safe two-phase processing)

**Configuration:**

* ``--config``: Configuration file (JSON format)
* ``--working-dir``: Working directory for intermediate files

**See all options:**

.. code-block:: bash

    macacaMRIprep-preproc --help

Python API
~~~~~~~~~~

**BIDS Dataset Processing (Recommended):**

.. code-block:: python

    from macacaMRIprep.workflow.bids_processor import BIDSDatasetProcessor
    
    # Initialize BIDS dataset processor
    processor = BIDSDatasetProcessor(
        dataset_dir="/path/to/your/bids/dataset",
        output_dir="/path/to/your/output/directory"
    )
    
    # Process entire dataset
    results = processor.run_dataset(
        run_anat=True,
        run_func=True,
        n_procs=4  # Parallel processing with dependency management
    )
    
    print(f"Processing completed: {results['completed_jobs']}/{results['total_jobs']} jobs")

**Individual Component Usage:**

.. code-block:: python

    from macacaMRIprep.workflow.anat2template import AnatomicalProcessor
    from macacaMRIprep.workflow.func2target import FunctionalProcessor
    from macacaMRIprep.config import get_config
    
    # Anatomical processing
    anat_processor = AnatomicalProcessor(
        anat_file="path/to/sub-001_T1w.nii.gz",
        output_dir="path/to/output/anat",
        working_dir="path/to/working",
        template_spec="NMT2Sym:res-1",
        config=get_config().to_dict()
    )
    anat_result = anat_processor.run()
    
    # Functional processing (func2anat2template pipeline)
    func_processor = FunctionalProcessor(
        func_file="path/to/sub-001_task-rest_bold.nii.gz",
        target_file=anat_result["imagef_preprocessed"],  # Use anatomical result
        output_dir="path/to/output/func",
        working_dir="path/to/working",
        config=get_config().to_dict(),
        target_type="anat",
        target2template=True,
        template_spec="NMT2Sym:res-1"
    )
    func_result = func_processor.run()

⚙️ Configuration
----------------

macacaMRIprep uses JSON configuration files for detailed control over processing parameters.

Basic Configuration
~~~~~~~~~~~~~~~~~~

.. code-block:: json

    {
        "template": {
            "output_space": "NMT2Sym:res-1"
        },
        "anat": {
            "bias_correction": {
                "enabled": true,
                "algorithm": "N4BiasFieldCorrection"
            },
            "skullstripping": {
                "enabled": true,
                "method": "unet"
            }
        },
        "func": {
            "slice_timing_correction": {
                "enabled": false,
                "repetition_time": null
            },
            "motion_correction": {
                "enabled": true,
                "dof": 6,
                "ref_vol": "mid"
            },
            "despike": {
                "enabled": true,
                "c1": 5,
                "c2": 10
            }
        }
    }

Advanced Configuration
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: json

    {
        "general": {
            "pipeline_name": "func2anat2template",
            "verbose": 2,
            "overwrite": true
        },
        "registration": {
            "enabled": true,
            "func2template_nonlin": false,
            "anat2template_nonlin": true,
            "interpolation": "LanczosWindowedSinc",
            "rigid": {
                "enabled": true,
                "gradient_step": ["0.1"],
                "metric": ["MI[fixed,moving,1,32,regular,0.25]"],
                "shrink": "8x4x2x1",
                "convergence": "[1000x500x250x100,1e-6,10]"
            },
            "syn": {
                "enabled": true,
                "gradient_step": ["0.1,3,0"],
                "metric": [
                    "mattes[fixed,moving,0.5,32,regular,0.3]",
                    "cc[fixed,moving,0.5,4,regular,0.3]"
                ]
            }
        }
    }

Pipeline Configurations
~~~~~~~~~~~~~~~~~~~~~~

macacaMRIprep supports three main pipeline configurations:

1. **func2anat2template** (default): Functional → Anatomical → Template
2. **func2anat**: Functional → Anatomical (stop at anatomical space)
3. **func2template**: Functional → Template (direct registration)

Set via configuration:

.. code-block:: json

    {
        "general": {
            "pipeline_name": "func2anat2template"
        }
    }

🔄 Caching and Resumption
-------------------------

macacaMRIprep includes robust caching and resumption capabilities to handle long-running processing jobs and interruptions.

Automatic Caching
~~~~~~~~~~~~~~~~~

**Immediate Job Completion Tracking:**
* Jobs are stamped as completed immediately when they finish processing
* Cache is saved to disk after each job completion
* No progress is lost even if processing is interrupted mid-batch

**Cache Location:**
* Cache file: ``<output_dir>/processing_cache.json``
* Contains job completion status and generated file lists
* Automatically created and maintained

**Cache Validation:**
* Optional output file verification for cached completion status
* Warns if files are missing but preserves completion status
* Configurable via ``check_outputs`` parameter

Resumption Support
~~~~~~~~~~~~~~~~~

**Automatic Resumption:**
* Processing automatically resumes from where it left off
* Completed jobs are skipped based on cache status
* No manual intervention required

**Resumption Examples:**

.. code-block:: bash

    # Start processing (will create cache)
    macacaMRIprep-preproc /path/to/bids /path/to/output --template NMT2Sym:res-1
    
    # Interrupt processing (Ctrl+C)
    # ... processing interrupted ...
    
    # Resume processing (automatically skips completed jobs)
    macacaMRIprep-preproc /path/to/bids /path/to/output --template NMT2Sym:res-1

**Force Reprocessing:**

.. code-block:: bash

    # Overwrite existing outputs and reprocess all jobs
    macacaMRIprep-preproc /path/to/bids /path/to/output --template NMT2Sym:res-1 --overwrite

Cache Management
~~~~~~~~~~~~~~~

**Python API Cache Control:**

.. code-block:: python

    from macacaMRIprep.workflow.bids_processor import BIDSDatasetProcessor
    
    processor = BIDSDatasetProcessor(dataset_dir="/path/to/bids", output_dir="/path/to/output")
    
    # Check if specific job is completed
    job = processor.discover_processing_jobs(subs=["001"])[0]
    is_completed = processor.check_job_completion(job, use_cache=True, verify_outputs=True)
    
    # Clear cache for specific jobs
    processor.clear_cache(job_ids=["sub-001_ses-01_anat"])
    
    # Clear entire cache
    processor.clear_cache()

**Cache Configuration:**

.. code-block:: json

    {
        "caching": {
            "check_outputs": true
        },
        "general": {
            "overwrite": false
        }
    }

**Cache File Format:**

.. code-block:: json

    {
        "cache_key_hash": {
            "job_id": "sub-001_ses-01_anat",
            "is_completed": true,
            "last_checked": 1703123456.789,
            "generated_files": [
                "/path/to/output/sub-001/anat/sub-001_desc-preproc_T1w.nii.gz",
                "/path/to/output/sub-001/anat/sub-001_desc-brain_mask.nii.gz"
            ]
        }
    }

📚 API Reference
---------------

Core Modules
~~~~~~~~~~~

**BIDS Processing**

* ``BIDSDatasetProcessor``: Complete BIDS dataset processing with dependency management
* ``ProcessingJob``: Individual processing job representation
* ``BIDSFile``: BIDS file metadata representation

**Individual Processors**

* ``AnatomicalProcessor``: Anatomical preprocessing and template registration
* ``FunctionalProcessor``: Functional preprocessing with flexible target registration
* ``anat2template``: Direct anatomical to template registration
* ``func2target``: Functional to target (anatomical or template) registration

**Configuration**

* ``get_config()``: Get default configuration
* ``load_config()``: Load configuration from file
* ``validate_config()``: Validate configuration parameters
* ``update_config_from_bids_metadata()``: Update config from BIDS metadata

**Utilities**

* ``setup_logging()``: Configure logging system
* ``resolve_template()``: Resolve template specifications
* ``parse_bids_entities()``: Parse BIDS entity information

🎯 Examples
-----------

Example 1: Basic BIDS Dataset Processing
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    from macacaMRIprep.workflow.bids_processor import BIDSDatasetProcessor
    
    # Process entire dataset
    processor = BIDSDatasetProcessor(
        dataset_dir="/data/bids_dataset",
        output_dir="/data/derivatives/macacaMRIprep"
    )
    
    results = processor.run_dataset()
    print(f"Processed {results['completed_jobs']} jobs in {results['duration_formatted']}")

Example 2: Parallel Processing with Entity Filtering
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    # Process specific subjects with parallel processing
    processor = BIDSDatasetProcessor(
        dataset_dir="/data/bids_dataset",
        output_dir="/data/derivatives/macacaMRIprep",
        working_dir="/tmp/macacaMRIprep_work"
    )
    
    results = processor.run_dataset(
        subs=["032100", "032097"],
        sess=["001", "002"],
        tasks=["resting"],
        run_anat=True,
        run_func=True,
        n_procs=4  # Dependency-safe parallel processing
    )

Example 3: Custom Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    from macacaMRIprep.config import get_config
    
    # Create custom configuration
    config = get_config().to_dict()
    config["template"]["output_space"] = "NMT2Sym:res-025"  # Higher resolution
    config["func"]["slice_timing_correction"]["enabled"] = True
    config["func"]["smoothing"]["enabled"] = True
    config["func"]["smoothing"]["fwhm"] = 2.0
    
    processor = BIDSDatasetProcessor(
        dataset_dir="/data/bids_dataset",
        output_dir="/data/derivatives/macacaMRIprep",
        config=config
    )
    
    results = processor.run_dataset()

Example 4: Job Discovery and Inspection
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    # Discover what would be processed without running
    processor = BIDSDatasetProcessor(
        dataset_dir="/data/bids_dataset",
        output_dir="/data/derivatives/macacaMRIprep"
    )
    
    jobs = processor.discover_processing_jobs(subs=["032100"])
    
    for job in jobs:
        print(f"{job.job_id}:")
        print(f"  Anatomical files: {len(job.anat_files)}")
        print(f"  Functional files: {len(job.func_files)}")
        
        for anat_file in job.anat_files:
            print(f"    T1w: {anat_file.path} (run: {anat_file.run})")

🔧 Troubleshooting
------------------

Common Issues
~~~~~~~~~~~~

**No processing jobs found**

* Check BIDS dataset structure: ensure dataset_description.json exists
* Verify subject/session/task/run filtering arguments
* Check file naming follows BIDS convention

**Functional processing fails with "target file not found"**

* Ensure anatomical processing completed successfully
* Check that anatomical and functional data have compatible BIDS entities
* For cross-session dependencies, run anatomical processing first

**Memory issues with parallel processing**

* Reduce ``n_procs`` (recommendation: 8GB+ RAM per process)
* Use ``--working-dir`` on fast local storage
* Consider ``--anat-only`` first, then ``--func-only``

**Template not found**

* List available templates: ``macacaMRIprep-preproc --list-templates``
* Check template specification format: ``TEMPLATE_NAME:RESOLUTION[:DESCRIPTION]``
* Verify template files are installed correctly

Debug Mode
~~~~~~~~~

Enable detailed logging for troubleshooting:

.. code-block:: bash

    macacaMRIprep-preproc /path/to/bids /path/to/output \
        --template NMT2Sym:res-1 \
        --verbose \
        --subjects 032100

Check processing logs:

.. code-block:: bash

    # Main processing log
    cat output_dir/logs/processing.log
    
    # Individual worker logs (for parallel processing)
    cat output_dir/logs/worker_*.log
    
    # Processing summary
    cat output_dir/processing_summary.json

Cross-Session Dependencies
~~~~~~~~~~~~~~~~~~~~~~~~~

macacaMRIprep automatically handles cross-session dependencies (e.g., anatomical data in session 1, functional data in session 2) using a two-phase processing approach:

1. **Phase 1**: Process ALL anatomical data across ALL sessions
2. **Phase 2**: Process ALL functional data across ALL sessions

This ensures functional data can find required anatomical dependencies regardless of session structure.

Getting Help
~~~~~~~~~~~

1. Check the documentation: [link to full documentation]
2. Search existing issues: [GitHub issues link]  
3. Create a new issue: [GitHub new issue link]
4. Join our discussion forum: [forum link]

🤝 Contributing
---------------

We welcome contributions! Please see our `Contributing Guide <CONTRIBUTING.md>`_ for details.

**Development Setup:**

.. code-block:: bash

    git clone https://github.com/yourusername/macacaMRIprep.git
    cd macacaMRIprep
    pip install -e ".[dev]"
    pre-commit install

**Running Tests:**

.. code-block:: bash

    pytest tests/
    pytest --cov=macacaMRIprep tests/

📄 Citation
-----------

If you use macacaMRIprep in your research, please cite:

.. code-block:: bibtex

    @software{macacaMRIprep,
        author = {Your Name},
        title = {macacaMRIprep: A Python package for preprocessing and registration of macaque neuroimaging data},
        year = {2024},
        url = {https://github.com/yourusername/macacaMRIprep},
        version = {1.0.0}
    }

📝 License
----------

This project is licensed under the MIT License - see the `LICENSE <LICENSE>`_ file for details.

🔗 Links
--------

* **Documentation**: https://macacaMRIprep.readthedocs.io/
* **Source Code**: https://github.com/yourusername/macacaMRIprep
* **Issue Tracker**: https://github.com/yourusername/macacaMRIprep/issues
* **PyPI Package**: https://pypi.org/project/macacaMRIprep/

📧 Contact
----------

For questions and support:

* **Email**: your.email@example.com
* **Twitter**: @yourusername
* **Mastodon**: @yourusername@mastodon.social

---

*macacaMRIprep is developed and maintained by the [Your Lab Name] at [Your Institution].*

