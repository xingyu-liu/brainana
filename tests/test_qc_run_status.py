"""Tests for QC report run-status tier logic and HTML rendering."""

import importlib.util
from pathlib import Path

import pytest

_RUN_STATUS_PATH = (
    Path(__file__).resolve().parents[1]
    / "src/nhp_mri_prep/quality_control/run_status.py"
)
_spec = importlib.util.spec_from_file_location("_run_status_under_test", _RUN_STATUS_PATH)
_run_status = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_run_status)

resolve_run_status = _run_status.resolve_run_status
run_status_log_label = _run_status.run_status_log_label
format_run_status_stats = _run_status.format_run_status_stats
render_run_status_content = _run_status.render_run_status_content

@pytest.mark.parametrize(
    "run_status,expected_tier,expected_css",
    [
        ({"success": True, "failed_count": 0, "ignored_count": 0}, "pass", "ok"),
        (
            {"success": True, "failed_count": 1, "ignored_count": 1},
            "pass_with_warnings",
            "warn",
        ),
        ({"success": True, "ignored_count": 2}, "pass_with_warnings", "warn"),
        ({"success": False, "failed_count": 1}, "fail", "fail"),
    ],
)
def test_resolve_run_status_tiers(
    run_status: dict, expected_tier: str, expected_css: str
) -> None:
    resolved = resolve_run_status(run_status)
    assert resolved["tier"] == expected_tier
    assert resolved["css_class"] == expected_css


def test_resolve_run_status_warn_headline_singular() -> None:
    resolved = resolve_run_status(
        {"success": True, "failed_count": 1, "ignored_count": 1}
    )
    assert resolved["headline"] == "Completed with 1 failed task"
    assert resolved["badge"] == "Pass with warnings"
    assert "guidance" in resolved


def test_run_status_log_label() -> None:
    assert run_status_log_label({"success": True}) == "success"
    assert (
        run_status_log_label({"success": True, "failed_count": 1})
        == "pass with warnings"
    )
    assert run_status_log_label({"success": False}) == "early abort"


def test_format_run_status_stats_omits_zero_counts() -> None:
    html = format_run_status_stats(
        {
            "duration": "10m 30s",
            "succeeded_count": 185,
            "failed_count": 0,
            "ignored_count": 0,
        }
    )
    assert "Tasks failed" not in html
    assert "Tasks ignored" not in html
    assert "185" in html


@pytest.mark.parametrize(
    "run_status,snippet",
    [
        ({"success": True, "succeeded_count": 185}, 'class="status ok"'),
        (
            {
                "success": True,
                "failed_count": 1,
                "ignored_count": 1,
                "succeeded_count": 185,
            },
            'class="status warn"',
        ),
        ({"success": False, "failed_count": 1}, 'class="status fail"'),
    ],
)
def test_render_run_status_content_css_class(run_status: dict, snippet: str) -> None:
    content = render_run_status_content(run_status)
    assert snippet in content


def test_render_run_status_warn_not_green_pass() -> None:
    content = render_run_status_content(
        {
            "success": True,
            "failed_count": 1,
            "ignored_count": 1,
            "succeeded_count": 185,
        }
    )
    assert 'class="status warn"' in content
    assert "Pass with warnings" in content
    assert "Completed with 1 failed task" in content
    assert 'class="status ok"' not in content
    assert "Completed successfully" not in content


def test_render_run_status_content_empty_without_run_status() -> None:
    assert render_run_status_content(None) == ""
