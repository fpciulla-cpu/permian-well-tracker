"""
Permian Well Tracker - Step 1c: Probe v3
A) Texas RRC: capture download-page structure and attempt one real end-to-end file download
B) New Mexico OCD: true data freshness (ignoring 9999-12-31 placeholders), 2026 spuds by month
C) Texas RRC public GIS services: list what is available as an alternative route
Writes probe/output/report_v3.md, report_v3.json, tx_pages/*.html, screenshots/*.png
"""
import datetime as dt
import json
import os
import re
import subprocess
from pathlib import Path

import requests

OUT = Path(__file__).parent / "output"
PAGES = OUT / "tx_pages"
SHOTS = OUT / "screenshots"
for d in (OUT, PAGES, SHOTS):
    d.mkdir(parents=True, exist_ok=True)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
NM_LAYER = "https://gis.emnrd.nm.gov/arcgis/rest/services/OCDView/Wells_Public/FeatureServer/0"
RRC_GIS = "https://gis.rrc.texas.gov/server/rest/services"
TX_LINKS = {
    "drilling-permits-daily": "5f07cc72-2e79-4df8-ade1-9aeb792e03fc",
    "completions-nightly": "ed7ab066-879f-40b6-8144-2ae4b6810c04",
    "p5-organization": "04652169-eed6-4396-9019-2e270e790f6c",
}
FILE_RE = re.compile(r"\.(zip|txt|csv|dat|ebc|gz|dbf|json|asc)\b", re.I)


def ms_to_date(v):
    return dt.datetime.utcfromtimestamp(v / 1000).strftime("%Y-%m-%d") if isinstance(v, (int, float)) else v


# ---------------- A) Texas ----------------
def texas():
    res = {}
    for name, uuid in TX_LINKS.items():
        url = f"https://mft.rrc.texas.gov/link/{uuid}"
        p = subprocess.run(["curl", "-sSL", "--max-time", "60", "-A", UA, "-o", str(PAGES / f"{name}.html"),
                            "-w", "%{http_code} %{size_download}", url], capture_output=True, text=True)
        res[name] = {"curl_page": (p.stdout + " " + p.stderr).strip()[:300]}
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            ctx = browser.new_context(accept_downloads=True, user_agent=UA)
            page = ctx.new_page()
            for name, uuid in TX_LINKS.items():
                r = res[name]
                try:
                    page.goto(f"https://mft.rrc.texas.gov/link/{uuid}", wait_until="networkidle", timeout=90000)
                    page.wait_for_timeout(3000)
                    page.screenshot(path=str(SHOTS / f"v3-{name}.png"), full_page=True)
                    (PAGES / f"{name}-rendered.html").write_text(page.content())
                    els = page.locator("a, button, [role=button], [onclick]")
                    items = []
                    for i in range(min(els.count(), 80)):
                        e = els.nth(i)
                        try:
                            items.append({"tag": e.evaluate("x => x.tagName"), "text": e.inner_text()[:80],
                                          "href": e.get_attribute("href"), "id": e.get_attribute("id")})
                        except Exception:
                            pass
                    r["clickables"] = items
                    target = None
                    for i in range(els.count()):
                        try:
                            if FILE_RE.search(els.nth(i).inner_text()):
                                target = els.nth(i)
                                break
                        except Exception:
                            pass
                    if target is None:
                        r["download"] = "no file-named element found"
                        continue
                    with page.expect_download(timeout=180000) as info:
                        target.click()
                    dl = info.value
                    r["download_url"] = dl.url
                    r["download_filename"] = dl.suggested_filename
                    if True:
                        path = Path("/tmp") / dl.suggested_filename
                        dl.save_as(str(path))
                        r["downloaded_mb"] = round(path.stat().st_size / 1e6, 2)
                        with open(path, "rb") as fh:
                            r["first_bytes"] = fh.read(300).decode("latin-1", "replace")
                        # Can the same URL be fetched without a browser (cookies passed to curl)?
                        cookie = "; ".join(f"{c['name']}={c['value']}" for c in ctx.cookies())
                        p = subprocess.run(["curl", "-sSL", "--max-time", "60", "-A", UA, "-H", f"Cookie: {cookie}",
                                            "-o", "/dev/null", "-w", "%{http_code} %{size_download} %{content_type}",
                                            dl.url], capture_output=True, text=True)
                        r["curl_replay_of_download_url"] = (p.stdout + " " + p.stderr).strip()[:300]
                except Exception as e:
                    r["error"] = repr(e)[:400]
            browser.close()
    except Exception as e:
        res["playwright_error"] = repr(e)[:400]
    return res


