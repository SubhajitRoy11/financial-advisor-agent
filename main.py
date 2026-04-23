"""
main.py — Orchestrator
-----------------------
Wires all modules together in sequence:
1. Ingest → 2. Analyze → 3. Reason (1 LLM call) → 4. Evaluate → 5. Print

ONE LLM client, shared across everything.
Calls happen one at a time, never simultaneously.
"""

import json
import sys
import time
import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()  # loads .env file if it exists

sys.path.insert(0, str(Path(__file__).parent))

from agent.ingestion import MarketDataIngestion
from agent.analytics import PortfolioAnalyticsEngine
from agent.reasoning import ReasoningEngine
from agent.evaluation import BriefingEvaluator
from agent.observability import ObservabilityManager, Timer
from agent.llm_client import LLMClient


def print_banner():
    print("\n" + "="*60)
    print("  🤖  AUTONOMOUS FINANCIAL ADVISOR AGENT")
    print("="*60 + "\n")


def print_output(analytics, output, eval_result):
    print(f"\n{'─'*60}")
    print(f"📊 {analytics.user_name}  |  {analytics.portfolio_type}")
    print(f"{'─'*60}")

    sign = "+" if analytics.day_change_pct >= 0 else ""
    print(f"\n📈 Day Change : {sign}{analytics.day_change_pct:.2f}%  "
          f"(₹{analytics.day_change_abs:+,.0f})")
    print(f"   Total Value: ₹{analytics.total_current_value:,.0f}")

    if analytics.risk_alerts:
        print(f"\n⚠️  RISK ALERTS")
        for a in analytics.risk_alerts:
            icon = "🔴" if a.level == "CRITICAL" else "🟠"
            print(f"   {icon} {a.message}")

    print(f"\n📰 BRIEFING")
    # Word-wrap the briefing at 70 chars for readability
    words = output.briefing.split()
    line, lines = [], []
    for w in words:
        line.append(w)
        if len(" ".join(line)) > 70:
            lines.append("   " + " ".join(line[:-1]))
            line = [w]
    if line:
        lines.append("   " + " ".join(line))
    print("\n".join(lines))

    if output.causal_chains:
        print(f"\n🔗 CAUSAL CHAINS")
        for c in output.causal_chains:
            print(f"   → {c}")

    if output.conflicting_signals:
        print(f"\n⚡ CONFLICTS")
        for c in output.conflicting_signals:
            print(f"   • {c}")

    print(f"\n🎯 Quality Score : {eval_result.overall_score*100:.0f}/100"
          f"  ({eval_result.method})")
    print()


def run_agent(portfolio_id, market_ctx, portfolios_data,
              analytics_engine, reasoning_engine, evaluator, obs):

    portfolio = portfolios_data.get(portfolio_id)
    if not portfolio:
        print(f"[ERROR] Portfolio '{portfolio_id}' not found.")
        print(f"Available: {list(portfolios_data.keys())}")
        return

    # Step 1 — Analytics (no LLM, instant)
    with Timer() as t:
        analytics = analytics_engine.analyze(portfolio)
    obs.log_analytics(portfolio_id, analytics.day_change_pct,
                      len(analytics.risk_alerts), analytics.confidence_score, t.elapsed_ms)

    # Step 2 — Reasoning (1 LLM call)
    with Timer() as t:
        output = reasoning_engine.generate_briefing(analytics)
    obs.log_llm_call(portfolio_id, analytics.user_name,
                     output.briefing[:200], output.tokens_used, t.elapsed_ms, True)

    # Step 3 — Evaluation
    # If --no-llm-eval: pure rule-based, zero API calls
    # If LLM eval: wait 5s first so we don't fire two calls in a row
    if evaluator.use_llm_eval:
        print("[Wait] 5s pause before evaluation call...")
        time.sleep(5)

    with Timer() as t:
        eval_result = evaluator.evaluate(output, analytics)
    obs.log_evaluation(portfolio_id, eval_result.overall_score,
                       eval_result.method, eval_result.rule_checks, t.elapsed_ms)

    output.reasoning_quality_score = eval_result.overall_score
    output.reasoning_quality_explanation = eval_result.explanation

    print_output(analytics, output, eval_result)
    return analytics, output, eval_result


def main():
    parser = argparse.ArgumentParser(description="Financial Advisor Agent")
    parser.add_argument("--portfolio", type=str, default=None,
                        help="PORTFOLIO_001 | PORTFOLIO_002 | PORTFOLIO_003")
    parser.add_argument("--no-llm-eval", action="store_true",
                        help="Skip LLM evaluation (faster, no extra API call)")
    parser.add_argument("--data-dir", type=str, default="./data")
    args = parser.parse_args()

    print_banner()

    obs = ObservabilityManager(trace_dir="./traces")

    # ── Ingest (no LLM) ───────────────────────────────────────────────────────
    with Timer() as t:
        ingestion = MarketDataIngestion(data_dir=args.data_dir)
        market_ctx = ingestion.load()
    obs.log_ingestion("GLOBAL", len(market_ctx.stocks), len(market_ctx.news),
                      market_ctx.overall_sentiment, t.elapsed_ms)

    print(f"   Date      : {market_ctx.date}")
    print(f"   Sentiment : {market_ctx.overall_sentiment}")
    print(f"   FII Flow  : ₹{market_ctx.fii_net_cr:,.0f} crore")
    print(f"   Breadth   : {market_ctx.market_breadth_ratio:.0%} advancing\n")

    # ── Load portfolios ───────────────────────────────────────────────────────
    with open(os.path.join(args.data_dir, "portfolios.json")) as f:
        portfolios_data = json.load(f)["portfolios"]

    # ── ONE shared LLM client — created once, used by both engines ────────────
    llm = LLMClient()

    analytics_engine  = PortfolioAnalyticsEngine(market_ctx)
    reasoning_engine  = ReasoningEngine(market_ctx, llm_client=llm)
    evaluator         = BriefingEvaluator(use_llm_eval=not args.no_llm_eval,
                                          llm_client=llm)

    # ── Run ───────────────────────────────────────────────────────────────────
    if args.portfolio:
        run_agent(args.portfolio, market_ctx, portfolios_data,
                  analytics_engine, reasoning_engine, evaluator, obs)
    else:
        ids = list(portfolios_data.keys())
        for i, pid in enumerate(ids):
            run_agent(pid, market_ctx, portfolios_data,
                      analytics_engine, reasoning_engine, evaluator, obs)
            if i < len(ids) - 1:
                print(f"\n⏳ Waiting 15s before next portfolio (rate limit)...")
                time.sleep(15)

    # ── Summary ───────────────────────────────────────────────────────────────
    s = obs.get_session_summary()
    print("="*60)
    print(f"  Tokens used : {s['total_tokens_used']}")
    print(f"  Time        : {s['total_duration_ms']:.0f}ms")
    print(f"  Avg quality : {s['avg_reasoning_quality']*100:.0f}/100")
    print(f"  Trace file  : {s['trace_file']}")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
