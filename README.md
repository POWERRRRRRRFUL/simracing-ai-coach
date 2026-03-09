# simcoach

**AI-powered post-session racing coach for Assetto Corsa.**

simcoach records your telemetry, organises it into a structured context, and uses a large language model to generate a personalised HTML coaching report — without you having to know anything about how telemetry works.

```
Drive → Record → Analyse → Read report → Drive better
```

---

## How it works

1. **Record** — simcoach reads Assetto Corsa's shared memory (Windows) at 25 Hz,
   automatically detecting lap boundaries and saving the session to a JSON file.
2. **Build context** — the best lap and your personal best are resampled to 100 evenly-spaced
   track-position points with key channels (speed, throttle, brake, steering, gear, RPM).
3. **Call LLM** — the context is sent to your chosen LLM provider.
   simcoach works with OpenAI, OpenRouter, and any OpenAI-compatible endpoint.
4. **Report** — a local HTML report with interactive telemetry charts and AI coaching text
   is opened in your browser.

There are **no hard-coded driving rules** in simcoach.
The LLM analyses the telemetry and decides what matters.

---

## Installation

### Prerequisites

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### Install with uv (recommended)

```bash
# Clone the repo
git clone https://github.com/yourusername/simracing-ai-coach.git
cd simracing-ai-coach

# Create virtual environment and install
uv venv
uv pip install -e .
```

### Install with pip

```bash
git clone https://github.com/yourusername/simracing-ai-coach.git
cd simracing-ai-coach

python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -e .
```

---

## Quick start

### 1. Initialise config

```bash
simcoach init
```

This creates `.env` and `config.yaml` in the current directory.

### 2. Add your API key

Edit `.env`:

```env
LLM_API_KEY=sk-your-key-here
```

Supported providers:
| Provider | LLM_BASE_URL | Example model |
|----------|-------------|---------------|
| OpenAI (default) | `https://api.openai.com/v1` | `gpt-4o-mini` |
| OpenRouter | `https://openrouter.ai/api/v1` | `openai/gpt-4o-mini` |
| Local Ollama | `http://localhost:11434/v1` | `llama3.2` |

### 3. Test the full pipeline without AC

```bash
simcoach analyze --demo
```

This generates a mock 5-lap session and produces a full AI report.
No Assetto Corsa or real telemetry required.

### 4. Record a real session

Start Assetto Corsa, load a session, then run:

```bash
simcoach record --source ac_shared_memory
```

simcoach will connect to AC's shared memory and record until you exit the session.

### 5. Analyse

```bash
simcoach analyze output/sessions/session_<id>_<track>.json
```

The HTML report opens automatically in your browser.

---

## CLI reference

```
simcoach init            Scaffold .env and config.yaml
simcoach record          Record a session from AC or mock
simcoach analyze <file>  Analyse a session and generate a report

Options for record:
  --source TEXT   ac_shared_memory | mock
  --laps INT      (mock only) number of laps to simulate [default: 6]
  --config PATH   path to config.yaml

Options for analyze:
  --demo          generate and analyse a mock session (no AC needed)
  --no-browser    don't open the report in the browser
  --config PATH   path to config.yaml
```

---

## Assetto Corsa shared memory

simcoach reads AC's three shared memory files:

| File | Contents |
|------|----------|
| `Local\acpmf_physics` | Speed, throttle, brake, steering, gear, RPM, G-forces, tyre data |
| `Local\acpmf_graphics` | Lap count, session state, track position, lap times |
| `Local\acpmf_static` | Car name, track name, session type |

**Requirements:**
- Windows 10/11
- Assetto Corsa installed and running
- The game must be in an active session (not menus/garage)

**Current status:** The shared memory bridge is fully implemented.
If AC is not running, `simcoach record` will print a clear error and suggest using `--source mock`.

---

## Configuration

`config.yaml` controls all tuneable behaviour:

```yaml
llm:
  base_url: "https://api.openai.com/v1"
  model: "gpt-4o-mini"
  max_tokens: 2048
  temperature: 0.3

recorder:
  sample_rate_hz: 25
  source: "mock"          # change to "ac_shared_memory" for real AC

context_builder:
  resample_points: 100    # points per lap sent to LLM

report:
  output_dir: "output/reports"
  open_browser: true
```

Environment variables override YAML values:
- `LLM_API_KEY` — required
- `LLM_BASE_URL` — optional override
- `LLM_MODEL` — optional override

---

## Project structure

```
simracing-ai-coach/
├─ src/simcoach/
│  ├─ cli/               Typer CLI commands
│  ├─ config/            YAML + .env loader → AppConfig
│  ├─ context_builder/   Telemetry → LLMAnalysisContext
│  ├─ llm/               LLM provider + prompts
│  ├─ models/            Pydantic data models
│  ├─ recorder/          Session recording loop
│  ├─ reference/         Personal best lap store
│  ├─ report/            HTML report generator + Jinja2 template
│  ├─ telemetry_bridge/  AC shared memory + mock source
│  └─ utils/             Resampling + statistics
├─ tests/                Pytest tests
├─ docs/
│  ├─ architecture.md
│  └─ telemetry_context_schema.md
├─ configs/config.example.yaml
├─ .env.example
└─ output/               Sessions, reports, PB laps (git-ignored)
```

---

## Running tests

```bash
# Install dev dependencies
uv pip install -e ".[dev]"

# Run tests
pytest
```

---

## Licence

MIT
