---
title: Financial Advisor Agent
emoji: 🤖
colorFrom: blue
colorTo: green
sdk: streamlit
sdk_version: 1.32.0
app_file: app.py
pinned: false
---




## ⚙️ Setup & Installation

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

## 🚀 Running the Agent

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

---





