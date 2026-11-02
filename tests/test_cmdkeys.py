import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

BIN = Path(__file__).resolve().parents[1] / "bin"
sys.path.insert(0, str(BIN))

import modules.cmdkeys as cmdkeys
from modules.cmdkeys import binds as B
from modules.cmdkeys import macros as M
from modules.cmdkeys import scancodes as S
from modules.cmdkeys import screen as SC

BINDS_XML = """<?xml version="1.0" encoding="UTF-8" ?>
<Root PresetName="Custom" MajorVersion="4" MinorVersion="1">
\t<KeyboardLayout>en-US</KeyboardLayout>
\t<MouseXMode Value="" />
\t<YawAxisRaw>
\t\t<Binding Device="SaitekX52Pro" Key="Joy_RZAxis" />
\t\t<Inverted Value="0" />
\t</YawAxisRaw>
\t<LandingGearToggle>
\t\t<Primary Device="Keyboard" Key="Key_L">
\t\t\t<Modifier Device="Keyboard" Key="Key_RightShift" />
\t\t</Primary>
\t\t<Secondary Device="{NoDevice}" Key="" />
\t</LandingGearToggle>
\t<DeployHardpointToggle>
\t\t<Primary Device="SaitekX52Pro" Key="Joy_2" />
\t\t<Secondary Device="Keyboard" Key="Key_U" />
\t</DeployHardpointToggle>
\t<ShipSpotLightToggle>
\t\t<Primary Device="Keyboard" Key="Key_Insert" />
\t\t<Secondary Device="{NoDevice}" Key="" />
\t</ShipSpotLightToggle>
\t<Supercruise>
\t\t<Primary Device="{NoDevice}" Key="" />
\t\t<Secondary Device="{NoDevice}" Key="" />
\t</Supercruise>
\t<ToggleCargoScoop>
\t\t<Primary Device="Keyboard" Key="Key_Home" />
\t\t<Secondary Device="{NoDevice}" Key="" />
\t\t<ToggleOn Value="1" />
\t</ToggleCargoScoop>
\t<EjectAllCargo>
\t\t<Primary Device="Keyboard" Key="Key_J">
\t\t\t<Modifier Device="SaitekX52Pro" Key="Joy_5" />
\t\t</Primary>
\t\t<Secondary Device="{NoDevice}" Key="" />
\t</EjectAllCargo>
	<FocusRightPanel>
		<Primary Device="Keyboard" Key="Key_4" />
		<Secondary Device="{NoDevice}" Key="" />
	</FocusRightPanel>
	<CycleNextPanel>
		<Primary Device="Keyboard" Key="Key_E" />
		<Secondary Device="{NoDevice}" Key="" />
	</CycleNextPanel>
	<GalaxyMapOpen>
		<Primary Device="Keyboard" Key="Key_F11" />
		<Secondary Device="{NoDevice}" Key="" />
	</GalaxyMapOpen>
	<UI_Up>
		<Primary Device="Keyboard" Key="Key_F5" />
		<Secondary Device="{NoDevice}" Key="" />
	</UI_Up>
	<UI_Down>
		<Primary Device="Keyboard" Key="Key_F6" />
		<Secondary Device="{NoDevice}" Key="" />
	</UI_Down>
	<UI_Select>
		<Primary Device="Keyboard" Key="Key_F9" />
		<Secondary Device="{NoDevice}" Key="" />
	</UI_Select>
	<UI_Back>
		<Primary Device="Mouse" Key="Mouse_4" />
		<Secondary Device="Keyboard" Key="Key_F10" />
	</UI_Back>
</Root>
"""

