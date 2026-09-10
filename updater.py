import json
import os
import re
import csv
import copy
import hashlib
import shutil
import sys
sys.dont_write_bytecode = True
import time
from datetime import datetime
from urllib.parse import unquote, urlparse
import requests
from requests.exceptions import ConnectionError, HTTPError, Timeout, ReadTimeout
from bs4 import BeautifulSoup
from packaging.version import Version, InvalidVersion

GITHUB_API_RELEASE = "https://api.github.com/repos/{repo}/releases/latest"
GITHUB_API_TAGS = "https://api.github.com/repos/{repo}/tags"
NPM_REGISTRY_API = "https://registry.npmjs.org/{package}"
OSV_QUERY_URL = "https://api.osv.dev/v1/query"
COMPANY_NAME = "Infopercept"

HEADERS = {
    "User-Agent": "Infopercept-SoftwareUpdater/1.0",
    "Accept": "application/json, text/html, */*"
}

WEB_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
}

FILE_EXTS = (".zip", ".tgz", ".tar.gz", ".gz", ".exe", ".msi", ".jar", ".war", ".js", ".7z")

NO_INTERNET_MSG = "No internet connection. Please check your network and try again."
GITHUB_HOSTS = (
    "github.com",
    "codeload.github.com",
    "api.github.com",
    "objects.githubusercontent.com",
    "raw.githubusercontent.com",
)
GITHUB_GAP_SEC = 1.5
_last_github_request = 0.0
_github_api_limited = False
_github_limit_notice_shown = False


def is_github_url(url):
    host = (urlparse(url or "").netloc or "").lower()
    return any(host == h or host.endswith("." + h) for h in GITHUB_HOSTS)


def wait_github_gap():
    """Quiet gap between GitHub calls (do not print — this is not a rate-limit error)."""
    global _last_github_request
    now = time.time()
    wait = GITHUB_GAP_SEC - (now - _last_github_request)
    if wait > 0:
        time.sleep(wait)
    _last_github_request = time.time()


def mark_github_api_limited():
    """Stop using api.github.com for the rest of this run; HTML pages still work."""
    global _github_api_limited, _github_limit_notice_shown
    _github_api_limited = True
    if not _github_limit_notice_shown:
        print("  GitHub API hourly limit reached. Switching to github.com pages.")
        _github_limit_notice_shown = True


def github_api_exhausted(response):
    if response is None:
        return False
    if response.status_code in (403, 429):
        return True
    remaining = response.headers.get("X-RateLimit-Remaining")
    return remaining == "0"


def retry_after_seconds(response, attempt):
    if response is not None:
        raw = response.headers.get("Retry-After")
        if raw:
            try:
                return max(int(raw), 5)
            except ValueError:
                pass
    return min(20 * (2 ** attempt), 180)

def is_network_error(exc):
    """Return True when the exception is caused by offline / DNS / connection failure."""
    if isinstance(exc, (ConnectionError, Timeout)):
        return True
    msg = str(exc).lower()
    markers = (
        "failed to resolve",
        "getaddrinfo",
        "nameresolution",
        "max retries exceeded",
        "connection aborted",
        "connection refused",
        "network is unreachable",
        "no route to host",
        "temporary failure in name resolution",
        "nodename nor servname",
        "name or service not known",
        "timed out",
        "timeout",
    )
    return any(m in msg for m in markers)

def format_lookup_error(exc, prefix="Lookup error"):
    """Convert exceptions into a clear user-facing error message."""
    if is_network_error(exc):
        return NO_INTERNET_MSG
    return f"{prefix}: {exc}"

def clean_version_str(ver_str):
    """Normalize version string for packaging.version comparison."""
    if not ver_str:
        return None
    cleaned = re.sub(r'^[vV@\.\s]+', '', str(ver_str).strip())
    match = re.search(r'(\d+(?:\.\d+)+)', cleaned)
    return match.group(1) if match else cleaned

def parse_version(ver_str):
    """Safely parse version string using packaging.version."""
    c_ver = clean_version_str(ver_str)
    if not c_ver:
        return None
    try:
        return Version(c_ver)
    except InvalidVersion:
        try:
            return Version(re.sub(r'[^0-9\.]', '', c_ver))
        except Exception:
            return None

def osv_package_for_app(app_config):
    """Map a config entry to an OSV ecosystem + package name for CVE lookup."""
    source = (app_config.get("source") or "").lower()
    if source == "maven":
        parts = [p for p in (app_config.get("maven_path") or "").strip("/").split("/") if p]
        if len(parts) >= 2:
            return "Maven", ".".join(parts[:-1]) + ":" + parts[-1]
    if source == "pypi" and app_config.get("package"):
        return "PyPI", app_config.get("package")
    if source == "npm" and app_config.get("package"):
        return "npm", app_config.get("package")
    if source == "jquery":
        return "npm", "jquery"
    if source == "jqueryui":
        return "npm", "jquery-ui"
    if source == "datatables":
        return "npm", "datatables.net"
    return None, None


def osv_severity(vuln):
    """Best-effort severity from OSV (CRITICAL/HIGH/MEDIUM/LOW)."""
    scores = []
    for item in vuln.get("severity") or []:
        try:
            scores.append(float(item.get("score") or 0))
        except (TypeError, ValueError):
            pass
    for aff in vuln.get("affected") or []:
        sev = (aff.get("database_specific") or {}).get("severity")
        if sev:
            return str(sev).upper()
    if not scores:
        return "UNKNOWN"
    top = max(scores)
    if top >= 9:
        return "CRITICAL"
    if top >= 7:
        return "HIGH"
    if top >= 4:
        return "MEDIUM"
    return "LOW"


def lookup_osv_vulns(ecosystem, package_name, version):
    """Query OSV for known CVEs of one package version. Returns [] if none/unmapped."""
    if not ecosystem or not package_name or not version or version in ("N/A", "latest"):
        return []
    ver = clean_version_str(version) or str(version).strip()
    if not ver or not re.search(r"\d", ver):
        return []
    try:
        r = requests.post(
            OSV_QUERY_URL,
            json={"version": ver, "package": {"name": package_name, "ecosystem": ecosystem}},
            headers=HEADERS,
            timeout=12,
        )
        if r.status_code != 200:
            return []
        found = []
        for vuln in r.json().get("vulns") or []:
            found.append({
                "id": vuln.get("id") or "",
                "severity": osv_severity(vuln),
                "summary": (vuln.get("summary") or "")[:180],
            })
        return found
    except Exception:
        return []


def attach_security_check(app_config, result):
    """Strong CVE check on installed version (and whether latest is still vulnerable)."""
    eco, pkg = osv_package_for_app(app_config)
    installed = result.get("current_version") or ""
    latest = result.get("latest_version") or ""
    if latest == "N/A":
        latest = ""
    vulns = lookup_osv_vulns(eco, pkg, installed) if installed else []
    vulns_latest = lookup_osv_vulns(eco, pkg, latest) if latest and latest != installed else []
    result["vulnerabilities"] = vulns
    result["vuln_count"] = len(vulns)
    result["cve_ids"] = ", ".join(v["id"] for v in vulns if v.get("id"))
    result["latest_still_vulnerable"] = len(vulns_latest)
    if not eco:
        result["security_status"] = "NOT_SCANNED"
        return result
    if vulns:
        order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "UNKNOWN": 0}
        worst = "UNKNOWN"
        for v in vulns:
            if order.get(v.get("severity"), 0) > order.get(worst, 0):
                worst = v.get("severity") or "UNKNOWN"
        result["security_status"] = f"VULNERABLE ({worst})"
    else:
        result["security_status"] = "CLEAN"
    return result


def version_update_status(current_ver, latest_ver):
    """OUTDATED unless installed exactly matches latest."""
    if not latest_ver:
        return "ERROR"
    if not current_ver:
        return "OUTDATED"
    c_parsed = parse_version(current_ver)
    l_parsed = parse_version(latest_ver)
    if c_parsed and l_parsed:
        if c_parsed < l_parsed:
            return "OUTDATED"
        if c_parsed == l_parsed:
            return "UP_TO_DATE"
        return "OUTDATED"
    if str(current_ver).strip() == str(latest_ver).strip():
        return "UP_TO_DATE"
    return "OUTDATED"

