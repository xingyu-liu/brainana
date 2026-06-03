Brainana Lite
=============

Brainana Lite is a lightweight, easy-to-run workflow for quick volumetric T1w preprocessing on a single subject. It runs in **Jupyter** (local) or **Google Colab** and does not require Docker.

Compared with the full Brainana release, Brainana Lite:

- Covers **T1w only** (no functional MRI, no cortical surface reconstruction)
- Uses a notebook-driven setup (``brainana[lite]``) instead of the Nextflow Docker pipeline
- Is suited for exploration and small jobs; for production-grade preprocessing, multi-modality data, surfaces, and the full QC suite, use :doc:`installation` and :doc:`usage_notes`.

Processing steps include BIDS organization, optional T1w synthesis, conformation, brain extraction and tissue segmentation, bias field correction, template registration, and atlas backprojection.

How to run
----------

Follow the interactive tutorial on GitHub:

`BrainanaLite.ipynb <https://github.com/xingyu-liu/brainana/blob/main/examples/BrainanaLite.ipynb>`_

It includes setup, configuration, preprocessing, and QC. Open it on GitHub or download it for local Jupyter; on Colab, open from GitHub or upload—the runtime (Colab vs local) is detected automatically.
