#!/usr/bin/env python3
"""
Write a BIDS ``dataset_description.json`` at the derivatives root.

Invoked once from ``main.nf`` at run start (right after the effective config is
generated) so the output dataset advertises itself as a brainana derivative and
records the run's template source (bundled spec or custom template file path).

Usage:
    python3 write_dataset_description.py --output-dir DIR --config-file FILE

Always exits 0: a missing dataset_description must never turn a successful run
into a failure.
"""

import sys
import argparse
import logging
from pathlib import Path

# Add src/ to path for nhp_mri_prep imports (nextflow_scripts/ -> nhp_mri_prep -> src)
_src_dir = Path(__file__).resolve().parent.parent.parent
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("write_dataset_description")


def main() -> int:
    parser = argparse.ArgumentParser(description="Write dataset_description.json")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--config-file", required=True)
    args = parser.parse_args()

    try:
        from nhp_mri_prep.utils.nextflow import load_config
        from nhp_mri_prep.utils.templates import resolve_template
        from nhp_mri_prep.utils.sidecar import write_dataset_description

        config = load_config(args.config_file)
        output_space = (config.get("template") or {}).get("output_space")

        resolved_template_path = None
        if output_space:
            try:
                resolved_template_path = str(resolve_template(output_space))
            except Exception as e:  # unresolved/custom-missing: record spec only
                logger.warning(f"Could not resolve template '{output_space}': {e}")

        dd_path = write_dataset_description(
            args.output_dir,
            output_space=output_space,
            resolved_template_path=resolved_template_path,
        )
        logger.info(f"Wrote {dd_path}")
    except Exception as e:  # never fail the run over a dataset description
        logger.warning(f"Skipping dataset_description.json: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