def pick_github_asset(assets):
    """Prefer a Windows/x64 binary over ARM/macOS/signature files."""
    if not assets:
        return None
    prefer = ("x64", "win64", "windows-amd64", "windows_amd64", "win32.x86_64", "-win.")
    avoid = ("arm64", "aarch64", "darwin", "macos", ".asc", ".sha", "freebsd", "aix")
    files = []
    for a in assets:
        name = (a.get("name") or "").lower()
        url = a.get("browser_download_url") or ""
        if any(name.endswith(e) for e in FILE_EXTS):
            files.append((name, url))
    for name, url in files:
        if any(p in name for p in prefer) and not any(x in name for x in avoid):
            return url
    for name, url in files:
        if not any(x in name for x in avoid):
            return url
    if files:
        return files[0][1]
    return assets[0].get("browser_download_url")


def apply_download_template(app_config, ver, fallback_url):
    """Replace {version} / {version_nodot} in an optional download_url_template."""
    tmpl = app_config.get("download_url_template")
    if not tmpl or not ver:
        return fallback_url
    nodot = re.sub(r"[^0-9]", "", str(ver))
    try:
        return tmpl.format(version=ver, version_nodot=nodot)
    except Exception:
        return fallback_url


def latest_github(repo):
    """Fetch latest version and download URL from GitHub repository with rate-limit resilient web fallback."""
    if not repo:
        return None, None, "GitHub repository name missing."
        
    repo = repo.strip().strip("/")
    api_error = None

    # 1. GitHub API (60 unauthenticated calls/hour). After the limit, skip API for this run.
    if not _github_api_limited:
        url = GITHUB_API_RELEASE.format(repo=repo)
        try:
            wait_github_gap()
            r = requests.get(url, headers=HEADERS, timeout=10)
            if github_api_exhausted(r):
                mark_github_api_limited()
            elif r.status_code == 200:
                data = r.json()
                raw_tag = data.get("tag_name", "")
                ver = clean_version_str(raw_tag)
                assets = data.get("assets", [])
                download_url = pick_github_asset(assets)
                if not download_url:
                    download_url = f"https://github.com/{repo}/archive/refs/tags/{raw_tag}.zip" if raw_tag else f"https://github.com/{repo}/archive/refs/heads/main.zip"
                return ver, download_url, None
            else:
                tags_url = GITHUB_API_TAGS.format(repo=repo)
                wait_github_gap()
                r_tags = requests.get(tags_url, headers=HEADERS, timeout=10)
                if github_api_exhausted(r_tags):
                    mark_github_api_limited()
                elif r_tags.status_code == 200:
                    tags = r_tags.json()
                    if tags and isinstance(tags, list) and len(tags) > 0:
                        raw_tag = tags[0]["name"]
                        ver = clean_version_str(raw_tag)
                        download_url = f"https://github.com/{repo}/archive/refs/tags/{raw_tag}.zip"
                        return ver, download_url, None
        except Exception as e:
            if is_network_error(e):
                return None, None, NO_INTERNET_MSG
            api_error = e

    # 2. Web Scraping Fallback (bypasses GitHub API Rate Limit)
    try:
        web_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }
        rel_url = f"https://github.com/{repo}/releases/latest"
        wait_github_gap()
        r_rel = requests.get(rel_url, headers=web_headers, allow_redirects=True, timeout=10)
        if r_rel.status_code == 200 and "/releases/tag/" in r_rel.url:
            raw_tag = r_rel.url.split("/")[-1]
            ver = clean_version_str(raw_tag)
            dl_url = f"https://github.com/{repo}/archive/refs/tags/{raw_tag}.zip"
            return ver, dl_url, None

        tags_web_url = f"https://github.com/{repo}/tags"
        wait_github_gap()
        r_web_tags = requests.get(tags_web_url, headers=web_headers, timeout=10)
        if r_web_tags.status_code == 200:
            soup = BeautifulSoup(r_web_tags.text, "html.parser")
            for link in soup.find_all("a", href=True):
                href = link["href"]
                if f"/{repo}/releases/tag/" in href or f"/{repo}/archive/refs/tags/" in href:
                    raw_tag = href.split("/")[-1].replace(".zip", "").replace(".tar.gz", "")
                    ver = clean_version_str(raw_tag)
                    dl_url = f"https://github.com/{repo}/archive/refs/tags/{raw_tag}.zip"
                    return ver, dl_url, None
    except Exception as scrape_err:
        return None, None, format_lookup_error(scrape_err, "GitHub lookup error")

    if api_error:
        return None, None, format_lookup_error(api_error, "GitHub lookup error")
    return None, None, f"Could not locate releases or tags for repository '{repo}'"

def latest_npm(package_name):
    """Fetch latest version and download URL from NPM Registry."""
    url = NPM_REGISTRY_API.format(package=package_name)
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        if r.status_code == 200:
            data = r.json()
            latest_ver = data.get("dist-tags", {}).get("latest")
            versions = data.get("versions", {})
            tarball_url = None
            if latest_ver and latest_ver in versions:
                tarball_url = versions[latest_ver].get("dist", {}).get("tarball")
            if not tarball_url and latest_ver:
                tarball_url = f"https://registry.npmjs.org/{package_name}/-/{package_name}-{latest_ver}.tgz"
            return latest_ver, tarball_url, None
        return None, None, f"NPM Registry HTTP {r.status_code}"
    except Exception as e:
        return None, None, format_lookup_error(e, "NPM connection error")

def latest_jquery():
    """Fetch latest jQuery release version and download URL."""
    ver, tarball, err = latest_npm("jquery")
    if ver:
        dl_url = f"https://code.jquery.com/jquery-{ver}.min.js"
        return ver, dl_url, None
    return None, None, err

def latest_jqueryui():
    """Fetch latest jQuery UI release version and download URL."""
    ver, tarball, err = latest_npm("jquery-ui")
    if ver:
        dl_url = f"https://jqueryui.com/resources/download/jquery-ui-{ver}.zip"
        return ver, dl_url, None
    return None, None, err

def latest_datatables():
    """Fetch latest DataTables release version and download URL."""
    ver, tarball, err = latest_npm("datatables.net")
    if ver:
        dl_url = f"https://cdn.datatables.net/{ver}/js/dataTables.min.js"
        return ver, dl_url, None
    return None, None, err

def latest_pypi(package_name):
    """Fetch latest version and sdist URL from PyPI."""
    if not package_name:
        return None, None, "PyPI package name missing."
    url = f"https://pypi.org/pypi/{package_name}/json"
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        if r.status_code != 200:
            return None, None, f"PyPI HTTP {r.status_code}"
        data = r.json()
        ver = data.get("info", {}).get("version")
        urls = data.get("urls") or []
        dl = next((u.get("url") for u in urls if u.get("packagetype") == "sdist"), None)
        if not dl and urls:
            dl = urls[0].get("url")
        return ver, dl, None
    except Exception as e:
        return None, None, format_lookup_error(e, "PyPI lookup error")

def latest_maven(maven_path):
    """Fetch latest stable version and jar URL from Maven Central."""
    if not maven_path:
        return None, None, "Maven path missing."
    maven_path = maven_path.strip("/")
    url = f"https://repo1.maven.org/maven2/{maven_path}/maven-metadata.xml"
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        if r.status_code != 200:
            return None, None, f"Maven HTTP {r.status_code}"
        versions = re.findall(r"<version>([^<]+)</version>", r.text)
        stable = [
            v for v in versions
            if not re.search(r"(?i)(alpha|beta|rc|snapshot|milestone|m\d+$)", v)
        ]
        ver = stable[-1] if stable else None
        if not ver:
            match = re.search(r"<release>([^<]+)</release>", r.text)
            ver = match.group(1) if match else None
        artifact = maven_path.split("/")[-1]
        dl = f"https://repo1.maven.org/maven2/{maven_path}/{ver}/{artifact}-{ver}.jar" if ver else None
        return ver, dl, None
    except Exception as e:
        return None, None, format_lookup_error(e, "Maven lookup error")

def latest_official(key):
    """Known public file downloads (Windows x64 preferred)."""
    if not key:
        return None, None, "Official source key missing."
    try:
        return _official_lookup(key)
    except Exception as e:
        return None, None, format_lookup_error(e, "Official lookup error")

