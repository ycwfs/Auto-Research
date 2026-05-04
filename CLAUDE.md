# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Auto-Research is an AI-powered research paper tracking system that:
- Fetches daily papers from arXiv based on configured categories and keywords
- Generates full-text bilingual (Chinese/English) summaries using AI CLI + MinerU MCP
- Performs trend analysis with TF-IDF, LDA topic modeling, and word clouds
- Syncs structured notes to Zotero via MCP
- Generates weekly research ideas by synthesizing collected papers
- Provides a Flask-based web UI for browsing results

## Core Architecture

### CLI Support

The system now supports **three AI CLI tools** interchangeably:
- **GitHub Copilot CLI** (`copilot`)
- **Claude CLI** (`claude`)
- **Codex CLI** (`codex`)

The CLI type is automatically detected from the command name configured in `agent.copilot_command`. All CLI-related code uses the unified `cli_runner.py` module which abstracts CLI-specific differences.

### Execution Modes

The system supports two backend modes (configured in `config/config.yaml`):

1. **Agent mode** (default, recommended): Uses AI CLI with MCP servers
   - `pipeline.summary_backend: "agent"` - Full-text summarization via CLI + MinerU
   - `pipeline.analysis_backend: "agent"` - Trend analysis via CLI
   - Requires: AI CLI (copilot/claude/codex) logged in, `mineru` and `zotero` MCP servers configured

2. **LLM mode** (legacy): Direct API calls to OpenAI/Gemini/Claude/DeepSeek/vLLM
   - `pipeline.summary_backend: "llm"` - Uses provider-specific clients in `src/summarizer/`
   - `pipeline.analysis_backend: "llm"` - Uses LLM factory pattern

### Main Workflows

**Daily Pipeline** (`main.py`):
1. Fetch papers from arXiv (`src/crawler/arxiv_fetcher.py`)
2. Deduplicate against previous runs using paper signatures
3. Generate summaries (agent or LLM mode)
4. Perform trend analysis (agent or LLM mode)
5. Save artifacts to `data/papers/`, `data/summaries/`, `data/analysis/`
6. Update `latest.json` symlinks for downstream consumption

**Zotero Upload** (`zotero_upload.py`):
- Triggered after daily pipeline completes (or manually)
- Reads `data/papers/latest.json` and `data/summaries/latest.json`
- Uses AI CLI + Zotero MCP to upload papers with bilingual notes
- Stores daily analysis reports in the `daily analysis` collection

**Weekly Idea Generation** (`weekly_idea.py`):
- Runs on configured weekday (default: Thursday)
- Summarizes locally collected papers from the week
- Queries Zotero library for supporting research signals
- Generates introduction-ready research ideas based on focus keywords
- Saves to `idea` collection in Zotero and local artifacts

**Scheduler** (`scheduler.py`):
- APScheduler-based cron jobs for all three workflows
- Configured via `config/config.yaml` under `scheduler.*`
- Supports email notifications on success/failure

### Agent Automation (`src/automation/`)

**New unified CLI runner** (`cli_runner.py`):
- `detect_cli_type()` - Auto-detects CLI type from command name
- `validate_cli_environment()` - Checks CLI availability and MCP servers
- `build_cli_command()` - Constructs CLI invocations with proper flags for each CLI type
- `write_run_log()` - Persists execution logs to `logs/`

**Legacy compatibility** (`copilot_runner.py`):
- Kept for backward compatibility, re-exports functions from `cli_runner.py`
- New code should import from `cli_runner.py` directly

Key workflow modules:
- `zotero_prompt_runner.py` - Handles Zotero upload workflow
- `weekly_idea_runner.py` - Handles weekly idea generation workflow

### Data Flow

```
arXiv API → arxiv_fetcher.py → data/papers/papers_YYYY-MM-DD.json
                              ↓
                         paper_summarizer.py (agent/llm) → data/summaries/summaries_YYYY-MM-DD.json
                              ↓
                         trend_analyzer.py (agent/llm) → data/analysis/analysis_YYYY-MM-DD.json
                              ↓
                         zotero_upload.py (CLI + Zotero MCP) → Zotero library
                              ↓
                         weekly_idea.py (CLI + Zotero MCP) → idea collection
```

### Deduplication Strategy

Papers are deduplicated using a signature hash (`build_paper_set_signature()` in `src/utils.py`):
- Signature = sorted concatenation of `(arxiv_id, title, published_date)`
- Stored in `data/runtime/seen_papers.json`
- Pipeline skips summarization/analysis if no new papers found

### Artifact Reuse

The daily pipeline checks for reusable artifacts before running expensive operations:
- `get_reusable_artifact_run_id()` in `main.py` validates that all artifacts (papers, summaries, analysis) belong to the same run and match the current paper set
- If valid, skips re-execution and reuses existing outputs
- Prevents redundant CLI invocations when re-running the same date