USER_KEYS = ("Key_0 Key_1 Key_2 Key_3 Key_4 Key_5 Key_6 Key_7 Key_8 Key_9 Key_A Key_B Key_BackSlash "
             "Key_Backspace Key_C Key_D Key_Delete Key_DownArrow Key_E Key_End Key_Enter Key_Equals Key_F "
             "Key_F1 Key_F12 Key_G Key_H Key_Home Key_Insert Key_J Key_L Key_LeftAlt Key_LeftArrow "
             "Key_LeftBracket Key_LeftControl Key_LeftShift Key_M Key_Minus Key_N Key_Numpad_0 Key_Numpad_1 "
             "Key_Numpad_2 Key_Numpad_3 Key_Numpad_4 Key_Numpad_5 Key_Numpad_6 Key_Numpad_7 Key_Numpad_8 "
             "Key_Numpad_9 Key_O Key_P Key_PageDown Key_PageUp Key_Q Key_R Key_RightArrow Key_RightBracket "
             "Key_RightControl Key_RightShift Key_S Key_Slash Key_Space Key_T Key_Tab Key_U Key_UpArrow "
             "Key_V Key_W Key_X Key_Y Key_Z").split()


class BindsTests(unittest.TestCase):
    def setUp(self):
        self.binding = B.parse_binds(BINDS_XML)

    def test_header_and_axes_ignored(self):
        self.assertEqual(self.binding["preset"], "Custom")
        self.assertEqual(self.binding["version"], "4.1")
        self.assertEqual(self.binding["layout"], "en-US")
        self.assertNotIn("YawAxisRaw", self.binding["actions"])
        self.assertNotIn("MouseXMode", self.binding["actions"])

    def test_primary_with_modifier(self):
        chord = B.keyboard_chord(self.binding, "LandingGearToggle")
        self.assertEqual(B.chord_keys(chord), ["Key_RightShift", "Key_L"])

    def test_secondary_used_when_primary_is_joystick(self):
        self.assertEqual(B.chord_keys(B.keyboard_chord(self.binding, "DeployHardpointToggle")), ["Key_U"])

    def test_unbound_and_non_keyboard_modifier(self):
        self.assertIsNone(B.keyboard_chord(self.binding, "Supercruise"))
        self.assertIsNone(B.keyboard_chord(self.binding, "EjectAllCargo"))
        self.assertIsNone(B.keyboard_chord(self.binding, "NoSuchAction"))
        self.assertEqual(self.binding["actions"]["Supercruise"], {"primary": None, "secondary": None})

    def test_find_binds_file_prefers_active_preset_and_watcher_reparses(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "Other.4.1.binds").write_text(BINDS_XML.replace('PresetName="Custom"', 'PresetName="Other"'), encoding="utf-8")
            (folder / "Custom.4.1.binds").write_text(BINDS_XML, encoding="utf-8")
            (folder / "StartPreset.4.start").write_text("Custom\nCustom\nCustom\nKeyboardMouseOnly\n", encoding="utf-8")
            self.assertEqual(B.find_binds_file(folder).name, "Custom.4.1.binds")
            watcher = B.BindsWatcher(folder)
            self.assertEqual(watcher.load()["preset"], "Custom")
            path = folder / "Custom.4.1.binds"
            path.write_text(BINDS_XML.replace("Key_L", "Key_G"), encoding="utf-8")
            os.utime(path, (path.stat().st_atime, path.stat().st_mtime + 5))
            self.assertEqual(B.chord_keys(B.keyboard_chord(watcher.load(), "LandingGearToggle")), ["Key_RightShift", "Key_G"])
            self.assertEqual(watcher.summary()["actions"], 13)
        self.assertIsNone(B.find_binds_file(Path(tmp) / "missing"))


class ScancodeTests(unittest.TestCase):
    def test_every_key_in_the_users_binds_is_mapped(self):
        self.assertEqual(S.unmapped(USER_KEYS), [])

    def test_extended_keys(self):
        self.assertEqual(S.scancode("Key_RightControl"), (0x1D, True))
        self.assertEqual(S.scancode("Key_LeftControl"), (0x1D, False))
        self.assertEqual(S.scancode("Key_Insert"), (0x52, True))
        self.assertEqual(S.scancode("Key_Numpad_0"), (0x52, False))
        self.assertIsNone(S.scancode("Joy_2"))


