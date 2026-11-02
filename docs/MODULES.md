# Companion modules

Companion modules live under `bin/modules/` and extend EDGPT additively. The
registry (`bin/modules/__init__.py`) imports each module and merges its HTTP
routes and MCP tools into the state server (`:8080`), the MCP server
(`:8000/mcp`) and the `/capabilities` contract. Modules must not start
listeners, threads or touch the filesystem at import time.

| Module | HTTP routes | MCP tools | Status |
| --- | --- | --- | --- |
| `exobio` | `/exobio`, `/exobio/body`, `/exobio/overview` | `get_exobio_status`, `get_exobio_body`, `get_exobio_system_overview` | Working |
| `cmdkeys` | `/cmdkeys`, `/cmdkeys/binds`, `/cmdkeys/page`; POST `/cmdkeys/enable`, `/cmdkeys/run`, `/cmdkeys/cancel` | `get_command_macros`, `get_key_binding` | Working (no global hotkeys yet) |
| `industry` | `/industry` | `get_industry_summary` | Scaffold |

## cmdkeys

Parses the active `.binds` file (preset from `StartPreset.4.start`, re-read on
change), resolves actions to keyboard chords, and runs small state-reactive
macros with Win32 `SendInput` scancodes. Open `/cmdkeys/page` on a second
screen for the button grid with live `Status.json` flags.

Macro steps (`data/macros.json`, defaults written disabled):
`{"press": "<Action>", "hold_ms": 60}`, `{"wait": <ms>}`,
`{"wait_until": "<Flag>", "is": true, "timeout_ms": <ms>}`; any step may add
`"if_flag": "<Flag>", "is": true|false` to run only in that state.

Safety: injection is OFF at startup and enabled per process by POST
`/cmdkeys/enable`; each macro is opt-in; 12 steps / 30 s caps; every wait has
a timeout; one macro at a time; CANCEL aborts; keys go out only while
`EliteDangerous64.exe` is the foreground window; POST routes accept loopback
clients only; MCP tools are read-only. Frontier's position on input automation
is not clearly stated. Use at your own risk.

Not yet: global hotkeys (needs a Win32 message loop thread), macro editing UI
(edit `macros.json`), joystick/mouse bindings (keyboard chords only).

## exobio

Reads the persistent system map (which retains `Scan`, `FSSBodySignals`,
`SAASignalsFound` and every `ScanOrganic` per body) and the normalized state.
Nothing new is written to disk; the reducers are pure.

| Endpoint | Query | Returns |
| --- | --- | --- |
| `/exobio` | optional `body=<name|id>` | Current body view, system overview, last `SellOrganicData`, recent sales total |
| `/exobio/body` | `body=<name|id>` required, optional `system=<name|address>` | One body: conditions, genera, sample progress, values, candidate species |
| `/exobio/overview` | optional `system=<name|address>` | Bodies with biology, progress, pending (analysed, unsold) value |

Per genus: `species`, `variant`, `samples` (0–3 counting `Log`/`Sample`;
`Analyse` marks completion), `value` (base), `value_first_logged` (×5),
`value_min`/`value_max` across the genus, `min_distance_m` (clonal range) and
up to six `candidates` predicted from the body's planet class, atmosphere,
gravity, temperature, pressure, volcanism and parent star types.
Predictions are heuristics; rules marked `unmodeled` depend on data the
journal does not carry (galactic region, nebula distance, etc.).

Reference data: `bin/modules/exobio/data/exobio_data.json`, generated from
dwomble/EDMC-ExplorerLite (MIT). See `bin/modules/exobio/NOTICE.md`.

Tests: `tests/test_exobio.py` (tables, reducers, endpoints with fakes) and
`tests/test_modules.py` (registry contract).