def discover_tomcat_lines():
    """Find every current Tomcat major line on Apache CDN (9, 10, 11, 12, ...)."""
    index = "https://dlcdn.apache.org/tomcat/"
    try:
        r = requests.get(index, headers=WEB_HEADERS, timeout=15)
        if r.status_code != 200:
            return [], f"Tomcat index HTTP {r.status_code}"
        majors = sorted({int(m) for m in re.findall(r'href="tomcat-(\d+)/"', r.text)})
        lines = []
        for major in majors:
            folder = f"tomcat-{major}"
            listing = requests.get(f"{index}{folder}/", headers=WEB_HEADERS, timeout=15)
            if listing.status_code != 200:
                continue
            vers = re.findall(r'href="v(\d+\.\d+\.\d+)/"', listing.text or "")
            if not vers:
                continue
            ver = sorted(set(vers), key=lambda v: tuple(int(x) for x in v.split(".")))[-1]
            url = f"{index}{folder}/v{ver}/bin/apache-tomcat-{ver}.zip"
            lines.append({"major": major, "version": ver, "url": url})
        if not lines:
            return [], "No Tomcat versions found on Apache CDN"
        return lines, None
    except Exception as e:
        return [], format_lookup_error(e, "Tomcat discovery error")

def discover_java_lts_majors():
    """Find every current Java LTS major from Adoptium (8, 11, 17, 21, 25, ...)."""
    try:
        r = requests.get("https://api.adoptium.net/v3/info/available_releases", headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return [], f"Adoptium HTTP {r.status_code}"
        majors = r.json().get("available_lts_releases") or []
        majors = [int(m) for m in majors]
        if not majors:
            return [], "No Java LTS releases returned by Adoptium"
        return majors, None
    except Exception as e:
        return [], format_lookup_error(e, "Java LTS discovery error")

def _installed_major(ver_str):
    m = re.match(r"(\d+)", str(ver_str or "").strip())
    return int(m.group(1)) if m else None


def parse_version_list(value):
    """Split current_version into version strings (string, comma-list, or JSON array)."""
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple)):
        return [str(v).strip().strip('"').strip("'") for v in value if str(v).strip()]
    text = str(value).strip()
    if not text:
        return []
    return [p.strip().strip('"').strip("'") for p in text.split(",") if p.strip()]


def format_lts_versions(value):
    """Unique versions sorted by major: ['8.0.502', '11.0.32', '17.0.20', ...]."""
    by_major = {}
    for ver in parse_version_list(value):
        major = _installed_major(ver)
        if major is None:
            continue
        by_major[major] = ver
    return [by_major[m] for m in sorted(by_major)]


def version_for_major(value, major):
    for ver in parse_version_list(value):
        if _installed_major(ver) == major:
            return ver
    return None


def version_display(value):
    parts = parse_version_list(value)
    return ", ".join(parts) if parts else ""


def _old_line_version(major, installed="", inst_major=None):
    """Installed version for this LTS line, or major.0.0 if that line is new."""
    found = version_for_major(installed, major)
    if found:
        return found
    if inst_major == major and installed and not isinstance(installed, (list, tuple)) and "," not in str(installed):
        return str(installed)
    return f"{major}.0.0"


def lts_family(app):
    """
    Return the LTS family name when this component should download
    every current LTS line. Otherwise return None (latest-only).
    """
    source = (app.get("source") or "").lower()
    key = (app.get("official_key") or "").lower()
    if source in {"java", "java-lts-all"}:
        return "java"
    if source in {"tomcat", "tomcat-lts-all"}:
        return "tomcat"
    if source in {"nodejs", "node"} or key == "nodejs":
        return "nodejs"
    return None


def discover_supported_nodejs_lts_majors():
    """Majors whose Node.js LTS support has not ended yet (from nodejs/Release)."""
    try:
        r = requests.get(
            "https://raw.githubusercontent.com/nodejs/Release/main/schedule.json",
            headers=HEADERS,
            timeout=15,
        )
        if r.status_code != 200:
            return None
        today = datetime.now().date()
        majors = set()
        for name, info in (r.json() or {}).items():
            if not isinstance(info, dict) or not info.get("lts"):
                continue
            end = info.get("end")
            if not end:
                continue
            try:
                end_date = datetime.strptime(str(end)[:10], "%Y-%m-%d").date()
            except ValueError:
                continue
            if end_date < today:
                continue
            major = _installed_major(str(name).lstrip("v"))
            if major is not None:
                majors.add(major)
        return majors
    except Exception:
        return None


