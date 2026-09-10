# SoftwareUpdater CLI

Command-line tool that checks software versions online, marks packages as outdated, downloads the latest files into `downloads/`, and writes CSV/JSON reports.

This project is **CLI only** (no UI).

Checked on **18 Aug 2026**. Runtime: **Python 3.14.7**.

---

## What this tool does

1. Reads the app list from `config.json`
2. Looks up the latest version from GitHub, Maven, PyPI, NPM, Apache, Adoptium, and vendor sites
3. Prints **Old Version / Latest Version / Status** for each component
4. Downloads the latest file using the **original filename** (example: `log4j-1.2-api-2.26.1.jar`)
5. Saves a report in `reports/`

Java LTS (8, 11, 17, 21, 25, …) and Apache Tomcat (9, 10, 11, …) are discovered automatically. New majors appear on the next run.

---

## Requirements

- Windows, Linux, or macOS
- **Python 3.14.7** (3.10+ also works)
- Internet connection

### Python libraries (`requirements.txt`)

| Library | Version |
|---------|---------|
| requests | 2.34.2 |
| beautifulsoup4 | 4.15.0 |
| packaging | 26.3 |

---

## How to run

### Step 1 — Open the project folder

```bash
cd "path\to\SoftwareUpdater-CLI"
```

### Step 2 — (Optional) Create a virtual environment

**Windows (Python 3.14.7):**

```bash
py -3.14 -m venv venv
venv\Scripts\activate
```

**Linux / macOS:**

```bash
python3 -m venv venv
source venv/bin/activate
```

### Step 3 — Install libraries

```bash
py -3.14 -m pip install -r requirements.txt
```

### Step 4 — Run the updater

```bash
py -3.14 updater.py
```

If `py` is not available:

```bash
python updater.py
```

On this PC, `python` may still start Python 3.12. Use `py -3.14 updater.py` so the script runs on **3.14.7**.

### Step 5 — Check results

| Output | Location |
|--------|----------|
| Console | Old Version / Latest Version / Status for each app |
| Downloaded files | `downloads/` (original vendor filenames) |
| CSV report | `reports/version_report_YYYYMMDD_HHMMSS.csv` |
| JSON report | `reports/version_report_YYYYMMDD_HHMMSS.json` |

---

## EXE (Windows) — CMD closes immediately? Fix

Do **not** use only `pyinstaller --onefile updater.py`. That EXE looks for `config.json` in a temp folder, fails, and the window closes.

### Build the EXE

```bash
py -3.14 build_exe.py
```

This creates:

```text
dist\SoftwareUpdater.exe
dist\config.json
```

### Run the EXE

1. Open folder `dist`
2. Keep **both** files together: `SoftwareUpdater.exe` + `config.json`
3. Double-click `SoftwareUpdater.exe`

The window stays open. Files save in `dist\downloads\`. When finished it shows **Press Enter to close...**

To share with others, zip and send:

- `Infopercept-SoftwareUpdater.exe` (or `SoftwareUpdater.exe`)
- `config.json` (optional — EXE can create it automatically)

### Other PC — what is required?

The EXE is **standalone**. The other computer does **not** need Python, pip, or this project folder.

| Required | Not required |
|----------|----------------|
| Windows 10 / 11 **64-bit** | Python |
| Internet connection | pip / libraries |
| Double-click the EXE | `updater.py` / this source code |

If Windows SmartScreen or antivirus blocks it, choose **More info → Run anyway**.

Folders `downloads/` and `reports/` are created automatically next to the EXE.

## Example console output

```text
Company   : Infopercept
Config    : config.json
Downloads : downloads/
Reports   : reports/

============================================================
log4j-1.2-api

Old Version : 2.25.4
Latest Version : 2.26.1

Status    : OUTDATED

Download  : https://repo1.maven.org/maven2/.../log4j-1.2-api-2.26.1.jar
  File      : log4j-1.2-api-2.26.1.jar
