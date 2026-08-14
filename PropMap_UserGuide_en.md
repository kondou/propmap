# PropMap User Guide

---

## 1. Introduction

### What is PropMap?

PropMap is a tool that aggregates public contest log data from amateur radio contests and RBN (Reverse Beacon Network) spot data, then visualizes past HF band propagation conditions as a heatmap on an Azimuthal Equidistant Map centered on a specified grid locator (also known as grid square or Maidenhead locator; this guide uses the term "grid locator" throughout). Based on historical data, it is useful for understanding propagation trends during contests held at the same time of year. Past data can be replayed, and by synchronizing the playback time with real time, you can reference historical data for the same time of day in real time.

Useful for planning contest operations, identifying optimal band-change timing, analyzing propagation trends from past contests, and real-time reference during live contests.

### System Requirements

- macOS Tahoe / Windows 11 (tested)
- Python 3.10+ (auto-detected by the launcher scripts; if absent, consent-based automatic setup is offered, so a prior install is normally unnecessary. **No developer environment** — Xcode / Command Line Tools / Visual Studio — is required. For manual installs see "[(Reference) Manual Python Installation](#reference-manual-python-installation)")
- Modern browser (Safari, Chrome, Edge, etc.)
- JSON data files for the contest you want to view (must be placed in `~/heatmap/data/`). [Data must be built in advance — see Section 10](#10-advance-data-preparation)

### Prerequisites
- Obtain public logs for the contest you want to reference
- Grid locator must be correctly filled in the log header (**GRID-LOCATOR**) — 4 characters are sufficient
- Stations without a grid locator declaration can be supplemented using cty.dat-estimated positions (displayed separately as **est. QSO** / **est. RBN**)
- RBN raw data (if using RBN)
- RBN data uses CW mode only
- RBN spots used are limited to stations whose grid locator is recorded in the public logs (**est. RBN** also includes stations with cty.dat-estimated positions)
- Only QSOs that pass cross-checking between public logs and where both stations' grid locators are known are included
- Cross-check criteria: both logs list the other station on the same band within 15 minutes; exchange number correctness is not checked
- Callsign matching: exact match or up to 2 character differences are accepted
- Band mismatch correction: if bands differ, the band with more QSOs within 15 minutes of each station's logged time is used as the correct band

---

## 2. Setup

### Placement

Extract the zip (or clone the repository) wherever you like — the folder name doesn't need to be `heatmap`. The rest of this guide uses `~/heatmap/` (macOS/Linux/WSL2) or `%USERPROFILE%\heatmap\` (Windows, e.g. `C:\Users\YourName\heatmap\`) as an example; substitute your actual location.

### Launching the Application

**macOS / Windows (with WSL2)**

On macOS, double-click `start_heatmap.command`, or run the following in a terminal. When double-clicked, a terminal opens and the default browser launches automatically — no need to open the browser separately. Closing the terminal window stops the server.

On WSL2, double-clicking usually isn't available, so run this from a WSL2 terminal (Ubuntu, etc.) instead:

```bash
bash ~/heatmap/start_heatmap.command
```

> **macOS, first launch only:** files extracted from a downloaded zip are blocked on first launch. Right-click `start_heatmap.command` → "Open" the first time; afterwards a plain double-click works.

> **WSL2, if the browser doesn't open automatically:** installing `wslu` (`sudo apt install wslu`) makes it open your default Windows browser automatically. Without it, the server still starts fine — just open the URL shown in the terminal (`http://localhost:8765/heatmap.html`) manually.

(If you manage your own Python, launching `python3 ~/heatmap/propmap_server.py` directly is also fine.)

**Windows (without WSL2)**

Double-click `start_heatmap.bat`, or run the following in Command Prompt:

```
%USERPROFILE%\heatmap\start_heatmap.bat
```

(If you manage your own Python, launching `python %USERPROFILE%\heatmap\propmap_server.py` directly is also fine.)

> **If Windows shows a "the publisher could not be verified" warning:** click **Run** to continue. To stop it appearing every time, open PowerShell in the extracted folder and run this (it unblocks the whole folder, including the other `.bat` files):
> ```powershell
> Get-ChildItem -Path "$env:USERPROFILE\heatmap" -Recurse | Unblock-File
> ```
> The Properties → Unblock checkbox some guides mention isn't always present or easy to find; the command above works regardless.

After launching, open `http://localhost:8765` in your browser.

The launcher auto-detects a usable Python 3.10+. If none is found, it offers guidance on the spot: with your consent, **uv** is installed and fetches a standalone Python binary — so **a prior Python install is normally unnecessary** (no compiler or developer environment either). For manual installs see "[(Reference) Manual Python Installation](#reference-manual-python-installation)".

The server binds to `127.0.0.1` only and cannot be reached from other machines. Launching with the traditional `python3 -m http.server 8765` still serves the map display, but the "Data update" feature (described below) will not be available.

> **Note:** A local file server is required — opening `heatmap.html` directly in a browser will not work.

---

### File Structure

All files are placed under `~/heatmap/` (macOS/Linux/WSL2) or `%USERPROFILE%\heatmap\` (Windows). In addition to files included in the repository, some files are automatically fetched by fetch scripts on first pipeline run (★), and others are generated by data build scripts (☆).

``` { .no-copy }
~/heatmap/
├── heatmap.html              Main application (self-contained single file)
├── update.html               Data update page (pre-built downloads / self-build)
├── propmap_server.py         Local server (static files + data update API)
├── find_python.sh            Python auto-detection (macOS/Linux/WSL2)
├── find_python.bat           Python auto-detection (Windows)
├── start_heatmap.command     Launcher (macOS)
├── start_heatmap.bat         Launcher (Windows)
├── countries-50m.json        Terrain data
├── fetch_cty.py              cty.dat download script
├── fetch_ssn.py              Sunspot number data download script
├── fetch_rbn_nodes.py        RBN node list generation script
├── make_data_release.py      Pre-built data release updater (maintainer)
├── cty_data/                 ★ cty.dat files (fetched by fetch_cty.py)
├── data/
│   ├── {contest}_{year}.json         ☆ QSO data (10-minute resolution)
│   └── {contest}_{year}_rbn.json     ☆ RBN data (10-minute resolution)
└── contest_logs/
    ├── raw/{contest}_{year}/*.txt     ☆ Public Cabrillo logs
    ├── csv/                           ☆ Processed CSV files
    │   ├── annotated/{contest}_{year}/  ☆ Annotated Cabrillo logs (regular)
    │   └── annotated_approx/{contest}_{year}/  ☆ Annotated Cabrillo logs (approx)
    ├── rbn/
    │   ├── raw/YYYYMMDD.zip           ★ RBN raw data (fetched by download_rbn.py)
    │   └── rbn_nodes.csv              ★ RBN node list (fetched by fetch_rbn_nodes.py)
    ├── SN_m_tot_V2.0.txt              ★ Sunspot number data (fetched by fetch_ssn.py)
    ├── *.py                           Data processing scripts
    ├── generate_all.sh                Batch regeneration script (macOS/Linux)
    └── generate_all.bat               Batch regeneration script (Windows)
```

### (Reference) Manual Python Installation

The launcher's auto-detection and automatic setup normally suffice, so this section is not needed. Refer to it only if you prefer to install and manage Python yourself.

Detection order: explicit override via the `PROPMAP_PYTHON` environment variable → `python3` on PATH (on macOS the developer-tools stub is safely excluded) → known install locations (Homebrew / python.org) → the macOS-bundled `python3` (only if Command Line Tools are installed) → uv.

#### macOS Tahoe

- **python.org official installer (recommended)**: download and run the macOS installer (universal2 binary) from [python.org](https://www.python.org/downloads/). Requires neither Xcode nor Command Line Tools
- **uv**: install with `curl -LsSf https://astral.sh/uv/install.sh | sh`; Python itself is fetched as a standalone binary (no building)
- If you already use Homebrew, `brew install python3` also works. Note that right after a major OS release, bottles (prebuilt binaries) may not yet be available, causing a source-build fallback that demands Xcode — hence the two options above are recommended for PropMap purposes

Verify: `python3 --version` shows `Python 3.10` or later.

#### Windows 11 — Without WSL2

The viewer and full data-building pipeline work with Python for Windows and the included `generate_all.bat`. Since `generate_all.sh` is a bash script and cannot be run directly on Windows, use the equivalent `generate_all.bat` instead.

1. Download the Windows installer from [python.org](https://www.python.org/downloads/)
2. During installation, **check "Add Python to PATH"** (unchecked by default — though even without it, the bundled `py` launcher is auto-detected)
3. Verify (Command Prompt): `py -3 --version` or `python --version` shows `Python 3.10` or later

The Microsoft Store "stub" (the alias that opens the Store when `python` is typed without Python installed) is safely excluded by the auto-detection.

> **Note:** On Windows, use `python` instead of `python3`

#### Windows 11 — With WSL2

With WSL2, shell scripts work as-is and the experience is equivalent to macOS. For WSL2 setup, refer to the [Microsoft official documentation](https://learn.microsoft.com/en-us/windows/wsl/install). After installing Ubuntu:

```bash
sudo apt update && sudo apt install -y python3 python3-pip
python3 --version
```
`Python 3.x.x` will be displayed on success.

All subsequent steps are the same as macOS. Access the browser on the Windows side at `http://localhost:8765`.

---

## 3. Screen Layout

<img src="images/sc1.png" alt="Full screen" style="max-width:100%;width:1400px;">

The screen is divided into two main areas.

**Azimuthal Map Area (left or top)**
Displays the heatmap on an Azimuthal Equidistant Map centered on the selected grid locator.

**Control + Graph Area (right or bottom)**
Contains display settings and time-series graphs showing QSO counts and active grid counts over ±3 hours.

### Responsive Layout

The layout switches automatically based on browser window width.

When the browser window is wide (desktop, laptop, etc.), the map area and control + graph area appear side by side. When narrow (tablet portrait, smartphone, or a resized window), they stack vertically.

<img src="images/sc2.png" alt="Stacked layout" style="max-width:100%;width:550px;">

In stacked mode, the map fills the full window width, and the graph height is limited to 2.2× the map height.

---

## 4. Basic Operation

<img src="images/sc3.png" alt="Control panel" style="max-width:100%;width:700px;">

### Center Grid and Display Range

**Center (center grid)**
Enter a 4-character grid locator (e.g., PM52). Click **Apply** or press Enter to apply. You can also drag the map to position the desired area at the center, then click **Apply**.

**Dist (distance filter)**
Use the slider to set the display radius from the center grid (km). Only QSOs and spots involving a station within this distance are shown.

**Fixed checkbox**

- **Checked (default)**: Dragging the map moves only the visual display; the heatmap is not recalculated. The heatmap updates to the new center when **Apply** is clicked.
- **Unchecked**: The heatmap updates in real time as you drag. Dragging over a large area increases rendering load.

While dragging, the center grid label is shown at full brightness on the map. Three seconds after the drag ends, it fades automatically to avoid interfering with grid panel display.

### Contest, Band, Mode, and Power Selection

| Item | Description |
|---|---|
| Band | Select band (160m / 80m / 40m / 20m / 15m / 10m / All) |
| Mode | Select mode (CW / SSB / All) |
| Power | Filter by power class (High / Low / QRP) |
| Contest | Select contest |

For single mode contests (CW-only or SSB-only), other modes cannot be selected.

### Year Selection and Multi-Year Merge

Use the **Year** checkboxes to select which years to display. Checking multiple years merges and overlays the data. Multi-year merge is useful for understanding overall propagation trends. Note that older public logs often lack grid locator data, so the heatmap may be empty for those years. To supplement the display for such stations, see the **est. QSO** checkbox.

The number of loaded records and the selected year(s) are shown in the upper right of the screen (e.g., `1,916,313 records (2025)`, `1,052,123 records (2024+2025)`).

### Time Slider

Drag the slider left or right to change the displayed time. The UTC time is shown in the text box on the left. You can also type a time directly (e.g., `14:30`) and press Enter or click away to jump the slider to that time.

For 48-hour contests (CQ WW, CQ WPX, WAE DX), a **+1d** checkbox appears. Check it to switch to Day 2 (24 hours after contest start).

### Set Default / Reset / Apply / Doc

| Button | Action |
|---|---|
| **Set Default** | Save current settings (center grid, distance, etc.) as defaults |
| **Reset** | Restore settings to defaults |
| **Apply** | Apply the Center change |
| **Doc** | Open this user guide in a new tab (language matches browser setting) |

---

## 5. Display Modes

### Manual (Slider)

Manually move the slider to inspect propagation at any time. The grid panels on the map and the graphs update to match the selected time.

### Play (Auto Replay)

Click **▶ Play** to advance the slider automatically from contest start, animating propagation changes. Click **■ Stop** to pause.

Playback can start from any time. For 48-hour contests, check **+1d** before clicking Play to start from Day 2.

### RT (Real Time)

Click **⏱ RT** to synchronize display with the current UTC time. Useful for checking propagation during a live contest.

For 48-hour contests, use the **+1d** checkbox to switch between Day 1 and Day 2. On the actual contest weekend, the correct day is selected automatically.

---

## 6. Azimuthal Map

<img src="images/sc4.png" alt="QSO heatmap" style="max-width:100%;width:960px;">

### What is an Azimuthal Equidistant Map?

An Azimuthal Equidistant Map accurately represents distance and bearing from the center point. Any straight line from the center traces a great circle (shortest path). Concentric circles indicate distance (km) from the center.

### QSO Heatmap

A colored rectangle placed on the map for each 4-character grid locator is called a **grid panel**. QSO counts near the selected time are aggregated per grid and displayed as the grid panel color.

- Color gradient: **low (green) → yellow → orange → high (red)**
- The **QSO** color scale bar in the upper left shows the color-to-count mapping

### RBN Heatmap

Available only for contests with a CW mode. Switching to an SSB contest automatically unchecks and disables the RBN checkbox. When the **RBN** checkbox is ON, RBN spot data is shown as magenta-toned grid panels.

<img src="images/sc5.png" alt="RBN heatmap" style="max-width:100%;width:960px;">

- Color gradient: **low (dark purple) → magenta → high (white)**
- The **RBN** color scale bar in the upper left shows the mapping

### est. QSO / est. RBN (Estimated Grid Data)

In contest logs up to around 2018, many stations did not declare a grid locator (MY LOCATOR) in their log headers, resulting in few or no grid panels being displayed. Enabling the **est. QSO** and **est. RBN** checkboxes supplements these stations with positions estimated from their callsign prefix using cty.dat.

- **est. QSO**: Adds QSO data for stations without a grid locator declaration
- **est. RBN**: Adds RBN data for spot stations without a grid locator declaration (CW contests only)

Notes:

- Grid locator accuracy is at the entity (country/territory) or call area level as defined in cty.dat, and may differ from the actual operating location
- No overlap with regular QSO / RBN data
- The record count in the upper right shows `(+N est.)` for est. data record counts

### Out-of-Range Grid Markers

Grids outside the map's display circle are shown as triangular markers on the circle's perimeter, indicating their bearing. QSO data uses white-toned triangles; RBN data uses magenta-toned triangles. When est. QSO / est. RBN is enabled, estimated grids are also shown as triangle markers. Multiple grids in the same direction are offset slightly. Markers blink when active.

### Gray Line (Day/Night Terminator)

The solar terminator at the displayed time is shown as an orange band. The gray line has a strong correlation with propagation conditions, especially on lower bands.

### Bottom-Right Overlay

<img src="images/sc6.png" alt="Bottom-right overlay" style="max-width:100%;width:162px;">

The following information is shown in the bottom-right overlay:

``` { .no-copy }
0/21 (  0.0%)        ← QSO: out-of-range grids / total grids (ratio)
0/17 (  0%)          ← RBN: out-of-range grids / total grids (ratio)
Center: PM52
Radius: 20,000km
21 grids · 24 QSOs   ← visible grids and QSO count
17 grids · 23 spots  ← visible RBN grids and spot count
```

**When est. QSO / est. RBN is enabled**, estimated grid counts, QSO counts, and spot counts are also included in the totals.

The large number (numerator) shows **grids outside the display circle**. A non-zero value blinks to indicate off-screen data. Hover over any row for a detailed tooltip. Click the overlay to reset the display radius (Radius) to its default value.

### Tooltips

Hover over a grid panel on the map to see detailed information in a tooltip:

- **Grid name** (bold)
- QSO count per selected year (e.g., `2024: 12 QSO`); listed by year when multiple years are selected
- When RBN is enabled, spot count shown in magenta (e.g., `RBN: 5`)
- **When est. QSO / est. RBN is enabled**, estimated QSO and spot counts are also included

---

## 7. Graph Panel

<img src="images/sc7.png" alt="Graph panel" style="max-width:100%;width:700px;">

The graph panel shows four graphs, all covering **±3 hours from the current display time**.

### QSOs (±3h)

QSO count per time step from contest logs, shown as a line graph by band. A vertical dotted line marks the current display time.

### RBN Spots (±3h)

Spot count per time step from RBN data, shown as a line graph by band.

### Grids (±3h)

Active grid count (unique grids) per time step from contest logs, shown by band.

### RBN Grids (±3h)

Active grid count per time step from RBN data, shown by band.

### Band Colors

| Band | Color |
|---|---|
| 10m | Red |
| 15m | Orange |
| 20m | Blue |
| 40m | Yellow |
| 80m | Green |
| 160m | Purple |

### Tooltips

Hover over a graph to see band-by-band values for that time in a tooltip.

---

## 8. Crawl Mode (Automatic Band Cycling)

<img src="images/sc8.png" alt="Crawl mode" style="max-width:100%;width:1400px;">

In [RT (Real Time)](#rt-real-time) mode, Crawl cycles through bands automatically at a set interval.

### Auto / All / No

| Setting | Behavior |
|---|---|
| **Auto** | Cycles through bands in descending QSO order, skipping bands with less than 15% of total QSOs near the center grid. Focuses on active bands. |
| **All** | Cycles through all bands (10m / 15m / 20m / 40m / 80m / 160m) in order |
| **No** | No automatic cycling; band and mode remain fixed |

For single mode contests (CW-only or SSB-only), Crawl cycles only through the locked mode and does not switch to other modes.

### Crawl Timer

Use **Crawl Timer** to set how long each band is displayed (5s / 10s / 15s).

---

## 9. Data

### Supported Contests and Coverage

| Contest | Period | Duration | RBN Data |
|---|---|---|---|
| IARU HF | Second full weekend of July (starts Sat 12Z) | 24h | Yes |
| CQ WW CW | Last full weekend of November (starts Sat 00Z) | 48h | Yes |
| CQ WW SSB | Last full weekend of October (starts Sat 00Z) | 48h | No |
| CQ WPX CW | Last full weekend of May (starts Sat 00Z) | 48h | Yes |
| CQ WPX SSB | Last full weekend of March (starts Sat 00Z) | 48h | No |
| WAE DX CW | Second full weekend of August (starts Sat 00Z) | 48h | Yes |
| WAE DX SSB | Second full weekend of September (starts Sat 00Z) | 48h | No |

### Reading the WAE DX Contest

In the WAE DX Contest, **a contact is only valid between a European station and a non-European station**. European stations do not work each other, and neither do stations outside Europe.

This makes the display behave differently from the other contests:

- Centred on Japan, **only the direction of Europe is shown**. North America, Oceania and Asia are blank.
- Centred on Europe, every direction outside Europe is shown, and only Europe itself is blank.

**A blank area does not mean signals failed to get through.** Those contacts simply never take place, so there is no data. Keep this in mind when comparing propagation between contests.

The RBN heatmap is matched to the same division and shows only paths between Europe and non-Europe, so that it reads consistently with the QSO heatmap. No such restriction is applied to the other contests.

### About RBN Data

RBN (Reverse Beacon Network) is a network that automatically receives, decodes, and spots CW and digital mode signals. PropMap uses RBN spot data to visualize propagation conditions not captured in contest logs. RBN data is available only for CW contests (IARU, CQ WW CW, CQ WPX CW, WAE DX CW).

### About SSN (Sunspot Number)

`SN_m_tot_V2.0.txt` (monthly sunspot number data provided by SILSO) is used to automatically resolve the SSN for the contest month and apply it during data processing (planned — not yet implemented). If the file does not exist, it is downloaded automatically when data is built.

---

## 10. Advance Data Preparation

PropMap requires data to be prepared in advance — it is too large to bundle with the tool. There are two ways to obtain it:

- **Download pre-built data (recommended)**: fetch ready-made JSON published by the project. Takes minutes
- **Build it yourself (advanced)**: run the full pipeline from public logs and RBN raw data covering the same contest period. Suited to importing a year not yet published as pre-built data, or to verification. A full build downloads several GB and takes hours

Both are driven from the Data update page by clicking buttons — no commands to type.

**Once data is prepared, using PropMap needs no internet connection.** The map, its terrain data (`countries-50m.json`), and heatmap playback all run entirely from local files. An internet connection is only needed to prepare or refresh data.

### Opening the Data Update Page

With the server started via `start_heatmap` (propmap_server.py) running, click the "⟳ Data update" link next to the Contest selector on the map screen. Opening `http://localhost:8765/update.html` directly in the browser works too.

### Downloading Pre-built Data (Recommended)

On the Data update page, click "Check" under "1. Download pre-built data". A list of distributed contest-years with sizes appears; select what you want and click "Download selected". Items already held are marked "held" and are not re-downloaded.

The distribution source is GitHub Releases. Downloads are verified by size and sha256, and a failed transfer never leaves a corrupt file in place.

### Importing Newly Published Years (Self-build)

This builds a contest year that has not yet been published as pre-built data, from public logs and RBN data.

On the Data update page, under "2. Build from public logs + RBN", click "Check" → review the estimate table → "Download and import". Target years are derived automatically from the contest schedule, so there is no year to specify. The map keeps working on existing data while the job runs; when it finishes, the new year appears in the year list on the map tab. Processing runs on the server, so the page can be closed (closing the terminal that started the server stops the job).

The estimate shows three items: public-log download size / RBN zip size / converted JSON size. If free disk space is below the estimated total, the run is aborted before starting.

**About how long it takes:** since raw logs and RBN data are fetched and processed from scratch, even a single contest/year can take an hour or more depending on your PC and connection speed, and large contests can take several hours. Progress is shown as a step name only, with no percentage, so a long wait with no visible change is usually still normal processing.

**About interruption and resuming:** if processing is interrupted (PC sleep/shutdown, closing the window, etc.), running "Check" then "Download and import" again resumes from the incomplete step instead of re-running steps that already finished. A file interrupted mid-download is never treated as "complete" either — it is correctly re-fetched on the next run.

### From the Command Line

The same preparation can be driven from the command line. The scripts under `contest_logs/` document their usage under `--help`; refer to that. This guide does not cover it.

---

## 11. Troubleshooting

### Opening `heatmap.html` directly in a browser shows no data

The `file://` protocol blocks JSON loading due to browser security restrictions. Always access it through a local server (see "[Launching the Application](#launching-the-application)").

### No panels are shown at all

Check in the following order.

1. **Check the contest/year/filter settings**
   Confirm the Band / Mode / Dist / Year selections are what you intended. In particular, a Dist that's too small will leave little to display.

2. **Check whether the data is there**
   On the "Data update" page, click "Check" under "1. Download pre-built data" and see whether that contest-year is marked "held". If it isn't, select it and download it.

If it still shows nothing, there may be no QSOs matching that contest, year, and set of conditions. Try a different year or a wider Dist.

### est. data is not shown

The estimated data (`*_approx.json`) for that contest-year is not present locally. Download that contest-year again from "1. Download pre-built data" on the "Data update" page — the distributed data includes the estimated data.

### The blinking animation or dragging stutters or stops, or Play skips frames

- Putting the PropMap tab in the background pauses the blinking due to browser timer throttling. This is normal browser behavior, not a bug.
- If another tab or window is running something CPU-heavy (video playback, WebGL, etc.), CPU contention can cause stutter. Making the PropMap tab active and closing other heavy pages usually helps.
- Dragging the map to recenter it (with **Fixed** unchecked, or in **Pan** mode) also involves continuous redrawing, so it can stutter under the same CPU-contention conditions as the blinking animation. The remedy is the same as above.
- If closing other tabs doesn't help, the PC itself may not have enough free memory or CPU headroom. This is especially true when merging multiple years, or with data-heavy contests like CQ WW / CQ WPX (a single JSON file can exceed 200MB), since the browser has more data to handle. Dropped frames during **Play** playback are often caused by this — narrowing the selected years, reducing Dist (display distance), or closing other applications to lighten the load usually helps.

### The first load is slow

JSON files can range from tens of MB to over 200MB each, so the first load can take a few seconds. This is due to the data volume; subsequent loads benefit from the browser cache.

### Browser compatibility

Tested on Chrome / Safari / Edge. Firefox also works, but performance may differ when processing large amounts of data.

### Use on smartphones/tablets

Not tested or intended for this use. A desktop browser is assumed.

---

## 12. Tips

### What happens to an already-open page after stopping and restarting the server

After stopping `start_heatmap` and starting it again, you don't need to close and reopen browser tabs (`heatmap.html` / `update.html`) that were already open. Doing something like reselecting a year or contest is enough to get it working normally again.

If a "Data update" page (`update.html`) was showing progress at the time, it may not pick back up automatically after a restart. Reloading the page, or clicking "Check" again, gets it working as usual.

Redoing work that only got partway done doesn't repeat the parts that already finished (see the note on interruption and resuming in "Advance Data Preparation").

When in doubt, reloading the browser (F5) is the simplest fix.
