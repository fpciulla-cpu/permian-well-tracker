"""
Permian Well Tracker - Texas access monitor
Runs every 2 hours. Measures how often the RRC download server accepts connections from
GitHub's servers, and captures what we need to build the Texas downloader:
  - output/tx_monitor_log.csv       one line per attempt (time, runner IP, result)
  - output/tx_pages/*.html          download-page HTML whenever a connection succeeds
  - output/tx_download_proof.json   first successful end-to-end file download (browser method)
  - output/tx_gis_wells.json        fields/count of the RRC public "Well Locations" map layer (once)
"""
import csv
import datetime as dt
import json
import re
import subprocess
from pathlib import Path

import requests

OUT = Path(__file__).parent / "output"
PAGES = OUT / "tx_pages"
PAGES.mkdir(parents=True, exist_ok=True)
LOG = OUT / "tx_monitor_log.csv"
PROOF = OUT / "tx_download_proof.json"
GIS_OUT = OUT / "tx_gis_wells.json"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
LINKS = {
    "drilling-permits-daily": "5f07cc72-2e79-4df8-ade1-9aeb792e03fc",
    "completions-nightly": "ed7ab066-879f-40b6-8144-2ae4b6810c04",
    "p5-organization": "04652169-eed6-4396-9019-2e270e790f6c",
}
GIS_SVC = "https://gis.rrc.texas.gov/server/rest/services/rrc_public/RRC_Public_Viewer_Srvs/MapServer"
FILE_RE = re.compile(r"\.(zip|txt|csv|dat|ebc|gz|dbf|json|asc)\b", re.I)


def runner_ip():
    try:
        j = requests.get("https://ipinfo.io/json", timeout=15).json()
        return j.get("ip", ""), j.get("city", ""), j.get("org", "")
    except Exception:
        return "", "", ""


def curl_page(name, uuid):
    tmp = PAGES / f"{name}.tmp"
    p = subprocess.run(["curl", "-sSL", "--max-time", "60", "--retry", "2", "-A", UA, "-o", str(tmp),
                        "-w", "%{http_code}", f"https://mft.rrc.texas.gov/link/{uuid}"],
                       capture_output=True, text=True)
    code = p.stdout.strip()
    if code == "200" and tmp.exists() and tmp.stat().st_size > 500:
        tmp.replace(PAGES / f"{name}.html")
    else:
        tmp.unlink(missing_ok=True)
    return code, p.stderr.strip()[:150]


def browser_download():
    rec = {"utc": dt.datetime.utcnow().isoformat(timespec="minutes")}
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx = b.new_context(accept_downloads=True, user_agent=UA)
        page = ctx.new_page()
        page.goto(f"https://mft.rrc.texas.gov/link/{LINKS['drilling-permits-daily']}",
                  wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(3000)
        (PAGES / "drilling-permits-daily-rendered.html").write_text(page.content())
        page.screenshot(path=str(OUT / "tx_download_page.png"), full_page=True)
        els = page.locator("a, button, [role=button], [onclick]")
        rec["clickables"] = []
        target = None
        for i in range(min(els.count(), 80)):
            e = els.nth(i)
            try:
                t = e.inner_text()[:80]
                rec["clickables"].append({"text": t, "href": e.get_attribute("href"), "id": e.get_attribute("id")})
                if target is None and FILE_RE.search(t):
                    target = e
            except Exception:
                pass
        if target is not None:
            with page.expect_download(timeout=180000) as info:
                target.click()
            dl = info.value
            path = Path("/tmp") / dl.suggested_filename
            dl.save_as(str(path))
            rec.update(download_url=dl.url, filename=dl.suggested_filename,
                       size_mb=round(path.stat().st_size / 1e6, 2))
            with open(path, "rb") as fh:
                rec["first_bytes"] = fh.read(400).decode("latin-1", "replace")
        b.close()
    return rec


def gis_wells():
    svc = requests.get(f"{GIS_SVC}?f=json", headers={"User-Agent": UA}, timeout=60).json()
    lid = next(l["id"] for l in svc.get("layers", []) if l.get("name") == "Well Locations")
    meta = requests.get(f"{GIS_SVC}/{lid}?f=json", headers={"User-Agent": UA}, timeout=60).json()
    cnt = requests.get(f"{GIS_SVC}/{lid}/query", params={"where": "1=1", "returnCountOnly": "true", "f": "json"},
                       headers={"User-Agent": UA}, timeout=60).json()
    sample = requests.get(f"{GIS_SVC}/{lid}/query", params={"where": "1=1", "outFields": "*", "returnGeometry": "false",
                                                              "resultRecordCount": 3, "f": "json"},
                          headers={"User-Agent": UA}, timeout=60).json()
    return {"layer_id": lid, "fields": [(f["name"], f["type"]) for f in meta.get("fields", [])],
            "max_record_count": meta.get("maxRecordCount"), "count": cnt.get("count", cnt),
            "sample": [f.get("attributes") for f in sample.get("features", [])] or sample}


def main():
    now = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    ip, city, org = runner_ip()
    rows, ok = [], False
    for name, uuid in LINKS.items():
        code, err = curl_page(name, uuid)
        ok |= code == "200"
        rows.append([now, ip, city, org, name, code, err])
    new = not LOG.exists()
    with open(LOG, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["utc", "runner_ip", "city", "org", "dataset", "http_code", "error"])
        w.writerows(rows)
    print("\n".join(" | ".join(map(str, r)) for r in rows))

    if ok and not PROOF.exists():
        try:
            PROOF.write_text(json.dumps(browser_download(), indent=2))
        except Exception as e:
            (OUT / "tx_download_attempt_error.txt").write_text(f"{now} {e!r}"[:1000])
    if not GIS_OUT.exists():
        try:
            GIS_OUT.write_text(json.dumps(gis_wells(), indent=2, default=str))
        except Exception as e:
            (OUT / "tx_gis_error.txt").write_text(f"{now} {e!r}"[:1000])


if __name__ == "__main__":
    main()
