# 🤖 Autonomous Financial Advisor Agent

An AI agent that ingests Indian market data, analyzes a user's portfolio, and generates a causal explanation of **why** their portfolio moved — linking macro news → sector trends → individual stock performance → portfolio impact.


**Key design principle:** Each module has exactly one responsibility.  
The LLM is called **once** per portfolio — analytics are pre-computed, not delegated to the LLM.

---

##  Project Structure

```
financial_agent/
├── main.py                    # Entry point — orchestrates all phases
├── requirements.txt
├── .env.example               # Copy to .env and add your API key
├── data/
│   ├── market_data.json       # 40 stocks, 5 indices, 10 sectors
│   ├── news_data.json         # 25 news items with sentiment + scope
│   ├── portfolios.json        # 3 user portfolios
│   ├── mutual_funds.json      # 12 MF schemes with NAV + holdings
│   ├── historical_data.json   # 7-day history, FII/DII flows, breadth
│   └── sector_mapping.json    # Macro correlations, sector characteristics
├── agent/
│   ├── ingestion.py           # Phase 1: Market Intelligence Layer
│   ├── analytics.py           # Phase 2: Portfolio Analytics Engine
│   ├── reasoning.py           # Phase 3: Autonomous Reasoning (LLM)
│   ├── evaluation.py          # Phase 4: Self-evaluation Layer
│   └── observability.py       # Tracing: Langfuse + local JSON logs
└── traces/                    # Auto-created — stores session trace files
```

---

##  Setup & Installation

### 1. Clone and install dependencies

```bash
git clone <your-repo-url>
cd financial_agent
pip install requests python-dotenv
pip install langfuse          # optional, for cloud tracing
```

### 2. Set your API key

```bash
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
# Get one at: https://console.anthropic.com

# Then load it:
export ANTHROPIC_API_KEY=sk-ant-YOUR_KEY_HERE
```

### 3. (Optional) Enable Langfuse tracing

Sign up at [cloud.langfuse.com](https://cloud.langfuse.com), create a project, and add to `.env`:

```bash
export LANGFUSE_SECRET_KEY=sk-lf-...
export LANGFUSE_PUBLIC_KEY=pk-lf-...
```

If Langfuse is not configured, traces are saved locally to `./traces/` as JSON files automatically.

---

##  Running the Agent

```bash
# Analyze all 3 portfolios
python main.py

# Analyze a specific portfolio
python main.py --portfolio PORTFOLIO_001   # Rahul — Diversified
python main.py --portfolio PORTFOLIO_002   # Priya — Banking-heavy (most interesting)
python main.py --portfolio PORTFOLIO_003   # Arun — Conservative MF-heavy

# Skip the second LLM evaluation call (faster, rule-based scoring only)
python main.py --no-llm-eval

# Use a different data directory
python main.py --data-dir ./my_data
```



##  Observability & Tracing

Every run writes a trace file to `./traces/trace_YYYYMMDD_HHMMSS.json` containing:

```json
{
  "session_id": "20260421_143022",
  "events": [
    { "event_type": "ingestion", "duration_ms": 45.2, ... },
    { "event_type": "analytics", "duration_ms": 12.1, ... },
    { "event_type": "llm_call", "tokens_used": 823, "duration_ms": 3240.5, ... },
    { "event_type": "evaluation", "overall_score": 0.84, ... }
  ]
}
```

If Langfuse is configured, all LLM generations and quality scores are also synced to the Langfuse dashboard for visual inspection.

---

## 🧪 Edge Cases Handled

| Scenario | How the Agent Handles It |
|----------|--------------------------|
| Positive news + falling price (Bajaj Finance) | `conflict_flag` detected → LLM explicitly explains sector override |
| Mixed signals (ICICI Bank NPA improved but NIM compressed) | Summarized as ambiguous with both factors mentioned |
| Sector divergence (Tata Motors up vs Auto sector down) | Stock-specific news scores higher → included in prompt |
| Conservative portfolio barely moving | Agent notes debt fund buffer and defensive stock positioning |
| 72% banking concentration on a banking crash day | CRITICAL alert + prominent mention in briefing |

---


