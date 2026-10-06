"""
Permian Well Tracker - Step 1: Source probe
-------------------------------------------
Tests whether every public data source can be reached and downloaded by a script
(no human clicks). Writes results to probe/output/ (report.md, report.json, screenshots).
Nothing large is downloaded: downloads are started, measured, and cancelled.
"""
import datetime as dt
import json
import os
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

OUT = Path(__file__).parent / "output"
SHOTS = OUT / "screenshots"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) permian-well-tracker-probe/0.1"}
DATA_EXT = re.compile(r"\.(zip|csv|txt|dat|xlsx?|mdb|accdb|json|gz|ebc|asc|dbf|shp|7z)(\?|$)", re.I)
FILE_IN_TEXT = re.compile(r"[\w\-. ()]+\.(?:zip|txt|csv|dat|ebc|gz|dbf|shp|json|7z)\b", re.I)

# Texas RRC managed-file-transfer links (from rrc.texas.gov "Data Sets Available for Download")
RRC = {
    "TX Drilling Permits - daily (lat/long)": "5f07cc72-2e79-4df8-ade1-9aeb792e03fc",
    "TX Drilling Permits - end of month (lat/long)": "f5dfea9c-bb39-4a5e-a44e-fb522e088cba",
    "TX Drilling Permit Master and Trailer (since 1976)": "beeeab0c-7d07-4111-af88-783c93677b2c",
    "TX Horizontal Drilling Permits": "c725637f-6748-47b9-ad74-e0396879d88b",
    "TX Drilling Permits Pending Approval": "0ad92a65-4212-49a1-98a7-d667a55fb497",
    "TX Completion Information (nightly)": "ed7ab066-879f-40b6-8144-2ae4b6810c04",
    "TX Full Wellbore (weekly)": "b070ce28-5c58-4fe2-9eb7-8b70befb7af9",
    "TX Wellbore Query Data (monthly)": "650649b7-e019-4d77-a8e0-d118d6455381",
    "TX Statewide API Data (ASCII)": "701db9a3-32b5-488d-812b-cd6ff7d0fe85",
    "TX Production Data Query Dump (CSV)": "1f5ddb8d-329a-4459-b7f8-177b4f5ee60d",
    "TX Production Report - Pending Leases": "941af606-dc16-44ef-9b1e-f942f36fc582",
    "TX Oil Detail Well": "f5ac3552-50ce-4959-844d-5079de0f1f62",
    "TX Oil Well Status (W-10)": "af355cae-e78b-4337-aba8-7ce57073dba3",
    "TX Gas Well Status (G-10)": "1363c373-fe71-4044-aa23-3c90cd162ff9",
    "TX P-5 Organization (operators)": "04652169-eed6-4396-9019-2e270e790f6c",
    "TX Well Layers by County (GIS)": "d551fb20-442e-4b67-84fa-ac3f23ecabb4",
}

# Pages to crawl for downloadable data links
CRAWL = {
    "FracFocus data download page": "https://www.fracfocus.org/data-download",
    "NM OCD statistics page": "https://www.emnrd.nm.gov/ocd/ocd-data/statistics/",
    "NM OCD home page": "https://www.emnrd.nm.gov/ocd/",
    "NM Tech GO-TECH all-wells page": "http://octane.nmt.edu/gotech/petroleum_data/allwells.aspx",
}

# ArcGIS items (feature services can be queried directly by API)
ARCGIS = {"NM OCD Oil and Gas Wells (ArcGIS Hub)": "387f397ebf164c7aa6a752aac7d22b17"}


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60]


def http_info(url, session=None, timeout=60):
    """HEAD (fallback: streamed GET) a URL; never downloads more than 4 KB."""
    s = session or requests.Session()
    info = {"url": url}
    try:
        r = s.head(url, headers=UA, allow_redirects=True, timeout=timeout)
        if r.status_code >= 400 or "content-length" not in r.headers:
            r = s.get(url, headers=UA, allow_redirects=True, timeout=timeout, stream=True)
            chunk = next(r.iter_content(4096), b"")
            info["first_bytes"] = chunk[:200].decode("latin-1", "replace")
            r.close()
        info.update(
            status=r.status_code,
            final_url=r.url,
            content_type=r.headers.get("content-type", ""),
            size_mb=round(int(r.headers["content-length"]) / 1e6, 1) if r.headers.get("content-length") else None,
            last_modified=r.headers.get("last-modified"),
        )
    except Exception as e:
        info["error"] = repr(e)[:300]
    return info


def probe_crawl(name, url):
    rec = {"source": name, "kind": "crawl", "page": http_info(url)}
    try:
        r = requests.get(url, headers=UA, timeout=60)
        soup = BeautifulSoup(r.text, "html.parser")
        links = []
        for a in soup.find_all("a", href=True):
            href = urljoin(r.url, a["href"])
            text = " ".join(a.get_text(" ").split())[:80]
            if DATA_EXT.search(href) or re.search(r"download|ftp|mft|data", href, re.I):
                links.append((text, href))
        seen, uniq = set(), []
        for t, h in links:
            if h not in seen:
                seen.add(h)
                uniq.append((t, h))
        rec["candidate_links"] = len(uniq)
        rec["files"] = [dict(text=t, **http_info(h)) for t, h in uniq[:40] if DATA_EXT.search(h)]
        rec["other_links"] = [{"text": t, "url": h} for t, h in uniq[:60] if not DATA_EXT.search(h)]
    except Exception as e:
        rec["error"] = repr(e)[:300]
    return rec