# ---------------- B) New Mexico ----------------
def nm_q(params):
    base = {"f": "json", "where": "1=1"}
    base.update(params)
    return requests.get(f"{NM_LAYER}/query", params=base, headers={"User-Agent": UA}, timeout=90).json()


def new_mexico():
    res = {}
    valid = "spud_date < DATE '2100-01-01'"
    el = "UPPER(county) IN ('EDDY','LEA')"
    try:
        j = nm_q({"where": f"{valid} AND last_production_date < DATE '2100-01-01'", "outStatistics": json.dumps([
            {"statisticType": "max", "onStatisticField": "spud_date", "outStatisticFieldName": "max_spud"},
            {"statisticType": "max", "onStatisticField": "last_production_date", "outStatisticFieldName": "max_prod"}])})
        a = j["features"][0]["attributes"] if j.get("features") else j
        res["latest_valid_dates"] = {k: ms_to_date(v) for k, v in a.items()}
    except Exception as e:
        res["latest_error"] = repr(e)[:300]
    try:
        j = nm_q({"where": f"{el} AND spud_date >= DATE '2026-01-01' AND {valid}", "returnGeometry": "false",
                  "outFields": "spud_date", "resultRecordCount": 6000})
        months = {}
        for f in j.get("features", []):
            m = ms_to_date(f["attributes"]["spud_date"])[:7]
            months[m] = months.get(m, 0) + 1
        res["eddy_lea_spuds_2026_by_month"] = dict(sorted(months.items()))
    except Exception as e:
        res["monthly_error"] = repr(e)[:300]
    try:
        j = nm_q({"where": f"{el} AND last_production_date >= DATE '2026-01-01' AND last_production_date < DATE '2100-01-01'",
                  "outStatistics": json.dumps([{"statisticType": "count", "onStatisticField": "OBJECTID",
                                                "outStatisticFieldName": "n"}]),
                  "groupByFieldsForStatistics": "type"})
        res["eddy_lea_wells_producing_in_2026_by_type"] = {f["attributes"]["type"]: f["attributes"]["n"]
                                                           for f in j.get("features", [])}
    except Exception as e:
        res["producing_error"] = repr(e)[:300]
    return res


# ---------------- C) Texas GIS ----------------
def tx_gis():
    res = {}
    for folder in ("rrc_public", "Hosted"):
        try:
            j = requests.get(f"{RRC_GIS}/{folder}?f=json", headers={"User-Agent": UA}, timeout=60).json()
            svcs = []
            for s in j.get("services", [])[:40]:
                entry = {"name": s["name"], "type": s["type"]}
                try:
                    m = requests.get(f"{RRC_GIS}/{s['name']}/{s['type']}?f=json", headers={"User-Agent": UA},
                                     timeout=60).json()
                    entry["layers"] = [l.get("name") for l in m.get("layers", [])][:30]
                except Exception as e:
                    entry["error"] = repr(e)[:150]
                svcs.append(entry)
            res[folder] = svcs or j
        except Exception as e:
            res[folder] = {"error": repr(e)[:300]}
    return res


def main():
    rep = {"run_utc": dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}
    for k, fn in (("texas", texas), ("new_mexico", new_mexico), ("tx_gis", tx_gis)):
        print("running", k, flush=True)
        try:
            rep[k] = fn()
        except Exception as e:
            rep[k] = {"fatal_error": repr(e)[:400]}
    (OUT / "report_v3.json").write_text(json.dumps(rep, indent=2, default=str))
    L = [f"# Probe v3 - {rep['run_utc']}", "", "## Texas downloads"]
    for name in TX_LINKS:
        r = rep["texas"].get(name, {})
        L.append(f"- {name}: file={r.get('download_filename')} size_mb={r.get('downloaded_mb')} "
                 f"curl_replay={r.get('curl_replay_of_download_url')} error={r.get('error') or r.get('download', '')}")
    L += ["", "## New Mexico", json.dumps(rep["new_mexico"], default=str), "", "## Texas GIS (service names)",
          json.dumps({k: [s.get('name') for s in v] if isinstance(v, list) else v for k, v in rep["tx_gis"].items()})]
    md = "\n".join(L)
    (OUT / "report_v3.md").write_text(md)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(md)
    print(md)


if __name__ == "__main__":
    main()
