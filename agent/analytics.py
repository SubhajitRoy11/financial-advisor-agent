
from dataclasses import dataclass, field
from typing import Optional
from agent.ingestion import MarketContext



@dataclass
class HoldingAnalysis:
    """Analysis of a single holding (stock or MF)."""
    symbol: str
    name: str
    holding_type: str           # STOCK | MUTUAL_FUND
    sector: str
    weight_in_portfolio: float  # percentage
    current_value: float
    day_change_abs: float       # in rupees
    day_change_pct: float       # percentage
    overall_gain_loss_pct: float
    relevant_news: list[str] = field(default_factory=list)  # news IDs
    has_conflict: bool = False


@dataclass
class RiskAlert:
    level: str          # CRITICAL | HIGH | MEDIUM
    message: str
    affected_sectors: list[str] = field(default_factory=list)


@dataclass
class PortfolioAnalytics:
    """Complete analytics output for one portfolio."""
    portfolio_id: str
    user_name: str
    portfolio_type: str
    total_current_value: float
    day_change_abs: float
    day_change_pct: float
    overall_gain_loss_pct: float

    sector_allocation: dict[str, float]         # sector -> % of portfolio
    asset_type_allocation: dict[str, float]     # "STOCKS" -> %, "MF" -> %

    holdings: list[HoldingAnalysis]
    risk_alerts: list[RiskAlert]

    top_losers: list[HoldingAnalysis]           # sorted by day_change_pct asc
    top_gainers: list[HoldingAnalysis]          # sorted by day_change_pct desc
    confidence_score: float                     # 0.0-1.0, data completeness proxy


