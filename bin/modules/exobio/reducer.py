"""Pure exobiology reducers over EDGPT system-map nodes. No I/O."""
from . import tables as T

SAMPLES_REQUIRED = 3
SAMPLE_SCAN_TYPES = ("Log", "Sample")
BIO_SIGNAL = "$SAA_SignalType_Biological;"


def _star_types(model):
    """Star classes of the system's scanned stars (used for star-dependent spawn rules)."""
    out = set()
    for node in (model or {}).get("nodes", {}).values():
        scan = node.get("event_data", {}).get("Scan", {})
        if scan.get("StarType"):
            out.add(scan["StarType"])
    return out


def _bio_signal_count(ev):
    for source in ("SAASignalsFound", "FSSBodySignals"):
        for signal in ev.get(source, {}).get("Signals", []) or []:
            if signal.get("Type") == BIO_SIGNAL:
                return int(signal.get("Count") or 0)
    return 0


def _genus_name(item):
    return T.canon_genus(item.get("Genus_Localised") or item.get("Genus") or "")


def _species_name(item):
    return T.canon_species(item.get("Species_Localised") or item.get("Species") or "")


def _empty_progress():
    return {"species": None, "variant": None, "samples": 0, "analysed": False}


def reduce_body(node, model=None):
    """Exobiology view of one map node: genera, sample progress, values, predictions."""
    ev = node.get("event_data", {})
    scan = ev.get("Scan")
    cond = T.body_conditions(scan, _star_types(model)) if scan else None
    signals = _bio_signal_count(ev)
    dss_genera = [_genus_name(g) for g in ev.get("SAASignalsFound", {}).get("Genuses", []) or []]

    progress = {}
    organics = sorted(ev.get("ScanOrganic", []) or [], key=lambda o: o.get("timestamp", ""))
    for organic in organics:
        genus = _genus_name(organic)
        if not genus:
            continue
        rec = progress.setdefault(genus, _empty_progress())
        species = _species_name(organic)
        if species and rec["species"] != species:
            rec.update(species=species, samples=0, analysed=False)
        rec["variant"] = organic.get("Variant_Localised") or organic.get("Variant") or rec["variant"]
        scan_type = organic.get("ScanType")
        if scan_type in SAMPLE_SCAN_TYPES:
            rec["samples"] = min(SAMPLES_REQUIRED, rec["samples"] + 1)
        elif scan_type == "Analyse":
            rec["analysed"] = True
            rec["samples"] = SAMPLES_REQUIRED

    genera = []
    for genus in sorted(set(dss_genera) | set(progress)):
        rec = progress.get(genus, _empty_progress())
        value = T.species_value(genus, rec["species"]) if rec["species"] else None
        lo_hi = T.genus_value_range(genus)
        candidates = [] if rec["species"] else T.predict_species(cond, genus)
        genera.append({
            "genus": genus,
            "species": rec["species"],
            "variant": rec["variant"],
            "samples": rec["samples"],
            "samples_required": SAMPLES_REQUIRED,
            "analysed": rec["analysed"],
            "value": value,
            "value_first_logged": value * T.first_logged_multiplier() if value else None,
            "value_min": lo_hi[0] if lo_hi else None,
            "value_max": lo_hi[1] if lo_hi else None,
            "min_distance_m": T.genus_min_distance(genus),
            "candidates": candidates[:6],
        })

    analysed_value = sum(g["value"] or 0 for g in genera if g["analysed"])
    return {
        "body_id": node.get("body_id"),
        "name": node.get("name"),
        "body_type": node.get("body_type"),
        "landable": (scan or {}).get("Landable"),
        "conditions": cond,
        "bio_signals": signals,
        "dss_done": "SAASignalsFound" in ev,
        "genera": genera,
        "predicted_genera": [] if dss_genera else (T.predict_genera(cond) if signals else []),
        "analysed_value": analysed_value,
        "complete": bool(genera) and all(g["analysed"] for g in genera) and len(genera) >= signals,
    }


def reduce_system(model):
    """Bodies in the system with any biology: signals, sampled, analysed, pending value."""
    if not model:
        return {"system": None, "system_address": None, "bodies": [], "pending_value": 0}
    bodies = []
    for node in model.get("nodes", {}).values():
        ev = node.get("event_data", {})
        if not (_bio_signal_count(ev) or ev.get("ScanOrganic")):
            continue
        body = reduce_body(node, model)
        bodies.append({
            "body_id": body["body_id"], "name": body["name"], "bio_signals": body["bio_signals"],
            "dss_done": body["dss_done"], "genera": [g["genus"] for g in body["genera"]],
            "analysed": sum(1 for g in body["genera"] if g["analysed"]),
            "in_progress": sum(1 for g in body["genera"] if g["samples"] and not g["analysed"]),
            "analysed_value": body["analysed_value"], "complete": body["complete"],
        })
    bodies.sort(key=lambda b: (b["body_id"] is None, b["body_id"] or 0))
    return {"system": model.get("system_name"), "system_address": model.get("system_address"),
            "bodies": bodies, "pending_value": sum(b["analysed_value"] for b in bodies)}


def find_node(model, body):
    """Node by numeric body id or exact name (case-insensitive)."""
    if not model or body is None:
        return None
    nodes = model.get("nodes", {})
    key = str(body).strip()
    if key.isdecimal() and key in nodes:
        return nodes[key]
    for node in nodes.values():
        if str(node.get("name", "")).lower() == key.lower():
            return node
    return None


def summarize_sales(events):
    """Total credits from SellOrganicData events (Value + Bonus per BioData item)."""
    total, items = 0, 0
    for ev in events or []:
        for item in ev.get("BioData", []) or []:
            if isinstance(item, dict):
                total += int(item.get("Value") or 0) + int(item.get("Bonus") or 0)
                items += 1
    return {"credits": total, "items": items, "sales": len(events or [])}
