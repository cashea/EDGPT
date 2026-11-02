"""Exobiology tracker: genera on body, sample progress, payout estimate.

Scaffold only. Events to consume: Scan, SAASignalsFound, ScanOrganic,
CodexEntry, SellOrganicData, Location/FSDJump.
"""
NAME = "exobio"


def status(qs=None):
    """Current exobiology status for the body the commander is on/near."""
    return {"module": NAME, "status": "scaffold", "body": None, "genera": [], "session_credits": 0}


def get_exobio_status() -> dict:
    """Exobiology on the current body: genera found, samples 0-3 per genus, estimated payout."""
    return status()


HTTP_ROUTES = {"/exobio": status}
MCP_TOOLS = [get_exobio_status]
