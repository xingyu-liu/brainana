<p align="center">
  <img src="docs/_static/brainana_logo_side.png" alt="Brainana logo" width="500">
</p>

# Brainana: a unified preprocessing framework for macaque MRI

[![Documentation](https://readthedocs.org/projects/brainana/badge/?version=stable)](https://brainana.readthedocs.io/en/stable/)
[![Docker](https://img.shields.io/badge/docker-liuxingyu987%2Fbrainana-brightgreen.svg?logo=docker)](https://hub.docker.com/r/liuxingyu987/brainana/tags/)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL--v3-blue.svg)](LICENSE)

<p align="center">
  <img src="docs/_static/pipeline_details/brainana_unified_framework.png" alt="Brainana pipeline overview schematic" width="100%">
</p>

**Brainana** provides anatomical and functional (fMRI) processing, image registration, surface reconstruction, fMRIPrep-compatible confound regressors, and HTML QC reports for macaque neuroimaging data in a reproducible workflow (FSL, ANTs, AFNI, FreeSurfer, Nextflow).

> **Status:** Research software, beta stage – feature-complete for main workflows; bugs and edge cases are still possible.

## Documentation

Brainana documentation is hosted on **[Read the Docs](https://brainana.readthedocs.io/en/stable/)**.


Start with [Installation](https://brainana.readthedocs.io/en/stable/installation.html), then [Usage notes](https://brainana.readthedocs.io/en/stable/usage_notes.html).

Additional references:
- [Try a demo](https://brainana.readthedocs.io/en/stable/demo.html) — run the full pipeline on the bundled [`examples/dataset_example/`](examples/dataset_example) dataset
- [Brainana Lite](https://brainana.readthedocs.io/en/stable/brainana_lite.html) (Jupyter / Colab T1w workflow)
- [Processing details](https://brainana.readthedocs.io/en/stable/processing.html)
- [Outputs](https://brainana.readthedocs.io/en/stable/outputs.html)
- [FAQ](https://brainana.readthedocs.io/en/stable/faq.html)

## Brainana Lite

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/xingyu-liu/brainana/blob/main/examples/BrainanaLite.ipynb)

Lightweight volumetric T1w preprocessing for a single subject (no functional MRI, no surfaces). Run interactively in Jupyter or Google Colab—no Docker required.

- **Notebook:** [`examples/BrainanaLite.ipynb`](examples/BrainanaLite.ipynb) — on Colab, use **Run all**; the first pass may restart the runtime once, then run again.

For the full multi-modality pipeline with surfaces and QC reports, use the installation above for docker.

## Citation

If you use **Brainana**, please cite:

> [Brainana: an end-to-end preprocessing framework for macaque neuroimaging](https://www.biorxiv.org/content/10.64898/2026.06.03.729972v1.abstract)

Please also cite the toolboxes **Brainana** uses (FSL, ANTs, AFNI, FreeSurfer, FastSurfer, FireANTs, and any macaque templates). Detailed references can be found in the QC report.

## License

Copyright (c) the Brainana Developers. Licensed under the GNU Affero General Public License v3 (AGPL-3.0). See [LICENSE](LICENSE) for the full text. Some dependencies (e.g. FreeSurfer) have their own licenses; you must comply with those as well.