class PortfolioAnalyticsEngine:

    # Thresholds for risk detection
    SECTOR_CONCENTRATION_THRESHOLD = 40.0   # % — warn if any sector > 40%
    SINGLE_STOCK_CONCENTRATION = 20.0       # % — warn if any stock > 20%
    CRITICAL_CONCENTRATION = 70.0          # % — critical if > 70%

    def __init__(self, market_ctx: MarketContext):
        self.market = market_ctx

    def _get_stock_sector(self, symbol: str) -> str:
        """Look up a stock's sector from market data, fall back gracefully."""
        stock = self.market.stocks.get(symbol)
        return stock.sector if stock else "UNKNOWN"

    def _get_mf_primary_sector(self, mf_data: dict) -> str:
        """
        For mutual funds, we can't assign one sector easily.
        Return the top sector from the fund's allocation, or DIVERSIFIED.
        """
        top_holdings = mf_data.get("top_holdings", [])
        if not top_holdings:
            return "DIVERSIFIED"
        # Use the sector of the top holding as a proxy
        top_stock = top_holdings[0] if isinstance(top_holdings[0], str) else top_holdings[0].get("stock", "")
        return self._get_stock_sector(top_stock) if top_stock else "DIVERSIFIED"

    def _find_relevant_news(self, symbol: str, sector: str) -> tuple[list[str], bool]:
        """
        Find news items that affect this specific holding.
        Returns (list of news IDs, has_conflict_flag)
        """
        relevant = []
        has_conflict = False
        for news in self.market.news:
            if symbol in news.stocks or sector in news.sectors:
                relevant.append(news.id)
                if news.has_conflict:
                    has_conflict = True
        return relevant, has_conflict

    def _detect_risk_alerts(
        self,
        sector_alloc: dict[str, float],
        holdings: list[HoldingAnalysis],
    ) -> list[RiskAlert]:
        """
        RISK DETECTION LOGIC:
        The assignment asks to flag >40% single-sector exposure.
        We also flag critical (>70%) and single-stock concentration.
        """
        alerts = []

        # Sector concentration
        for sector, weight in sector_alloc.items():
            if sector in ("DIVERSIFIED", "DIVERSIFIED_MF", "DEBT_FUNDS"):
                continue
            if weight >= self.CRITICAL_CONCENTRATION:
                alerts.append(RiskAlert(
                    level="CRITICAL",
                    message=f"Extreme concentration: {weight:.1f}% in {sector}. "
                            f"A single sector event could devastate this portfolio.",
                    affected_sectors=[sector],
                ))
            elif weight >= self.SECTOR_CONCENTRATION_THRESHOLD:
                alerts.append(RiskAlert(
                    level="HIGH",
                    message=f"High concentration risk: {weight:.1f}% in {sector} "
                            f"(threshold: {self.SECTOR_CONCENTRATION_THRESHOLD}%).",
                    affected_sectors=[sector],
                ))

        # Single stock concentration
        for h in holdings:
            if h.holding_type == "STOCK" and h.weight_in_portfolio >= self.SINGLE_STOCK_CONCENTRATION:
                alerts.append(RiskAlert(
                    level="HIGH",
                    message=f"Single stock risk: {h.symbol} is {h.weight_in_portfolio:.1f}% of portfolio.",
                    affected_sectors=[h.sector],
                ))

        # Rate-sensitive sector overexposure during bearish macro
        rate_sensitive = {"BANKING", "REALTY", "AUTOMOBILE", "FINANCIAL_SERVICES"}
        rate_exposure = sum(
            w for s, w in sector_alloc.items() if s in rate_sensitive
        )
        if rate_exposure >= 50.0:
            alerts.append(RiskAlert(
                level="HIGH",
                message=f"High rate-sensitive exposure: {rate_exposure:.1f}% in sectors "
                        f"affected by RBI rate decisions (Banking, Realty, Auto, FS).",
                affected_sectors=list(rate_sensitive),
            ))

        return alerts

    def analyze(self, portfolio: dict) -> PortfolioAnalytics:
        """
        Main method. Takes a raw portfolio dict (from portfolios.json)
        and returns a fully-computed PortfolioAnalytics object.
        """
        holdings_raw = portfolio.get("holdings", {})
        raw_analytics = portfolio.get("analytics", {})
        day_summary = raw_analytics.get("day_summary", {})

        all_holdings: list[HoldingAnalysis] = []

        #  Process STOCKS 
        for stock in holdings_raw.get("stocks", []):
            symbol = stock["symbol"]
            sector = stock.get("sector") or self._get_stock_sector(symbol)
            news_ids, conflict = self._find_relevant_news(symbol, sector)

            # Compute gain/loss percent from raw data or recalculate
            inv = stock.get("investment_value", 1)
            curr = stock.get("current_value", inv)
            overall_pct = ((curr - inv) / inv * 100) if inv else 0.0

            all_holdings.append(HoldingAnalysis(
                symbol=symbol,
                name=stock.get("name", symbol),
                holding_type="STOCK",
                sector=sector,
                weight_in_portfolio=stock.get("weight_in_portfolio", 0.0),
                current_value=curr,
                day_change_abs=stock.get("day_change", 0.0),
                day_change_pct=stock.get("day_change_percent", 0.0),
                overall_gain_loss_pct=overall_pct,
                relevant_news=news_ids,
                has_conflict=conflict,
            ))

        # ── Process MUTUAL FUNDS ─────────────────────────────────────────────
        for mf in holdings_raw.get("mutual_funds", []):
            code = mf["scheme_code"]
            # MF sector is approximate — use the fund's primary exposure
            sector = self._get_mf_primary_sector(mf)

            inv = mf.get("investment_value", 1)
            curr = mf.get("current_value", inv)
            overall_pct = ((curr - inv) / inv * 100) if inv else 0.0

            news_ids, conflict = self._find_relevant_news(code, sector)

            all_holdings.append(HoldingAnalysis(
                symbol=code,
                name=mf.get("scheme_name", code),
                holding_type="MUTUAL_FUND",
                sector=mf.get("category", sector),
                weight_in_portfolio=mf.get("weight_in_portfolio", 0.0),
                current_value=curr,
                day_change_abs=mf.get("day_change", 0.0),
                day_change_pct=mf.get("day_change_percent", 0.0),
                overall_gain_loss_pct=overall_pct,
                relevant_news=news_ids,
                has_conflict=conflict,
            ))

        # ── Sector & Asset Allocation ────────────────────────────────────────
        sector_alloc = raw_analytics.get("sector_allocation", {})
        asset_alloc = raw_analytics.get("asset_type_allocation", {})

        # ── Risk Detection ───────────────────────────────────────────────────
        risk_alerts = self._detect_risk_alerts(sector_alloc, all_holdings)

        # ── Sort for top gainers/losers ──────────────────────────────────────
        sorted_by_change = sorted(all_holdings, key=lambda h: h.day_change_pct)
        top_losers = sorted_by_change[:3]
        top_gainers = list(reversed(sorted_by_change))[:3]
        top_gainers = [g for g in top_gainers if g.day_change_pct > 0]

        # ── Confidence Score ─────────────────────────────────────────────────
        # How much of the portfolio do we have real-time price data for?
        total_val = portfolio.get("current_value", 1)
        covered_val = sum(h.current_value for h in all_holdings if h.day_change_pct != 0)
        confidence = min(1.0, covered_val / total_val) if total_val else 0.5

        return PortfolioAnalytics(
            portfolio_id=portfolio.get("user_id", "UNKNOWN"),
            user_name=portfolio.get("user_name", "User"),
            portfolio_type=portfolio.get("portfolio_type", "UNKNOWN"),
            total_current_value=portfolio.get("current_value", 0),
            day_change_abs=day_summary.get("day_change_absolute", 0.0),
            day_change_pct=day_summary.get("day_change_percent", 0.0),
            overall_gain_loss_pct=portfolio.get("overall_gain_loss_percent", 0.0),
            sector_allocation=sector_alloc,
            asset_type_allocation=asset_alloc,
            holdings=all_holdings,
            risk_alerts=risk_alerts,
            top_losers=top_losers,
            top_gainers=top_gainers,
            confidence_score=round(confidence, 2),
        )
