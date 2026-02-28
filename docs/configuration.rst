Configuration
=============

You can run brainana with built-in defaults and common options (e.g. ``--anat_only``, ``--output_space``) passed on the command line. For full control over pipeline options (anatomical and functional steps, registration, template, etc.), use a custom YAML config file and pass it with ``--config /path/to/config.yaml``. See :doc:`usage_local` (:ref:`command-line-reference`) for how to pass the config when using Docker or ``run_brainana.sh``.

Generate your own config
------------------------

A static HTML tool lets you set all options and download a valid config file. Open it from the built documentation or from the repository:

- **From the docs:** `Configuration generator <_static/config_generator.html>`_
- **From the repo:** open ``docs/_static/config_generator.html`` in a browser.

Save the generated YAML, then mount it into the container and pass ``--config /path/to/config.yaml`` (see :doc:`usage_local` and :doc:`faq`).
