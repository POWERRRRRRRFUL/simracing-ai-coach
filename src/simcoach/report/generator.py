"""
HTML report generator.

LLM response handling (in priority order):
  1. Try to parse the response as JSON (new structured format from updated prompts).
  2. Strip markdown code fences and try again.
  3. Fall back to legacy ## Section regex so old/placeholder responses still render.

The HTML template uses `structured` (dict) for rich card rendering when present,
and falls back to the flat string fields for the no-API / legacy path.
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


# Legacy fallback: regex that matched the old ## Section format
_SECTION_RE = re.compile(
    r"##\s+(Best Lap vs Reference|Session Findings|Coaching Summary|Next Training Focus)"
    r"(.*?)(?=##\s+|\Z)",
    re.DOTALL,
)

# The four top-level keys we expect in a valid structured response
_EXPECTED_KEYS = {
    "best_lap_vs_reference",
    "session_findings",
    "coaching_summary",
    "next_training_focus",
}


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
        chart_traces: dict | None = None,
    ) -> AnalysisReport:
        """Parse LLM response (structured JSON or legacy markdown) into AnalysisReport.

        Args:
            chart_traces: Optional high-resolution trace dict produced by
                          ContextBuilder.build_chart_traces().  When provided,
                          render_html() uses these instead of the 100-point LLM
                          traces so the interactive Plotly charts have full detail.
        """
        structured, legacy_sections = self._parse_llm_response(llm_response)

        delta_str: str | None = None
        if context.delta_vs_reference_ms is not None:
            delta_ms = context.delta_vs_reference_ms
            sign = "+" if delta_ms >= 0 else "-"
            delta_str = f"{sign}{abs(delta_ms) / 1000:.3f}s"

        ref_time_str: str | None = None
        if context.reference_lap:
            ref_time_str = context.reference_lap.lap_time_str

        # Populate flat string fields (used by fallback template path & legacy compat)
        if structured:
            bvr_text = self._flat_best_vs_ref(structured)
            sf_text  = self._flat_session_findings(structured)
            cs_text  = self._flat_coaching_summary(structured)
            ntf_text = self._flat_next_focus(structured)
        else:
            bvr_text = legacy_sections.get("Best Lap vs Reference", "")
            sf_text  = legacy_sections.get("Session Findings", "")
            cs_text  = legacy_sections.get("Coaching Summary", "")
            ntf_text = legacy_sections.get("Next Training Focus", "")

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
            structured_analysis=structured or {},
            best_vs_reference_analysis=bvr_text,
            session_findings=sf_text,
            coaching_summary=cs_text,
            next_training_focus=ntf_text,
            chart_traces=chart_traces or {},
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

        ctx = report.context_json

        # Prefer high-resolution chart_traces when available; fall back to the
        # 100-point LLM context traces for old reports or when no chart_traces
        # were built (e.g. sessions loaded without re-running build_chart_traces).
        if report.chart_traces and report.chart_traces.get("best"):
            best_trace = report.chart_traces["best"]
            ref_trace  = report.chart_traces.get("reference") or []
        else:
            best_trace = ctx.get("best_lap", {}).get("trace", [])
            ref_trace  = ctx.get("reference_lap", {}).get("trace", []) if ctx.get("reference_lap") else []

        chart_data    = self._build_chart_data(best_trace, ref_trace)
        lap_summaries = ctx.get("all_lap_summaries", [])
        track_map_data = self._build_track_map_data(report, best_trace, ref_trace)

        template = self._env.get_template("report.html.j2")
        html = template.render(
            report=report,
            structured=report.structured_analysis,  # convenience shorthand
            chart_data_json=json.dumps(chart_data),
            track_map_data_json=json.dumps(track_map_data),
            lap_summaries=lap_summaries,
            generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        )

        out_path.write_text(html, encoding="utf-8")

        if open_browser:
            webbrowser.open(out_path.resolve().as_uri())

        return out_path

    # ── Parsing ───────────────────────────────────────────────────────────────

    def _parse_llm_response(
        self, text: str
    ) -> tuple[dict[str, Any] | None, dict[str, str]]:
        """
        Returns (structured_dict | None, legacy_sections_dict).
        Tries JSON first (direct, then fence-stripped), then falls back to regex.
        """
        structured = self._try_parse_json(text)
        if structured:
            return structured, {}

        stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
        structured = self._try_parse_json(stripped)
        if structured:
            return structured, {}

        return None, self._parse_legacy_sections(text)

    def _try_parse_json(self, text: str) -> dict[str, Any] | None:
        """Return parsed dict only when it contains all four expected keys."""
        try:
            data = json.loads(text.strip())
            if isinstance(data, dict) and _EXPECTED_KEYS.issubset(data.keys()):
                return data
        except (json.JSONDecodeError, ValueError):
            pass
        return None

    def _parse_legacy_sections(self, text: str) -> dict[str, str]:
        sections: dict[str, str] = {}
        for match in _SECTION_RE.finditer(text):
            sections[match.group(1).strip()] = match.group(2).strip()
        return sections

    # ── Flat-text helpers: structured JSON → plain strings ────────────────────

    def _flat_best_vs_ref(self, s: dict) -> str:
        d = s.get("best_lap_vs_reference", {})
        lines = [d.get("summary", "")]
        for item in d.get("time_loss_sections", []):
            lines.append(f"• {item}")
        causes = d.get("main_causes", [])
        if causes:
            lines.append("Causes: " + "; ".join(causes))
        return "\n".join(l for l in lines if l)

    def _flat_session_findings(self, s: dict) -> str:
        d = s.get("session_findings", {})
        lines = [d.get("consistency_note", "")]
        for p in d.get("repeated_patterns", []):
            lines.append(f"• {p}")
        for o in d.get("outliers", []):
            lines.append(f"! {o}")
        return "\n".join(l for l in lines if l)

    def _flat_coaching_summary(self, s: dict) -> str:
        d = s.get("coaching_summary", {})
        return "\n".join(f"• {t}" for t in d.get("top_takeaways", []))

    def _flat_next_focus(self, s: dict) -> str:
        d = s.get("next_training_focus", {})
        lines = []
        for i, p in enumerate(d.get("priorities", []), 1):
            lines.append(f"{i}. {p.get('title', '')}: {p.get('action', '')}")
        return "\n".join(lines)

    # ── Chart data ────────────────────────────────────────────────────────────

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

    def _build_track_map_data(
        self,
        report: AnalysisReport,
        best_trace: list[dict[str, Any]],
        ref_trace: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        """Extract world position arrays for the track map visualization.

        Returns None when the session has no position data (old recordings).
        """
        ct = report.chart_traces
        if not ct:
            return None

        bp = ct.get("best_pos", {})
        if not bp or bp.get("x") is None:
            return None

        rp = ct.get("ref_pos")

        ref_entry = None
        if rp and rp.get("x") is not None:
            ref_entry = {
                "x": rp["x"],
                "z": rp["z"],
                "speed": [round(p.get("spd", 0), 1) for p in (ref_trace or [])],
            }

        return {
            "best": {
                "x": bp["x"],
                "z": bp["z"],
                "speed": [round(p.get("spd", 0), 1) for p in best_trace],
            },
            "reference": ref_entry,
        }
