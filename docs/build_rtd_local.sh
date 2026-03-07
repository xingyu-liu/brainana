#!/usr/bin/env bash
# Replicate Read the Docs build locally (docs-only: fast, no torch/SimpleITK etc.).
# Run from repository root:  bash docs/build_rtd_local.sh
set -e
cd "$(dirname "$0")/.."

# echo "=== 1. Creating virtualenv (Python 3.12 recommended, like RTD) ==="
# if command -v uv &>/dev/null; then
#   uv venv .rtd-venv --python 3.12 2>/dev/null || true
#   source .rtd-venv/bin/activate
#   uv pip install --upgrade pip setuptools
# else
#   python3.12 -m venv .rtd-venv 2>/dev/null || python3 -m venv .rtd-venv
#   source .rtd-venv/bin/activate
#   pip install --upgrade pip setuptools
# fi

# echo "=== 2. Docs-only install (same as .readthedocs.yaml build.commands) ==="
# pip install "sphinx>=7.0" "myst-parser>=2.0" "sphinx-rtd-theme>=2.0"
# pip install --no-deps .

echo "=== 3. Building Sphinx docs (config: docs/conf.py) ==="
sphinx-build -b html -c docs docs docs/_build

echo "=== Done. Open docs/_build/index.html in a browser. ==="


# after successful build, run the following commands to clean up:
# rm -rf docs/_build .rtd-venv 