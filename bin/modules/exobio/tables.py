"""Exobiology reference tables (values, distances, spawn rules). Pure, lazy, no I/O at import."""
import json
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent / "data" / "exobio_data.json"
G = 9.80665          # m/s^2 per g
ATM = 101325.0       # Pa per atmosphere
_tables = None


def tables():
    global _tables
    if _tables is None:
        with open(DATA_FILE, encoding="utf-8") as fh:
            _tables = json.load(fh)
    return _tables


def genera():
    return list(tables()["species_value"])


def canon_genus(name):
    """Game plural ("Brain Trees") -> table singular ("Brain Tree")."""
    name = (name or "").strip()
    values = tables()["species_value"]
    singular = name[:-1] if name.endswith("s") else name
    return singular if name not in values and singular in values else name


def canon_species(name):
    """Game "Roseum Brain Tree" -> table "Brain Tree Roseum"."""
    name = (name or "").strip()
    for genus in tables()["species_value"]:
        suffix = f" {genus}"
        if name.endswith(suffix):
            return f"{genus} {name[:-len(suffix)]}"
    return name


def species_value(genus, species):
    return tables()["species_value"].get(canon_genus(genus), {}).get(canon_species(species))


def genus_value_range(genus):
    values = tables()["species_value"].get(canon_genus(genus))
    if not values:
        return None
    return min(values.values()), max(values.values())


def genus_min_distance(genus):
    return tables()["genus_min_distance_m"].get(canon_genus(genus))


def first_logged_multiplier():
    return int(tables().get("first_logged_bonus_multiplier", 5))


def body_conditions(scan, star_types=()):
    """Normalize a Scan event into the units the rulesets use. Missing fields stay None."""
    if not isinstance(scan, dict):
        return None
    gravity = scan.get("SurfaceGravity")
    pressure = scan.get("SurfacePressure")
    atmosphere_type = scan.get("AtmosphereType")
    if atmosphere_type is None and scan.get("Atmosphere") == "":
        atmosphere_type = "None"
    return {
        "planet_class": scan.get("PlanetClass"),
        "atmosphere_type": atmosphere_type,
        "atmosphere": scan.get("Atmosphere"),
        "gravity_g": round(gravity / G, 4) if isinstance(gravity, (int, float)) else None,
        "temperature_k": scan.get("SurfaceTemperature"),
        "pressure_atm": round(pressure / ATM, 6) if isinstance(pressure, (int, float)) else None,
        "volcanism": scan.get("Volcanism") or "",
        "landable": scan.get("Landable"),
        "star_types": sorted({s for s in star_types if s}),
    }


def _volcanism_ok(rule, volcanism):
    want = rule.get("volcanism")
    text = (volcanism or "").lower()
    if want is None:
        return True
    if want == "any":
        return bool(text)
    if want == "none":
        return not text
    if isinstance(want, list):
        return any(w.lstrip("=").lower() in text for w in want)
    return True


def rule_matches(rule, cond):
    """True when every constraint present in ``rule`` is satisfied by ``cond``. Unknown values pass."""
    pc = cond.get("planet_class")
    if rule.get("body_types") and pc is not None and pc not in rule["body_types"]:
        return False
    at = cond.get("atmosphere_type")
    if rule.get("atmosphere") and at is not None and at not in rule["atmosphere"]:
        return False
    for key, lo, hi in (("gravity_g", "min_gravity_g", "max_gravity_g"),
                        ("temperature_k", "min_temp_k", "max_temp_k"),
                        ("pressure_atm", "min_pressure_atm", "max_pressure_atm")):
        value = cond.get(key)
        if value is None:
            continue
        if lo in rule and value < rule[lo]:
            return False
        if hi in rule and value > rule[hi]:
            return False
    if not _volcanism_ok(rule, cond.get("volcanism")):
        return False
    stars = cond.get("star_types") or []
    if rule.get("star_types") and stars and not (set(rule["star_types"]) & set(stars)):
        return False
    return True


def predict_species(cond, genus=None):
    """Candidate species for a body, optionally limited to one genus. Sorted by value, descending."""
    if not cond:
        return []
    out = []
    rules = tables()["species_rules"]
    values = tables()["species_value"]
    wanted = canon_genus(genus) if genus else None
    for g, species_map in rules.items():
        if wanted and g != wanted:
            continue
        for species, rule_list in species_map.items():
            if any(rule_matches(r, cond) for r in rule_list):
                out.append({"genus": g, "species": species,
                            "value": values.get(g, {}).get(species),
                            "unmodeled": sorted({r["unmodeled"] for r in rule_list if r.get("unmodeled")})})
    out.sort(key=lambda s: (-(s["value"] or 0), s["species"]))
    return out


def predict_genera(cond):
    """Genera whose genus-level rules match; used before a DSS reveals the real list."""
    if not cond:
        return []
    out = []
    for g, rule_list in tables()["genus_rules"].items():
        if any(rule_matches(r, cond) for r in rule_list):
            lo_hi = genus_value_range(g)
            out.append({"genus": g, "value_min": lo_hi[0] if lo_hi else None,
                        "value_max": lo_hi[1] if lo_hi else None})
    out.sort(key=lambda s: (-(s["value_max"] or 0), s["genus"]))
    return out