class ValidationTests(unittest.TestCase):
    def test_defaults_are_valid_and_disabled(self):
        for macro in M.DEFAULT_MACROS:
            self.assertEqual(M.validate_macro(macro), [], macro["name"])
            self.assertFalse(macro["enabled"])

    def test_limits(self):
        too_many = {"name": "x", "steps": [{"wait": 10}] * (M.MAX_STEPS + 1)}
        self.assertTrue(any("too many" in p for p in M.validate_macro(too_many)))
        self.assertTrue(any("timeout_ms" in p for p in M.validate_macro({"name": "x", "steps": [{"wait_until": "Docked"}]})))
        self.assertTrue(any("runtime" in p for p in M.validate_macro(
            {"name": "x", "steps": [{"wait": M.MAX_WAIT_MS}] * (M.MAX_RUNTIME_MS // M.MAX_WAIT_MS + 1)})))
        self.assertTrue(any("exactly one" in p for p in M.validate_macro({"name": "x", "steps": [{"press": "A", "wait": 1}]})))
        self.assertEqual(M.validate_macro({"name": "", "steps": []}), ["macro needs a name"])

    def test_storage_roundtrip_writes_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "macros.json"
            macros = M.load_macros(path)
            self.assertEqual([m["name"] for m in macros], [m["name"] for m in M.DEFAULT_MACROS])
            macros[0]["enabled"] = True
            M.save_macros(macros, path)
            self.assertTrue(M.load_macros(path)[0]["enabled"])
            path.write_text("not json", encoding="utf-8")
            self.assertEqual(M.load_macros(path), [])


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.binding = B.parse_binds(BINDS_XML)
        self.flags = set()
        self.focused = True
        self.sender = M.FakeSender()
        self.now = [0.0]
        self.engine = M.MacroEngine(self.sender, lambda: set(self.flags), lambda: self.focused,
                                    lambda: self.binding, sleep=self._sleep, clock=lambda: self.now[0])

    def _sleep(self, seconds):
        self.now[0] += seconds

    def test_conditional_press_and_wait_until(self):
        macro = {"name": "gear", "steps": [{"if_flag": "LandingGearDown", "is": False, "press": "LandingGearToggle"},
                                           {"wait_until": "LandingGearDown", "is": True, "timeout_ms": 1000}]}
        original = self.sender.press_chord

        def press_then_flag(keys, hold_ms=60):
            original(keys, hold_ms)
            self.flags.add("LandingGearDown")
        self.sender.press_chord = press_then_flag
        result = self.engine.run(macro)
        self.assertTrue(result["ok"], result)
        self.assertEqual(self.sender.pressed, [(["Key_RightShift", "Key_L"], 60)])
        # gear already down: press skipped, wait satisfied immediately
        self.sender.pressed.clear()
        result = self.engine.run(macro)
        self.assertTrue(result["ok"])
        self.assertEqual(self.sender.pressed, [])
        self.assertIn("skip", result["log"][0])

    def test_wait_timeout_aborts(self):
        macro = {"name": "t", "steps": [{"wait_until": "Docked", "timeout_ms": 500}]}
        result = self.engine.run(macro)
        self.assertFalse(result["ok"])
        self.assertIn("timeout", result["error"])

    def test_focus_loss_and_cancel_abort(self):
        macro = {"name": "w", "steps": [{"wait": 1000}, {"press": "ShipSpotLightToggle"}]}
        self.focused = False
        self.assertIn("not focused", self.engine.run(macro)["error"])
        self.focused = True
        calls = {"n": 0}

        def lose_focus_later():
            calls["n"] += 1
            return calls["n"] < 5
        self.engine.focus_check = lose_focus_later
        result = self.engine.run(macro)
        self.assertFalse(result["ok"])
        self.assertIn("focus", result["error"])
        self.assertEqual(self.sender.pressed, [])

        self.engine.focus_check = lambda: True
        self.engine._cancel.set()
        self.assertEqual(self.engine.run(macro)["ok"], True)  # run clears a stale cancel first
        polls = {"n": 0}

        def cancel_during_wait(seconds):
            polls["n"] += 1
            if polls["n"] == 3:
                self.engine.cancel()
            self._sleep(seconds)
        self.engine.sleep = cancel_during_wait
        result = self.engine.run(macro)
        self.assertEqual(result["error"], "cancelled")

    def test_unbound_action_and_dry_run(self):
        result = self.engine.run({"name": "u", "steps": [{"press": "Supercruise"}]})
        self.assertIn("no keyboard binding", result["error"])
        self.focused = False
        result = self.engine.run({"name": "d", "steps": [{"press": "ShipSpotLightToggle"}]}, dry_run=True)
        self.assertTrue(result["ok"])
        self.assertTrue(result["dry_run"])
        self.assertEqual(self.sender.pressed, [])

    def test_gui_focus_flag_mapping(self):
        self.assertEqual(M.gui_focus_flag(0), "GuiFocus:NoFocus")
        self.assertEqual(M.gui_focus_flag(5), "GuiFocus:StationServices")
        self.assertIsNone(M.gui_focus_flag(99))
        self.assertIsNone(M.gui_focus_flag(True))
        self.assertIsNone(M.gui_focus_flag(None))

    def test_press_gap_is_applied_and_validated(self):
        macro = {"name": "two", "steps": [{"press": "UI_Down"}, {"press": "UI_Down", "gap_ms": 500}]}
        result = self.engine.run(macro)
        self.assertTrue(result["ok"], result)
        self.assertAlmostEqual(self.now[0], (M.DEFAULT_GAP_MS + 500) / 1000.0, places=3)
        self.assertIn("gap_ms must be 0-2000", M.validate_macro({"name": "x", "steps": [{"press": "UI_Down", "gap_ms": 9000}]})[0])

    def test_open_starport_services_macro(self):
        macro = next(m for m in M.DEFAULT_MACROS if m["name"] == "Open Starport Services")
        self.assertEqual(M.validate_macro(macro), [])
        # not docked -> aborts before any key is sent
        self.flags = {"GuiFocus:NoFocus"}
        result = self.engine.run(macro)
        self.assertFalse(result["ok"])
        self.assertIn("Docked", result["error"])
        self.assertEqual(self.sender.pressed, [])
        # docked but a side panel is open -> aborts, nothing sent
        self.flags = {"Docked", "GuiFocus:InternalPanel"}
        result = self.engine.run(macro)
        self.assertFalse(result["ok"])
        self.assertIn("GuiFocus:NoFocus", result["error"])
        self.assertEqual(self.sender.pressed, [])
        # docked, cockpit view: 4x down, 2x up, select; station services appears after the select
        self.flags = {"Docked", "GuiFocus:NoFocus"}
        original = self.sender.press_chord

        def press_then_focus(keys, hold_ms=60):
            original(keys, hold_ms)
            if keys == ["Key_F9"]:
                self.flags = {"Docked", "GuiFocus:StationServices"}
        self.sender.press_chord = press_then_focus
        result = self.engine.run(macro)
        self.assertTrue(result["ok"], result)
        self.assertEqual([k for k, _ in self.sender.pressed],
                         [["Key_F6"]] * 4 + [["Key_F5"]] * 2 + [["Key_F9"]])
        # select never opens the menu -> timeout, reported
        self.sender.press_chord = original
        self.flags = {"Docked", "GuiFocus:NoFocus"}
        result = self.engine.run(macro)
        self.assertFalse(result["ok"])
        self.assertIn("GuiFocus:StationServices", result["error"])

    def test_close_starport_services_macro(self):
        macro = next(m for m in M.DEFAULT_MACROS if m["name"] == "Close Starport Services")
        self.assertEqual(M.validate_macro(macro), [])
        # not in station services -> aborts, nothing sent
        self.flags = {"Docked", "GuiFocus:NoFocus"}
        result = self.engine.run(macro)
        self.assertFalse(result["ok"])
        self.assertEqual(self.sender.pressed, [])
        # two pages deep: first back goes to the root, second back leaves; third is skipped
        depth = [2]
        original = self.sender.press_chord

        def back(keys, hold_ms=60):
            original(keys, hold_ms)
            depth[0] -= 1
            self.flags = {"Docked", "GuiFocus:StationServices" if depth[0] > 0 else "GuiFocus:NoFocus"}
        self.sender.press_chord = back
        self.flags = {"Docked", "GuiFocus:StationServices"}
        result = self.engine.run(macro)
        self.assertTrue(result["ok"], result)
        self.assertEqual([k for k, _ in self.sender.pressed], [["Key_F10"], ["Key_F10"]])
        self.assertTrue(any("skip" in line for line in result["log"]))

    def test_galaxy_map_macros(self):
        open_map = next(m for m in M.DEFAULT_MACROS if m["name"] == "Open galaxy map")
        close_map = next(m for m in M.DEFAULT_MACROS if m["name"] == "Close galaxy map")
        original = self.sender.press_chord

        def toggle(keys, hold_ms=60):
            original(keys, hold_ms)
            self.flags = {"GuiFocus:NoFocus"} if "GuiFocus:GalaxyMap" in self.flags else {"GuiFocus:GalaxyMap"}
        self.sender.press_chord = toggle
        self.flags = {"GuiFocus:GalaxyMap"}
        self.assertFalse(self.engine.run(open_map)["ok"])      # already open -> abort, nothing sent
        self.assertEqual(self.sender.pressed, [])
        self.flags = {"GuiFocus:NoFocus"}
        self.assertTrue(self.engine.run(open_map)["ok"])
        self.assertEqual(self.flags, {"GuiFocus:GalaxyMap"})
        self.assertTrue(self.engine.run(close_map)["ok"])
        self.assertEqual(self.flags, {"GuiFocus:NoFocus"})
        self.assertEqual([k for k, _ in self.sender.pressed], [["Key_F11"], ["Key_F11"]])

    def test_screen_steps_need_a_probe_and_validate(self):
        self.assertEqual(SC.parse_expectation("right_panel_tab=Inventory"), ("right_panel_tab", "Inventory"))
        self.assertIsNone(SC.parse_expectation("right_panel_tab=Nope"))
        self.assertIsNone(SC.parse_expectation("bogus=Inventory"))
        self.assertIsNone(SC.parse_expectation(42))
        problems = M.validate_macro({"name": "x", "steps": [
            {"expect_screen": "right_panel_tab=Nope"},
            {"until_screen": "right_panel_tab=Inventory", "press": "CycleNextPanel"},
            {"until_screen": "right_panel_tab=Inventory", "press": "CycleNextPanel", "max_presses": 99}]})
        self.assertEqual(len(problems), 3, problems)
        # engine without a probe refuses screen steps (but dry-runs them)
        macro = {"name": "x", "steps": [{"expect_screen": "right_panel_tab=Inventory"}]}
        result = self.engine.run(macro)
        self.assertFalse(result["ok"])
        self.assertIn("not available", result["error"])
        self.assertFalse(self.engine.run(macro, dry_run=True)["ok"])   # None != Inventory, reported

    def test_screen_evaluate_on_synthetic_pixels(self):
        box = SC.PROBES["right_panel_tab"]["Inventory"]
        inside = lambda x, y: box[0] <= x < box[1] and box[2] <= y < box[3]
        pixel_at = lambda x, y: (211, 133, 0) if inside(x, y) else (40, 15, 4)
        self.assertEqual(SC.evaluate("right_panel_tab", pixel_at, SC.REFERENCE), "Inventory")
        # half-resolution window: boxes scale down with it
        half = lambda x, y: pixel_at(x * 2, y * 2)
        self.assertEqual(SC.evaluate("right_panel_tab", half, (1280, 720)), "Inventory")
        # nothing highlighted -> None; two highlighted -> ambiguous -> None
        self.assertIsNone(SC.evaluate("right_panel_tab", lambda x, y: (40, 15, 4), SC.REFERENCE))
        self.assertIsNone(SC.evaluate("right_panel_tab", lambda x, y: (211, 133, 0), SC.REFERENCE))

    def test_open_inventory_tab_macro(self):
        macro = next(m for m in M.DEFAULT_MACROS if m["name"] == "Open inventory tab")
        self.assertEqual(M.validate_macro(macro), [])
        tabs = ["Home", "Modules", "FireGroups", "Ship", "Inventory", "Storage", "Status", "Playlist"]
        state = {"tab": 6}   # panel was left on Status
        self.engine.screen_probe = lambda probe: tabs[state["tab"]]
        original = self.sender.press_chord

        def press(keys, hold_ms=60):
            original(keys, hold_ms)
            if keys == ["Key_4"]:
                self.flags = {"Docked", "GuiFocus:InternalPanel"}
            elif keys == ["Key_E"]:
                state["tab"] = (state["tab"] + 1) % len(tabs)
        self.sender.press_chord = press
        self.flags = {"Docked", "GuiFocus:NoFocus"}
        result = self.engine.run(macro)
        self.assertTrue(result["ok"], result)
        # opened the panel, then Status -> Playlist -> Home -> ... -> Inventory = 6 presses of E
        self.assertEqual([k for k, _ in self.sender.pressed], [["Key_4"]] + [["Key_E"]] * 6)
        self.assertIn("after 6 x CycleNextPanel", " ".join(result["log"]))
        # already on Inventory with the panel open: no key at all
        self.sender.pressed.clear()
        result = self.engine.run(macro)
        self.assertTrue(result["ok"], result)
        self.assertEqual(self.sender.pressed, [])
        # probe never sees Inventory (e.g. wrong resolution): stops after max_presses and reports it
        self.engine.screen_probe = lambda probe: None
        result = self.engine.run(macro)
        self.assertFalse(result["ok"])
        self.assertIn("after 8 presses", result["error"])

    def test_params_type_and_conditional_screen_steps(self):
        macro = {"name": "t", "params": ["system"], "steps": [
            {"type": "{system}\n"},
            {"if_screen": "galmap_search_list=open", "press": ["UI_Down", "UI_Select"]},
            {"if_screen": "galmap_route_bar={system}", "is": False, "press": "UI_Select"},
            {"expect_screen": "galmap_route_bar={system}"}]}
        self.assertEqual(M.validate_macro(macro), [])
        self.assertIn("type cannot send", M.validate_macro({"name": "x", "steps": [{"type": "a?b"}]})[0])
        result = self.engine.run(macro)
        self.assertFalse(result["ok"])
        self.assertIn("missing parameters: system", result["error"])
        self.assertEqual(self.sender.pressed, [])
        answers = {"galmap_search_list": "closed", "galmap_route_bar": "DESTINATION ALTAIR 8 JUMPS"}
        self.engine.screen_probe = lambda probe: answers[probe]
        result = self.engine.run(macro, params={"system": "Altair"})
        self.assertTrue(result["ok"], result)
        keys = [k[0] for k, _ in self.sender.pressed]
        self.assertEqual(keys, ["Key_A", "Key_L", "Key_T", "Key_A", "Key_I", "Key_R", "Key_Enter"])
        self.assertTrue(any("skip (galmap_search_list" in line for line in result["log"]))
        self.assertTrue(any("skip (galmap_route_bar" in line for line in result["log"]))
        # list open + no route yet: the conditional presses fire
        self.sender.pressed.clear()
        answers.update({"galmap_search_list": "open", "galmap_route_bar": "NO ROUTE SET"})
        result = self.engine.run(macro, params={"system": "Altair"})
        self.assertFalse(result["ok"])          # final expect fails: bar still says NO ROUTE SET
        self.assertIn("screen check failed", result["error"])
        self.assertEqual([k[0] for k, _ in self.sender.pressed][7:], ["Key_F6", "Key_F9", "Key_F9"])

    def test_plot_route_macro_is_valid_and_parameterised(self):
        macro = next(m for m in M.DEFAULT_MACROS if m["name"] == "Plot route")
        self.assertEqual(macro["params"], ["system"])
        filled, missing = M.fill_params(macro, {"system": "Sol"})
        self.assertEqual(missing, [])
        self.assertEqual(M.validate_macro(filled), [])
        self.assertIn({"type": "Sol\n"}, filled["steps"])
        self.assertIn("galmap_route_bar=Sol", [s.get("expect_screen") for s in filled["steps"]])

    def test_invalid_macro_rejected_before_running(self):
        result = self.engine.run({"name": "bad", "steps": [{"wait_until": "Docked"}]})
        self.assertEqual(result["error"], "invalid macro")


class EndpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        folder = Path(self.tmp.name)
        (folder / "Custom.4.1.binds").write_text(BINDS_XML, encoding="utf-8")
        cmdkeys._runtime.update(watcher=B.BindsWatcher(folder), engine=None, enabled=False)
        self.addCleanup(lambda: cmdkeys._runtime.update(watcher=None, engine=None, enabled=False))
        self.env = patch.dict(os.environ, {"EDGPT_DATA_DIR": self.tmp.name})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.flags = patch.object(cmdkeys, "_status_flags", return_value={"Docked"})
        self.flags.start()
        self.addCleanup(self.flags.stop)

    def test_list_and_bindings(self):
        listing = cmdkeys.list_macros({})
        json.dumps(listing)
        self.assertFalse(listing["injection_enabled"])
        self.assertEqual(listing["binds"]["actions"], 13)
        names = [m["name"] for m in listing["macros"]]
        self.assertIn("Gear down", names)
        prepare = next(m for m in listing["macros"] if m["name"] == "Prepare to land")
        self.assertEqual(prepare["problems"], [])
        self.assertEqual(prepare["unbound_actions"], [])
        one = cmdkeys.bindings({"action": ["LandingGearToggle"]})
        self.assertEqual(one["keys"], ["Key_RightShift", "Key_L"])
        self.assertIsNone(cmdkeys.bindings({"action": ["Supercruise"]})["keys"])

    def test_run_is_gated(self):
        fake = M.FakeSender()
        cmdkeys._runtime["engine"] = M.MacroEngine(fake, cmdkeys._status_flags, lambda: True,
                                                   cmdkeys._watcher().load)
        self.assertIn("disabled", cmdkeys.run({}, {"macro": "Gear down"})["error"])
        self.assertTrue(cmdkeys.run({}, {"macro": "Gear down", "dry_run": True})["ok"])
        self.assertEqual(fake.pressed, [])
        with self.assertRaises(ValueError):
            cmdkeys.enable({}, {"enabled": "yes"})
        self.assertTrue(cmdkeys.enable({}, {"enabled": True})["injection_enabled"])
        self.assertIn("disabled in macros.json", cmdkeys.run({}, {"macro": "Gear down"})["error"])
        macros = M.load_macros()
        macros[0]["enabled"] = True
        M.save_macros(macros)
        result = cmdkeys.run({}, {"macro": "Gear down"})
        self.assertTrue(result["ok"], result)
        self.assertEqual(fake.pressed, [(["Key_RightShift", "Key_L"], 60)])
        with self.assertRaises(ValueError):
            cmdkeys.run({}, {"macro": "nope"})
        self.assertFalse(cmdkeys.cancel({}, {})["cancelled"])
        self.assertFalse(cmdkeys.enable({}, {"enabled": False})["injection_enabled"])

    def test_engine_creation_does_not_deadlock(self):
        import threading
        done = threading.Event()
        holder = {}

        def build():
            with patch("modules.cmdkeys.sendinput.game_focused", lambda: False):
                holder["engine"] = cmdkeys._engine()
            done.set()
        threading.Thread(target=build, daemon=True).start()
        self.assertTrue(done.wait(5), "cmdkeys._engine() deadlocked")
        self.assertIs(holder["engine"], cmdkeys._engine())

    def test_mcp_tools_are_read_only(self):
        self.assertEqual(set(cmdkeys.MCP_TOOLS), {cmdkeys.get_command_macros, cmdkeys.get_key_binding})
        self.assertNotIn("/cmdkeys/run", cmdkeys.HTTP_ROUTES)


if __name__ == "__main__":
    unittest.main()
