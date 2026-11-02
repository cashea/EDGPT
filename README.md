# EDGPT 0.2.0 Beta

**A universal Elite Dangerous → AI bridge.**

EDGPT does not provide an AI chat UI. It reads Elite Dangerous data on your Windows PC and exposes that data to AI clients through **MCP** or an optional **GitHub Relay**.

```text
Elite Dangerous
      ↓
    EDGPT
   ↙     ↘
 MCP   GitHub Relay
  ↓         ↓
Any compatible AI client
```

## What it exposes

EDGPT can make the following available to an AI client:

- current system/location and route
- current ship and complete `Loadout` data
- module engineering data
- Elite live JSON sidecars such as `Status.json`, `NavRoute.json`, `Cargo.json`, `Backpack.json`, `ShipLocker.json`, `ModulesInfo.json`, `Market.json`, `Outfitting.json`, and `Shipyard.json`
- recent raw Journal events
- **all historical `Journal.*.log` files** through a local SQLite history index
- raw historical search and pagination
- optional Full Context GitHub mirror for AI clients that cannot reach local MCP

EDGPT preserves raw Frontier journal events so useful event types remain accessible even when EDGPT does not yet have a special parser for them.

## Fastest setup

### Live map page (Elite State)

With the Elite State server running (default port 8080), open
`http://127.0.0.1:8080/map` for a standalone HTML map of your current or last
system. It follows location changes and refreshes every five seconds, making
it usable as a browser page or an OBS browser source.

Use `http://127.0.0.1:8080/map?system=123456789` to keep the page on a saved
system by its numeric **SystemAddress**. You can also enter the ID on the page.
The map uses a dark, orange-accented hierarchy with body-type colors and summary
counts. Body cards show recorded mass, radius, gravity, temperature, orbital and
rotation periods, pressure, landability, terraforming and discovery status,
surface mapping, signals, rings, and materials. Expand **All recorded details**
for every retained body event, including composition, organics, Codex records,
and nested scan data. System signals and complete system records appear below
the hierarchy. Expanded sections stay open during live refreshes of the same
system; **Expand all details** opens everything at once.

Click **Export WordPress HTML** to download a snapshot of the displayed system.
Open the downloaded `.html` file in a text editor and paste its contents into a
WordPress **Custom HTML** block. The export includes the map data and styles,
with no auto refresh, search, scripts, or server links. Expandable details work
without JavaScript. All CSS is scoped to the map container, including mobile
and print styles, so it does not restyle the surrounding website. WordPress must
allow the included `<style>` element for the map styling to appear.
You can also download directly from `/map/export` or
`/map/export?system=123456789`.

Organic scans add an **Organic confirmed seen** badge and the organism's name;
completed analysis is marked separately. All Log, Sample, and Analyse journal
records remain available under **Scan Organic**. Existing indexed scans are
recovered automatically when saved maps upgrade to the current schema.
Stars use spectral-type colors and luminous icons, with distinct neutron-star,
white-dwarf, and black-hole visuals. Empty inferred asteroid-belt parent cards
are hidden while their recorded clusters remain in the hierarchy.

Measurements on cards use readable units; detailed journal fields preserve their
original values and units. This is a journal-based schematic, not an
orbital-position chart. Only recorded information is available. Existing JSON
endpoints remain available separately.

### 1. Install

Download and run `EDGPT-Setup-0.2.0-beta.exe` from Releases.

No Python installation is required for the packaged Windows build.

EDGPT automatically looks for Elite data at:

```text
%USERPROFILE%\Saved Games\Frontier Developments\Elite Dangerous
```

For a standard installation, open EDGPT and the core bridge starts automatically.

### 2. Connect an AI

EDGPT runs a local Streamable HTTP MCP endpoint at:

```text
http://127.0.0.1:8000/mcp
```

If your AI client supports **local MCP directly**, it can connect to that endpoint.

If you are using a **hosted/cloud AI client that cannot directly access `localhost`**, a secure tunnel or another supported MCP transport is required between EDGPT and the AI service.