def discover_nodejs_lts_lines():
    """Latest Windows x64 MSI for every currently supported Node.js LTS major."""
    try:
        r = requests.get("https://nodejs.org/dist/index.json", headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return [], f"Node.js index HTTP {r.status_code}"
        supported = discover_supported_nodejs_lts_majors()
        by_major = {}
        for item in r.json() or []:
            if not item.get("lts"):
                continue
            ver = (item.get("version") or "").lstrip("v")
            major = _installed_major(ver)
            if major is None or major in by_major:
                continue
            if supported is not None and major not in supported:
                continue
            by_major[major] = ver
        lines = [
            {
                "major": major,
                "version": by_major[major],
                "url": f"https://nodejs.org/dist/v{by_major[major]}/node-v{by_major[major]}-x64.msi",
            }
            for major in sorted(by_major)
        ]
        if not lines:
            return [], "No Node.js LTS releases found"
        return lines, None
    except Exception as e:
        return [], format_lookup_error(e, "Node.js LTS discovery error")


def expand_dynamic_apps(apps):
    """
    If a component has multiple LTS lines, expand to one download per line.
    If it has no LTS, keep a single latest-version check.
    New majors (Java 29, Tomcat 12, Node 26, ...) appear on the next run.
    """
    has_java_family = any(lts_family(a) == "java" for a in apps)
    expanded = []
    for app in apps:
        family = lts_family(app)
        key = (app.get("official_key") or "").lower()
        if has_java_family and re.match(r"^temurin\d+$", key) and family != "java":
            continue
        if family == "tomcat":
            lines, err = discover_tomcat_lines()
            if err:
                print(f"Tomcat LTS discovery failed: {err}")
                expanded.append({**app, "source": "official", "official_key": "tomcat-discover"})
                continue
            installed = app.get("current_version")
            for line in lines:
                expanded.append({
                    "id": f"tomcat-lts-{line['major']}",
                    "name": f"Apache Tomcat {line['major']}",
                    "current_version": _old_line_version(line["major"], installed),
                    "source": "discovered",
                    "discovered_version": line["version"],
                    "discovered_url": line["url"],
                })
            continue
        if family == "java":
            majors, err = discover_java_lts_majors()
            if err:
                print(f"Java LTS discovery failed: {err}")
                expanded.append({**app, "source": "official", "official_key": "temurin21"})
                continue
            installed = app.get("current_version")
            for major in majors:
                expanded.append({
                    "id": f"java-lts-{major}",
                    "name": f"Java LTS {major}",
                    "current_version": _old_line_version(major, installed),
                    "source": "official",
                    "official_key": f"temurin{major}",
                })
            continue
        if family == "nodejs":
            lines, err = discover_nodejs_lts_lines()
            if err:
                print(f"Node.js LTS discovery failed: {err}")
                expanded.append({**app, "source": "official", "official_key": "nodejs"})
                continue
            installed = app.get("current_version")
            for line in lines:
                expanded.append({
                    "id": f"nodejs-lts-{line['major']}",
                    "name": f"Node.js LTS {line['major']}",
                    "current_version": _old_line_version(line["major"], installed),
                    "source": "discovered",
                    "discovered_version": line["version"],
                    "discovered_url": line["url"],
                })
            continue
        expanded.append(copy.deepcopy(app))
    for app in expanded:
        if "_config_old_version" not in app:
            app["_config_old_version"] = copy.deepcopy(app.get("current_version"))
    return expanded

def latest_tomcat(key):
    """Latest binary zip for one Tomcat major, discovered from Apache CDN (not hardcoded)."""
    m = re.match(r"tomcat(\d+)$", str(key or ""))
    if not m:
        return None, None, f"Unknown Tomcat key: {key}"
    major = int(m.group(1))
    lines, err = discover_tomcat_lines()
    if err:
        return None, None, err
    for line in lines:
        if line["major"] == major:
            return line["version"], line["url"], None
    return None, None, f"Tomcat {major} is not on the current Apache CDN (may be archived)"

def _gnu_latest_tarball(index_url, prefix):
    r = requests.get(index_url, headers=WEB_HEADERS, timeout=12)
    vers = re.findall(rf"{re.escape(prefix)}-(\d+\.\d+(?:\.\d+)?)\.tar\.gz", r.text or "")
    if not vers:
        return None, None, f"Could not parse {prefix} versions"
    ver = sorted(set(vers), key=lambda v: tuple(int(x) for x in v.split(".")))[-1]
    return ver, f"{index_url}{prefix}-{ver}.tar.gz", None

def _official_lookup(key):
    if key == "corretto11":
        r = requests.get("https://api.github.com/repos/corretto/corretto-11/releases/latest", headers=HEADERS, timeout=12)
        ver = None
        if r.status_code == 200:
            ver = clean_version_str(r.json().get("tag_name"))
        return ver or "11", "https://corretto.aws/downloads/latest/amazon-corretto-11-x64-windows-jdk.msi", None

    if key == "httpd":
        r = requests.get("https://httpd.apache.org/download.cgi", headers=WEB_HEADERS, timeout=12)
        m = re.search(r"httpd-(\d+\.\d+\.\d+)\.tar\.gz", r.text or "")
        if not m:
            return None, "https://httpd.apache.org/download.cgi", "Could not parse httpd version"
        ver = m.group(1)
        return ver, f"https://dlcdn.apache.org/httpd/httpd-{ver}.tar.gz", None

    if key == "jmeter":
        r = requests.get("https://dlcdn.apache.org/jmeter/binaries/", headers=WEB_HEADERS, timeout=12)
        m = re.search(r"apache-jmeter-(\d+\.\d+\.\d+)\.zip", r.text or "")
        if m:
            ver = m.group(1)
            return ver, f"https://dlcdn.apache.org/jmeter/binaries/apache-jmeter-{ver}.zip", None
        return "5.6.3", "https://dlcdn.apache.org/jmeter/binaries/apache-jmeter-5.6.3.zip", None

    if re.match(r"^tomcat\d+$", key or ""):
        return latest_tomcat(key)

    if key == "maven":
        r = requests.get("https://maven.apache.org/download.cgi", headers=WEB_HEADERS, timeout=12)
        m = re.search(r"apache-maven-(\d+\.\d+\.\d+)-bin\.zip", r.text or "")
        if not m:
            return None, "https://maven.apache.org/download.cgi", "Could not parse Maven version"
        ver = m.group(1)
        return ver, f"https://dlcdn.apache.org/maven/maven-3/{ver}/binaries/apache-maven-{ver}-bin.zip", None

    if key == "bash":
        return _gnu_latest_tarball("https://ftp.gnu.org/gnu/bash/", "bash")

    if key == "cloud-sql-proxy":
        r = requests.get("https://github.com/GoogleCloudPlatform/cloud-sql-proxy/tags", headers=WEB_HEADERS, timeout=12)
        tags = re.findall(r"/GoogleCloudPlatform/cloud-sql-proxy/releases/tag/(v2\.[^\"'\s]+)", r.text or "")
        if tags:
            tag = tags[0]
            ver = tag.lstrip("v")
            # GitHub release has no Windows asset; binaries are on GCS
            return ver, f"https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/{tag}/cloud-sql-proxy.x64.exe", None
        return latest_github("GoogleCloudPlatform/cloud-sql-proxy")

    if key == "gcloud":
        r = requests.get("https://dl.google.com/dl/cloudsdk/channels/rapid/components-2.json", headers=HEADERS, timeout=12)
        ver = None
        if r.status_code == 200:
            try:
                ver = r.json().get("version")
            except Exception:
                ver = None
        return ver, "https://dl.google.com/dl/cloudsdk/channels/rapid/GoogleCloudSDKInstaller.exe", None

    if key == "intellij":
        r = requests.get(
            "https://data.services.jetbrains.com/products/releases?code=IIC&latest=true&type=release",
            headers=HEADERS,
            timeout=12,
        )
        if r.status_code == 200:
            data = r.json().get("IIC") or []
            if data:
                ver = data[0].get("version")
                dls = data[0].get("downloads") or {}
                dl = (dls.get("windows") or {}).get("link") or (dls.get("windowsZip") or {}).get("link")
                return ver, dl, None
        return None, "https://www.jetbrains.com/idea/download/", "IntelliJ API parse failed"

    if key.startswith("temurin"):
        major = key.replace("temurin", "").strip()
        if not major.isdigit():
            return None, None, f"Unknown Temurin key: {key}"
        r = requests.get(
            f"https://api.adoptium.net/v3/assets/latest/{major}/hotspot?os=windows&architecture=x64&image_type=jdk",
            headers=HEADERS,
            timeout=12,
        )
        if r.status_code == 200 and r.json():
            arr = r.json()[0]
            ver = (arr.get("version") or {}).get("openjdk_version") or arr.get("release_name")
            if major == "8" and ver:
                m8 = re.search(r"1\.8\.0_(\d+)", str(ver)) or re.search(r"8u(\d+)", str(ver))
                if m8:
                    ver = f"8.0.{m8.group(1)}"
            dl = arr.get("binary", {}).get("package", {}).get("link")
            return ver, dl, None
        return None, f"https://adoptium.net/temurin/releases/?version={major}", "Adoptium lookup failed"

    if key == "jenkins":
        r = requests.get("https://updates.jenkins.io/current/latestCore.txt", headers=HEADERS, timeout=12)
        ver = r.text.strip() if r.status_code == 200 else None
        if ver:
            return ver, f"https://get.jenkins.io/war/{ver}/jenkins.war", None
        return None, "https://www.jenkins.io/download/", "Jenkins lookup failed"

    if key == "firefox":
        r = requests.get("https://product-details.mozilla.org/1.0/firefox_versions.json", headers=HEADERS, timeout=12)
        ver = r.json().get("LATEST_FIREFOX_VERSION") if r.status_code == 200 else None
        if ver:
            return ver, "https://download.mozilla.org/?product=firefox-latest-ssl&os=win64&lang=en-US", None
        return None, "https://www.mozilla.org/firefox/download/", "Firefox lookup failed"

    if key == "nodejs":
        r = requests.get("https://nodejs.org/dist/index.json", headers=HEADERS, timeout=12)
        if r.status_code == 200:
            arr = r.json()
            lts = next((x for x in arr if x.get("lts")), arr[0])
            ver = lts.get("version", "").lstrip("v")
            return ver, f"https://nodejs.org/dist/v{ver}/node-v{ver}-x64.msi", None
        return None, "https://nodejs.org/en/download", "Node.js lookup failed"

    if key == "nuget":
        return "latest", "https://dist.nuget.org/win-x86-commandline/latest/nuget.exe", None

    if key == "openssh":
        r = requests.get("https://cdn.openbsd.org/pub/OpenBSD/OpenSSH/portable/", headers=WEB_HEADERS, timeout=12)
        vers = re.findall(r"openssh-(\d+\.\d+(?:p\d+)?)\.tar\.gz", r.text or "")
        if vers:
            ver = vers[-1]
            return ver, f"https://cdn.openbsd.org/pub/OpenBSD/OpenSSH/portable/openssh-{ver}.tar.gz", None
        return None, "https://www.openssh.com/portable.html", "OpenSSH parse failed"

    if key == "pinginfoview":
        return "latest", "https://www.nirsoft.net/utils/pinginfoview.zip", None

    if key == "postman":
        return "latest", "https://dl.pstmn.io/download/latest/win64", None

    if key == "putty":
        r = requests.get("https://www.chiark.greenend.org.uk/~sgtatham/putty/latest.html", headers=WEB_HEADERS, timeout=12)
        ver = None
        if r.status_code == 200:
            m = re.search(r"putty-64bit-(0\.\d+)-installer\.msi", r.text, re.I)
            if m:
                ver = m.group(1)
        if ver:
            return ver, f"https://the.earth.li/~sgtatham/putty/latest/w64/putty-64bit-{ver}-installer.msi", None
        return None, "https://www.chiark.greenend.org.uk/~sgtatham/putty/latest.html", "PuTTY parse failed"

    if key == "python":
        r = requests.get("https://www.python.org/ftp/python/", headers=WEB_HEADERS, timeout=12)
        vers = re.findall(r'href="(\d+\.\d+\.\d+)/"', r.text or "")
        ordered = sorted(set(vers), key=lambda v: tuple(int(x) for x in v.split(".")), reverse=True)
        for ver in ordered[:15]:
            dl = f"https://www.python.org/ftp/python/{ver}/python-{ver}-amd64.exe"
            try:
                head = requests.head(dl, headers=WEB_HEADERS, allow_redirects=True, timeout=10)
                if head.status_code == 200:
                    return ver, dl, None
            except Exception:
                continue
        return None, "https://www.python.org/downloads/", "Python installer not found"

    if key == "rstudio":
        r = requests.get("https://posit.co/download/rstudio-desktop/", headers=WEB_HEADERS, timeout=12)
        if r.status_code == 200:
            m = re.search(r"rstudio-(\d+\.\d+\.\d+)-(\d+)", r.text, re.I)
            if m:
                ver = f"{m.group(1)}-{m.group(2)}"
                return ver, f"https://download1.rstudio.org/electron/windows/RStudio-{ver}.exe", None
        return None, "https://posit.co/download/rstudio-desktop/", "RStudio parse failed"

    if key == "vlc":
        r = requests.get("https://get.videolan.org/vlc/last/win64/", headers=WEB_HEADERS, timeout=12)
        m = re.search(r"vlc-(\d+\.\d+\.\d+)-win64\.exe", r.text or "")
        if m:
            ver = m.group(1)
            return ver, f"https://get.videolan.org/vlc/{ver}/win64/vlc-{ver}-win64.exe", None
        return None, "https://www.videolan.org/vlc/download-windows.html", "VLC parse failed"

    if key == "wget":
        return _gnu_latest_tarball("https://ftp.gnu.org/gnu/wget/", "wget")

    if key == "winscp":
        r = requests.get("https://winscp.net/eng/downloads.php", headers=WEB_HEADERS, timeout=12)
        if r.status_code == 200:
            m = re.search(r"WinSCP (\d+\.\d+(?:\.\d+)?)", r.text)
            if m:
                ver = m.group(1)
                return ver, f"https://winscp.net/download/WinSCP-{ver}-Setup.exe", None
        return None, "https://winscp.net/eng/downloads.php", "WinSCP parse failed"

    if key == "wireshark":
        r = requests.get("https://www.wireshark.org/download.html", headers=WEB_HEADERS, timeout=12)
        if r.status_code == 200:
            m = re.search(r"Wireshark[^\d]{0,20}(\d+\.\d+\.\d+)", r.text)
            if m:
                ver = m.group(1)
                # Official path redirects to a nearby CDN; 2.na.dl can stall from some regions
                return ver, f"https://www.wireshark.org/download/win64/Wireshark-{ver}-x64.exe", None
        return None, "https://www.wireshark.org/download.html", "Wireshark parse failed"

    if key == "zoom":
        return "latest", "https://zoom.us/client/latest/ZoomInstallerFull.exe", None

    if key == "golang":
        r = requests.get("https://go.dev/dl/?mode=json", headers=HEADERS, timeout=12)
        if r.status_code == 200:
            for rel in r.json() or []:
                if not rel.get("stable"):
                    continue
                ver = (rel.get("version") or "").lstrip("go")
                for f in rel.get("files") or []:
                    if f.get("os") == "windows" and f.get("arch") == "amd64" and str(f.get("filename") or "").endswith(".msi"):
                        return ver, "https://go.dev/dl/" + f["filename"], None
        return None, "https://go.dev/dl/", "Go download lookup failed"

    if key == "android-studio":
        r = requests.get("https://developer.android.com/studio", headers=WEB_HEADERS, timeout=15)
        m = re.search(r"android-studio-(\d+\.\d+\.\d+\.\d+)-windows\.exe", r.text or "")
        if m:
            ver = m.group(1)
            return ver, (
                f"https://redirector.gstatic.com/edgedl/android/studio/install/{ver}/"
                f"android-studio-{ver}-windows.exe"
            ), None
        return None, "https://developer.android.com/studio", "Android Studio parse failed"

    if key == "eclipse":
        r = requests.get("https://download.eclipse.org/eclipse/downloads/", headers=WEB_HEADERS, timeout=15)
        m = re.search(r"R-(\d+\.\d+)-(\d+)/", r.text or "")
        if m:
            ver, stamp = m.group(1), m.group(2)
            return ver, (
                f"https://download.eclipse.org/eclipse/downloads/drops4/R-{ver}-{stamp}/"
                f"eclipse-SDK-{ver}-win32-x86_64.zip"
            ), None
        return None, "https://www.eclipse.org/downloads/", "Eclipse parse failed"

    if key == "autoit":
        r = requests.get("https://www.autoitscript.com/site/autoit/downloads/", headers=WEB_HEADERS, timeout=15)
        ver = None
        if r.status_code == 200:
            m = re.search(r"v(\d+\.\d+\.\d+\.\d+)", r.text or "", re.I)
            if m:
                ver = m.group(1)
        return ver or "latest", "https://www.autoitscript.com/cgi-bin/getfile.pl?autoit3/autoit-v3-setup.exe", None

    if key == "postgresql":
        r = requests.get("https://ftp.postgresql.org/pub/source/", headers=WEB_HEADERS, timeout=15)
        vers = re.findall(r'href="v(\d+\.\d+)/"', r.text or "")
        if vers:
            ver = sorted(set(vers), key=lambda v: tuple(int(x) for x in v.split(".")))[-1]
            return ver, f"https://ftp.postgresql.org/pub/source/v{ver}/postgresql-{ver}.tar.gz", None
        return None, "https://www.postgresql.org/download/windows/", "PostgreSQL parse failed"

    if key == "tightvnc":
        r = requests.get("https://www.tightvnc.com/download.php", headers=WEB_HEADERS, timeout=12)
        m = re.search(r"tightvnc-(\d+\.\d+(?:\.\d+)?)-gpl-setup-64bit\.msi", r.text or "", re.I)
        if m:
            ver = m.group(1)
            return ver, f"https://www.tightvnc.com/download/{ver}/tightvnc-{ver}-gpl-setup-64bit.msi", None
        return None, "https://www.tightvnc.com/download.php", "TightVNC parse failed"

    if key in {"dotnet8", "dotnet-sdk"}:
        r = requests.get(
            "https://builds.dotnet.microsoft.com/dotnet/release-metadata/8.0/releases.json",
            headers=HEADERS,
            timeout=12,
        )
        if r.status_code == 200:
            ver = r.json().get("latest-sdk")
            if ver:
                return ver, (
                    f"https://builds.dotnet.microsoft.com/dotnet/Sdk/{ver}/"
                    f"dotnet-sdk-{ver}-win-x64.exe"
                ), None
        return None, "https://dotnet.microsoft.com/download/dotnet/8.0", ".NET SDK lookup failed"

    if key in {"dotnet8-runtime", "dotnet-runtime"}:
        r = requests.get(
            "https://builds.dotnet.microsoft.com/dotnet/release-metadata/8.0/releases.json",
            headers=HEADERS,
            timeout=12,
        )
        if r.status_code == 200:
            ver = r.json().get("latest-runtime")
            if ver:
                return ver, (
                    f"https://builds.dotnet.microsoft.com/dotnet/Runtime/{ver}/"
                    f"dotnet-runtime-{ver}-win-x64.exe"
                ), None
        return None, "https://dotnet.microsoft.com/download/dotnet/8.0", ".NET Runtime lookup failed"

    return None, None, f"Unknown official source key: {key}"

def latest_microsoft_dotnet():
    """Scrape / fetch latest .NET Framework release version."""
    url = "https://dotnet.microsoft.com/en-us/download/dotnet-framework"
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        if r.status_code == 200:
            match = re.search(r'\.NET Framework\s+([0-9]+\.[0-9]+(?:\.[0-9]+)?)', r.text, re.IGNORECASE)
            if match:
                latest_ver = match.group(1)
                return latest_ver, url, None
        return "4.8.1", url, None
    except Exception as e:
        return None, None, format_lookup_error(e, "Microsoft lookup error")

def latest_oracle_xe():
    """Fetch latest Oracle Database Express Edition (XE) info."""
    url = "https://www.oracle.com/database/technologies/appdev/xe.html"
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            text = soup.get_text()
            match = re.search(r'Oracle Database\s+(23c|21c|23\.[0-9]+\.[0-9]+|19c)', text, re.IGNORECASE)
            if match:
                ver_found = match.group(1)
                ver_norm = "23.2.0" if "23" in ver_found else ("21.3.0" if "21" in ver_found else "19.0.0")
                return ver_norm, url, None
        return "23.2.0", url, None
    except Exception as e:
        return None, None, format_lookup_error(e, "Oracle lookup error")

def is_direct_file_url(url):
    """True when the URL points at a real file, not a download webpage."""
    if not url or url == "#":
        return False
    path = (urlparse(url).path or "").lower()
    return path.endswith(FILE_EXTS)


def is_webpage_download(url):
    """True when auto-download would only save an HTML page."""
    if not url or url == "#":
        return True
    if is_direct_file_url(url):
        return False
    lower = url.lower()
    path = (urlparse(url).path or "").lower()
    if path.endswith((".html", ".htm", ".php", ".aspx")):
        return True
    return any(
        host in lower
        for host in (
            "oracle.com",
            "hub.docker.com",
            "netacad.com",
            "aws.amazon.com/migration-evaluator",
            "kali.org",
            "ubuntu.com/download",
        )
    )


NOT_AVAILABLE_SOURCE = "Exiting Script Not available source"


def _src_github(app):
    return latest_github(app.get("repo"))


def _src_npm(app):
    return latest_npm(app.get("package"))


def _src_pypi(app):
    return latest_pypi(app.get("package"))


def _src_maven(app):
    return latest_maven(app.get("maven_path"))


def _src_official(app):
    ver, url, err = latest_official(app.get("official_key"))
    if err and "Unknown official source key" in str(err or ""):
        if app.get("repo"):
            return latest_github(app.get("repo"))
        if app.get("maven_path"):
            return latest_maven(app.get("maven_path"))
        if app.get("package"):
            return latest_pypi(app.get("package"))
        return None, None, NOT_AVAILABLE_SOURCE
    return ver, url, err


def _src_discovered(app):
    ver = app.get("discovered_version")
    url = app.get("discovered_url")
    if not ver or not url:
        return None, None, "Discovered version or download URL missing."
    return ver, url, None


def _src_jquery(_app):
    return latest_jquery()


def _src_jqueryui(_app):
    return latest_jqueryui()


def _src_datatables(_app):
    return latest_datatables()


def _src_microsoft(_app):
    return latest_microsoft_dotnet()


def _src_oracle(_app):
    return latest_oracle_xe()


def _src_manual(app):
    url = app.get("download_url") or app.get("manual_url")
    ver = app.get("current_version") or app.get("_config_old_version") or "see vendor page"
    if not url:
        return None, None, "Manual download URL missing."
    return ver, url, None


def _src_java(app):
    major = _installed_major(app.get("current_version")) or 21
    return latest_official(f"temurin{major}")


def _src_tomcat(app):
    major = _installed_major(app.get("current_version")) or 9
    return latest_tomcat(f"tomcat{major}")


def _src_nodejs(_app):
    return latest_official("nodejs")


# New config.json apps using these sources are processed automatically (no code change).
SOURCE_HANDLERS = {
    "github": _src_github,
    "npm": _src_npm,
    "pypi": _src_pypi,
    "maven": _src_maven,
    "official": _src_official,
    "discovered": _src_discovered,
    "jquery": _src_jquery,
    "jqueryui": _src_jqueryui,
    "datatables": _src_datatables,
    "microsoft": _src_microsoft,
    "oracle": _src_oracle,
    "manual": _src_manual,
    "java": _src_java,
    "java-lts-all": _src_java,
    "tomcat": _src_tomcat,
    "tomcat-lts-all": _src_tomcat,
    "nodejs": _src_nodejs,
    "node": _src_nodejs,
}


def lookup_by_source(app_config):
    """Dispatch by config.json source. Unknown sources return Not available source."""
    source = (app_config.get("source") or "").strip().lower()
    handler = SOURCE_HANDLERS.get(source)
    if handler is None:
        return None, None, NOT_AVAILABLE_SOURCE
    return handler(app_config)


def check_app_version(app_config):
    """Query live online sources for the specified app configuration."""
    name = app_config.get("name", "Unknown App")
    current_ver = app_config.get("current_version", "")
    current_id = current_ver if isinstance(current_ver, str) else ",".join(parse_version_list(current_ver))
    app_id = app_config.get("id") or f"{name.lower().replace(' ', '-')}-{str(current_id).replace('.', '')}"
    source = (app_config.get("source") or "").strip().lower()
    
    old_ver = app_config.get("_config_old_version")
    if old_ver is None:
        old_ver = current_ver

    latest_ver, download_url, error_msg = lookup_by_source(app_config)

    if latest_ver and not error_msg and source != "manual":
        download_url = apply_download_template(app_config, latest_ver, download_url)
    
    # Strong outdated check: CURRENT only when installed == latest
    status = "ERROR"
    skip_reason = ""
    if error_msg:
        status = "ERROR"
    elif source == "manual":
        status = "OUTDATED"
        skip_reason = "no public file; open download_url in a browser"
    elif latest_ver:
        status = version_update_status(old_ver, latest_ver)
        if status not in {"UP_TO_DATE", "OUTDATED", "ERROR"}:
            status = "ERROR"
        
    result = {
        "id": app_id,
        "name": name,
        "old_version": old_ver,
        "current_version": old_ver,
        "latest_version": latest_ver or "N/A",
        "status": status,
        "download_url": download_url or "#",
        "source": source,
        "remark": "",
        "skip_reason": skip_reason,
        "error": error_msg,
        "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    result["remark"] = build_remark(result)
    return result

def get_project_dir():
    """Always the folder that contains this EXE (or updater.py). Changes on every PC."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def find_config_path():
    """
    Always use config.json next to the EXE/script.
    If the EXE is copied alone, copy the bundled config into that folder.
    """
    project = get_project_dir()
    local = os.path.join(project, "config.json")
    if os.path.isfile(local):
        return local
    bundled_dir = getattr(sys, "_MEIPASS", None)
    if bundled_dir:
        bundled = os.path.join(bundled_dir, "config.json")
        if os.path.isfile(bundled):
            shutil.copy2(bundled, local)
            print("Created   : config.json (next to EXE)")
            return local
    cwd = os.path.join(os.getcwd(), "config.json")
    if os.path.isfile(cwd):
        shutil.copy2(cwd, local)
        return local
    return local


def _config_for_disk(config):
    """config.json must not store internal runtime keys such as _config_old_version."""
    out = copy.deepcopy(config)
    for app in out.get("apps", []):
        for key in [k for k in app if str(k).startswith("_")]:
            app.pop(key, None)
    return out


def write_config(config_path, config):
    """Persist config.json (temp file then replace, so Ctrl+C cannot leave a half-written file)."""
    tmp = config_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_config_for_disk(config), f, indent=2)
        f.write("\n")
    os.replace(tmp, config_path)


def lts_versions_from_results(family, by_id):
    """All successful latest versions for an LTS family. ERROR rows are ignored."""
    prefix = f"{family}-lts-"
    found = []
    for rid, rec in by_id.items():
        if not str(rid).startswith(prefix):
            continue
        if not result_ok_for_config(rec):
            continue
        found.append(rec.get("latest_version"))
    return format_lts_versions(found)


def result_ok_for_config(rec):
    """Do not write config.json from ERROR / manual / missing lookups."""
    if not rec:
        return False
    if rec.get("status") == "ERROR" or rec.get("error"):
        return False
    if rec.get("source") == "manual":
        return False
    latest = rec.get("latest_version")
    return bool(latest) and latest != "N/A"


def latest_for_config_app(app, by_id):
    """
    Latest version(s) to store for this config row.
    ERROR components are skipped so config.json keeps the old version.
    """
    family = lts_family(app)
    if family:
        found = lts_versions_from_results(family, by_id)
        if not found:
            return None
        existing = format_lts_versions(app.get("current_version"))
        found_majors = {_installed_major(v) for v in found}
        merged = [v for v in existing if _installed_major(v) not in found_majors]
        merged.extend(found)
        return format_lts_versions(merged)
    rec = by_id.get(app.get("id")) or {}
    if not result_ok_for_config(rec):
        return None
    return rec.get("latest_version")


def versions_equal(current, latest):
    if isinstance(latest, list) or isinstance(current, list) or (
        isinstance(current, str) and "," in current
    ):
        return format_lts_versions(current) == format_lts_versions(latest)
    return str(current or "").strip() == str(latest or "").strip()


def update_config_versions(config, results):
    """
    Write found latest versions into the in-memory config.
    Returns [(name, old, new), ...] for rows that changed.
    """
    by_id = {r.get("id"): r for r in results}
    changes = []
    for app in config.get("apps", []):
        current = app.get("current_version", "")
        latest = latest_for_config_app(app, by_id)
        if latest is None or versions_equal(current, latest):
            continue
        app["current_version"] = latest
        # Only current_version is updated. Report old_version stays the pre-update snapshot.
        changes.append((app.get("name") or app.get("id"), current, latest))
    return changes


def persist_found_versions(config_path, config, results, quiet=False):
    """Save config.json as soon as a latest version is found (survives Ctrl+C)."""
    if not config_path or config is None:
        return []
    changes = update_config_versions(config, results)
    if not changes:
        return []
    write_config(config_path, config)
    if not quiet:
        for name, old, new in changes:
            print(f"config.json : {name}  {version_display(old) or '(empty)'} -> {version_display(new)}")
        print()
    return changes


def pause_if_frozen():
    """Keep the CMD window open when the EXE is double-clicked."""
    if not getattr(sys, "frozen", False):
        return
    try:
        input("\nPress Enter to close...")
    except Exception:
        time.sleep(20)


def resolve_folder(folder_name, default_name="downloads"):
    """
    Always create the folder next to the EXE/script.
    Absolute paths in config.json are ignored so no PC-specific C:\\Users\\... is used.
    """
    name = (folder_name or default_name).strip() or default_name
    if os.path.isabs(name):
        name = os.path.basename(name.rstrip("\\/")) or default_name
    path = os.path.join(get_project_dir(), name)
    os.makedirs(path, exist_ok=True)
    return path


def rel_to_project(path):
    """Show a portable relative name (config.json, downloads\\file.jar)."""
    try:
        return os.path.relpath(path, get_project_dir()).replace("\\", "/")
    except ValueError:
        return os.path.basename(path)

def download_candidate_urls(url):
    """Return URL plus regional mirrors for known large installers."""
    urls = [url]
    m = re.search(r"Wireshark-(\d+\.\d+\.\d+)-x64\.exe", url or "")
    if m:
        ver = m.group(1)
        for extra in (
            f"https://www.wireshark.org/download/win64/Wireshark-{ver}-x64.exe",
            f"https://1.na.dl.wireshark.org/win64/Wireshark-{ver}-x64.exe",
            f"https://2.na.dl.wireshark.org/win64/Wireshark-{ver}-x64.exe",
        ):
            if extra not in urls:
                urls.append(extra)
    return urls

def _safe_download_filename(name):
    """Keep the vendor filename; only strip characters Windows cannot store."""
    if not name:
        return None
    name = unquote(name).strip().strip('"').replace("\\", "/").split("/")[-1]
    name = re.sub(r'[<>:"|?*]', "_", name).strip(" .")
    if not name or name in {".", ".."}:
        return None
    return name[:180]


def _filename_from_url(url):
    if not url:
        return None
    path = unquote(urlparse(url).path or "").rstrip("/")
    return _safe_download_filename(path.split("/")[-1] if path else "")


def _filename_from_content_disposition(header):
    if not header:
        return None
    star = re.search(r"filename\*\s*=\s*(?:UTF-8''|utf-8'')?([^;]+)", header, re.I)
    if star:
        return _safe_download_filename(star.group(1))
    quoted = re.search(r'filename\s*=\s*"([^"]+)"', header, re.I)
    if quoted:
        return _safe_download_filename(quoted.group(1))
    plain = re.search(r"filename\s*=\s*([^;]+)", header, re.I)
    if plain:
        return _safe_download_filename(plain.group(1))
    return None


def original_download_filename(request_url, response=None):
    """Use the real download name (e.g. log4j-1.2-api-2.26.1.jar), never rename/prefix."""
    if response is not None:
        from_header = _filename_from_content_disposition(response.headers.get("Content-Disposition", ""))
        if from_header:
            return from_header
        from_final = _filename_from_url(getattr(response, "url", "") or "")
        if from_final and "." in from_final:
            return from_final
    from_request = _filename_from_url(request_url)
    if from_request and "." in from_request:
        return from_request
    return from_request or "download.bin"


def download_file(url, destination_folder):
    """Download a file from URL using the original filename. Shows progress and aborts if stalled."""
    if not url or url == "#" or url.startswith("javascript"):
        return False, "Invalid or missing download URL."
    
    os.makedirs(destination_folder, exist_ok=True)
    last_error = "Download failed"
    
    for attempt_url in download_candidate_urls(url):
        save_path = None
        max_tries = 6 if is_github_url(attempt_url) else 2
        for attempt in range(max_tries):
            try:
                if is_github_url(attempt_url):
                    wait_github_gap()
                headers = WEB_HEADERS if is_github_url(attempt_url) else HEADERS
                # connect timeout 15s; if no bytes arrive for 30s the transfer is stalled
                r = requests.get(
                    attempt_url,
                    headers=headers,
                    stream=True,
                    timeout=(15, 30),
                    allow_redirects=True,
                )
                if r.status_code in (429, 403):
                    wait = retry_after_seconds(r, attempt)
                    last_error = f"GitHub download HTTP {r.status_code}; retry in {wait}s"
                    print(f"  {last_error}")
                    r.close()
                    time.sleep(wait)
                    continue
                r.raise_for_status()

                filename = original_download_filename(attempt_url, r)
                save_path = os.path.join(destination_folder, filename)
                
                total = int(r.headers.get("Content-Length") or 0)
                if total:
                    print(f"  Size      : {round(total / (1024 * 1024), 1)} MB")
                print(f"  File      : {filename}")
                print(f"  From      : {attempt_url}")
                
                hasher = hashlib.sha256()
                downloaded = 0
                last_print = time.time()
                started = time.time()
                with open(save_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=64 * 1024):
                        if not chunk:
                            continue
                        f.write(chunk)
                        hasher.update(chunk)
                        downloaded += len(chunk)
                        now = time.time()
                        if now - last_print >= 1 or (total and downloaded >= total):
                            mb = downloaded / (1024 * 1024)
                            elapsed = max(now - started, 0.1)
                            speed = mb / elapsed
                            if total:
                                pct = int(downloaded * 100 / total)
                                total_mb = total / (1024 * 1024)
                                line = f"  Progress  : {mb:.1f}/{total_mb:.1f} MB ({pct}%)  {speed:.1f} MB/s"
                            else:
                                line = f"  Progress  : {mb:.1f} MB  {speed:.1f} MB/s"
                            print("\r" + line.ljust(64), end="", flush=True)
                            last_print = now
                print()
                
                sha256_hash = hasher.hexdigest()
                file_size_kb = round(os.path.getsize(save_path) / 1024, 2)
                project_dir = get_project_dir()
                try:
                    relative_path = rel_to_project(save_path)
                except ValueError:
                    relative_path = filename
                
                return True, {
                    "file_path": relative_path.replace("\\", "/"),
                    "absolute_path": save_path,
                    "filename": filename,
                    "size_kb": file_size_kb,
                    "sha256": sha256_hash
                }
            except KeyboardInterrupt:
                print()
                if save_path and os.path.exists(save_path):
                    try:
                        os.remove(save_path)
                    except OSError:
                        pass
                return False, "Download skipped (Ctrl+C)"
            except (Timeout, ReadTimeout, ConnectionError) as e:
                last_error = format_lookup_error(e, "Download stalled or timed out")
                print()
                print(f"  Retry     : {last_error}")
                if save_path and os.path.exists(save_path):
                    try:
                        os.remove(save_path)
                    except OSError:
                        pass
                if attempt + 1 < max_tries:
                    time.sleep(5)
                    continue
                break
            except HTTPError as e:
                code = e.response.status_code if e.response is not None else None
                last_error = format_lookup_error(e, "Download failed")
                print()
                if code in (429, 403) and attempt + 1 < max_tries:
                    wait = retry_after_seconds(e.response, attempt)
                    print(f"  GitHub download HTTP {code}; retry in {wait}s")
                    time.sleep(wait)
                    continue
                print(f"  Retry     : {last_error}")
                if save_path and os.path.exists(save_path):
                    try:
                        os.remove(save_path)
                    except OSError:
                        pass
                break
            except Exception as e:
                last_error = format_lookup_error(e, "Download failed")
                print()
                print(f"  Retry     : {last_error}")
                if save_path and os.path.exists(save_path):
                    try:
                        os.remove(save_path)
                    except OSError:
                        pass
                break
    
    return False, last_error

def _report_cell(value):
    if isinstance(value, (list, tuple)):
        return ", ".join(str(x) for x in value)
    if value is None:
        return ""
    return value


REPORT_FIELDS = [
    "id",
    "name",
    "old_version",
    "latest_version",
    "status",
    "download_url",
    "source",
    "remark",
    "checked_at",
]


def versions_match(old, latest):
    if old in (None, "", []) or latest in (None, "", "N/A"):
        return False
    return _report_cell(old).strip() == _report_cell(latest).strip() or versions_equal(old, latest)


def build_remark(result):
    """Why this component was downloaded, skipped, or failed."""
    status = result.get("status") or ""
    err = (result.get("error") or "").strip()
    skip = (result.get("skip_reason") or "").strip()
    source = (result.get("source") or "").lower()
    if err == NOT_AVAILABLE_SOURCE:
        return NOT_AVAILABLE_SOURCE
    if status == "ERROR" or err:
        return f"Error: {err or 'lookup failed'}"
    if versions_match(result.get("old_version"), result.get("latest_version")) or status == "UP_TO_DATE":
        return "Up to date version"
    if result.get("downloaded_file"):
        return "Latest version downloaded to downloads folder"
    if source == "manual":
        return "Not downloaded: no public file; open download_url in a browser"
    if skip:
        return f"Not downloaded: {skip}"
    if status == "OUTDATED":
        return "Latest version downloaded to downloads folder"
    return "Not downloaded"


def write_reports(results, csv_path, json_path):
    """Rewrite live CSV/JSON reports after every component (survives Ctrl+C)."""
    rows = []
    for r in results:
        row = {k: r.get(k, "") for k in REPORT_FIELDS}
        if row.get("old_version") in (None, ""):
            row["old_version"] = r.get("old_version") or r.get("current_version") or ""
        row["latest_version"] = r.get("latest_version") or "N/A"
        if versions_match(row.get("old_version"), row.get("latest_version")):
            row["status"] = "UP_TO_DATE"
            row["remark"] = "Up to date version"
        else:
            row["remark"] = build_remark(r)
        if row.get("status") not in {"UP_TO_DATE", "OUTDATED", "ERROR"}:
            row["status"] = "ERROR" if r.get("error") else "OUTDATED"
        rows.append(row)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=REPORT_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _report_cell(row.get(k, "")) for k in REPORT_FIELDS})
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, default=str)


def generate_report(results, report_folder="reports", format_type="csv"):
    """Generate summary report CSV/JSON file."""
    os.makedirs(report_folder, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if format_type == "csv":
        file_path = os.path.join(report_folder, f"version_report_{timestamp}.csv")
        write_reports(results, file_path, os.path.join(report_folder, f"version_report_{timestamp}.json"))
        return file_path
    file_path = os.path.join(report_folder, f"version_report_{timestamp}.json")
    csv_path = os.path.join(report_folder, f"version_report_{timestamp}.csv")
    write_reports(results, csv_path, file_path)
    return file_path

if __name__ == "__main__":
    config = None
    config_path = None
    all_results = []
    csv_report = None
    json_report = None
    try:
        project_dir = get_project_dir()
        config_path = find_config_path()
        if not os.path.exists(config_path):
            print("config.json not found!")
            print(f"Looked next to: {project_dir}")
            print("Put config.json in the same folder as SoftwareUpdater.exe")
            raise SystemExit(1)

        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        # Dynamic project folders (change with PC / project location)
        downloads_dir = resolve_folder(config.get("download_folder", "downloads"), "downloads")
        reports_dir = resolve_folder(config.get("reports_folder", "reports"), "reports")
        download_folder_name = config.get("download_folder", "downloads")

        print(f"Company   : {COMPANY_NAME}")
        if getattr(sys, "frozen", False):
            print(f"Mode      : EXE")
        print(f"Config    : {rel_to_project(config_path)}")
        print(f"Downloads : {rel_to_project(downloads_dir)}/")
        print(f"Reports   : {rel_to_project(reports_dir)}/")
        print()
        apps = expand_dynamic_apps(config.get("apps", []))
        print(f"Apps      : {len(apps)}")
        print()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_report = os.path.join(reports_dir, f"version_report_{timestamp}.csv")
        json_report = os.path.join(reports_dir, f"version_report_{timestamp}.json")

        for app in apps:
            print("=" * 60)
            print(app["name"])
            print()

            res = check_app_version(app)
            all_results.append(res)
            write_reports(all_results, csv_report, json_report)

            if res.get("error") == NOT_AVAILABLE_SOURCE:
                print("Status    : ERROR")
                print()
                print(f"Error     : {NOT_AVAILABLE_SOURCE}")
                print()
                continue
            elif res.get("source") == "manual":
                print(f"Old Version : {res['old_version'] or '(not tracked)'}")
                print()
                print("Status    : OUTDATED")
                print()
                print("Open this link in a browser to download (no auto-download):")
                print(f"Link      : {res['download_url']}")
                print()
            elif res["latest_version"] == "N/A" and res["error"]:
                print(f"Old Version : {res['old_version']}")
                print(f"Latest Version : N/A")
                print()
                print(f"Status    : ERROR")
                print()
                print(f"Error     : {res['error']}")
                print()
            else:
                print(f"Old Version : {res['old_version']}")
                print(f"Latest Version : {res['latest_version']}")
                print()
                print(f"Status    : {res['status']}")
                print()
                if res["download_url"] and res["download_url"] != "#":
                    print(f"Download  : {res['download_url']}")
                    print()

                should_download = res["status"] == "OUTDATED" and res.get("source") != "manual"
                if should_download:
                    download_url = res.get("download_url") or ""
                    if is_webpage_download(download_url):
                        res["skip_reason"] = "vendor webpage only; no direct file. Open download_url in a browser"
                        res["remark"] = build_remark(res)
                        print("Auto-download skipped (webpage only). Open this link in a browser:")
                        print(f"Link      : {download_url}")
                        print()
                    else:
                        print(f"Downloading outdated package to '{download_folder_name}/' ...")
                        ok, dl_result = download_file(download_url, downloads_dir)
                        if ok:
                            print(f"Saved     : {dl_result['file_path']}")
                            print(f"Size      : {dl_result['size_kb']} KB")
                            res["downloaded_file"] = dl_result["file_path"]
                            res["remark"] = build_remark(res)
                        else:
                            print(f"Download failed: {dl_result}")
                            res["error"] = str(dl_result)
                            res["status"] = "ERROR"
                            res["remark"] = build_remark(res)
                            write_reports(all_results, csv_report, json_report)
                            if "Ctrl+C" in str(dl_result):
                                raise KeyboardInterrupt
                            print("Continuing with the next component...")
                        print()

            write_reports(all_results, csv_report, json_report)

        write_reports(all_results, csv_report, json_report)
        saved = persist_found_versions(config_path, config, all_results)
        if saved:
            print("=" * 60)
            print(f"config.json updated after report: {len(saved)} version(s)")
            print()

        up_to_date_n = sum(1 for r in all_results if r.get("status") == "UP_TO_DATE")
        outdated_n = sum(1 for r in all_results if r.get("status") == "OUTDATED")
        error_n = sum(1 for r in all_results if r.get("status") == "ERROR")
        print("=" * 60)
        print(f"{COMPANY_NAME}")
        print(f"  Components : {len(all_results)}")
        print(f"  Up to date : {up_to_date_n}")
        print(f"  Outdated   : {outdated_n}")
        print(f"  Error      : {error_n}")
        print()
        print("Reports created next to this program:")
        print(f" - CSV : {rel_to_project(csv_report)}")
        print(f" - JSON: {rel_to_project(json_report)}")
    except KeyboardInterrupt:
        print()
        print("Stopped by user (Ctrl+C).")
        if csv_report and json_report and all_results:
            write_reports(all_results, csv_report, json_report)
            print(f"Report saved: {rel_to_project(csv_report)}")
        saved = persist_found_versions(config_path, config, all_results, quiet=True)
        if saved:
            print(f"config.json updated after report ({len(saved)} version(s)).")
        elif all_results:
            print("config.json already has the versions found before cancel.")
    except SystemExit:
        raise
    except Exception:
        print()
        print("Script failed with an error:")
        import traceback
        traceback.print_exc()
        raise SystemExit(1)
    finally:
        pause_if_frozen()
