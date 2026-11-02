import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BIN = Path(__file__).resolve().parents[1] / "bin"
sys.path.insert(0, str(BIN))

import modules.exobio as exobio
from modules.exobio import reducer as R
from modules.exobio import tables as T


def organic(ts, scan_type, genus, species=None, variant=None, body=5):
    ev = {"timestamp": ts, "event": "ScanOrganic", "ScanType": scan_type, "Body": body,
          "Genus": f"$Codex_Ent_{genus}_Genus_Name;", "Genus_Localised": genus}
    if species:
        ev["Species_Localised"] = species
    if variant:
        ev["Variant_Localised"] = variant
    return ev


CO2_ROCKY_SCAN = {"event": "Scan", "BodyName": "Test 5", "BodyID": 5, "PlanetClass": "Rocky body",
                  "AtmosphereType": "CarbonDioxide", "Atmosphere": "thin carbon dioxide atmosphere",
                  "SurfaceGravity": 1.5, "SurfaceTemperature": 178.0, "SurfacePressure": 2000.0,
                  "Volcanism": "", "Landable": True}


def node(body_id=5, name="Test 5", **event_data):
    return {"body_id": body_id, "name": name, "body_type": "Rocky body", "event_data": event_data}


def dss(*genera, count=None):
    return {"event": "SAASignalsFound", "BodyID": 5,
            "Signals": [{"Type": "$SAA_SignalType_Biological;", "Count": count or len(genera)}],
            "Genuses": [{"Genus": f"$Codex_Ent_{g}_Genus_Name;", "Genus_Localised": g} for g in genera]}


class TableTests(unittest.TestCase):
    def test_data_loads_with_expected_shape(self):
        t = T.tables()
        self.assertEqual(len(t["species_value"]), 21)
        self.assertEqual(sum(len(v) for v in t["species_value"].values()), 117)
        self.assertEqual(T.first_logged_multiplier(), 5)

    def test_canonical_names(self):
        self.assertEqual(T.canon_genus("Brain Trees"), "Brain Tree")
        self.assertEqual(T.canon_genus("Bacterium"), "Bacterium")
        self.assertEqual(T.canon_species("Roseum Brain Tree"), "Brain Tree Roseum")
        self.assertEqual(T.canon_species("Tussock Stigmasis"), "Tussock Stigmasis")
        self.assertEqual(T.species_value("Brain Trees", "Roseum Brain Tree"),
                         T.tables()["species_value"]["Brain Tree"]["Brain Tree Roseum"])

    def test_body_conditions_units(self):
        cond = T.body_conditions(CO2_ROCKY_SCAN, {"K"})
        self.assertAlmostEqual(cond["gravity_g"], 1.5 / 9.80665, places=4)
        self.assertAlmostEqual(cond["pressure_atm"], 2000 / 101325, places=6)
        self.assertEqual(cond["atmosphere_type"], "CarbonDioxide")
        self.assertEqual(cond["star_types"], ["K"])
        self.assertIsNone(T.body_conditions(None))

    def test_prediction_matches_aleoida_arcus_window(self):
        cond = T.body_conditions(CO2_ROCKY_SCAN)
        names = [s["species"] for s in T.predict_species(cond, "Aleoida")]
        self.assertIn("Aleoida Arcus", names)
        self.assertNotIn("Aleoida Spica", names)  # ammonia-only
        genera = [g["genus"] for g in T.predict_genera(cond)]
        self.assertIn("Aleoida", genera)
        self.assertEqual(T.predict_species(None), [])

    def test_volcanism_rules(self):
        self.assertTrue(T.rule_matches({"volcanism": "none"}, {"volcanism": ""}))
        self.assertFalse(T.rule_matches({"volcanism": "none"}, {"volcanism": "minor water geysers"}))
        self.assertTrue(T.rule_matches({"volcanism": "any"}, {"volcanism": "major silicate vapour"}))
        self.assertTrue(T.rule_matches({"volcanism": ["water"]}, {"volcanism": "minor water geysers"}))
        self.assertFalse(T.rule_matches({"volcanism": ["water"]}, {"volcanism": "rocky magma"}))