For **ChatGPT/OpenAI**, use OpenAI's official **Secure MCP Tunnel** with `tunnel-client` (`tunnel-client.exe` on Windows):

```text
Elite Dangerous
      ↓
    EDGPT
      ↓
Local MCP (127.0.0.1:8000/mcp)
      ↓
OpenAI Secure MCP Tunnel
(tunnel-client.exe)
      ↓
ChatGPT / supported OpenAI client
```

`tunnel-client.exe` is an OpenAI component and is **not bundled with the public EDGPT release**. Download/install the official OpenAI tunnel client separately and configure it to forward EDGPT's local MCP endpoint.

MCP itself is **not OpenAI-only**. Other compatible AI clients may support local MCP directly or provide their own secure/remote MCP transport. Check the connection requirements of the AI client you want to use.

If your AI cannot use EDGPT through MCP but can access GitHub, use **GitHub Relay** instead. See `QUICKSTART.md`.

### 3. Click CHECK

A healthy core installation should report:

```text
OK  Elite journal folder
OK  State server
OK  MCP server
```

Current state is also visible locally at:

```text
http://127.0.0.1:8080/state
```

The default response is intentionally compact. It omits `history_summary`,
`recent_events`, the raw `loadout`, and the complete `live_files` collection.
Those fields can be requested independently:

```text
http://127.0.0.1:8080/state?history_summary=true
http://127.0.0.1:8080/state?recent_events=25
http://127.0.0.1:8080/state?loadout=true
http://127.0.0.1:8080/state?live_files=true
```

To request the previous full-context shape:

```text
http://127.0.0.1:8080/state?history_summary=true&recent_events=250&loadout=true&live_files=true
```

Boolean options accept `true`/`false`, `1`/`0`, `yes`/`no`, or `on`/`off`.
`recent_events` accepts an integer from 0 to 5,000. Invalid values return HTTP
400. EDGPT still uses its internal replay window and loadout/live data to derive
accurate normalized state when those raw fields are omitted.

## MCP tools

Endpoint references: [State Engine HTTP API](docs/STATE_ENGINE_ENDPOINTS.md)
and [MCP endpoint and tools](docs/MCP_ENDPOINTS.md).

```text
get_elite_state
get_full_loadout
get_navroute
get_status
list_elite_live_files
get_elite_live_file
get_recent_events
search_journal
get_latest_journal_event
get_history_summary
get_raw_history_page
get_current_session_summary
list_game_sessions
get_game_session
get_current_system_map_simple
get_current_system_map_full
list_saved_system_maps
get_saved_system_map_simple
get_saved_system_map_full
get_current_system_summary
get_saved_system_summary
get_exobio_status
get_exobio_body
get_exobio_system_overview
get_command_macros
get_industry_summary
```

The last five come from companion modules; see [docs/MODULES.md](docs/MODULES.md).

`Status.json` responses preserve Frontier's numeric `Flags` and `Flags2` while
also adding `FlagsDecoded`/`Flags2Decoded` name lists. Unknown active bit
positions are reported in `FlagsUnknownBits`/`Flags2UnknownBits`. Missing raw
fields remain absent rather than being treated as zero. The numeric `GuiFocus`
field is likewise preserved and accompanied by `GuiFocusDecoded` for documented
values, such as `"Galaxy Map"`.

System maps are built incrementally from exploration journal events and saved
by `SystemAddress`. EDGPT backfills maps from indexed historical journals and
merges later visits into the existing map. Compact tools return a body tree
with types and arrival distances; full tools include all retained scan and
signal event data.

Compact system overviews are available at `/system-map/summary` and through
`get_current_system_summary` / `get_saved_system_summary`. They group stars,
planets and rings, with recorded biology when available. Summaries become
available after `FSSAllBodiesFound`, persist across visits, and refresh derived
curiosities when retrieved. Use `?system=...` for a saved name or SystemAddress.
See [the overview contract](docs/SYSTEM_SUMMARIES.md).

