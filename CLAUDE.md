# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TradingAgents is a multi-agent LLM financial trading framework built with LangGraph. It deploys specialized agents (analysts, researchers, trader, risk managers, portfolio manager) that collaboratively evaluate market conditions and produce trading decisions.

## Common Commands

```bash
# Install
pip install .

# Run CLI
tradingagents                # installed entry point
python -m cli.main           # from source

# Tests
pytest                       # all tests
pytest -m unit               # unit tests only
pytest -m smoke              # smoke tests only
pytest tests/test_memory_log.py          # single test file
pytest tests/test_memory_log.py::test_name  # single test

# Run a quick analysis from Python
python main.py
```

## Architecture

### Agent Pipeline (LangGraph)

The core workflow is a LangGraph state machine defined in `tradingagents/graph/`:

1. **Analyst Team** (`tradingagents/agents/analysts/`) — four parallel analysts (fundamentals, market/technical, news, social media) each produce reports
2. **Researcher Team** (`tradingagents/agents/researchers/`) — bull and bear researchers debate analyst findings via `InvestDebateState`
3. **Research Manager** (`tradingagents/agents/managers/research_manager.py`) — synthesizes debate into a research report
4. **Trader** (`tradingagents/agents/trader/trader.py`) — produces a trade proposal from all reports
5. **Risk Management** (`tradingagents/agents/risk_mgmt/`) — aggressive/conservative/neutral debators evaluate risk via `RiskDebateState`
6. **Portfolio Manager** (`tradingagents/agents/managers/portfolio_manager.py`) — final approve/reject decision

Entry point: `TradingAgentsGraph` in `tradingagents/graph/trading_graph.py`. Call `.propagate(ticker, date)` to run the full pipeline.

### Key Subsystems

- **LLM Clients** (`tradingagents/llm_clients/`) — provider abstraction (OpenAI, Anthropic, Google, xAI, DeepSeek, Qwen, GLM, OpenRouter, Ollama, Azure). `factory.py` creates clients; `model_catalog.py` maps model names.
- **Data Flows** (`tradingagents/dataflows/`) — market data abstraction. Supports yfinance and Alpha Vantage backends. Vendor selection is config-driven (`data_vendors` / `tool_vendors` in config).
- **Agent Utilities** (`tradingagents/agents/utils/`) — shared tools (`agent_utils.py` for data-fetching tool functions), state definitions (`agent_states.py`), structured output schemas (`schemas.py`, `structured.py`), memory/reflection (`memory.py`), rating scale (`rating.py`).
- **Graph internals** (`tradingagents/graph/`) — `setup.py` builds the LangGraph graph, `conditional_logic.py` handles routing, `propagation.py` runs the graph, `signal_processing.py` extracts trading signals, `reflection.py` handles post-decision reflection, `checkpointer.py` manages checkpoint resume.
- **CLI** (`cli/`) — Typer-based CLI with Rich UI. `main.py` is the entry point, `config.py` handles provider/model selection, `models.py` defines data models.

### Configuration

All defaults live in `tradingagents/default_config.py`. Key settings: `llm_provider`, `deep_think_llm`, `quick_think_llm`, `max_debate_rounds`, `data_vendors`, `checkpoint_enabled`, `output_language`.

### Persistence

- **Decision log**: `~/.tradingagents/memory/trading_memory.md` — appended after each run, includes reflection on realized returns. Override with `TRADINGAGENTS_MEMORY_LOG_PATH`.
- **Checkpoints**: opt-in (`checkpoint_enabled: True`), SQLite per ticker at `~/.tradingagents/cache/checkpoints/`. Override base with `TRADINGAGENTS_CACHE_DIR`.
- **Data cache**: `~/.tradingagents/cache/`

### State Types

Three LangGraph state schemas in `agent_states.py`:
- `AgentState` — main pipeline state (carries all analyst/researcher/trader reports)
- `InvestDebateState` — bull vs bear researcher debate
- `RiskDebateState` — risk management debate

### Test Markers

Tests use pytest markers: `unit`, `integration`, `smoke`. The `conftest.py` auto-patches API key env vars with placeholders so tests don't hang without keys.