class ReducerTests(unittest.TestCase):
    def test_sample_progress_log_sample_sample_analyse(self):
        events = [organic("t1", "Log", "Bacterium", "Bacterium Alcyoneum", "Bacterium Alcyoneum - Red"),
                  organic("t2", "Sample", "Bacterium", "Bacterium Alcyoneum"),
                  organic("t3", "Sample", "Bacterium", "Bacterium Alcyoneum"),
                  organic("t4", "Analyse", "Bacterium", "Bacterium Alcyoneum"),
                  organic("t5", "Log", "Tussock", "Tussock Stigmasis")]
        body = R.reduce_body(node(Scan=CO2_ROCKY_SCAN, SAASignalsFound=dss("Bacterium", "Tussock"),
                                  ScanOrganic=events))
        by = {g["genus"]: g for g in body["genera"]}
        self.assertEqual(by["Bacterium"]["samples"], 3)
        self.assertTrue(by["Bacterium"]["analysed"])
        self.assertEqual(by["Bacterium"]["variant"], "Bacterium Alcyoneum - Red")
        self.assertEqual(by["Bacterium"]["value"], 1_658_500)
        self.assertEqual(by["Bacterium"]["value_first_logged"], 1_658_500 * 5)
        self.assertEqual(by["Tussock"]["samples"], 1)
        self.assertFalse(by["Tussock"]["analysed"])
        self.assertEqual(by["Tussock"]["value"], 19_010_800)
        self.assertEqual(by["Tussock"]["min_distance_m"], 200)
        self.assertEqual(body["analysed_value"], 1_658_500)
        self.assertFalse(body["complete"])
        self.assertEqual(body["bio_signals"], 2)
        self.assertTrue(body["dss_done"])

    def test_samples_cap_at_three_and_species_switch_resets(self):
        events = [organic("t1", "Log", "Tussock", "Tussock Stigmasis"),
                  organic("t2", "Sample", "Tussock", "Tussock Stigmasis"),
                  organic("t3", "Log", "Tussock", "Tussock Propagito"),
                  organic("t4", "Sample", "Tussock", "Tussock Propagito"),
                  organic("t5", "Sample", "Tussock", "Tussock Propagito"),
                  organic("t6", "Sample", "Tussock", "Tussock Propagito")]
        body = R.reduce_body(node(ScanOrganic=events))
        g = body["genera"][0]
        self.assertEqual((g["species"], g["samples"], g["analysed"]), ("Tussock Propagito", 3, False))

    def test_unsampled_dss_genus_gets_candidates_and_range(self):
        body = R.reduce_body(node(Scan=CO2_ROCKY_SCAN, SAASignalsFound=dss("Aleoida")))
        g = body["genera"][0]
        self.assertIsNone(g["species"])
        self.assertIn("Aleoida Arcus", [c["species"] for c in g["candidates"]])
        self.assertLessEqual(g["value_min"], g["value_max"])
        self.assertEqual(body["predicted_genera"], [])

    def test_fss_signals_without_dss_predict_genera(self):
        fss = {"event": "FSSBodySignals", "BodyID": 5,
               "Signals": [{"Type": "$SAA_SignalType_Biological;", "Count": 3}]}
        body = R.reduce_body(node(Scan=CO2_ROCKY_SCAN, FSSBodySignals=fss))
        self.assertEqual(body["bio_signals"], 3)
        self.assertFalse(body["dss_done"])
        self.assertEqual(body["genera"], [])
        self.assertIn("Aleoida", [g["genus"] for g in body["predicted_genera"]])

    def test_plural_genus_and_reversed_species_names(self):
        events = [organic("t1", "Log", "Brain Trees", "Roseum Brain Tree")]
        g = R.reduce_body(node(ScanOrganic=events))["genera"][0]
        self.assertEqual(g["genus"], "Brain Tree")
        self.assertEqual(g["species"], "Brain Tree Roseum")
        self.assertIsNotNone(g["value"])

    def test_system_overview_and_lookup(self):
        model = {"system_name": "Deltius", "system_address": 42, "nodes": {
            "1": {"body_id": 1, "name": "Deltius 1", "event_data": {"Scan": {"StarType": "K"}}},
            "5": node(Scan=CO2_ROCKY_SCAN, SAASignalsFound=dss("Bacterium"),
                      ScanOrganic=[organic("t", "Analyse", "Bacterium", "Bacterium Alcyoneum")]),
            "6": {"body_id": 6, "name": "Test 6", "event_data": {}},
        }}
        overview = R.reduce_system(model)
        self.assertEqual([b["name"] for b in overview["bodies"]], ["Test 5"])
        self.assertEqual(overview["pending_value"], 1_658_500)
        self.assertTrue(overview["bodies"][0]["complete"])
        self.assertEqual(R.find_node(model, "test 5")["body_id"], 5)
        self.assertEqual(R.find_node(model, "5")["body_id"], 5)
        self.assertIsNone(R.find_node(model, "nope"))
        self.assertEqual(R.reduce_system(None)["bodies"], [])

    def test_sales_summary(self):
        sales = [{"event": "SellOrganicData", "BioData": [
            {"Species_Localised": "Bacterium Alcyoneum", "Value": 1658500, "Bonus": 0},
            {"Species_Localised": "Tussock Stigmasis", "Value": 19010800, "Bonus": 76043200}]}]
        self.assertEqual(R.summarize_sales(sales), {"credits": 96_712_500, "items": 2, "sales": 1})
        self.assertEqual(R.summarize_sales([]), {"credits": 0, "items": 0, "sales": 0})


class EndpointTests(unittest.TestCase):
    def setUp(self):
        self.model = {"system_name": "Deltius", "system_address": 42, "nodes": {
            "5": node(Scan=CO2_ROCKY_SCAN, SAASignalsFound=dss("Bacterium"))}}
        self.patches = [patch.object(exobio, "_state", return_value={"system": "Deltius", "body": "Test 5"}),
                        patch.object(exobio, "_current_map", return_value=self.model),
                        patch.object(exobio, "_recent_sales", return_value=[])]
        for p in self.patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in self.patches])

    def test_status_uses_current_body(self):
        result = exobio.status({})
        json.dumps(result)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["body"]["name"], "Test 5")
        self.assertEqual(result["overview"]["bodies"][0]["genera"], ["Bacterium"])
        self.assertIsNone(result["last_sale"])

    def test_body_param_and_errors(self):
        self.assertEqual(exobio.body({"body": ["5"]})["body"]["body_id"], 5)
        self.assertIn("error", exobio.body({"body": ["Test 9"]}))
        with self.assertRaises(ValueError):
            exobio.body({})
        self.assertEqual(exobio.get_exobio_body("Test 5")["body"]["name"], "Test 5")

    def test_no_map(self):
        with patch.object(exobio, "_current_map", return_value=None):
            result = exobio.status({})
        self.assertEqual(result["status"], "no_system_map")
        self.assertIsNone(result["body"])


if __name__ == "__main__":
    unittest.main()
