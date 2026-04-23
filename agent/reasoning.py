"""
reasoning.py — Autonomous Reasoning Layer
------------------------------------------
Calls the LLM with a lean, focused prompt.
Prompt is kept under 1500 chars to work on all free API tiers.
"""

import json
import os
import re
from dataclasses import dataclass
from agent.ingestion import MarketContext, NewsItem
from agent.analytics import PortfolioAnalytics, HoldingAnalysis
from agent.llm_client import LLMClient


@dataclass
class ReasoningOutput:
    briefing: str
    causal_chains: list[str]
    risk_summary: str
    confidence_score: float
    reasoning_quality_score: float
    reasoning_quality_explanation: str
    conflicting_signals: list[str]
    tokens_used: int = 0


class ReasoningEngine:

    def __init__(self, market_ctx: MarketContext, llm_client: LLMClient = None):
        self.market = market_ctx
        self.llm = llm_client or LLMClient()

    def _filter_relevant_news(
        self,
        analytics: PortfolioAnalytics,
        max_items: int = 4,          # reduced from 8 → keeps prompt short
    ) -> list[NewsItem]:
        """Pick only the most relevant news for this portfolio."""
        portfolio_sectors = set(analytics.sector_allocation.keys())
        portfolio_stocks  = {h.symbol for h in analytics.holdings}

        scored = []
        for news in self.market.news:
            score = 0
            if news.scope == "MARKET_WIDE":            score += 3
            if any(s in portfolio_sectors for s in news.sectors): score += 2
            if any(s in portfolio_stocks  for s in news.stocks):  score += 4
            if news.impact_level == "HIGH":            score += 2
            if news.has_conflict:                      score += 1
            if score > 0:
                scored.append((score, news))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [n for _, n in scored[:max_items]]

    def _build_prompt(
        self,
        analytics: PortfolioAnalytics,
        relevant_news: list[NewsItem],
    ) -> str:
        """
        Lean prompt — all essential info, nothing redundant.
        Kept under ~1500 chars so it works on every free API tier.
        """
        # Indices one-liner
        nifty     = self.market.indices.get("NIFTY50")
        banknifty = self.market.indices.get("BANKNIFTY")
        niftyit   = self.market.indices.get("NIFTYIT")
        idx = (f"NIFTY50 {nifty.change_percent:+.2f}% | "
               f"BANKNIFTY {banknifty.change_percent:+.2f}% | "
               f"NIFTYIT {niftyit.change_percent:+.2f}%")

        # Top 4 holdings one-liner each
        top_h = sorted(
            [h for h in analytics.holdings if h.holding_type == "STOCK"],
            key=lambda h: h.weight_in_portfolio, reverse=True
        )[:4]
        holdings = "; ".join(
            f"{h.symbol}({h.weight_in_portfolio:.0f}%,{h.day_change_pct:+.1f}%)"
            for h in top_h
        )

        # Top sector exposure
        top_s = sorted(analytics.sector_allocation.items(),
                       key=lambda x: x[1], reverse=True)[:3]
        sectors = ", ".join(f"{s}:{w:.0f}%" for s, w in top_s)

        # Risk alerts (one line each)
        risks = "; ".join(f"[{a.level}]{a.message[:60]}" for a in analytics.risk_alerts) \
                or "None"

        # News (headline + conflict flag only — no summaries)
        news_lines = []
        for n in relevant_news:
            flag = " ⚠️CONFLICT" if n.has_conflict else ""
            news_lines.append(
                f"- [{n.scope}][{n.sentiment}] {n.headline}{flag}"
            )
        news_block = "\n".join(news_lines)

        prompt = f"""You are a financial advisor AI. Analyze this portfolio and explain why it moved today.

MARKET ({self.market.date}): {idx} | FII: ₹{self.market.fii_net_cr:,.0f}cr | Sentiment: {self.market.overall_sentiment}

PORTFOLIO: {analytics.user_name} ({analytics.portfolio_type})
Day change: {analytics.day_change_pct:+.2f}% (₹{analytics.day_change_abs:,.0f})
Top holdings: {holdings}
Sector exposure: {sectors}
Risk alerts: {risks}

NEWS (relevant):
{news_block}

Reply ONLY with this JSON (no markdown):
{{
  "briefing": "2-3 sentences explaining WHY the portfolio moved, naming specific stocks and news",
  "causal_chains": ["News → Sector → Stock → Portfolio impact"],
  "risk_summary": "1 sentence on concentration risk if any",
  "conflicting_signals": ["explain any ⚠️CONFLICT items"],
  "confidence_score": 0.85
}}"""

        return prompt

    def _call_llm(self, prompt: str) -> tuple[str, int]:
        return self.llm.call(prompt, max_tokens=600)   # reduced from 1500

    def _parse_llm_response(self, raw: str) -> dict:
        cleaned = re.sub(r"```json\s*|\s*```", "", raw).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                return json.loads(match.group())
            # Fallback: wrap raw text in expected structure
            return {
                "briefing": raw[:500],
                "causal_chains": [],
                "risk_summary": "",
                "conflicting_signals": [],
                "confidence_score": 0.5,
            }

    def generate_briefing(self, analytics: PortfolioAnalytics) -> ReasoningOutput:
        print(f"[Reasoning] Building briefing for {analytics.user_name}...")
        relevant_news = self._filter_relevant_news(analytics)
        print(f"[Reasoning] Using {len(relevant_news)} news items.")

        prompt = self._build_prompt(analytics, relevant_news)
        print(f"[Reasoning] Prompt size: {len(prompt)} chars. Calling LLM...")

        raw_response, tokens = self._call_llm(prompt)
        parsed = self._parse_llm_response(raw_response)

        return ReasoningOutput(
            briefing=parsed.get("briefing", ""),
            causal_chains=parsed.get("causal_chains", []),
            risk_summary=parsed.get("risk_summary", ""),
            confidence_score=float(parsed.get("confidence_score", 0.75)),
            reasoning_quality_score=0.0,
            reasoning_quality_explanation="",
            conflicting_signals=parsed.get("conflicting_signals", []),
            tokens_used=tokens,
        )
