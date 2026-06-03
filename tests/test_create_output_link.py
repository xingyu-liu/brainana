"""Tests for gzip-safe NIfTI publishing in create_output_link."""

from pathlib import Path

import nibabel as nib
import numpy as np
import pytest

from nhp_mri_prep.utils.nextflow import _file_starts_with_gzip_magic, create_output_link


@pytest.fixture
def minimal_uncompressed_nii(tmp_path: Path) -> Path:
    path = tmp_path / "input.nii"
    data = np.zeros((4, 4, 4), dtype=np.float32)
    nib.save(nib.Nifti1Image(data, np.eye(4)), str(path))
    assert not _file_starts_with_gzip_magic(path)
    return path


@pytest.fixture
def minimal_compressed_nii_gz(tmp_path: Path) -> Path:
    path = tmp_path / "input.nii.gz"
    data = np.zeros((4, 4, 4), dtype=np.float32)
    nib.save(nib.Nifti1Image(data, np.eye(4)), str(path))
    assert _file_starts_with_gzip_magic(path)
    return path


def test_create_output_link_compresses_uncompressed_nii_to_nii_gz(
    minimal_uncompressed_nii: Path, tmp_path: Path
) -> None:
    dst = tmp_path / "sub-01_T1w.nii.gz"
    create_output_link(minimal_uncompressed_nii, dst)
    assert dst.exists()
    assert _file_starts_with_gzip_magic(dst)
    loaded = nib.load(str(dst))
    assert loaded.shape == (4, 4, 4)


def test_create_output_link_preserves_already_gzipped_nii_gz(
    minimal_compressed_nii_gz: Path, tmp_path: Path
) -> None:
    dst = tmp_path / "sub-01_T1w.nii.gz"
    create_output_link(minimal_compressed_nii_gz, dst)
    assert dst.exists()
    assert _file_starts_with_gzip_magic(dst)
    nib.load(str(dst))
