# Architecture

## System overview

```
Assetto Corsa
    │  Windows Shared Memory
    ▼
TelemetrySource (interface)
    ├─ ACSharedMemorySource   ← real AC
    └─ MockTelemetrySource    ← demo / testing
    │
    ▼
SessionRecorder
    │  polls at 25 Hz, detects lap boundaries
    ▼
Session JSON  (output/sessions/)
    │
    ▼
ContextBuilder
    │  cleans, segments, resamples, computes stats
    ▼
LLMAnalysisContext (JSON)
    │
    ├─ ReferenceManager  ← loads/saves personal best laps
    │
    ▼
LLMProvider  (OpenAI-compatible)
    │  httpx POST /chat/completions
    ▼
LLM response (structured markdown)
    │
    ▼
ReportGenerator
    │  parses sections, renders Jinja2 template
    ▼
HTML Report  (output/reports/)
```

## Module responsibilities

| Module | Responsibility |
|--------|---------------|
| `telemetry_bridge/` | Abstract interface + AC shared memory + mock source |
| `recorder/` | Polling loop, lap detection, session serialisation |
| `models/` | Pydantic data models (TelemetryFrame → Session → AnalysisReport) |
| `context_builder/` | Clean → resample → select best/reference → build LLMAnalysisContext |
| `reference/` | Persist and retrieve personal best laps |
| `llm/` | OpenAI-compatible API client + prompt templates |
| `report/` | Parse LLM output + render HTML via Jinja2 |
| `config/` | Load YAML + .env → AppConfig |
| `cli/` | Typer CLI (init / record / analyze) |
| `utils/` | Resampling and statistics helpers |

## Key design constraints

1. **No hand-written driving rules engine** — the LLM does all driving analysis.
   The code's job is to produce clean, well-structured telemetry context.

2. **Provider-agnostic LLM** — `LLMProvider` calls any OpenAI-compatible endpoint.
   OpenRouter, local Ollama, or the OpenAI API all work without code changes.

3. **Session-first architecture** — sessions are always persisted to disk before analysis.
   This means `analyze` can be re-run with different models/prompts without re-recording.

4. **Post-session only (v1)** — no real-time coaching, no in-game overlay.
   The loop is: drive → record → analyze → read report → drive again.

## Data flow details

### Lap detection

`SessionRecorder` detects lap boundaries by watching `TelemetryFrame.lap_id`.
For the AC shared memory source, `lap_id` is incremented when `completedLaps` increases.
For the mock source, `lap_id` increments when `normalized_track_position` crosses 1.0.

### Resampling

`resample_trace()` takes a list of TelemetryFrames sorted by `normalized_track_position`
and returns N evenly-spaced samples using linear interpolation between adjacent frames.
This ensures consistent 0→1 coverage regardless of where the driver was slow or fast.

### Personal best storage

PB laps are stored at `output/pb_laps/{car_id}/{track_id}/pb.json`.
On each `analyze` run, the session's best lap is compared against the stored PB.
If the session is faster, the PB is updated automatically.

## Future extension points

- **Real-time coaching**: replace `SessionRecorder` with a streaming pipeline
- **Sector-level analysis**: add sector time tracking to `TelemetryFrame` and `LapContextEntry`
- **Multi-car comparison**: `ContextBuilder.build()` accepts multiple sessions
- **Web UI**: the HTML report is self-contained; a web server is not required
- **Additional providers**: add `AnthropicProvider`, `OllamaProvider` as `LLMProvider` subclasses
