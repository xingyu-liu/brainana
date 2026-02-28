#!/usr/bin/env python3
"""Quick test: load a YAML config (e.g. with tabs) via brainana's loader."""

import sys
from pathlib import Path

# Run from brainana repo root: python tests/test_config_load.py [config.yaml]
_repo = Path(__file__).resolve().parent.parent
_src = _repo / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from nhp_mri_prep.config.config_io import load_yaml_config
from nhp_mri_prep.steps.bids_discovery import _normalize_to_list

CONFIG_PATH = Path(
    "/mnt/DataDrive2/macaque/data_preproc/macaque_mri/PRIME-DE_brainana/site-uwmadison/config.yaml"
)


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else CONFIG_PATH
    if not path.exists():
        print(f"ERROR: File not found: {path}", file=sys.stderr)
        sys.exit(1)
    try:
        config = load_yaml_config(path)
        print(f"OK: Loaded config from {path}")
        print(f"    Top-level keys: {list(config.keys())}")
        if config:
            # Show a bit of content
            for k, v in list(config.items())[:5]:
                if isinstance(v, dict):
                    print(f"    {k}: <dict with keys {list(v.keys())[:6]}...>")
                else:
                    print(f"    {k}: {v}")

        subjects = config.get("bids_filtering", {}).get("subjects")
        print(f"bids_filtering.subjects = {subjects!r}")

        # Test that _normalize_to_list turns string into list (as in bids_discovery)
        subjects_list = _normalize_to_list(subjects)
        print(f"After _normalize_to_list: {subjects_list!r}")
        assert subjects_list is None or isinstance(subjects_list, list), "subjects should normalize to list or None"
        if subjects_list:
            assert all(isinstance(s, str) for s in subjects_list), "each subject should be a string"

        sys.exit(0)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
