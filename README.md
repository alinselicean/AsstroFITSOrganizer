# Astro FITS Organizer & Deduplicator

A fast, standalone desktop utility for indexing, filtering, and deduplicating astronomical **FITS (`.fit` / `.fits`)** archives across large storage drives. Built exclusively with the Python standard library (`tkinter`, `sqlite3`, `hashlib`) — zero external dependencies.

![Application Screenshot](screenshot.png)

## Key Features

* **Fast Asynchronous Scanning:** Uses `os.scandir` and direct 2880-byte FITS header block parsing (`OBJECT`, `IMAGETYP`, `EXPTIME`, `FOCALLEN`, `FILTER`, `DATE-OBS`) in a background thread with live progress and manual stop support.
* **Persistent SQLite Index:** Stores metadata and content fingerprints locally so subsequent searches and filters execute instantaneously without re-scanning drives.
* **Metadata-Aware Deduplication:** Computes two-stage `blake2b` hashes (64 KB edge/center sampling followed by full-file verification) exclusively among files sharing identical byte size and FITS metadata — preventing post-processed derivatives (GraXpert, StarNet, stacked masters) from being false-flagged as duplicates.
* **Flexible Duplicate Management:** Displays originals alongside duplicates, supports **Invert Tags** (for swapping original/duplicate priority on calibration libraries), **Select Duplicates Only**, **Move to Quarantine**, and **Permanent Deletion**.
* **Multi-Criteria Filtering & Folder Discovery:** Filter by frame type, target name, filter, exposure, focal length (`±5 mm` tolerance for focal reducers), date range, or wildcard patterns (`*` / `?`). Includes a dedicated **Is Folder** mode showing recursive total file counts per directory.
* **Audit Logging & Themes:** Records all scan, quarantine, and deletion events to a timestamped log file. Supports **System**, **Dark**, and **Light** UI themes.

## Download & Usage

### Windows Executable (No Python Required)
1. Go to the [**Releases**](../../releases) section of this repository and download **`AstroFITSOrganizer.exe`**.
2. Place it in a dedicated folder (e.g., `C:\Astro\AstroFITSOrganizer\`) and run it.
3. On first launch, it automatically generates `config.json`, `astro_archive.db`, and `astro_organizer.log` in its own directory.

### Running from Source
Requires Python 3.10+ (standard library only):
```bash
python astro_organizer.py
