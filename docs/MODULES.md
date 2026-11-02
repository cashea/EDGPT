# Companion modules

Companion modules live under `bin/modules/` and extend EDGPT additively. The
registry (`bin/modules/__init__.py`) imports each module and merges its HTTP
routes and MCP tools into the state server (`:8080`), the MCP server
(`:8000/mcp`) and the `/capabilities` contract. Modules must not start
listeners, threads or touch the filesystem at import time.

| Module | HTTP routes | MCP tools | Status |
| --- | --- | --- | --- |
| `exobio` | `/exobio`, `/exobio/body`, `/exobio/overview` | `get_exobio_status`, `get_exobio_body`, `get_exobio_system_overview` | Working |
| `cmdkeys` | `/cmdkeys` | `get_command_macros` | Scaffold |
| `industry` | `/industry` | `get_industry_summary` | Scaffold |

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