## Full Context history

Session summaries are available separately at `/sessions`, `/sessions/current`,
and `/sessions/get?id=...`, with matching MCP tools listed above. They include
compact activity totals, text, source event ranges and incomplete-data warnings.
Lists support pagination and start-time filters. `/state` remains unchanged.
See [session summary API and supported activities](docs/SESSIONS.md).

On startup, EDGPT indexes historical Elite journals into a local SQLite database. The first run may take longer; later runs only add new events.

The AI does **not** receive every historical event in every prompt. MCP tools retrieve only the relevant history when needed, while raw events remain available.

## GitHub Relay

GitHub Relay is optional and **disabled by default**.

When enabled, EDGPT can publish:

```text
elite_state.json
edgpt_manifest.json
edgpt_raw/journals/...
edgpt_raw/live/...
```

to a repository you control.

The relay explicitly requests the full `/state` response, so this compact
local default does not remove its existing loadout, history, or live-file data.

**Use a private repository.** Full Context journals can contain detailed commander location and activity history.

## OpenAI Secure MCP Tunnel

EDGPT's MCP server is vendor-neutral. The OpenAI Secure MCP Tunnel is an optional transport specifically for connecting a local/private MCP server to supported OpenAI clients.

For ChatGPT/OpenAI setups that cannot access EDGPT's localhost endpoint directly, the official OpenAI `tunnel-client` (`tunnel-client.exe` on Windows) is required. EDGPT does not redistribute this third-party executable; obtain it from OpenAI and configure it separately.

Availability and account-side setup are controlled by the relevant provider and can change independently of EDGPT.

## Privacy and security

- EDGPT does not need your Frontier password.
- Core local MCP runs on `127.0.0.1` only.
- GitHub Relay is opt-in.
- Credentials entered through EDGPT are protected locally with Windows DPAPI.
- `data/`, secret `*.bin` files, and history databases must never be committed or packaged.
- Public release builds intentionally exclude third-party tunnel executables unless redistribution rights are separately verified.

Read `SECURITY.md` before publishing logs or enabling Full Context GitHub Relay.

## Building from source

Developer-oriented architecture, extension notes, and the suggested roadmap
are available in [`docs/PROGRAM_DESIGN.md`](docs/PROGRAM_DESIGN.md),
[`docs/EXTENDING_EDGPT.md`](docs/EXTENDING_EDGPT.md), and
[`docs/ROADMAP.md`](docs/ROADMAP.md).

Developer requirements:

- Windows 10/11 x64
- Python
- Inno Setup 6 or 7 for the installer

Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\build-release.ps1
```

The release builder produces:

```text
release/installer/EDGPT-Setup-0.2.0-beta.exe
release/EDGPT-Portable.zip
release/SHA256SUMS.txt
```

It also fails the build if runtime secrets/data are found in the staged release.

## Release status

0.2.0 is a **beta**. The bridge and Full Context path are functional, but stable `1.0` should wait until the installer and bridge modes have been tested on several independent Windows PCs.

See `RELEASE_CHECKLIST.md`.

## Disclaimer

EDGPT is an unofficial community project and is not affiliated with, endorsed by, or sponsored by Frontier Developments or OpenAI.

Elite Dangerous is a trademark of Frontier Developments. Third-party services and components are subject to their own licenses and terms.

## License

See `LICENSE`.

## Health and feature discovery

Open `/health` for ready, degraded, indexing, stale or error status; `/capabilities` lists available features and `/version` identifies schemas. MCP provides `get_edgpt_health` and `get_edgpt_capabilities`. Launcher CHECK uses endpoint diagnostics and retains the last issue. See [the health contract](docs/HEALTH.md).

## Shared state and automated checks

HTTP and MCP use the same current-state reducer. MCP retains raw context and
also returns the normalized HTTP fields. See [the state foundation](docs/STATE_FOUNDATION.md)
for compatibility and database recovery. Run all tests without live commander data:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
