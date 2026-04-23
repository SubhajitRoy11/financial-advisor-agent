"""
app.py — Streamlit Web UI for the Financial Advisor Agent
----------------------------------------------------------
Run locally:  streamlit run app.py
Deploy:       Push to Hugging Face Spaces (free public URL)
"""

import streamlit as st
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Financial Advisor Agent",
    page_icon="🤖",
    layout="centered",
)

# ── Header ────────────────────────────────────────────────────────────────────
st.title("🤖 Autonomous Financial Advisor Agent")
st.caption("Explains **why** your portfolio moved — linking News → Sector → Stock → Portfolio")
st.divider()

# ── Sidebar: API Key + Provider ───────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Configuration")

    provider = st.selectbox(
        "LLM Provider",
        ["gemini", "groq", "grok", "anthropic"],
        index=0,
        help="Gemini is free forever. Get key at aistudio.google.com"
    )

    key_labels = {
        "gemini":    "Gemini API Key",
        "groq":      "Groq API Key",
        "grok":      "Grok API Key",
        "anthropic": "Anthropic API Key",
    }
    key_links = {
        "gemini":    "https://aistudio.google.com/apikey",
        "groq":      "https://console.groq.com",
        "grok":      "https://console.x.ai",
        "anthropic": "https://console.anthropic.com",
    }

    api_key = st.text_input(
        key_labels[provider],
        type="password",
        placeholder="Paste your API key here",
        help=f"Get free key at: {key_links[provider]}"
    )
    st.markdown(f"[Get free {provider} key ↗]({key_links[provider]})")

    st.divider()
    st.markdown("**Market Date:** 2026-04-21")
    st.markdown("**Sentiment:** 🔴 STRONGLY BEARISH")
    st.markdown("**FII Flow:** ₹-4,500 crore")

# ── Portfolio selector ────────────────────────────────────────────────────────
st.subheader("📁 Select Portfolio")

portfolio_options = {
    "PORTFOLIO_001 — Rahul Sharma (Diversified)":      "PORTFOLIO_001",
    "PORTFOLIO_002 — Priya Patel (Banking-Heavy) ⚠️":  "PORTFOLIO_002",
    "PORTFOLIO_003 — Arun Krishnamurthy (Conservative)": "PORTFOLIO_003",
}

selected_label = st.radio(
    "Choose a portfolio to analyze:",
    list(portfolio_options.keys()),
    index=1,  # default to the interesting banking-heavy one
)
portfolio_id = portfolio_options[selected_label]

# Show portfolio quick stats
portfolio_stats = {
    "PORTFOLIO_001": {"change": "-0.44%", "value": "₹28.75L", "risk": "✅ No concentration risk"},
    "PORTFOLIO_002": {"change": "-2.73%", "value": "₹20.46L", "risk": "🔴 CRITICAL: 72% Banking"},
    "PORTFOLIO_003": {"change": "-0.04%", "value": "₹41.26L", "risk": "✅ Conservative, well hedged"},
}
stats = portfolio_stats[portfolio_id]
col1, col2, col3 = st.columns(3)
col1.metric("Day Change", stats["change"])
col2.metric("Portfolio Value", stats["value"])
col3.metric("Risk Status", stats["risk"])

st.divider()

# ── Run button ────────────────────────────────────────────────────────────────
run_clicked = st.button("🚀 Generate Briefing", type="primary", use_container_width=True)

if run_clicked:
    if not api_key:
        st.error(f"⚠️ Please enter your {key_labels[provider]} in the sidebar first.")
        st.stop()

    # Set env vars for the agent
    os.environ["LLM_PROVIDER"] = provider
    key_env = {
        "gemini": "GEMINI_API_KEY",
        "groq": "GROQ_API_KEY",
        "grok": "GROK_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY"
    }
    os.environ[key_env[provider]] = api_key

    # Run the full pipeline with a progress indicator
    with st.spinner("🧠 Analyzing portfolio and generating briefing..."):
        try:
            from agent.ingestion import MarketDataIngestion
            from agent.analytics import PortfolioAnalyticsEngine
            from agent.reasoning import ReasoningEngine
            from agent.evaluation import BriefingEvaluator
            from agent.llm_client import LLMClient

            # Load data
            ctx = MarketDataIngestion(data_dir="./data").load()

            # Load portfolio
            with open("./data/portfolios.json") as f:
                portfolios = json.load(f)["portfolios"]

            # Run pipeline — ONE LLM client, sequential
            llm      = LLMClient()
            analytics = PortfolioAnalyticsEngine(ctx).analyze(portfolios[portfolio_id])
            output    = ReasoningEngine(ctx, llm_client=llm).generate_briefing(analytics)
            eval_res  = BriefingEvaluator(use_llm_eval=False, llm_client=llm).evaluate(output, analytics)

            # ── Display results ───────────────────────────────────────────────

            # Performance banner
            st.subheader(f"📊 {analytics.user_name} — Portfolio Briefing")
            change_color = "🟢" if analytics.day_change_pct >= 0 else "🔴"
            st.metric(
                label="Today's Portfolio Change",
                value=f"{analytics.day_change_pct:+.2f}%",
                delta=f"₹{analytics.day_change_abs:+,.0f}"
            )

            # Risk alerts
            if analytics.risk_alerts:
                for alert in analytics.risk_alerts:
                    if alert.level == "CRITICAL":
                        st.error(f"🔴 **{alert.level}:** {alert.message}")
                    else:
                        st.warning(f"🟠 **{alert.level}:** {alert.message}")

            # Main briefing
            st.subheader("📰 AI Briefing")
            st.info(output.briefing)

            # Causal chains
            if output.causal_chains:
                st.subheader("🔗 Causal Chains")
                for chain in output.causal_chains:
                    st.markdown(f"**→** {chain}")

            # Conflicting signals
            if output.conflicting_signals:
                st.subheader("⚡ Conflicting Signals")
                for cs in output.conflicting_signals:
                    st.markdown(f"• {cs}")

            # Holdings table
            st.subheader("📋 Holdings Breakdown")
            stock_holdings = [h for h in analytics.holdings if h.holding_type == "STOCK"]
            if stock_holdings:
                import pandas as pd
                df = pd.DataFrame([{
                    "Symbol":   h.symbol,
                    "Sector":   h.sector,
                    "Weight %": f"{h.weight_in_portfolio:.1f}%",
                    "Day Change": f"{h.day_change_pct:+.2f}%",
                    "Day P&L":  f"₹{h.day_change_abs:+,.0f}",
                } for h in sorted(stock_holdings,
                                   key=lambda x: x.weight_in_portfolio,
                                   reverse=True)])
                st.dataframe(df, use_container_width=True, hide_index=True)

            # Quality score
            st.subheader("🎯 Reasoning Quality")
            score_pct = int(eval_res.overall_score * 100)
            st.progress(eval_res.overall_score)
            st.caption(f"Score: {score_pct}/100 ({eval_res.method}) — {eval_res.explanation}")

        except Exception as e:
            err = str(e)
            if "429" in err:
                st.error("⚠️ **Rate limit hit.** Your API key has hit its free tier limit. "
                         "Wait 1 minute and try again, or create a new API key.")
            elif "API key" in err or "401" in err:
                st.error("❌ **Invalid API key.** Please check your key and try again.")
            else:
                st.error(f"❌ Error: {err}")

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption("Built with Streamlit · Powered by Gemini/Grok/Anthropic · "
           "Data: Mock Indian Market Data (Apr 2026)")
