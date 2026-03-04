<p align="center">
  <img src="docs/_static/brainana_logo_side.png" alt="brainana logo" width="400">
</p>

# Brainana: a non-human primate MRI preprocessing pipeline

A non-human primate MRI volume and surface preprocessing pipeline for macaque neuroimaging data. Anatomical and functional processing, image registration, and surface reconstruction are wrapped into a reproducible workflow (FSL, ANTs, AFNI, FreeSurfer, Nextflow).

> **Status:** Research software, alpha stage – interfaces and defaults may still change.

Full documentation (installation, configuration, and detailed usage) can be found in the [documentation](https://brainana.readthedocs.io) page.

## Quick start (Docker)

The easiest way to run **brainana** is via the pre-built Docker image, which includes FSL, ANTs, AFNI, FreeSurfer, Nextflow, and a pre-configured Python environment.

1. **Pull (or build) the image**

   ```bash
   # Pull from Docker Hub
   docker pull liuxingyu987/brainana:latest

   # Or build from source (from the project root)
   docker build \
       --build-arg USER_ID=$(id -u) \
       --build-arg GROUP_ID=$(id -g) \
       -t liuxingyu987/brainana:latest .
   ```

2. **Prepare input, output, and FreeSurfer license**

   - BIDS dataset root on the host, e.g. `/data/my_bids_dataset`
   - Output directory, e.g. `/data/preprocessed`
   - FreeSurfer license file, e.g. `$HOME/freesurfer/license.txt`

3. **Run the pipeline**

   Omit ``--gpus all`` if no GPU is available.

   ```bash
   docker run -it --rm --gpus all \
       -v /data/my_bids_dataset:/input \
       -v /data/preprocessed:/output \
       -v $HOME/freesurfer/license.txt:/fs_license.txt \
       liuxingyu987/brainana:latest /input /output --freesurfer-license /fs_license.txt
   ```

This runs the full pipeline with built-in defaults. More examples are in **Usage** below and in the documentation.

## Usage

### Input data (BIDS)

**Brainana** expects a valid [BIDS](https://bids-specification.readthedocs.io/) dataset. A minimal example layout:

```text
./   # dataset root
└── sub-aaa
    ├── ses-bbb
    │   ├── anat
    │   │   ├── sub-aaa_ses-bbb_run-ccc_T1w.nii.gz
    │   │   └── sub-aaa_ses-bbb_run-ccc_T1w.json
    │   └── func
    │       ├── sub-aaa_ses-bbb_task-ddd_run-eee_bold.nii.gz
    │       └── sub-aaa_ses-bbb_task-ddd_run-eee_bold.json
```

Validate datasets with the [BIDS Validator](https://bids-standard.github.io/bids-validator/).

### FreeSurfer license

Surface reconstruction requires a FreeSurfer license:

- Obtain a license at [FreeSurfer](https://surfer.nmr.mgh.harvard.edu/registration.html).
- Mount it into the container and pass it to the pipeline:

  ```bash
  -v /path/to/license.txt:/fs_license.txt \
  ...
  liuxingyu987/brainana:latest /input /output --freesurfer-license /fs_license.txt
  ```

### Example Docker commands

Omit ``--gpus all`` if no GPU is available.

- **Full pipeline (default)**

  ```bash
  docker run -it --rm --gpus all \
      -v <bids_dir>:/input \
      -v <output_dir>:/output \
      -v <path/to/license.txt>:/fs_license.txt \
      liuxingyu987/brainana:latest /input /output --freesurfer-license /fs_license.txt
  ```

- **Custom configuration** (YAML via ``--config``; generate one with the configuration generator in the documentation)

  ```bash
  docker run -it --rm --gpus all \
      -v <bids_dir>:/input \
      -v <output_dir>:/output \
      -v <path/to/license.txt>:/fs_license.txt \
      -v <path/to/config.yaml>:/config.yaml \
      liuxingyu987/brainana:latest /input /output \
          --freesurfer-license /fs_license.txt \
          --config /config.yaml
  ```

For the full command-line reference, see the documentation.

## Outputs

Directory layout and file naming are described in the outputs section of the documentation.

## Citation

If you use **Brainana**, please cite:

> Brainana — a non-human primate MRI volume and surface preprocessing pipeline (in preparation).

Please also cite the toolboxes **Brainana** uses (FSL, ANTs, AFNI, FreeSurfer, FastSurfer, FireANTs, and any macaque templates). Detailed references are in the pipeline output (e.g. the QC report).

## License

Copyright (c) the Brainana Developers. Licensed under the GNU Affero General Public License v3 (AGPL-3.0). See [LICENSE](LICENSE) for the full text. Some dependencies (e.g. FreeSurfer) have their own licenses; you must comply with those as well.

## Caveats and tips

- **GPU availability**: Optional. The image runs on CPU or GPU; output quality is the same, only speed and resource use differ.
- **Memory and disk**: Large image dimensions may require substantial RAM and disk; see the documentation for resource profiles.
- **BIDS**: Non-BIDS or invalid datasets may not process correctly. Running the [BIDS Validator](https://bids-standard.github.io/bids-validator/) first is recommended.
- **FreeSurfer license**: Surface reconstruction runs only with a valid license; the rest of the pipeline runs regardless.
