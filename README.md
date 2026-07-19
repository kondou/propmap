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
  CQ WPX CW/SSB (2008–)
- Built-in data update page: check for newly published logs, see a disk-usage
  estimate, and import them from the browser

## Requirements

- Python 3.10+ — if none is found, the launcher offers to set one up
  automatically (via [uv](https://docs.astral.sh/uv/), with your consent;
  no Xcode / Visual Studio / Homebrew required, and nothing outside your
  user directory is touched)
- A modern browser (Safari, Chrome, Edge, ...)

## Quick start

1. Download the latest release zip (or clone this repository) and place it
   at `~/heatmap` (macOS/Linux/WSL2) or `%USERPROFILE%\heatmap` (Windows)
2. Double-click `start_heatmap.command` (macOS) or `start_heatmap.bat`
   (Windows)
   - macOS, first launch only: right-click → Open to pass Gatekeeper
3. Your browser opens `http://localhost:8765` automatically

The server binds to 127.0.0.1 only and is not reachable from other machines.

## Preparing data

Contest data is **not** bundled — it is too large. Get it once after
installing, from the "Data update" page linked from the map screen:

- **Download pre-built data (recommended):** fetch ready-made heatmap JSON
  published on the project's rolling release. Takes minutes
- **Build from public logs (advanced):** run the full pipeline yourself —
  useful for years not yet published as pre-built data. A full build
  downloads many gigabytes and can take hours

Both are also available from the command line (`fetch_prebuilt.py` /
`generate_all.sh`); see the user guide.

## Documentation

- [User guide (English)](PropMap_UserGuide_en.md)
- [ユーザーガイド（日本語）](PropMap_UserGuide.md)

## License

[MIT](LICENSE)
