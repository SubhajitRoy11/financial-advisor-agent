
import os
import re
import json
from dataclasses import dataclass
from agent.reasoning import ReasoningOutput
from agent.analytics import PortfolioAnalytics
from agent.llm_client import LLMClient


@dataclass
class EvaluationResult:
    overall_score: float
    causal_depth_score: float
    specificity_score: float
    conflict_handling_score: float
    risk_coverage_score: float
    rule_checks: dict[str, bool]
    explanation: str
    method: str                 


class BriefingEvaluator:

    def __init__(self, use_llm_eval: bool = True, llm_client: LLMClient = None):
        """
        use_llm_eval: If True, does a second LLM call for quality scoring.
                      If False (faster/cheaper), uses only rule-based checks.
        """
        self.use_llm_eval = use_llm_eval
        self.llm = llm_client or LLMClient()

    # ── Rule-Based Checks ────────────────────────────────────────────────────

    def _rule_based_checks(
        self,
        output: ReasoningOutput,
        analytics: PortfolioAnalytics,
    ) -> dict[str, bool]:
        """
        Fast, deterministic checks. No LLM needed.
        These verify STRUCTURAL completeness of the briefing.
        """
        briefing = output.briefing.lower()
        checks = {}

        # 1. Does it mention the portfolio's day P&L percentage?
        pct_str = f"{abs(analytics.day_change_pct):.1f}"
        checks["mentions_pnl_percentage"] = pct_str in output.briefing

        # 2. Does it name at least 2 specific stocks?
        stock_mentions = sum(
            1 for h in analytics.holdings[:10]
            if h.symbol.lower() in briefing or h.name.lower() in briefing
        )
        checks["mentions_stocks"] = stock_mentions >= 2

        # 3. Does it include at least one causal chain?
        checks["has_causal_chains"] = len(output.causal_chains) >= 1

        # 4. Does it reference market events (RBI, FII, sector moves)?
        news_keywords = ["rbi", "fii", "sector", "market", "interest rate",
                         "banking", "it sector", "inflation", "earnings"]
        checks["references_market_events"] = any(kw in briefing for kw in news_keywords)

        # 5. If risk alerts exist, does it mention risk?
        if analytics.risk_alerts:
            risk_keywords = ["concentration", "risk", "exposure", "overweight", "heavily"]
            checks["mentions_risk"] = any(kw in briefing for kw in risk_keywords)
        else:
            checks["mentions_risk"] = True  # N/A → pass

        # 6. If there were conflicting signals, does it address them?
        holdings_with_conflicts = [h for h in analytics.holdings if h.has_conflict]
        if holdings_with_conflicts:
            checks["addresses_conflicts"] = len(output.conflicting_signals) > 0
        else:
            checks["addresses_conflicts"] = True  # N/A → pass

        return checks

    def _score_from_rules(self, checks: dict[str, bool]) -> float:
        if not checks:
            return 0.5
        return sum(checks.values()) / len(checks)

    # ── LLM-Based Evaluation ─────────────────────────────────────────────────

    def _llm_evaluate(
        self,
        output: ReasoningOutput,
        analytics: PortfolioAnalytics,
    ) -> dict:
        """Ask the LLM to score the briefing on our rubric."""
        eval_prompt = f"""You are evaluating the quality of a financial portfolio briefing.

## THE BRIEFING TO EVALUATE:
{output.briefing}

## CAUSAL CHAINS PROVIDED:
{json.dumps(output.causal_chains, indent=2)}

## GROUND TRUTH:
- Portfolio: {analytics.user_name} ({analytics.portfolio_type})
- Actual day change: {analytics.day_change_pct:+.2f}%
- Risk alerts present: {len(analytics.risk_alerts) > 0}
- Top losers: {[h.symbol for h in analytics.top_losers[:3]]}

## SCORE EACH DIMENSION 0-10:

1. causal_depth (40%): Does it trace News → Sector → Stock → Portfolio?
2. specificity (30%): Does it cite actual numbers and stock names?
3. conflict_handling (20%): Does it explain conflicting signals?
4. risk_coverage (10%): Does it explain concentration risk if present?

Respond ONLY with this JSON (no markdown):
{{
  "causal_depth": 0-10,
  "specificity": 0-10,
  "conflict_handling": 0-10,
  "risk_coverage": 0-10,
  "explanation": "2-3 sentence summary"
}}"""

        raw, _ = self.llm.call(eval_prompt, max_tokens=400)
        cleaned = re.sub(r"```json\s*|\s*```", "", raw).strip()
        return json.loads(cleaned)

    # ── Main Evaluate Method ─────────────────────────────────────────────────

    def evaluate(
        self,
        output: ReasoningOutput,
        analytics: PortfolioAnalytics,
    ) -> EvaluationResult:
        print("[Evaluation] Running rule-based checks...")
        rule_checks = self._rule_based_checks(output, analytics)
        rule_score = self._score_from_rules(rule_checks)

        if self.use_llm_eval:
            print("[Evaluation] Running LLM quality evaluation...")
            try:
                scores = self._llm_evaluate(output, analytics)
                causal   = scores.get("causal_depth", 5) / 10
                specific = scores.get("specificity", 5) / 10
                conflict = scores.get("conflict_handling", 5) / 10
                risk     = scores.get("risk_coverage", 5) / 10
                explanation = scores.get("explanation", "")

                overall = (causal * 0.40) + (specific * 0.30) + \
                          (conflict * 0.20) + (risk * 0.10)
                blended = (overall * 0.7) + (rule_score * 0.3)

                return EvaluationResult(
                    overall_score=round(blended, 3),
                    causal_depth_score=causal,
                    specificity_score=specific,
                    conflict_handling_score=conflict,
                    risk_coverage_score=risk,
                    rule_checks=rule_checks,
                    explanation=explanation,
                    method="HYBRID",
                )
            except Exception as e:
                print(f"[Evaluation] LLM eval failed ({e}), falling back to rule-based.")

        # Fallback: rule-based only
        passed = sum(rule_checks.values())
        total = len(rule_checks)
        explanation = (f"Rule-based: {passed}/{total} checks passed. " +
                       ", ".join(f"{k}={'✓' if v else '✗'}"
                                 for k, v in rule_checks.items()))

        return EvaluationResult(
            overall_score=round(rule_score, 3),
            causal_depth_score=rule_score,
            specificity_score=rule_score,
            conflict_handling_score=rule_score,
            risk_coverage_score=rule_score,
            rule_checks=rule_checks,
            explanation=explanation,
            method="RULE_BASED",
        )
