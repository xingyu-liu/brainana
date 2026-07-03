"""Pipeline run-status tier logic and HTML for QC reports."""

import html
from typing import Any, Dict, Optional


def resolve_run_status(run_status: Dict[str, Any]) -> Dict[str, str]:
    """Map Nextflow run stats to a three-tier QC status (pass / warn / fail)."""
    success = bool(run_status.get("success"))
    failed = int(run_status.get("failed_count") or 0)
    ignored = int(run_status.get("ignored_count") or 0)
    tolerated_failures = max(failed, ignored)

    if not success:
        return {
            "tier": "fail",
            "css_class": "fail",
            "badge": "Fail",
            "headline": "Early abort \u2014 the pipeline did not finish",
        }

    if tolerated_failures > 0:
        task_word = "task" if tolerated_failures == 1 else "tasks"
        return {
            "tier": "pass_with_warnings",
            "css_class": "warn",
            "badge": "Pass with warnings",
            "headline": f"Completed with {tolerated_failures} failed {task_word}",
            "guidance": (
                "One or more optional steps failed. "
                "Check the execution trace for details."
            ),
        }

    return {
        "tier": "pass",
        "css_class": "ok",
        "badge": "Pass",
        "headline": "Completed successfully",
    }


def run_status_log_label(run_status: Dict[str, Any]) -> str:
    """Short label for log lines (generate_reports.py)."""
    tier = resolve_run_status(run_status)["tier"]
    return {
        "pass": "success",
        "pass_with_warnings": "pass with warnings",
        "fail": "early abort",
    }[tier]


def format_run_status_stats(run_status: Dict[str, Any]) -> str:
    """Render task-count stats as an HTML list for the run-status section."""
    duration = run_status.get("duration")
    succeeded = run_status.get("succeeded_count")
    ignored = run_status.get("ignored_count")
    failed = run_status.get("failed_count")

    parts = []
    if duration:
        parts.append(f"Duration: <b>{html.escape(str(duration))}</b>")
    if succeeded is not None:
        parts.append(f"Tasks succeeded: <b>{succeeded}</b>")
    if ignored:
        parts.append(f"Tasks ignored: <b>{ignored}</b>")
    if failed:
        parts.append(f"Tasks failed: <b>{failed}</b>")
    if not parts:
        return ""
    return '<ul class="meta"><li>' + "</li><li>".join(parts) + "</li></ul>"


def render_run_status_content(run_status: Optional[Dict[str, Any]]) -> str:
    """Render the inner HTML block for the run-status section."""
    if not run_status:
        return ""

    resolved = resolve_run_status(run_status)
    stat_line = format_run_status_stats(run_status)

    if resolved["tier"] == "fail":
        error_text = (
            run_status.get("error_report") or run_status.get("error_message") or ""
        )
        exit_status = run_status.get("exit_status")
        failed_process = run_status.get("failed_process")
        trace_file = run_status.get("trace_file")

        detail_items = []
        if failed_process:
            detail_items.append(
                f"<li>Failed process: <code>{html.escape(str(failed_process))}</code></li>"
            )
        if exit_status is not None:
            detail_items.append(
                f"<li>Exit status: {html.escape(str(exit_status))}</li>"
            )
        if trace_file:
            detail_items.append(
                "<li>Execution trace: "
                f"<code>{html.escape(str(trace_file))}</code></li>"
            )
        details = (
            f'<ul class="meta">{"".join(detail_items)}</ul>' if detail_items else ""
        )

        error_block = (
            f'<pre class="errlog">{html.escape(str(error_text))}</pre>'
            if error_text
            else ""
        )

        return f"""<div class="status fail">
<p class="headline"><span class="badge">{resolved["badge"]}</span>{resolved["headline"]}</p>
<p>This report was generated from the steps that completed before the failure;
some sections may be missing or incomplete.</p>
{stat_line}
{details}
{error_block}
</div>"""

    guidance = resolved.get("guidance")
    guidance_block = f"<p>{guidance}</p>" if guidance else ""

    return f"""<div class="status {resolved["css_class"]}">
<p class="headline"><span class="badge">{resolved["badge"]}</span>{resolved["headline"]}</p>
{guidance_block}{stat_line}
</div>"""
