

import json
import os
from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# DATA CLASSES  (Think of these as "contracts" — they describe exactly what
#               shape data will have throughout the system)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class IndexData:
    name: str
    current_value: float
    change_percent: float
    sentiment: str          # BULLISH | BEARISH | NEUTRAL


@dataclass
class StockData:
    symbol: str
    name: str
    sector: str
    current_price: float
    change_percent: float
    volume: int
    beta: float


@dataclass
class SectorData:
    name: str
    change_percent: float
    sentiment: str
    key_drivers: list[str]
    top_losers: list[str]
    top_gainers: list[str]


@dataclass
class NewsItem:
    id: str
    headline: str
    summary: str
    sentiment: str          # POSITIVE | NEGATIVE | MIXED | NEUTRAL
    sentiment_score: float  # -1.0 to +1.0
    scope: str              # MARKET_WIDE | SECTOR_SPECIFIC | STOCK_SPECIFIC
    impact_level: str       # HIGH | MEDIUM | LOW
    sectors: list[str]
    stocks: list[str]
    causal_factors: list[str]
    has_conflict: bool = False
    conflict_explanation: str = ""


@dataclass
class MarketContext:
    """The full market picture for one trading day."""
    date: str
    overall_sentiment: str          # computed from indices
    indices: dict[str, IndexData]
    sectors: dict[str, SectorData]
    stocks: dict[str, StockData]
    news: list[NewsItem]
    fii_net_cr: float               # FII net buy/sell in crores
    market_breadth_ratio: float     # advances / (advances + declines)


# ─────────────────────────────────────────────────────────────────────────────
# LOADER CLASS
# ─────────────────────────────────────────────────────────────────────────────

class MarketDataIngestion:
    """
    Loads all data files and exposes a single .load() method that returns
    a fully-populated MarketContext object.
    """

    def __init__(self, data_dir: str = "./data"):
        self.data_dir = data_dir

    def _load_json(self, filename: str) -> dict:
        """Load a JSON file from the data directory."""
        path = os.path.join(self.data_dir, filename)
        with open(path, "r") as f:
            return json.load(f)

    def _compute_overall_sentiment(self, indices: dict[str, IndexData]) -> str:
        """
        REASONING: We look at NIFTY50 (broad market) + BANKNIFTY (largest sector).
        If both are down > 1%, the market is clearly BEARISH.
        If NIFTY is flat but sectors diverge, it's MIXED.
        """
        nifty = indices.get("NIFTY50")
        banknifty = indices.get("BANKNIFTY")

        if not nifty:
            return "UNKNOWN"

        avg_change = nifty.change_percent
        if banknifty:
            avg_change = (nifty.change_percent + banknifty.change_percent) / 2

        if avg_change <= -1.5:
            return "STRONGLY_BEARISH"
        elif avg_change <= -0.3:
            return "BEARISH"
        elif avg_change >= 1.5:
            return "STRONGLY_BULLISH"
        elif avg_change >= 0.3:
            return "BULLISH"
        else:
            return "NEUTRAL"

    def _parse_indices(self, raw: dict) -> dict[str, IndexData]:
        result = {}
        for symbol, data in raw.get("indices", {}).items():
            result[symbol] = IndexData(
                name=data["name"],
                current_value=data["current_value"],
                change_percent=data["change_percent"],
                sentiment=data.get("sentiment", "NEUTRAL"),
            )
        return result

    def _parse_stocks(self, raw: dict) -> dict[str, StockData]:
        result = {}
        for symbol, data in raw.get("stocks", {}).items():
            result[symbol] = StockData(
                symbol=symbol,
                name=data["name"],
                sector=data["sector"],
                current_price=data["current_price"],
                change_percent=data["change_percent"],
                volume=data.get("volume", 0),
                beta=data.get("beta", 1.0),
            )
        return result

    def _parse_sectors(self, raw: dict) -> dict[str, SectorData]:
        result = {}
        for name, data in raw.get("sector_performance", {}).items():
            result[name] = SectorData(
                name=name,
                change_percent=data["change_percent"],
                sentiment=data["sentiment"],
                key_drivers=data.get("key_drivers", []),
                top_losers=data.get("top_losers", []),
                top_gainers=data.get("top_gainers", []),
            )
        return result

    def _parse_news(self, raw: dict) -> list[NewsItem]:
        items = []
        for article in raw.get("news", []):
            entities = article.get("entities", {})
            items.append(NewsItem(
                id=article["id"],
                headline=article["headline"],
                summary=article.get("summary", ""),
                sentiment=article["sentiment"],
                sentiment_score=article.get("sentiment_score", 0.0),
                scope=article["scope"],
                impact_level=article.get("impact_level", "LOW"),
                sectors=entities.get("sectors", []),
                stocks=entities.get("stocks", []),
                causal_factors=article.get("causal_factors", []),
                has_conflict=article.get("conflict_flag", False),
                conflict_explanation=article.get("conflict_explanation", ""),
            ))
        return items

    def load(self) -> MarketContext:
        """
        Main entry point. Loads all files and returns a clean MarketContext.
        DESIGN PRINCIPLE: Fail loudly with clear errors, not silently with bad data.
        """
        print("[Ingestion] Loading market data...")
        market_raw = self._load_json("market_data.json")
        news_raw = self._load_json("news_data.json")
        historical_raw = self._load_json("historical_data.json")

        indices = self._parse_indices(market_raw)
        stocks = self._parse_stocks(market_raw)
        sectors = self._parse_sectors(market_raw)
        news = self._parse_news(news_raw)

        # Pull FII/DII data from historical for market flow context
        fii_data = historical_raw.get("fii_dii_data", {})
        fii_net = fii_data.get("fii", {}).get("net_value_cr", 0.0)

        # Market breadth
        breadth = historical_raw.get("market_breadth", {}).get("nifty50", {})
        advances = breadth.get("advances", 0)
        declines = breadth.get("declines", 1)
        breadth_ratio = advances / (advances + declines)

        overall_sentiment = self._compute_overall_sentiment(indices)

        print(f"[Ingestion] Loaded {len(stocks)} stocks, {len(news)} news items. "
              f"Market: {overall_sentiment}")

        return MarketContext(
            date=market_raw["metadata"]["date"],
            overall_sentiment=overall_sentiment,
            indices=indices,
            sectors=sectors,
            stocks=stocks,
            news=news,
            fii_net_cr=fii_net,
            market_breadth_ratio=breadth_ratio,
        )
