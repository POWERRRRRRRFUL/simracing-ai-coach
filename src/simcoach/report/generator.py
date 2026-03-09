"""
HTML report generator.

Parses the LLM response into structured sections, then renders a
local HTML report using Jinja2. Chart data is embedded inline as
JSON so no server is required.
"""

from __future__ import annotations

import json
import re
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from simcoach.models.telemetry import AnalysisReport, LLMAnalysisContext


SECTION_RE = re.compile(
    r"##\s+(Best Lap vs Reference|Session Findings|Coaching Summary|Next Training Focus)"
    r"(.*?)(?=##\s+|\Z)",
    re.DOTALL,
)


class ReportGenerator:
    """Parses LLM output and renders an HTML report."""

    def __init__(self, output_dir: str = "output/reports") -> None:
        self._output_dir = Path(output_dir)
        template_dir = Path(__file__).parent / "templates"
        self._env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=True,
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def build_report(
        self,
        context: LLMAnalysisContext,
        llm_response: str,
        llm_model: str,
    ) -> AnalysisReport:
        """Parse LLM response into an AnalysisReport object."""
        sections = self._parse_sections(llm_response)

        delta_str: str | None = None
        if context.delta_vs_reference_ms is not None:
            delta_ms = context.delta_vs_reference_ms
            sign = "+" if delta_ms >= 0 else "-"
            abs_ms = abs(delta_ms)
            delta_str = f"{sign}{abs_ms / 1000:.3f}s"

        ref_time_str: str | None = None
        if context.reference_lap:
            ref_time_str = context.reference_lap.lap_time_str

        return AnalysisReport(
            session_id=context.session_id,
            car_id=context.car_id,
            track_id=context.track_id,
            session_date=context.session_date,
            best_lap_time_str=context.best_lap.lap_time_str,
            reference_lap_time_str=ref_time_str,
            delta_vs_reference_str=delta_str,
            llm_model=llm_model,
            llm_raw_response=llm_response,
            best_vs_reference_analysis=sections.get("Best Lap vs Reference", ""),
            session_findings=sections.get("Session Findings", ""),
            coaching_summary=sections.get("Coaching Summary", ""),
            next_training_focus=sections.get("Next Training Focus", ""),
            context_json=context.model_dump(),
        )

    def render_html(
        self,
        report: AnalysisReport,
        open_browser: bool = True,
    ) -> Path:
        """Render the AnalysisReport to an HTML file and return its path."""
        self._output_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        fname = f"report_{report.session_id}_{report.track_id}_{ts}.html"
        out_path = self._output_dir / fname

        # Prepare chart data
        ctx = report.context_json
        best_trace = ctx.get("best_lap", {}).get("trace", [])
        ref_trace  = ctx.get("reference_lap", {}).get("trace", []) if ctx.get("reference_lap") else []

        chart_data = self._build_chart_data(best_trace, ref_trace)
        lap_summaries = ctx.get("all_lap_summaries", [])

        template = self._env.get_template("report.html.j2")
        html = template.render(
            report=report,
            chart_data_json=json.dumps(chart_data),
            lap_summaries=lap_summaries,
            generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        )

        out_path.write_text(html, encoding="utf-8")

        if open_browser:
            webbrowser.open(out_path.resolve().as_uri())

        return out_path

    # ── Internal ──────────────────────────────────────────────────────────────

    def _parse_sections(self, text: str) -> dict[str, str]:
        sections: dict[str, str] = {}
        for match in SECTION_RE.finditer(text):
            title = match.group(1).strip()
            content = match.group(2).strip()
            sections[title] = content
        return sections

    def _build_chart_data(
        self,
        best_trace: list[dict[str, Any]],
        ref_trace:  list[dict[str, Any]],
    ) -> dict[str, Any]:
        def extract(trace: list[dict], key: str) -> list[float]:
            return [round(p.get(key, 0), 3) for p in trace]

        positions = extract(best_trace, "pos") or [i / 99 for i in range(100)]

        return {
            "positions": positions,
            "best": {
                "speed":    extract(best_trace, "spd"),
                "throttle": extract(best_trace, "thr"),
                "brake":    extract(best_trace, "brk"),
                "steering": extract(best_trace, "str"),
                "gear":     extract(best_trace, "gear"),
            },
            "reference": {
                "speed":    extract(ref_trace, "spd"),
                "throttle": extract(ref_trace, "thr"),
                "brake":    extract(ref_trace, "brk"),
                "steering": extract(ref_trace, "str"),
                "gear":     extract(ref_trace, "gear"),
            } if ref_trace else None,
        }
