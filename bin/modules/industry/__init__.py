"""Industry: mining and trade helpers, cargo value, session earnings.

Scaffold only. Sources: Market.json, Cargo.json, ProspectedAsteroid,
MiningRefined, MarketSell/MarketBuy, plus cached Spansh/EDSM lookups.
"""
NAME = "industry"


def summary(qs=None):
    """Mining/trade summary for the current session."""
    return {"module": NAME, "status": "scaffold", "cargo_value": None, "tons_per_hour": None}


def get_industry_summary() -> dict:
    """Mining and trading summary: cargo value, tons per hour, best known sell prices."""
    return summary()


HTTP_ROUTES = {"/industry": summary}
MCP_TOOLS = [get_industry_summary]
