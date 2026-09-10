# SoftwareUpdater CLI

Command-line tool that checks software versions online, marks packages as outdated, downloads the latest files into `downloads/`, and writes CSV/JSON reports.

**Company:** Infopercept  
**Type:** CLI only (no UI)

---

## What it does

1. Reads the app list from `config.json`
2. Looks up the latest version (GitHub, official sites, npm, PyPI, Maven, and more)
3. Prints **Old Version / Latest Version / Status** for each component
4. Downloads outdated packages into `downloads/` (when auto-download is supported)
5. Saves reports in `reports/`

---

## Requirements

- Windows, Linux, or macOS
- Python 3.10+ (tested on 3.14)
- Internet connection

### Python libraries

```bash
pip install -r requirements.txt
```

| Library | Version |
|---------|---------|
| requests | 2.34.2 |
| beautifulsoup4 | 4.15.0 |
| packaging | 26.3 |
| urllib3 | 2.7.0 |
| certifi | 2026.7.22 |
| charset-normalizer | 3.5.1 |
| idna | 3.19 |

---

## How to run

### Option 1 — Python script

```bash
cd path\to\SoftwareUpdater-Script\Soft
python updater.py
```

Or:

```bash
py -3.14 updater.py
```

### Option 2 — Windows EXE

1. Open the `dist` folder
2. Keep **both** files together:
   - `SoftwareUpdater.exe`
   - `config.json`
3. Double-click `SoftwareUpdater.exe`

To rebuild the EXE:

```bash
python build_exe.py
```

Output:

```text
dist\SoftwareUpdater.exe
dist\config.json
```

---

## Controls

| Key | Action |
|-----|--------|
| **CTRL+C** | Skip current component |
| **CTRL+Q** | Exit the script |

---

## Output folders

| Output | Location |
|--------|----------|
| Console | Old / Latest / Status for each app |
| Downloaded files | `downloads/` |
| CSV report | `reports/version_report_YYYYMMDD_HHMMSS.csv` |
| JSON report | `reports/version_report_YYYYMMDD_HHMMSS.json` |

### Status values

| Status | Meaning |
|--------|---------|
| `UP_TO_DATE` | Installed version matches latest |
| `OUTDATED` | Newer version found (may auto-download) |
| `Need To Download Manually` | Open the link in a browser |
| `ERROR` | Lookup or download failed |
| `Skip` | Skipped by user (CTRL+C) |

---

## How to add a component

Edit `config.json` and add an entry under `apps`.

### 1) GitHub release

Use when the project publishes releases on GitHub.

```json
{
  "id": "robocode-195",
  "name": "Robocode",
  "current_version": "1.8.5",
  "source": "github",
  "repo": "robo-code/robocode"
}
```

### 2) Official site (auto-download)

Use when the script already has an `official_key` handler.

```json
{
  "id": "tightvnc-2881",
  "name": "TightVNC",
  "current_version": "2.7.81.0",
  "source": "official",
  "official_key": "tightvnc"
}
```

Common `official_key` values:  
`postman`, `putty`, `pinginfoview`, `tightvnc`, `wget`, `wireshark`, `zoom`, `pdfcreator`, `gcloud`, `nuget`, `python`, `firefox`, `nodejs`, `jenkins`, `vlc`, `golang`, `eclipse`, and others defined in `updater.py`.

### 3) Manual download (link only)

Use for ISO pages, login portals, Docker Hub, Eclipse update sites, etc.

```json
{
  "id": "ubuntu-2404",
  "name": "Ubuntu",
  "current_version": "24.04",
  "source": "manual",
  "download_url": "https://ubuntu.com/download/desktop"
}
```

### 4) npm / PyPI / Maven

```json
{
  "id": "typescript-572",
  "name": "TypeScript",
  "current_version": "5.7.2",
  "source": "npm",
  "package": "typescript"
}
```

```json
{
  "id": "django-413",
  "name": "Django",
  "current_version": "4.1.3",
  "source": "pypi",
  "package": "Django"
}
```

```json
{
  "id": "testng-7110",
  "name": "TestNG",
  "current_version": "7.11.0",
  "source": "maven",
  "maven_path": "org/testng/testng"
}
```

### Which source to choose?

| Source | When to use | Extra field |
|--------|-------------|-------------|
| `github` | Releases on GitHub | `repo` |
| `official` | Vendor site + handler exists | `official_key` |
| `manual` | No reliable auto-download | `download_url` |
| `npm` | npm package | `package` |
| `pypi` | Python package | `package` |
| `maven` | Maven artifact | `maven_path` |

**Do not mix fields:**  
- `github` → use `repo` only  
- `official` → use `official_key` only  
- `manual` → use `download_url` only  

Set `current_version` to the version you currently track (old/installed baseline). The script finds the latest version online on every run.

---

## Notes

- Keep `config.json` next to `updater.py` or `EXENAME.exe`
- Folders `downloads/` and `reports/` are created automatically
- The EXE is standalone (other PCs do not need Python)
- If Windows SmartScreen blocks the EXE: **More info → Run anyway**