def probe_arcgis(name, item_id):
    rec = {"source": name, "kind": "arcgis"}
    try:
        item = requests.get(f"https://www.arcgis.com/sharing/rest/content/items/{item_id}?f=json",
                            headers=UA, timeout=60).json()
        svc = item.get("url")
        rec["service_url"] = svc
        rec["item_modified"] = item.get("modified")
        if svc:
            layer = svc if re.search(r"/\d+$", svc) else svc.rstrip("/") + "/0"
            meta = requests.get(f"{layer}?f=json", headers=UA, timeout=60).json()
            rec["fields"] = [f.get("name") for f in meta.get("fields", [])][:80]
            rec["edit_info"] = meta.get("editingInfo")
            cnt = requests.get(f"{layer}/query", params={"where": "1=1", "returnCountOnly": "true", "f": "json"},
                               headers=UA, timeout=60).json()
            rec["record_count"] = cnt.get("count")
    except Exception as e:
        rec["error"] = repr(e)[:300]
    return rec


def probe_rrc(page, context, name, uuid):
    url = f"https://mft.rrc.texas.gov/link/{uuid}"
    rec = {"source": name, "kind": "rrc_mft", "direct_http": http_info(url)}
    try:
        page.goto(url, wait_until="networkidle", timeout=90000)
        rec["title"] = page.title()
        text = page.inner_text("body")
        rec["page_text_excerpt"] = " ".join(text.split())[:600]
        rec["file_names_seen"] = sorted({f.strip() for f in FILE_IN_TEXT.findall(text)})[:60]
        shot = SHOTS / f"{slug(name)}.png"
        page.screenshot(path=str(shot), full_page=True)
        rec["screenshot"] = f"screenshots/{shot.name}"
        cands = page.locator("a, button").filter(has_text=re.compile(r"\.(zip|txt|csv|dat|ebc|gz|dbf|json)", re.I))
        rec["clickable_file_elements"] = cands.count()
        if rec["clickable_file_elements"]:
            with page.expect_download(timeout=60000) as dl_info:
                cands.first.click()
            dl = dl_info.value
            rec["download_url"] = dl.url
            rec["download_filename"] = dl.suggested_filename
            s = requests.Session()
            for c in context.cookies():
                s.cookies.set(c["name"], c["value"], domain=c["domain"])
            rec["download_http"] = http_info(dl.url, session=s)
            dl.cancel()
    except Exception as e:
        rec["error"] = repr(e)[:400]
    return rec


def verdict(rec):
    if rec["kind"] == "rrc_mft":
        if rec.get("download_url"):
            return "OK - scripted download works"
        if (rec["direct_http"].get("content_type") or "").startswith("application"):
            return "OK - direct file link"
        if rec.get("file_names_seen"):
            return "PARTIAL - files listed, download not triggered"
        return "CHECK - see screenshot/error"
    if rec["kind"] == "crawl":
        ok = [f for f in rec.get("files", []) if f.get("status") == 200]
        return f"OK - {len(ok)} data files reachable" if ok else "CHECK - no direct data files found"
    if rec["kind"] == "arcgis":
        return f"OK - API, {rec['record_count']} records" if rec.get("record_count") else "CHECK"
    return "?"


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    SHOTS.mkdir(parents=True)
    results = []
    for n, u in CRAWL.items():
        print("crawl:", n, flush=True)
        results.append(probe_crawl(n, u))
    for n, i in ARCGIS.items():
        print("arcgis:", n, flush=True)
        results.append(probe_arcgis(n, i))
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            context = browser.new_context(accept_downloads=True, user_agent=UA["User-Agent"])
            page = context.new_page()
            for n, u in RRC.items():
                print("rrc:", n, flush=True)
                results.append(probe_rrc(page, context, n, u))
            browser.close()
    except Exception as e:
        results.append({"source": "Playwright (browser) setup", "kind": "setup", "error": repr(e)[:400]})

    for r in results:
        r["verdict"] = verdict(r) if r["kind"] != "setup" else "ERROR"

    du = shutil.disk_usage("/")
    env = {
        "run_utc": dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "python": sys.version.split()[0],
        "disk_free_gb": round(du.free / 1e9, 1),
        "runner": os.environ.get("RUNNER_OS", "local"),
    }
    (OUT / "report.json").write_text(json.dumps({"environment": env, "results": results}, indent=2, default=str))

    lines = [f"# Source probe report - {env['run_utc']}", "",
             f"Runner: {env['runner']} | Python {env['python']} | Free disk: {env['disk_free_gb']} GB", "",
             "| Source | Verdict | Size (MB) | Note |", "|---|---|---|---|"]
    for r in results:
        size = r.get("download_http", {}).get("size_mb") or r.get("direct_http", {}).get("size_mb") or ""
        note = r.get("error") or r.get("download_filename") or ", ".join(r.get("file_names_seen", [])[:3]) or ""
        lines.append(f"| {r['source']} | {r['verdict']} | {size} | {str(note)[:120].replace('|', '/')} |")
    lines += ["", "Full details: report.json. Browser screenshots: screenshots/."]
    md = "\n".join(lines)
    (OUT / "report.md").write_text(md)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(md)
    print(md)


if __name__ == "__main__":
    main()