## Common Development Commands

### Environment Setup

```bash
# Create virtual environment (Python 3.12+ required)
conda create -n auto-research python=3.12 -y
conda activate auto-research

# Install dependencies
pip install uv
uv pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with API keys (optional for agent mode)
```

### CLI Configuration

To use a different CLI, edit `config/config.yaml`:

```yaml
agent:
  copilot_command: "claude"  # or "codex" or full path like "/usr/local/bin/claude"
```

The system will automatically detect the CLI type and use appropriate command-line flags.

### Testing

```bash
# Test individual components
python test/test_fetcher.py          # arXiv crawler
python test/test_summarizer.py       # Summarization config
python test/test_analyzer.py         # Trend analysis config
python test/test_weekly_idea.py      # Weekly idea config
python test/test_zotero_upload.py    # Zotero upload config
python test/test_web.py              # Web service
python test/test_scheduler.py        # Scheduler config
```

### Running Workflows

```bash
# Manual execution
python main.py                       # Daily pipeline
python zotero_upload.py              # Zotero upload
python weekly_idea.py                # Weekly idea generation

# Web UI (development mode)
python src/web/app.py                # Starts on http://localhost:5000

# Scheduled execution
./deploy/start.sh                    # Recommended
python scheduler.py                  # Direct invocation
```

### Configuration

Primary config: `config/config.yaml`

Key sections:
- `arxiv.*` - Search categories, keywords, max results
- `agent.*` - CLI settings (command, model, reasoning effort), prompt files, timeouts
- `pipeline.*` - Backend selection (agent vs llm)
- `llm.*` - Legacy provider configs (OpenAI, Gemini, Claude, DeepSeek, vLLM)
- `scheduler.*` - Cron schedules for all workflows
- `web.*` - Flask server settings

Prompt templates: `config/prompts/*.txt`

### Logs and Artifacts

```
logs/
├── daily_digest/       # CLI summarization logs
├── daily_analysis/     # CLI analysis logs
├── zotero_upload/      # Zotero upload logs
└── weekly_idea/        # Weekly idea logs

data/
├── papers/             # Fetched paper metadata
├── summaries/          # Generated summaries
├── analysis/           # Trend analysis + word clouds
├── fulltext/           # MinerU-extracted paper PDFs
└── runtime/            # Deduplication state, pipeline locks
```

## Important Patterns

### CLI Invocation

All agent-mode tasks follow this pattern:
1. Validate environment (CLI + MCP servers) via `validate_cli_environment()`
2. Build command with `build_cli_command()` which handles CLI-specific flags
3. Run with timeout (default: 180-360 minutes)
4. Parse stdout for structured output (JSON/Markdown)
5. Write execution log to `logs/`

The `build_cli_command()` function automatically:
- Detects CLI type from command name
- Adds appropriate flags (`-p` for prompt, `--no-ask-user` for non-interactive mode)
- Disables non-required MCP servers
- Sets model and reasoning effort if specified

### Adding Support for New CLIs

To add support for a new CLI:
1. Add CLI type constant to `CLIType` class in `cli_runner.py`
2. Update `detect_cli_type()` to recognize the new CLI
3. Implement `_build_<cli>_command()` function with CLI-specific flags
4. Update `build_cli_command()` to route to the new builder

### Pipeline State Management

- `data/runtime/pipeline_state.json` tracks last run status
- `pipeline_run_lock()` context manager prevents concurrent executions
- Zotero upload waits for pipeline completion via `wait_for_zotero_artifacts()`

### Weekly Idea Anchor Weekday

The weekly idea task uses an "anchor weekday" system:
- Configured via `scheduler.weekly_idea.day_of_week` (e.g., "thu")
- Collects papers from the most recent anchor weekday to today
- Ensures consistent weekly boundaries even if task runs late

## Dependencies

Core:
- `arxiv` - arXiv API client
- `apscheduler` - Cron scheduling
- `flask` + `flask-cors` - Web UI
- `openai`, `anthropic`, `httpx` - LLM clients (legacy mode)
- `nltk`, `jieba`, `scikit-learn`, `wordcloud` - NLP/analysis
- `zotero-mcp-server` - Zotero integration (from GitHub)

Agent mode requires:
- One of: GitHub Copilot CLI (`copilot`), Claude CLI (`claude`), or Codex CLI (`codex`)
- MinerU MCP server (PDF extraction)
- Zotero MCP server (library sync)

## Notes

- The system is timezone-aware; configure `scheduler.timezone` in config.yaml
- Paper signatures prevent duplicate processing across runs
- Agent mode is preferred over LLM mode for full-text summarization quality
- Weekly idea generation requires at least one paper collected in the target week
- All CLI tasks use `--no-ask-user` (or equivalent) to ensure non-interactive execution
- CLI type is auto-detected from the command name - no manual configuration needed beyond setting `agent.copilot_command`
