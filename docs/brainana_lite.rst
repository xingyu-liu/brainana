:og:description: Brainana Lite is a notebook-based (Jupyter/Google Colab) volumetric T1w preprocessing workflow for a single macaque subject — no Docker or Nextflow required.

.. meta::
   :description: Brainana Lite is a notebook-based (Jupyter/Google Colab) volumetric T1w preprocessing workflow for a single macaque subject — no Docker or Nextflow required.
   :keywords: Brainana Lite, macaque T1w preprocessing, Colab neuroimaging, Jupyter, single subject

Brainana Lite
=============

Brainana Lite is a **notebook-based** workflow for volumetric T1w preprocessing on macaque MRI. Run it in **Jupyter** or **Google Colab**—no Docker or Nextflow.

When to use Brainana Lite
-------------------------

- **Single subject, T1w only** — one macaque, anatomical T1w
- **No BIDS dataset required** — you only need nifti file(s) in a folder
- **No local system setup** — On Colab, a browser is enough
- **Quick, interactive runs** — trying a scan, teaching, or a one-off preprocess

Use the **full Brainana Docker pipeline** (:doc:`installation`, :doc:`usage_notes`) for production batch work, multiple modalities, surfaces, and the complete HTML QC suite.

What you get
------------

After **Run All**, derivatives are written in a **BIDS-styled** layout. In practice you receive:

- **Preprocessed T1w** in **individual (T1w) space** and in your chosen **template space** (skull-stripped brain volumes included)
- **Brain mask** and **atlas-based tissue segmentation** in individual space (e.g. ARM2), with a color lookup table
- **Standard macaque atlases** backprojected into **individual spaces** (T1w and scanner)
- **QC snapshot figures** (conformation, skull stripping, bias correction, segmentation, registration, and related checks)

Exact filenames and the output tree are printed in the notebook when preprocessing finishes. For the full Docker pipeline’s canonical layout, see :doc:`outputs`.

How to run
----------

For setup, folder layout, settings, GPU and Drive notes, and the full run-through, follow the notebook below.

- **Colab:** `Open in Colab <https://colab.research.google.com/github/xingyu-liu/brainana/blob/main/examples/BrainanaLite.ipynb>`_
- **GitHub:** `BrainanaLite.ipynb <https://github.com/xingyu-liu/brainana/blob/main/examples/BrainanaLite.ipynb>`_
- **Local:** ``examples/BrainanaLite.ipynb`` in the repository

Open the notebook, edit ``WORKING_DIR`` in the **USER SETTINGS** cell, then **Run All**. Colab vs local Jupyter is detected automatically.

Lite outputs are related to but not identical to the full pipeline layout; see :doc:`outputs` for the canonical Docker derivative structure.

See also
--------

- :doc:`installation`
- :doc:`processing`
- :doc:`outputs`
- :doc:`faq`
