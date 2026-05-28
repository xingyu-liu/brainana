<p align="center">
  <img src="docs/_static/brainana_logo_side.png" alt="Brainana logo" width="500">
</p>

# Brainana: a unified preprocessing framework for macaque MRI

<p align="center">
  <img src="docs/_static/pipeline_details/brainana_unified_framework.png" alt="Brainana pipeline overview schematic" width="100%">
</p>

**Brainana** provides anatomical and functional processing, image registration, and surface reconstruction for macaque neuroimaging data in a reproducible workflow (FSL, ANTs, AFNI, FreeSurfer, Nextflow).

> **Status:** Research software, beta stage – feature-complete for main workflows; bugs and edge cases are still possible.

## Documentation

Brainana documentation is hosted on **[Read the Docs](https://brainana.readthedocs.io/en/stable/)**.

- **Use [`stable`](https://brainana.readthedocs.io/en/stable/)** for the latest released behavior.
- **Use [`latest`](https://brainana.readthedocs.io/en/latest/)** for in-development docs that may be ahead of release.

Start with [Installation](https://brainana.readthedocs.io/en/stable/installation.html), then [Usage notes](https://brainana.readthedocs.io/en/stable/usage_notes.html).

Additional references:
- [Processing details](https://brainana.readthedocs.io/en/stable/processing.html)
- [Outputs](https://brainana.readthedocs.io/en/stable/outputs.html)
- [FAQ](https://brainana.readthedocs.io/en/stable/faq.html)
- [Changelog](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md)

## Citation

If you use **Brainana**, please cite:

> Brainana: a unified preprocessing framework for macaque MRI (in preparation).

Please also cite the toolboxes **Brainana** uses (FSL, ANTs, AFNI, FreeSurfer, FastSurfer, FireANTs, and any macaque templates). Detailed references can be found in the QC report.

## License

Copyright (c) the Brainana Developers. Licensed under the GNU Affero General Public License v3 (AGPL-3.0). See [LICENSE](LICENSE) for the full text. Some dependencies (e.g. FreeSurfer) have their own licenses; you must comply with those as well.