Saved     : downloads/log4j-1.2-api-2.26.1.jar
```

---

## Edit the app list (`config.json`)

| Field | Required | Meaning | Example |
|-------|----------|---------|---------|
| `id` | Yes | Unique id, no spaces | `bootstrap-538` |
| `name` | Yes | Display name | `Bootstrap` |
| `current_version` | Yes | Real installed version (not `0.0.0`) | `2.25.4` |
| `source` | Yes | Where to look up latest | `github` |
| `repo` | GitHub only | `owner/repo` | `twbs/bootstrap` |
| `package` | NPM / PyPI | Package name | `jquery` |
| `maven_path` | Maven | Group/artifact path | `org/apache/logging/log4j/log4j-api` |
| `official_key` | Official | Vendor lookup key | `python` |

Example:

```json
{
  "id": "bootstrap-538",
  "name": "Bootstrap",
  "current_version": "5.0.0",
  "source": "github",
  "repo": "twbs/bootstrap"
}
```

Copy one object inside `"apps"`, change the fields, and keep a comma between objects.

---

## Source types

| `source` | Extra fields | Notes |
|----------|--------------|-------|
| `github` | `repo` | Latest GitHub release/tag. GitHub downloads wait/retry on HTTP 429 |
| `npm` | `package` | NPM registry tarball |
| `pypi` | `package` | PyPI source tarball |
| `maven` | `maven_path` | Maven Central JAR |
| `official` | `official_key` | Vendor file (Python, Firefox, JDK, …) |
| `java` | `current_version` of installed Java | Latest of every current Java LTS (Adoptium) |
| `tomcat` | `current_version` of installed Tomcat | Latest of every current Tomcat line (Apache CDN) |
| `nodejs` | `current_version` of installed Node.js | Latest of every currently supported Node.js LTS |
| `jquery` | — | jQuery from CDN |
| `jqueryui` | — | jQuery UI zip |
| `datatables` | — | DataTables JS |

---

## Folder structure

```text
SoftwareUpdater-CLI/
├── updater.py              Main script
├── config.json             App list
├── requirements.txt        Python libraries
├── package_project.py      Optional ZIP packager
├── README.md               This guide
├── Open Source list.xlsx   Original inventory
├── downloads/              Latest files (original names)
└── reports/                CSV / JSON version reports
```

---

## Troubleshooting

| Problem | What to do |
|---------|------------|
| `config.json not found!` | Run the command from the folder that contains `config.json` |
| `No module named 'requests'` | Install with `py -3.14 -m pip install -r requirements.txt` |
| `python` shows 3.12 | Use `py -3.14 updater.py` |
| HTTP 429 Too Many Requests | GitHub rate limit. The script waits and retries automatically |
| Download skipped (webpage) | That vendor has no direct file URL (login page / HTML) |
| Status is OUTDATED even if versions match | The script always downloads the latest file when a URL is found |
| Ctrl+C during a download | That file is skipped; the next component continues |

---

## Optional — create a project ZIP

```bash
py -3.14 package_project.py
```

Creates `SoftwareUpdater.zip` in the parent folder.

---

## Version report (18 Aug 2026)

`config.json` stores **real outdated versions** (example: log4j `2.25.4`). Do **not** use `0.0.0`. The next script run marks them OUTDATED and downloads latest.

Total config apps: **143**. Expanded LTS rows below: **151**.

**Java LTS**

| Name | Old Version | Latest Version |
|------|-------------|----------------|
| Java LTS 8 | 8.0.0 | 8.0.502 |
| Java LTS 11 | 11.0.0 | 11.0.32+9 |
| Java LTS 17 | 17.0.0 | 17.0.20+8 |
| Java LTS 21 | 21.0.0 | 21.0.12+8-LTS |
| Java LTS 25 | 25.0.0 | 25.0.4+7-LTS |

**Apache Tomcat**

| Name | Old Version | Latest Version |
|------|-------------|----------------|
| Apache Tomcat 9 | 9.0.0 | 9.0.121 |
| Apache Tomcat 10 | 10.0.0 | 10.1.57 |
| Apache Tomcat 11 | 11.0.0 | 11.0.25 |

**Node.js LTS**

| Name | Old Version | Latest Version |
|------|-------------|----------------|
| Node.js LTS 18 | 18.0.0 | 18.20.8 |
| Node.js LTS 22 | 22.0.0 | 22.23.2 |
| Node.js LTS 24 | 24.0.0 | 24.19.0 |

**Python**

| Name | Old Version | Latest Version |
|------|-------------|----------------|
| Python | 3.14.0 | 3.14.7 |

### All 151 components

| # | Name | Old Version | Latest Version | Status | Source | Download |
|---|---|---|---|---|---|---|
| 1 | log4j-api | 2.26.1 | 2.26.1 | UP_TO_DATE | maven | https://repo1.maven.org/maven2/org/apache/logging/log4j/log4j-api/2.26.1/log4j-api-2.26.1.jar |
| 2 | log4j-core | 2.25.4 | 2.26.1 | OUTDATED | maven | https://repo1.maven.org/maven2/org/apache/logging/log4j/log4j-core/2.26.1/log4j-core-2.26.1.jar |
| 3 | log4j-slf4j2-impl | 2.25.4 | 2.26.1 | OUTDATED | maven | https://repo1.maven.org/maven2/org/apache/logging/log4j/log4j-slf4j2-impl/2.26.1/log4j-slf4j2-impl-2.26.1.jar |
| 4 | log4j-1.2-api | 2.25.4 | 2.26.1 | OUTDATED | maven | https://repo1.maven.org/maven2/org/apache/logging/log4j/log4j-1.2-api/2.26.1/log4j-1.2-api-2.26.1.jar |
| 5 | Java LTS 8 | 8.0.0 | 8.0.502 | OUTDATED | official | https://github.com/adoptium/temurin8-binaries/releases/download/jdk8u502-b07/OpenJDK8U-jdk_x64_windows_hotspot_8u502b07.zip |
| 6 | Java LTS 11 | 11.0.0 | 11.0.32+9 | OUTDATED | official | https://github.com/adoptium/temurin11-binaries/releases/download/jdk-11.0.32%2B9/OpenJDK11U-jdk_x64_windows_hotspot_11.0.32_9.zip |
| 7 | Java LTS 17 | 17.0.0 | 17.0.20+8 | OUTDATED | official | https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.20%2B8/OpenJDK17U-jdk_x64_windows_hotspot_17.0.20_8.zip |
| 8 | Java LTS 21 | 21.0.0 | 21.0.12+8-LTS | OUTDATED | official | https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.12%2B8/OpenJDK21U-jdk_x64_windows_hotspot_21.0.12_8.zip |
| 9 | Java LTS 25 | 25.0.0 | 25.0.4+7-LTS | OUTDATED | official | https://github.com/adoptium/temurin25-binaries/releases/download/jdk-25.0.4%2B7/OpenJDK25U-jdk_x64_windows_hotspot_25.0.4_7.zip |
| 10 | Apache Tomcat 9 | 9.0.0 | 9.0.121 | OUTDATED | discovered | https://dlcdn.apache.org/tomcat/tomcat-9/v9.0.121/bin/apache-tomcat-9.0.121.zip |
| 11 | Apache Tomcat 10 | 10.0.0 | 10.1.57 | OUTDATED | discovered | https://dlcdn.apache.org/tomcat/tomcat-10/v10.1.57/bin/apache-tomcat-10.1.57.zip |
| 12 | Apache Tomcat 11 | 11.0.0 | 11.0.25 | OUTDATED | discovered | https://dlcdn.apache.org/tomcat/tomcat-11/v11.0.25/bin/apache-tomcat-11.0.25.zip |
| 13 | jQuery UI | 1.10.3 | 1.14.2 | OUTDATED | jqueryui | https://jqueryui.com/resources/download/jquery-ui-1.14.2.zip |
| 14 | Moment | 2.9.0 | 2.30.1 | OUTDATED | github | https://github.com/moment/moment/archive/refs/tags/2.30.1.zip |
| 15 | jQuery Mobile | 1.3.1 | 1.5.0 | OUTDATED | github | https://github.com/jquery-archive/jquery-mobile/archive/refs/tags/1.5.0-rc1.zip |
| 16 | Vue | 2.0.0 | 2.7.16 | OUTDATED | github | https://github.com/vuejs/vue/archive/refs/tags/v2.7.16.zip |
| 17 | Lodash | 4.17.19 | 4.18.1 | OUTDATED | github | https://github.com/lodash/lodash/archive/refs/tags/4.18.1.zip |
| 18 | DOMPurify | 2.3.0 | 3.4.13 | OUTDATED | github | https://github.com/cure53/DOMPurify/releases/download/3.4.13/3.4.13.tar.gz |
| 19 | 7-Zip | 25.01 | 26.02 | OUTDATED | github | https://github.com/ip7z/7zip/releases/download/26.02/7z2602-x64.exe |
| 20 | Allure reports | 2.36 | 2.45.0 | OUTDATED | github | https://github.com/allure-framework/allure2/releases/download/2.45.0/allure-2.45.0.tgz |
| 21 | Amazon Corretto | 11.0.27 | 11.0.32.9.1 | OUTDATED | official | https://corretto.aws/downloads/latest/amazon-corretto-11-x64-windows-jdk.msi |
| 22 | Angular JS | 1.8 | 1.8.3 | OUTDATED | github | https://github.com/angular/angular.js/archive/refs/tags/v1.8.3.zip |
| 23 | Ansible | 2.16.6 | 2.21.3 | OUTDATED | pypi | https://files.pythonhosted.org/packages/1c/11/cb53834d320c38d739e756e2458852d6e74a6c7018a9ab9f6d4ab5e5196e/ansible_core-2.21.3.tar.gz |
| 24 | Apache HTTP Server | 2.4.63 | 2.4.68 | OUTDATED | official | https://dlcdn.apache.org/httpd/httpd-2.4.68.tar.gz |
| 25 | Apache JMeter | 5.0.0 | 5.6.3 | OUTDATED | official | https://dlcdn.apache.org/jmeter/binaries/apache-jmeter-5.6.3.zip |
| 26 | Apache Maven | 3.9.4 | 3.9.16 | OUTDATED | official | https://dlcdn.apache.org/maven/maven-3/3.9.16/binaries/apache-maven-3.9.16-bin.zip |
| 27 | Appium | 3.3.0 | 3.6.0 | OUTDATED | npm | https://registry.npmjs.org/appium/-/appium-3.6.0.tgz |
| 28 | APScheduler | 3.9.1 | 3.11.3 | OUTDATED | pypi | https://files.pythonhosted.org/packages/8c/6b/eeff360196bb20b312c9e762a820fd1b2c6d809466c755ef57863478e454/apscheduler-3.11.3.tar.gz |
| 29 | AWS CLI | 2.34.29 | 2.36.24 | OUTDATED | github | https://github.com/aws/aws-cli/archive/refs/tags/2.36.24.zip |
| 30 | AWS CloudFormation CLI | 0.1.0 | 0.2.39 | OUTDATED | pypi | https://files.pythonhosted.org/packages/12/ed/36f14b63957e99d9f2cbb5ac5671eed9fb93569e57add60534d47fc630e4/cloudformation-cli-0.2.39.tar.gz |
| 31 | Bash | 5.0.0 | 5.3 | OUTDATED | official | https://ftp.gnu.org/gnu/bash/bash-5.3.tar.gz |
| 32 | beautifulsoup (Python library) | 4.10.0 | 4.15.0 | OUTDATED | pypi | https://files.pythonhosted.org/packages/43/65/318323f98dbee45d42dff61d8f047181bc6f2268a9068cfad035a46be5af/beautifulsoup4-4.15.0.tar.gz |
| 33 | Bootstrap | 5.0.0 | 5.3.8 | OUTDATED | github | https://github.com/twbs/bootstrap/releases/download/v5.3.8/bootstrap-5.3.8-dist.zip |
| 34 | Bytecode Viewer | 2.0.0 | 2.13.2 | OUTDATED | github | https://github.com/Konloch/bytecode-viewer/releases/download/v2.13.2/Bytecode-Viewer-2.13.2.jar |
| 35 | CCA | 1.2 | 3.5.5 | OUTDATED | github | https://github.com/ThePacielloGroup/CCAe/releases/download/v3.5.5/CCA-Portable-x64-3.5.5.exe |
| 36 | certifi (python library) | 2020.6.20 | 2026.7.22 | OUTDATED | pypi | https://files.pythonhosted.org/packages/a3/c2/24167ea9858356b47a87a50d39908bfdb72ceeefe0041586e704e5376b3a/certifi-2026.7.22.tar.gz |
| 37 | cfn-lint | 1.0.0 | 1.55.1 | OUTDATED | pypi | https://files.pythonhosted.org/packages/04/85/37d9d1dc05cb00ab870e9fd424b334c94a4703bae48533ecc56e2feb28a6/cfn_lint-1.55.1.tar.gz |
| 38 | chardet (python library) | 3.0.4 | 7.6.0 | OUTDATED | pypi | https://files.pythonhosted.org/packages/b1/51/cd61c567092a6cec796144510a68aff158ebfc1df82950a45bae65f28413/chardet-7.6.0.tar.gz |
| 39 | Cloud SQL Auth proxy | 2.1.2 | 2.25.2 | OUTDATED | official | https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.25.2/cloud-sql-proxy.x64.exe |
| 40 | Color Contrast Analyzer (CCA2) for Liferay | 3.0.0 | 3.5.5 | OUTDATED | github | https://github.com/ThePacielloGroup/CCAe/releases/download/v3.5.5/CCA-Portable-x64-3.5.5.exe |
| 41 | DataTables | 2.3.7 | 3.0.1 | OUTDATED | datatables | https://cdn.datatables.net/3.0.1/js/dataTables.min.js |
| 42 | DB Browser for SQLite | 3.13.0 | 3.13.1 | OUTDATED | github | https://github.com/sqlitebrowser/sqlitebrowser/releases/download/v3.13.1/DB.Browser.for.SQLite-v3.13.1-win64.msi |
| 43 | DBeaver | 24.2.5 | 26.1.5 | OUTDATED | github | https://github.com/dbeaver/dbeaver/releases/download/26.1.5/dbeaver-ce-26.1.5-linux-x86_64.tar.gz |
| 44 | Django | 4.1.3 | 6.1 | OUTDATED | pypi | https://files.pythonhosted.org/packages/e2/42/6cb20996733984c1f6661daeda3877990836c76c633c6c8879d39f7120eb/django-6.1.tar.gz |
| 45 | Django REST framework | 3.14.0 | 3.18.0 | OUTDATED | pypi | https://files.pythonhosted.org/packages/79/bc/de04e3d4dc65e8b926700956ee70d4f084f2005603d21122d4d0683006fd/djangorestframework-3.18.0.tar.gz |
| 46 | Docker | 27.3.1 | 29.7.2 | OUTDATED | github | https://github.com/moby/moby/archive/refs/tags/docker-v29.7.2.zip |
| 47 | Elasticsearch | 8.6.2 | 9.5.1 | OUTDATED | github | https://github.com/elastic/elasticsearch/archive/refs/tags/v9.5.1.zip |
| 48 | Erlang | 27.3.4.6 | 29.0.5 | OUTDATED | github | https://github.com/erlang/otp/releases/download/OTP-29.0.5/otp_win64_29.0.5.exe |
| 49 | Extent Report | 5.0.0 | 5.1.2 | OUTDATED | maven | https://repo1.maven.org/maven2/com/aventstack/extentreports/5.1.2/extentreports-5.1.2.jar |
| 50 | formulas (Python library) | 1.2.10 | 1.3.4 | OUTDATED | pypi | https://files.pythonhosted.org/packages/a1/03/87e2931f7e134cfffb6c6199003ce1a59feeea5160abd774dfad1c19e1ef/formulas-1.3.4.tar.gz |
| 51 | gcloud CLI | 423.0.0 | 580.0.0 | OUTDATED | official | https://dl.google.com/dl/cloudsdk/channels/rapid/GoogleCloudSDKInstaller.exe |
| 52 | Geany | 1.38.0 | 2.1.0 | OUTDATED | github | https://github.com/geany/geany/releases/download/2.1.0/geany-2.1.tar.gz |
| 53 | Glowroot | 0.14.4 | 0.14.7 | OUTDATED | github | https://github.com/glowroot/glowroot/releases/download/v0.14.7/glowroot-0.14.7-dist.zip |
| 54 | Google CLI Linux and Windows | 494.0.0 | 580.0.0 | OUTDATED | official | https://dl.google.com/dl/cloudsdk/channels/rapid/GoogleCloudSDKInstaller.exe |
| 55 | Gradle | 9.0.0 | 9.7.0 | OUTDATED | github | https://services.gradle.org/distributions/gradle-9.7.0-bin.zip |
| 56 | Grafana | 12.0 | 13.1.3 | OUTDATED | github | https://github.com/grafana/grafana/archive/refs/tags/v13.1.3.zip |
| 57 | HELM | 3.17.0 | 4.2.4 | OUTDATED | github | https://get.helm.sh/helm-v4.2.4-windows-amd64.zip |
| 58 | Hibernate | 6.1 | 7.2.24 | OUTDATED | github | https://github.com/hibernate/hibernate-orm/archive/refs/tags/7.2.24.zip |
| 59 | IAP Desktop | 2.45.1717 | 2.50.1825 | OUTDATED | github | https://github.com/GoogleCloudPlatform/iap-desktop/releases/download/2.50.1825/IapDesktopX64.msi |
| 60 | IntelliJ IDEA (Community Edition) | 2025.1 | 2025.3 | OUTDATED | official | https://download.jetbrains.com/idea/idea-2025.3.exe |
| 61 | Jenkins | 2.459 | 2.577 | OUTDATED | official | https://get.jenkins.io/war/2.577/jenkins.war |
| 62 | JQ | 1.8.1 | 1.8.2 | OUTDATED | github | https://github.com/jqlang/jq/releases/download/jq-1.8.2/jq-win64.exe |
| 63 | Jupyter Notebook | 7.4.4 | 7.6.2 | OUTDATED | pypi | https://files.pythonhosted.org/packages/31/d9/5c76de84e96e1cf8aae3fce930875e0615e14f3557bbcdb634aab52da9d3/notebook-7.6.2.tar.gz |
| 64 | Jython | 2.7.0 | 2.7.4 | OUTDATED | github | https://github.com/jython/jython/archive/refs/tags/v2.7.4.zip |
| 65 | Kibana | 8.6.2 | 9.5.1 | OUTDATED | github | https://github.com/elastic/kibana/archive/refs/tags/v9.5.1.zip |
| 66 | matplotlib | 3.5.3 | 3.11.1 | OUTDATED | pypi | https://files.pythonhosted.org/packages/49/64/f9a391af28f518b11ad45a8a712353c94a0aefce09d3703200e5c54b610a/matplotlib-3.11.1.tar.gz |
| 67 | Metricbeat | 8.6.2 | 9.5.1 | OUTDATED | github | https://github.com/elastic/beats/archive/refs/tags/v9.5.1.zip |
| 68 | Metro Bundler | 0.83.1 | 0.87.0 | OUTDATED | npm | https://registry.npmjs.org/metro/-/metro-0.87.0.tgz |
| 69 | Miniforge | 25.3.1 | 26.3.2 | OUTDATED | github | https://github.com/conda-forge/miniforge/releases/download/26.3.2-3/Miniforge3-26.3.2-3-Windows-x86_64.exe |
| 70 | Mozilla Firefox | 151.0.4 | 153.0.4 | OUTDATED | official | https://download.mozilla.org/?product=firefox-latest-ssl&os=win64&lang=en-US |
| 71 | nginx | 1.30.0 | 1.31.3 | OUTDATED | github | https://github.com/nginx/nginx/releases/download/release-1.31.3/nginx-1.31.3.tar.gz |
| 72 | Node.js LTS 18 | 18.0.0 | 18.20.8 | OUTDATED | official | https://nodejs.org/dist/v18.20.8/node-v18.20.8-x64.msi |
| 73 | Node.js LTS 22 | 22.0.0 | 22.23.2 | OUTDATED | official | https://nodejs.org/dist/v22.23.2/node-v22.23.2-x64.msi |
| 74 | Node.js LTS 24 | 24.0.0 | 24.19.0 | OUTDATED | official | https://nodejs.org/dist/v24.19.0/node-v24.19.0-x64.msi |
| 75 | Notepad++ | 8.8.0 | 8.9.7 | OUTDATED | github | https://github.com/notepad-plus-plus/notepad-plus-plus/releases/download/v8.9.7/npp.8.9.7.Installer.x64.exe |
| 76 | NuGet | 6.8.0 | latest | OUTDATED | official | https://dist.nuget.org/win-x86-commandline/latest/nuget.exe |
| 77 | NUnit | 3.13.3 | 4.6.1 | OUTDATED | github | https://github.com/nunit/nunit/releases/download/v4.6.1/NUnit.Framework-4.6.1.zip |
| 78 | OpenPyXL | 3.0.0 | 3.1.5 | OUTDATED | pypi | https://files.pythonhosted.org/packages/3d/f9/88d94a75de065ea32619465d2f77b29a0469500e99012523b91cc4141cd1/openpyxl-3.1.5.tar.gz |
| 79 | OpenRefine | 3.8.7 | 3.10.1 | OUTDATED | github | https://github.com/OpenRefine/OpenRefine/releases/download/3.10.1/openrefine-linux-3.10.1.tar.gz |
| 80 | OpenSSH | 9.7 | 9.9p2 | OUTDATED | official | https://cdn.openbsd.org/pub/OpenBSD/OpenSSH/portable/openssh-9.9p2.tar.gz |
| 81 | OpenSSL | 3.5.0 | 4.0.1 | OUTDATED | github | https://github.com/openssl/openssl/releases/download/openssl-4.0.1/openssl-4.0.1.tar.gz |
| 82 | OpenTelemetry | 0.1.0 | 0.158.0 | OUTDATED | github | https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/v0.158.0/otelcol-contrib_0.158.0_windows_amd64.tar.gz |
| 83 | Pandas | 2.3.1 | 3.0.5 | OUTDATED | pypi | https://files.pythonhosted.org/packages/be/4f/5f3422a2afec5ffc46308b79e53291365a93748b498ac2e58bead0197916/pandas-3.0.5.tar.gz |
| 84 | PingInfoView | 2.22 | latest | OUTDATED | official | https://www.nirsoft.net/utils/pinginfoview.zip |
| 85 | Pip | 22.3 | 26.2.1 | OUTDATED | pypi | https://files.pythonhosted.org/packages/ae/15/4500e320e6b101ec3b719ae85b697d9940b6cda672bc555bd6016fc60c6f/pip-26.2.1.tar.gz |
| 86 | Playwright (JAR dependencies) | 1.50.0 | 1.62.0 | OUTDATED | maven | https://repo1.maven.org/maven2/com/microsoft/playwright/playwright/1.62.0/playwright-1.62.0.jar |
| 87 | Podman Desktop | 1.20.0 | 1.29.1 | OUTDATED | github | https://github.com/podman-desktop/podman-desktop/releases/download/v1.29.1/podman-desktop-1.29.1-setup-x64.exe |
| 88 | Postman | 12.4.4 | latest | OUTDATED | official | https://dl.pstmn.io/download/latest/win64 |
| 89 | PuTTY | 0.84 | 0.85 | OUTDATED | official | https://the.earth.li/~sgtatham/putty/latest/w64/putty-64bit-0.85-installer.msi |
| 90 | Python | 3.14.0 | 3.14.7 | OUTDATED | official | https://www.python.org/ftp/python/3.14.7/python-3.14.7-amd64.exe |
| 91 | Python ML Auto (library) | 0.1.0 | 0.15.0 | OUTDATED | pypi | https://files.pythonhosted.org/packages/e5/0f/abac227b48edd7f4d9309492b35bdb7a4f70d4d643a60244cac83fd96029/auto-sklearn-0.15.0.tar.gz |
| 92 | RabbitMQ | 4.2.1 | 4.3.4 | OUTDATED | github | https://github.com/rabbitmq/rabbitmq-server/releases/download/v4.3.4/rabbitmq-server-4.3.4.exe |
| 93 | React Native | 0.84.1 | 0.87.0 | OUTDATED | npm | https://registry.npmjs.org/react-native/-/react-native-0.87.0.tgz |
| 94 | Redis | 8.0 | 8.10.1 | OUTDATED | github | https://github.com/redis/redis/releases/download/8.10.1/redis-full.tar.gz |
| 95 | RStudio | 4.2.1 | 2026.08.0-187 | OUTDATED | official | https://download1.rstudio.org/electron/windows/RStudio-2026.08.0-187.exe |
| 96 | RUST language | 1.88.0 | 1.97.1 | OUTDATED | github | https://static.rust-lang.org/dist/rust-1.97.1-x86_64-pc-windows-msvc.msi |
| 97 | schedule (Python Library) | 0.6.0 | 1.2.2 | OUTDATED | pypi | https://files.pythonhosted.org/packages/0c/91/b525790063015759f34447d4cf9d2ccb52cdee0f1dd6ff8764e863bcb74c/schedule-1.2.2.tar.gz |
| 98 | Selenium | 4.35.0 | 4.47.0 | OUTDATED | pypi | https://files.pythonhosted.org/packages/c3/a2/213190a606bc036b4db1b8129f399964988872a555b50dfbfddf612d333c/selenium-4.47.0.tar.gz |
| 99 | SikuliX API (JAR dependencies) | 2.0.0 | 2.0.5 | OUTDATED | github | https://github.com/oculix-org/SikuliX1/releases/download/v2.0.5/sikulixapi-2.0.5-linux.jar |
| 100 | simplecaptcha | 1.2.1 | 1.2.2 | OUTDATED | maven | https://repo1.maven.org/maven2/cn/apiclub/tool/simplecaptcha/1.2.2/simplecaptcha-1.2.2.jar |
| 101 | SOAP UI | 5.7.0 | 5.10.0 | OUTDATED | github | https://github.com/SmartBear/soapui/archive/refs/tags/v5.10.0.zip |
| 102 | SonarQube | 9.0.0 | 26.8.0.126808 | OUTDATED | github | https://github.com/SonarSource/sonarqube/archive/refs/tags/26.8.0.126808.zip |
| 103 | soupsieve (Python Library) | 2.1 | 2.9.2 | OUTDATED | pypi | https://files.pythonhosted.org/packages/69/99/a6ca3beb3ccacb41fb3321d8a60e5566f9e6467601ef8eba6a17e1b89778/soupsieve-2.9.2.tar.gz |
| 104 | Spring Tool Suite | 5.0.0 | 5.3.0 | OUTDATED | github | https://github.com/spring-projects/spring-tools/releases/download/5.3.0.RELEASE/vscode-spring-boot-2.3.0-RC2.vsix |
| 105 | SQLite Browser | 3.12.2 | 3.13.1 | OUTDATED | github | https://github.com/sqlitebrowser/sqlitebrowser/releases/download/v3.13.1/DB.Browser.for.SQLite-v3.13.1-win64.msi |
| 106 | Terraform For Linux | 1.9.6 | 1.15.8 | OUTDATED | github | https://releases.hashicorp.com/terraform/1.15.8/terraform_1.15.8_windows_amd64.zip |
| 107 | TestNG | 7.11.0 | 7.12.0 | OUTDATED | maven | https://repo1.maven.org/maven2/org/testng/testng/7.12.0/testng-7.12.0.jar |
| 108 | Trivy | 0.70.0 | 0.74.0 | OUTDATED | github | https://github.com/aquasecurity/trivy/releases/download/v0.74.0/trivy_0.74.0_Linux-32bit.tar.gz |
| 109 | TypeScript | 5.7.2 | 7.0.2 | OUTDATED | npm | https://registry.npmjs.org/typescript/-/typescript-7.0.2.tgz |
| 110 | tzlocal | 2.1 | 5.4.4 | OUTDATED | pypi | https://files.pythonhosted.org/packages/81/5b/879b2f932adfa7a053c360d50bc896c977fa6426109185f7c12ebdd0cb9d/tzlocal-5.4.4.tar.gz |
| 111 | urllib3 (python library) | 1.26.9 | 2.7.0 | OUTDATED | pypi | https://files.pythonhosted.org/packages/53/0c/06f8b233b8fd13b9e5ee11424ef85419ba0d8ba0b3138bf360be2ff56953/urllib3-2.7.0.tar.gz |
| 112 | VLC Media Player | 2.1.3 | 3.0.23 | OUTDATED | official | https://get.videolan.org/vlc/3.0.23/win64/vlc-3.0.23-win64.exe |
| 113 | WebSphere Liberty | 25.0.0.6 | 26.0.0.8 | OUTDATED | github | https://github.com/OpenLiberty/open-liberty/archive/refs/tags/gm-26.0.0.8.zip |
| 114 | Wget | 1.20.0 | 1.25.0 | OUTDATED | official | https://ftp.gnu.org/gnu/wget/wget-1.25.0.tar.gz |
| 115 | WildFly | 28.0.1 | 41.0.0 | OUTDATED | github | https://github.com/wildfly/wildfly/releases/download/41.0.0.Final/wildfly-41.0.0.Final-src.tar.gz |
| 116 | Windows Subsystem for Linux (WSL) | 2.0.0 | 2.7.11 | OUTDATED | github | https://github.com/microsoft/WSL/releases/download/2.7.11/wsl.2.7.11.0.x64.msi |
| 117 | WinSCP | 5.21 | 6.5 | OUTDATED | official | https://winscp.net/download/WinSCP-6.5-Setup.exe |
| 118 | Wireshark | 4.4.0 | 4.6.8 | OUTDATED | official | https://www.wireshark.org/download/win64/Wireshark-4.6.8-x64.exe |
| 119 | Xlsxwriter | 3.2.5 | 3.2.9 | OUTDATED | pypi | https://files.pythonhosted.org/packages/46/2c/c06ef49dc36e7954e55b802a8b231770d286a9758b3d936bd1e04ce5ba88/xlsxwriter-3.2.9.tar.gz |
| 120 | Xunit (.NET Foundation) | 3.2.2 | 4.0.0 | OUTDATED | github | https://github.com/xunit/xunit/archive/refs/tags/v3-4.0.0.zip |
| 121 | Zoom Workplace Basic | 5.9.6.3701 | latest | OUTDATED | official | https://zoom.us/client/latest/ZoomInstallerFull.exe |
| 122 | Android Studio Jellyfish | 2023.3.1 |  | OUTDATED | official |  |
| 123 | AutoIT | 3.3.14.2 |  | OUTDATED | official |  |
| 124 | AWS Migration evaluator tool (TSOCollector) | 1.50.23 |  | OUTDATED | manual |  |
| 125 | Beetl-sql | 3.0.6 |  | OUTDATED | maven |  |
| 126 | Cisco Packet Tracer | 8.2.2 |  | OUTDATED | manual |  |
| 127 | DotNetStack (MS) | 8.0.403 |  | OUTDATED | official |  |
| 128 | Dynatrace Chromium | 113 |  | OUTDATED | manual |  |
| 129 | Echo Mirage | 3.1 |  | OUTDATED | manual |  |
| 130 | Eclipse | 4.4.18 |  | OUTDATED | official |  |
| 131 | EPEL Package | 8 |  | OUTDATED | manual |  |
| 132 | ES Docker Image | 8.17.6 |  | OUTDATED | manual |  |
| 133 | Fiddler | 5.0.20211 |  | OUTDATED | manual |  |
| 134 | Golang | 1.23.0 |  | OUTDATED | official |  |
| 135 | Kali Linux OS - ISO scan only | 2025.3 |  | OUTDATED | manual |  |
| 136 | Liferay Docker Image | 2025.Q1.2 |  | OUTDATED | manual |  |
| 137 | Liferay Workspace with Dev Studio | 3.10.2 |  | OUTDATED | manual |  |
| 138 | Metasploit | 6.6.2 |  | OUTDATED | github |  |
| 139 | Nuitka | 2.1.23 |  | OUTDATED | pypi |  |
| 140 | PDF Scanner | 4.1.2 |  | OUTDATED | manual |  |
| 141 | PDF-XChange | 13 |  | OUTDATED | manual |  |
| 142 | PostgreSQL | 15.0 |  | OUTDATED | official |  |
| 143 | Python requests library | 2.31.0 |  | OUTDATED | pypi |  |
| 144 | Robocode | 1.9.5 |  | OUTDATED | github |  |
| 145 | TightVNC | 2.8.81 |  | OUTDATED | official |  |
| 146 | Ubuntu | 24.04 |  | OUTDATED | manual |  |
| 147 | .NET Core | 8.0.26 |  | OUTDATED | official |  |
| 148 | .NET Framework | 4.6.1 |  | OUTDATED | manual |  |
| 149 | Java Runtime Environment (JRE) | 21.0.6+7 | 21.0.12+8-LTS | OUTDATED | official | https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.12%2B8/OpenJDK21U-jdk_x64_windows_hotspot_21.0.12_8.zip |
| 150 | JDK (Java Development kit) | 25 | 25.0.4+7-LTS | OUTDATED | official | https://github.com/adoptium/temurin25-binaries/releases/download/jdk-25.0.4%2B7/OpenJDK25U-jdk_x64_windows_hotspot_25.0.4_7.zip |
| 151 | OpenJDK | 21 | 21.0.12+8-LTS | OUTDATED | official | https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.12%2B8/OpenJDK21U-jdk_x64_windows_hotspot_21.0.12_8.zip |

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).

Third-party software downloaded by this tool remains under each vendor's own license. That does not apply to the updater itself.
