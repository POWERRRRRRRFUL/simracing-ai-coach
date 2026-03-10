"""
simcoach CLI — built with Typer.

Commands:
  simcoach init              — scaffold .env and config.yaml
  simcoach record            — connect to telemetry source and record a session
  simcoach analyze <file>    — analyse a session file and generate HTML report
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TimeElapsedColumn
from rich.table import Table

app = typer.Typer(
    name="simcoach",
    help="AI-powered post-session racing coach for Assetto Corsa.",
    add_completion=False,
)
console = Console()

# ─── init ─────────────────────────────────────────────────────────────────────

@app.command()
def init(
    force: bool = typer.Option(False, "--force", help="Overwrite existing files"),
) -> None:
    """Scaffold .env and config.yaml for first-time setup."""
    root = Path(".")
    src_configs = Path(__file__).parent.parent.parent.parent / "configs"
    src_env = Path(__file__).parent.parent.parent.parent / ".env.example"

    env_dst    = root / ".env"
    config_dst = root / "config.yaml"

    console.print(Panel.fit("[bold cyan]simcoach — first-time setup[/bold cyan]"))

    # .env
    if env_dst.exists() and not force:
        console.print(f"[yellow]  .env already exists[/yellow] (use --force to overwrite)")
    else:
        shutil.copy(src_env, env_dst)
        console.print(f"[green]  Created[/green] .env")

    # config.yaml
    config_example = src_configs / "config.example.yaml"
    if config_dst.exists() and not force:
        console.print(f"[yellow]  config.yaml already exists[/yellow] (use --force to overwrite)")
    else:
        shutil.copy(config_example, config_dst)
        console.print(f"[green]  Created[/green] config.yaml")

    # output dirs
    for d in ["output/sessions", "output/reports", "output/pb_laps"]:
        Path(d).mkdir(parents=True, exist_ok=True)
    console.print(f"[green]  Created[/green] output/ directories")

    console.print()
    console.print("[bold]Next steps:[/bold]")
    console.print("  1. Edit [cyan].env[/cyan] — add your [yellow]LLM_API_KEY[/yellow]")
    console.print("     OpenAI:     [dim]https://platform.openai.com/api-keys[/dim]")
    console.print("     OpenRouter: [dim]https://openrouter.ai/keys[/dim]")
    console.print("  2. (Optional) Edit [cyan]config.yaml[/cyan] to change provider/model")
    console.print("  3. Run [cyan]simcoach record[/cyan] to capture a session")
    console.print("     Or run [cyan]simcoach analyze --demo[/cyan] to test with mock data")


# ─── record ───────────────────────────────────────────────────────────────────

@app.command()
def record(
    source: Optional[str] = typer.Option(
        None, "--source", "-s",
        help="Telemetry source: 'ac_shared_memory' or 'mock'. Overrides config.yaml."
    ),
    laps: int = typer.Option(6, "--laps", "-l", help="(mock only) Number of laps to simulate"),
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Path to config.yaml"),
) -> None:
    """Connect to Assetto Corsa (or mock source) and record a session."""
    from simcoach.config import load_config
    from simcoach.recorder import SessionRecorder
    from simcoach.telemetry_bridge.mock_source import MockTelemetrySource
    from simcoach.telemetry_bridge.ac_shared_memory import ACSharedMemorySource

    cfg = load_config(config)
    chosen_source = source or cfg.recorder.source

    console.print(Panel.fit(f"[bold cyan]simcoach record[/bold cyan] — source: [yellow]{chosen_source}[/yellow]"))

    # Build telemetry source
    if chosen_source == "ac_shared_memory":
        tel_source = ACSharedMemorySource()
        console.print("[dim]Attempting to connect to Assetto Corsa shared memory...[/dim]")
        if not tel_source.connect():
            console.print(
                "[red]Failed to connect to AC shared memory.[/red]\n"
                "Make sure Assetto Corsa is running and you are in a session.\n"
                "Tip: use [cyan]--source mock[/cyan] to test without AC."
            )
            raise typer.Exit(1)
        console.print("[green]Connected to AC shared memory![/green]")
    else:
        tel_source = MockTelemetrySource(n_laps=laps, seed=42)
        tel_source.connect()
        console.print(f"[dim]Using mock source — simulating {laps} laps[/dim]")

    recorder = SessionRecorder(
        source=tel_source,
        sample_rate_hz=cfg.recorder.sample_rate_hz,
        output_dir=cfg.recorder.output_dir,
    )

    def _on_lap_complete(lap: "Lap") -> None:
        valid_laps = sum(1 for l in recorder._session.laps if l.is_valid) if recorder._session else 0
        console.print(
            f"  Lap {lap.lap_id + 1} complete — [green]{lap.lap_time_str}[/green]"
            + (f"  (total valid laps: {valid_laps})" if lap.is_valid else " [dim](invalid)[/dim]")
        )

    recorder._on_lap_complete = _on_lap_complete

    console.print(
        "\n[green]Recording started.[/green] "
        "Press [bold]Ctrl+C[/bold] to stop and save the session.\n"
    )

    session = None
    try:
        with Progress(
            SpinnerColumn(),
            "[progress.description]{task.description}",
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Recording...", total=None)
            session = recorder.record(
                progress_callback=lambda lap_id, n_frames: progress.update(
                    task,
                    description=f"Recording — lap {lap_id + 1}, {n_frames} frames captured"
                ),
            )
    finally:
        tel_source.disconnect()

        if session is None:
            console.print("[yellow]No session data collected — nothing to save.[/yellow]")
            raise typer.Exit(1)

        total_frames = len(session.raw_frames)
        valid_count  = sum(1 for l in session.laps if l.is_valid)
        console.print(
            f"  Frames: {total_frames}  |  Laps: {len(session.laps)}  |  Valid: {valid_count}"
        )

        if total_frames == 0 or not session.laps:
            console.print("[yellow]No valid laps recorded. Session not saved.[/yellow]")
            raise typer.Exit(1)

        console.print("Saving session atomically...")
        try:
            out_path = recorder.save(session)
        except ValueError as e:
            # save() raises ValueError when there are no laps
            console.print(f"[yellow]{e}[/yellow]")
            raise typer.Exit(1)
        except Exception as e:
            console.print(f"[red]ERROR: failed to save session:[/red] {e}")
            raise typer.Exit(1)

        console.print(f"[green]Session saved to:[/green] {out_path}")
        if valid_count:
            console.print(f"\nRun: [cyan]simcoach analyze {out_path}[/cyan]")
        else:
            console.print("[yellow]No valid laps. Drive a complete lap before stopping.[/yellow]")


# ─── analyze ──────────────────────────────────────────────────────────────────

@app.command()
def analyze(
    session_file: Optional[str] = typer.Argument(
        None, help="Path to session JSON file"
    ),
    demo: bool = typer.Option(
        False, "--demo",
        help="Generate and analyse a mock session (no AC or API key needed for structure test)"
    ),
    no_browser: bool = typer.Option(False, "--no-browser", help="Don't open report in browser"),
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Path to config.yaml"),
) -> None:
    """Analyse a recorded session and generate an AI coaching HTML report."""
    from simcoach.config import load_config
    from simcoach.models import Session
    from simcoach.context_builder import ContextBuilder
    from simcoach.reference import ReferenceManager
    from simcoach.llm import LLMProvider, build_system_prompt, build_user_prompt
    from simcoach.report import ReportGenerator

    cfg = load_config(config)

    # ── Load or generate session ─────────────────────────────────────────────
    if demo:
        session = _generate_demo_session()
        console.print("[dim]Using demo mock session[/dim]")
    elif session_file:
        path = Path(session_file)
        if not path.exists():
            console.print(f"[red]File not found:[/red] {path}")
            raise typer.Exit(1)
        with open(path, encoding="utf-8") as f:
            session = Session.model_validate(json.load(f))
        console.print(f"Loaded session [cyan]{session.session_id}[/cyan] — {path.name}")
    else:
        console.print("[red]Provide a session file or use --demo[/red]")
        raise typer.Exit(1)

    # ── Show session summary ─────────────────────────────────────────────────
    _print_session_summary(session)

    # ── Load reference lap (personal best) ───────────────────────────────────
    ref_mgr = ReferenceManager(pb_dir=cfg.reference.pb_dir)
    reference_lap = ref_mgr.load_pb(session.car_id, session.track_id)
    if reference_lap:
        console.print(f"  Reference (PB): [blue]{reference_lap.lap_time_str}[/blue]")
    else:
        console.print("  Reference: [dim]none (this session's best lap will be the reference)[/dim]")

    # ── Build LLM context ────────────────────────────────────────────────────
    console.print("\n[dim]Building telemetry context...[/dim]")
    builder = ContextBuilder(resample_points=cfg.context_builder.resample_points)
    try:
        context = builder.build(session, reference_lap)
    except ValueError as e:
        console.print(f"[red]Cannot build context:[/red] {e}")
        raise typer.Exit(1)

    console.print(
        f"  Best lap: [green]{context.best_lap.lap_time_str}[/green]  "
        f"(lap {context.best_lap.lap_id + 1} of {context.valid_laps} valid)"
    )

    # ── Update personal best ──────────────────────────────────────────────────
    valid_laps = [l for l in session.laps if l.is_valid and l.frames]
    if valid_laps:
        best_lap_obj = min(valid_laps, key=lambda l: l.lap_time_ms)
        was_updated, new_pb = ref_mgr.update_pb_if_faster(session, best_lap_obj)
        if was_updated:
            console.print(f"  [green]New personal best![/green] {new_pb.lap_time_str} saved.")

    # ── Build high-res chart traces (separate from LLM context) ──────────────
    chart_traces = builder.build_chart_traces(
        session, reference_lap, chart_points=cfg.context_builder.chart_points
    )

    # ── Call LLM ─────────────────────────────────────────────────────────────
    if not cfg.llm.api_key:
        console.print(
            "\n[yellow]No LLM_API_KEY set.[/yellow] Skipping AI analysis.\n"
            "Add your key to .env and re-run, or run [cyan]simcoach init[/cyan] first."
        )
        _render_no_llm_report(context, cfg, not no_browser, chart_traces)
        return

    context_json = builder.to_json(context)
    system_prompt = build_system_prompt()
    user_prompt   = build_user_prompt(context_json)

    console.print(f"\n[dim]Calling {cfg.llm.model} at {cfg.llm.base_url}...[/dim]")
    with Progress(SpinnerColumn(), "[progress.description]{task.description}", console=console) as progress:
        task = progress.add_task("Waiting for AI analysis...", total=None)
        try:
            with LLMProvider(cfg.llm) as provider:
                llm_response = provider.complete(system_prompt, user_prompt, json_mode=True)
        except Exception as e:
            console.print(f"\n[red]LLM call failed:[/red] {e}")
            raise typer.Exit(1)

    # ── Generate report ───────────────────────────────────────────────────────
    gen = ReportGenerator(output_dir=cfg.report.output_dir)
    report = gen.build_report(context, llm_response, cfg.llm.model, chart_traces=chart_traces)
    out_path = gen.render_html(report, open_browser=not no_browser)

    console.print(f"\n[green]Report generated:[/green] {out_path}")
    if not no_browser:
        console.print("[dim]Opening in browser...[/dim]")


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _generate_demo_session() -> "Session":
    """Generate a synthetic session using the mock source (blocking)."""
    from simcoach.models import Session
    from simcoach.recorder import SessionRecorder
    from simcoach.telemetry_bridge.mock_source import MockTelemetrySource

    console.print("[dim]Generating mock session data...[/dim]")
    src = MockTelemetrySource(n_laps=5, seed=7)
    src.connect()

    recorder = SessionRecorder(src, sample_rate_hz=25, output_dir="output/sessions")
    session = recorder.record(fast_mode=True)
    src.disconnect()

    saved = recorder.save(session)
    console.print(f"[dim]Mock session saved: {saved}[/dim]")
    return session


def _print_session_summary(session: "Session") -> None:
    table = Table(title=f"Session {session.session_id}", show_header=True, header_style="dim")
    table.add_column("Car", style="cyan")
    table.add_column("Track", style="cyan")
    table.add_column("Laps", justify="right")
    table.add_column("Valid", justify="right", style="green")
    table.add_column("Source")
    valid = sum(1 for l in session.laps if l.is_valid)
    table.add_row(session.car_id, session.track_id, str(len(session.laps)), str(valid), session.source)
    console.print(table)


def _render_no_llm_report(context, cfg, open_browser: bool, chart_traces=None) -> None:
    """Render a report with a structured placeholder when no API key is configured."""
    import json as _json
    from simcoach.report import ReportGenerator

    # Use the structured JSON format so the template renders the same way
    placeholder = _json.dumps({
        "best_lap_vs_reference": {
            "summary": "No API key configured — AI analysis was not performed.",
            "time_loss_sections": [],
            "main_causes": []
        },
        "session_findings": {
            "consistency_note": "Add LLM_API_KEY to .env and re-run simcoach analyze.",
            "repeated_patterns": [],
            "outliers": []
        },
        "coaching_summary": {
            "top_takeaways": [
                "Telemetry collected and context built successfully",
                "Configure your LLM provider to receive the full analysis",
                "Review the telemetry charts above for a manual overview"
            ]
        },
        "next_training_focus": {
            "priorities": [
                {"title": "Configure LLM", "action": "Add LLM_API_KEY to .env, then re-run simcoach analyze."}
            ]
        }
    })
    gen = ReportGenerator(output_dir=cfg.report.output_dir)
    report = gen.build_report(context, placeholder, "no-llm", chart_traces=chart_traces)
    out_path = gen.render_html(report, open_browser=open_browser)
    console.print(f"\n[yellow]Report (no AI analysis):[/yellow] {out_path}")


if __name__ == "__main__":
    app()
