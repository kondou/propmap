# PropMap

[日本語 README](README.ja.md)

PropMap replays past HF-band propagation as an animated heatmap on an
azimuthal equidistant map centered on your grid locator, built from public
amateur-radio contest logs and RBN (Reverse Beacon Network) spot data.
By syncing playback to the current clock, you can see what propagation
looked like at the same time of day in past runnings of a contest — useful
for operating plans and band-change timing during contests held at the same
time of year.

![PropMap screenshot](images/sc1.png)

## Features

- QSO heatmap from cross-checked public contest logs (both stations' grid
  locators confirmed)
- RBN spot heatmap for CW contests
- Estimated positions (est. QSO / est. RBN) via cty.dat for stations that
  did not declare a grid locator — greatly extends coverage of older logs
- Playback, real-time sync (RT), and automatic band cycling (Crawl)
- Multi-year merge, distance filter, gray-line overlay, ±3 h activity graphs
- Supported contests: IARU HF (2018–), CQ WW CW/SSB (2005–),
  CQ WPX CW/SSB (2008–), WAE DX CW/SSB (2017–)
- Built-in data update page: check for newly published logs, see a disk-usage
  estimate, and import them from the browser

## Requirements

- Python 3.10+ — if none is found, the launcher offers to set one up
  automatically (via [uv](https://docs.astral.sh/uv/), with your consent;
  no Xcode / Visual Studio / Homebrew required, and nothing outside your
  user directory is touched)
- A modern browser (Safari, Chrome, Edge, ...)

## Quick start

1. Download the [latest release zip](https://github.com/kondou/propmap/releases/latest/download/propmap-latest.zip)
   (or clone this repository) and place it anywhere you like — e.g.
   `~/heatmap` (macOS/Linux/WSL2) or `%USERPROFILE%\heatmap` (Windows); the
   folder name doesn't matter. That link always points to the newest
   version — bookmark it if you'd like
2. Double-click `start_heatmap.command` (macOS) or `start_heatmap.bat`
   (Windows)
   - macOS, first launch only: right-click → Open
   - Windows: unlike macOS, a "Security Warning" dialog saying the publisher
     could not be verified will keep appearing on **every** launch until you
     take action. Clicking **Run** each time works, but to make it stop for
     good, open PowerShell in the extracted folder and run:
     ```powershell
     Get-ChildItem -Recurse | Unblock-File
     ```
     (The Properties → Unblock checkbox some guides mention isn't always
     present or easy to find; the command above works regardless.)
3. Your browser opens `http://localhost:8765` automatically

The server binds to 127.0.0.1 only and is not reachable from other machines.

## Updating to a new version

Contest data (`data/`) is **not** part of the release zip, so it is not
automatically carried over when you install into a folder you haven't
used before — that starts you over with no data.

If you always use the [stable link](https://github.com/kondou/propmap/releases/latest/download/propmap-latest.zip)
above, this is mostly automatic: its filename never changes, so your OS's
default "Extract All" will consistently create (or reuse) the same
`propmap-latest` folder every time. Extracting there again and confirming
overwrite naturally keeps `data/`, since the zip doesn't contain it and
so doesn't touch it.

If you downloaded a version-specific zip instead, or moved/renamed your
install, extract the new zip directly into that same existing folder
(rather than a new one) and confirm overwrite — the same reasoning
applies either way: only the app files get overwritten, `data/` is left
alone.

Windows: overwritten files come from a freshly downloaded zip, so they
carry the internet-zone mark again even if you unblocked the previous
version — re-run the PowerShell command above after every update.

## Preparing data

Contest data is **not** bundled — it is too large. Get it once after
installing, from the "Data update" page linked from the map screen:

- **Download pre-built data (recommended):** fetch ready-made heatmap JSON
  published on the project's rolling release. Takes minutes
- **Build from public logs and RBN (advanced):** run the full pipeline
  yourself from public contest logs and RBN (Reverse Beacon Network) spot
  data covering the same contest period — useful for years not yet
  published as pre-built data. A full build downloads many gigabytes and
  can take hours

Both are also available from the command line (`fetch_prebuilt.py` /
`generate_all.sh`); see the user guide.

**Once data is prepared, PropMap needs no internet connection.** The map,
its terrain data, and the heatmap/replay all run from files on your own
machine; an internet connection is only needed to prepare or refresh data.

## Documentation

- [User guide (English)](PropMap_UserGuide_en.md)
- [ユーザーガイド（日本語）](PropMap_UserGuide.md)

## License

[MIT](LICENSE)
