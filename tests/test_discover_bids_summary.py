"""Unit tests for BIDS discovery console summary (inputs vs jobs)."""

from __future__ import annotations

import io
from contextlib import redirect_stdout
from typing import Any, Dict, List

from nhp_mri_prep.nextflow_scripts.discover_bids_for_nextflow import (
    _count_job_bids_inputs,
    _sum_job_bids_inputs,
    print_summary,
)


def test_count_job_bids_inputs_file_paths_list():
    job = {"file_paths": ["a.nii.gz", "b.nii.gz"]}
    assert _count_job_bids_inputs(job) == 2


def test_count_job_bids_inputs_single_file_path():
    assert _count_job_bids_inputs({"file_path": "a.nii.gz"}) == 1


def test_count_job_bids_inputs_empty_or_missing():
    assert _count_job_bids_inputs({}) == 0
    assert _count_job_bids_inputs({"file_paths": []}) == 0
    # Empty file_paths falls through; file_path still counts if present
    assert _count_job_bids_inputs({"file_paths": [], "file_path": "a.nii.gz"}) == 1


def test_sum_job_bids_inputs():
    jobs: List[Dict[str, Any]] = [
        {"file_paths": ["a.nii.gz", "b.nii.gz"]},
        {"file_path": "c.nii.gz"},
    ]
    assert _sum_job_bids_inputs(jobs) == 3


def _capture_summary(
    anat_jobs: List[Dict[str, Any]],
    func_jobs: List[Dict[str, Any]],
    anat_only: bool = False,
) -> str:
    buf = io.StringIO()
    with redirect_stdout(buf):
        print_summary(anat_jobs, func_jobs, anat_only=anat_only)
    return buf.getvalue()


def test_print_summary_within_session_synthesis_shows_inputs_and_jobs():
    """longmonk1-style: 2 T1w + 2 T2w runs → 1 job each after within-session synth."""
    anat_jobs = [
        {
            "subject_id": "longmonk1",
            "suffix": "T1w",
            "needs_synthesis": True,
            "synthesis_type": "t1w",
            "synthesis_scope": "within_session",
            "file_paths": ["t1_run-1.nii.gz", "t1_run-2.nii.gz"],
        },
        {
            "subject_id": "longmonk1",
            "suffix": "T2w",
            "needs_synthesis": True,
            "synthesis_type": "t2w",
            "synthesis_scope": "within_session",
            "file_paths": ["t2_run-1.nii.gz", "t2_run-2.nii.gz"],
        },
    ]
    out = _capture_summary(anat_jobs, [])

    assert "BIDS inputs → processing jobs: 4 → 2" in out
    assert "T1w: 2 BIDS files → 1 job" in out
    assert "Within-session synthesis: 1 job (2 inputs)" in out
    assert "T2w: 2 BIDS files → 1 job" in out
    assert "Processing jobs: 0" in out
    assert "BOLD: 0 BIDS files" in out
    # Old misleading labels must not appear
    assert "T1w files:" not in out
    assert "Total jobs:" not in out


def test_print_summary_no_synthesis_omits_breakdown():
    anat_jobs = [
        {
            "subject_id": "sub01",
            "suffix": "T1w",
            "needs_synthesis": False,
            "file_path": f"t1_run-{i}.nii.gz",
        }
        for i in (1, 2, 3)
    ]
    out = _capture_summary(anat_jobs, [])

    assert "BIDS inputs → processing jobs: 3 → 3" in out
    assert "T1w: 3 BIDS files → 3 jobs" in out
    assert "Within-session synthesis" not in out
    assert "Cross-session synthesis" not in out
    assert "Single (no synthesis)" not in out


def test_print_summary_mixed_synthesis_and_singles():
    anat_jobs = [
        {
            "subject_id": "sub01",
            "suffix": "T1w",
            "needs_synthesis": True,
            "synthesis_type": "t1w",
            "synthesis_scope": "cross_session",
            "file_paths": ["a.nii.gz", "b.nii.gz", "c.nii.gz"],
        },
        {
            "subject_id": "sub01",
            "suffix": "T1w",
            "needs_synthesis": False,
            "file_path": "d.nii.gz",
        },
        {
            "subject_id": "sub01",
            "suffix": "T1w",
            "needs_synthesis": False,
            "file_path": "e.nii.gz",
        },
    ]
    out = _capture_summary(anat_jobs, [])

    assert "BIDS inputs → processing jobs: 5 → 3" in out
    assert "T1w: 5 BIDS files → 3 jobs" in out
    assert "Cross-session synthesis: 1 job (3 inputs)" in out
    assert "Single (no synthesis): 2 jobs" in out


def test_print_summary_anat_only_replaces_zero_func_counts():
    """anat_only skips func discovery, so zero counts must not be printed."""
    anat_jobs = [
        {
            "subject_id": "sub01",
            "suffix": "T1w",
            "needs_synthesis": False,
            "file_path": "t1.nii.gz",
        }
    ]
    out = _capture_summary(anat_jobs, [], anat_only=True)

    assert "Functional data:" in out
    assert "Skipped: anat_only = true" in out
    assert "not discovered or processed" in out
    # Misleading zero counts must be gone
    assert "Processing jobs: 0" not in out
    assert "BOLD:" not in out
    # Anatomical summary is unaffected
    assert "T1w: 1 BIDS file → 1 job" in out


def test_print_summary_anat_only_false_keeps_func_counts():
    """Without anat_only, a genuinely func-free dataset still reports zeros."""
    anat_jobs = [
        {
            "subject_id": "sub01",
            "suffix": "T1w",
            "needs_synthesis": False,
            "file_path": "t1.nii.gz",
        }
    ]
    out = _capture_summary(anat_jobs, [], anat_only=False)

    assert "Processing jobs: 0" in out
    assert "BOLD: 0 BIDS files" in out
    assert "anat_only" not in out


def test_print_summary_functional_tasks():
    func_jobs = [
        {
            "subject_id": "sub01",
            "file_path": "bold1.nii.gz",
            "task": "rest",
        },
        {
            "subject_id": "sub01",
            "file_path": "bold2.nii.gz",
            "task": "rest",
        },
    ]
    out = _capture_summary([], func_jobs)

    assert "Processing jobs: 2" in out
    assert "BOLD: 2 BIDS files" in out
    assert "Tasks: rest" in out
