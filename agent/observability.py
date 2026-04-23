"""
observability.py — Tracing & Structured Logging
-------------------------------------------------
WHY THIS FILE EXISTS:
  The assignment requires Langfuse integration.
  But more importantly, this teaches you a KEY principle:
  In production AI systems, you MUST be able to audit what the LLM was
  given and what it returned. Debugging "why did the agent say X?" is
  impossible without traces.

  We implement two modes:
  1. Langfuse (if LANGFUSE_SECRET_KEY is set in environment)
  2. Local JSON trace logs (always runs, even without Langfuse)

  The local traces are written to ./traces/ and are human-readable JSON.
  This means even without Langfuse, you have full observability.
"""

import json
import os
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Any


@dataclass
class TraceEvent:
    """A single traceable event in the agent's execution."""
    event_type: str         # e.g. "ingestion", "analytics", "llm_call", "evaluation"
    timestamp: str
    duration_ms: float
    portfolio_id: str
    metadata: dict          # event-specific data (prompt, response, scores, etc.)


class ObservabilityManager:
    """
    Manages tracing and logging.
    Drop-in support for Langfuse if configured.
    Always writes to local JSON trace logs.
    """

    def __init__(self, trace_dir: str = "./traces"):
        self.trace_dir = Path(trace_dir)
        self.trace_dir.mkdir(exist_ok=True)
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.events: list[TraceEvent] = []

        # Try to initialize Langfuse
        self.langfuse = None
        self._init_langfuse()

    def _init_langfuse(self):
        """Initialize Langfuse if credentials are available."""
        secret_key = os.getenv("LANGFUSE_SECRET_KEY")
        public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
        host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")

        if secret_key and public_key:
            try:
                from langfuse import Langfuse
                self.langfuse = Langfuse(
                    secret_key=secret_key,
                    public_key=public_key,
                    host=host,
                )
                print("[Observability] Langfuse initialized ✓")
            except ImportError:
                print("[Observability] Langfuse package not installed. "
                      "Run: pip install langfuse")
            except Exception as e:
                print(f"[Observability] Langfuse init failed: {e}. Using local only.")
        else:
            print("[Observability] No Langfuse credentials found. "
                  "Set LANGFUSE_SECRET_KEY + LANGFUSE_PUBLIC_KEY to enable cloud tracing. "
                  "Writing local traces to ./traces/")

    def log_ingestion(
        self,
        portfolio_id: str,
        num_stocks: int,
        num_news: int,
        market_sentiment: str,
        duration_ms: float,
    ):
        event = TraceEvent(
            event_type="ingestion",
            timestamp=datetime.now().isoformat(),
            duration_ms=duration_ms,
            portfolio_id=portfolio_id,
            metadata={
                "stocks_loaded": num_stocks,
                "news_loaded": num_news,
                "market_sentiment": market_sentiment,
            },
        )
        self._record(event)

    def log_analytics(
        self,
        portfolio_id: str,
        day_change_pct: float,
        risk_alerts: int,
        confidence: float,
        duration_ms: float,
    ):
        event = TraceEvent(
            event_type="analytics",
            timestamp=datetime.now().isoformat(),
            duration_ms=duration_ms,
            portfolio_id=portfolio_id,
            metadata={
                "day_change_pct": day_change_pct,
                "risk_alerts_count": risk_alerts,
                "confidence_score": confidence,
            },
        )
        self._record(event)

    def log_llm_call(
        self,
        portfolio_id: str,
        prompt_preview: str,    # first 200 chars of prompt
        response_preview: str,  # first 200 chars of response
        tokens_used: int,
        duration_ms: float,
        success: bool,
    ):
        event = TraceEvent(
            event_type="llm_call",
            timestamp=datetime.now().isoformat(),
            duration_ms=duration_ms,
            portfolio_id=portfolio_id,
            metadata={
                "prompt_preview": prompt_preview[:200],
                "response_preview": response_preview[:200],
                "tokens_used": tokens_used,
                "success": success,
            },
        )
        self._record(event)

        # Send to Langfuse if available
        if self.langfuse:
            try:
                trace = self.langfuse.trace(
                    name="financial_advisor_briefing",
                    id=f"{self.session_id}_{portfolio_id}",
                    metadata={"portfolio_id": portfolio_id},
                )
                trace.generation(
                    name="briefing_generation",
                    input=prompt_preview,
                    output=response_preview,
                    usage={
                        "output": tokens_used,
                    },
                )
            except Exception as e:
                print(f"[Observability] Langfuse log failed: {e}")

    def log_evaluation(
        self,
        portfolio_id: str,
        overall_score: float,
        method: str,
        rule_checks: dict[str, bool],
        duration_ms: float,
    ):
        event = TraceEvent(
            event_type="evaluation",
            timestamp=datetime.now().isoformat(),
            duration_ms=duration_ms,
            portfolio_id=portfolio_id,
            metadata={
                "overall_score": overall_score,
                "method": method,
                "rule_checks": rule_checks,
            },
        )
        self._record(event)

        # Score in Langfuse
        if self.langfuse:
            try:
                self.langfuse.score(
                    trace_id=f"{self.session_id}_{portfolio_id}",
                    name="reasoning_quality",
                    value=overall_score,
                    comment=f"Method: {method}",
                )
            except Exception as e:
                print(f"[Observability] Langfuse score failed: {e}")

    def _record(self, event: TraceEvent):
        """Save event to in-memory list and to local JSON file."""
        self.events.append(event)
        self._write_trace()

    def _write_trace(self):
        """Write all events to a session trace file."""
        trace_file = self.trace_dir / f"trace_{self.session_id}.json"
        with open(trace_file, "w") as f:
            json.dump(
                {
                    "session_id": self.session_id,
                    "events": [
                        {
                            "event_type": e.event_type,
                            "timestamp": e.timestamp,
                            "duration_ms": e.duration_ms,
                            "portfolio_id": e.portfolio_id,
                            "metadata": e.metadata,
                        }
                        for e in self.events
                    ],
                },
                f,
                indent=2,
            )

    def get_session_summary(self) -> dict:
        """Return a summary of this session's performance."""
        total_tokens = sum(
            e.metadata.get("tokens_used", 0)
            for e in self.events
            if e.event_type == "llm_call"
        )
        total_duration = sum(e.duration_ms for e in self.events)
        eval_scores = [
            e.metadata.get("overall_score", 0)
            for e in self.events
            if e.event_type == "evaluation"
        ]
        avg_quality = sum(eval_scores) / len(eval_scores) if eval_scores else 0

        return {
            "session_id": self.session_id,
            "total_events": len(self.events),
            "total_tokens_used": total_tokens,
            "total_duration_ms": total_duration,
            "avg_reasoning_quality": round(avg_quality, 3),
            "trace_file": str(self.trace_dir / f"trace_{self.session_id}.json"),
        }


# ── Simple timer context manager ────────────────────────────────────────────

class Timer:
    """Use with `with Timer() as t:` then access `t.elapsed_ms`."""
    def __enter__(self):
        self.start = time.perf_counter()
        return self

    def __exit__(self, *args):
        self.elapsed_ms = (time.perf_counter() - self.start) * 1000
