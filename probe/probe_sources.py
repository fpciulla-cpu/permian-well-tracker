"""
Permian Well Tracker - Step 1b: Diagnostic probe (v2)
-----------------------------------------------------
A) Texas RRC connectivity diagnosis (why downloads are refused from GitHub)
B) New Mexico OCD well service: freshness and spud counts (Eddy/Lea)
C) FracFocus CSV: structure, Permian job counts by state/year, latest job date
Writes probe/output/report_v2.md and report_v2.json
"""
import csv
import datetime as dt
import io
import json
import os
import re
import subprocess
import time
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import requests

OUT = Path(__file__).parent / "output"
OUT.mkdir(parents=True, exist_ok=True)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
TMP = Path("/tmp/probe")
TMP.mkdir(exist_ok=True)

NM_LAYER = "https://gis.emnrd.nm.gov/arcgis/rest/services/OCDView/Wells_Public/FeatureServer/0"
FF_CSV = "https://www.fracfocusdata.org/digitaldownload/FracFocusCSV.zip"

# Provisional Permian county list (to be replaced by the formal basin map)
TX_PERMIAN = {
    "ANDREWS", "BORDEN", "COCHRAN", "COKE", "CRANE", "CROCKETT", "CULBERSON", "DAWSON", "ECTOR", "GAINES",
    "GARZA", "GLASSCOCK", "HOCKLEY", "HOWARD", "IRION", "JEFF DAVIS", "LOVING", "LYNN", "MARTIN", "MIDLAND",
    "MITCHELL", "PECOS", "REAGAN", "REEVES", "SCHLEICHER", "SCURRY", "STERLING", "TERRY", "TOM GREEN",
    "UPTON", "WARD", "WINKLER", "YOAKUM", "KENT", "NOLAN",
}
NM_PERMIAN = {"EDDY", "LEA", "CHAVES", "ROOSEVELT"}


def run(cmd, timeout=60):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {"rc": p.returncode, "out": p.stdout.strip()[-300:], "err": p.stderr.strip()[-300:]}
    except Exception as e:
        return {"rc": -1, "err": repr(e)[:300]}


# ---------------- A) Texas RRC diagnosis ----------------
def texas():
    res = {"runner_ip": run(["curl", "-s", "--max-time", "20", "https://ipinfo.io/json"])}
    urls = {
        "RRC main website": "https://www.rrc.texas.gov/",
        "RRC data-sets page": "https://www.rrc.texas.gov/resource-center/research/data-sets-available-for-download/",
        "MFT root (https)": "https://mft.rrc.texas.gov/",
        "MFT root (http)": "http://mft.rrc.texas.gov/",
        "MFT permit link": "https://mft.rrc.texas.gov/link/beeeab0c-7d07-4111-af88-783c93677b2c",
        "RRC webapps (PDQ online)": "https://webapps2.rrc.texas.gov/EWA/ewaPdqMain.do",
        "RRC GIS viewer": "https://gis.rrc.texas.gov/GISViewer/",
        "RRC GIS REST (server)": "https://gis.rrc.texas.gov/server/rest/services?f=json",
        "RRC GIS REST (arcgis)": "https://gis.rrc.texas.gov/arcgis/rest/services?f=json",
    }
    variants = {
        "default": [],
        "browser UA": ["-A", UA],
        "TLS 1.2 only": ["--tlsv1.2", "--tls-max", "1.2", "-A", UA],
        "HTTP/1.1": ["--http1.1", "-A", UA],
    }
    matrix = []
    for name, url in urls.items():
        for vname, flags in variants.items():
            if vname != "default" and "MFT" not in name:
                continue  # full matrix only for the download server
            r = run(["curl", "-sS", "-o", "/dev/null", "--max-time", "30", "-w",
                     "%{http_code} | ip=%{remote_ip} | %{time_total}s", *flags, url], timeout=45)
            matrix.append({"target": name, "variant": vname, "url": url,
                           "result": r.get("out") or "", "error": r.get("err") or ""})
    res["matrix"] = matrix
    res["tls_handshake"] = run(["bash", "-c",
                                "echo | timeout 20 openssl s_client -connect mft.rrc.texas.gov:443 "
                                "-servername mft.rrc.texas.gov 2>&1 | head -25"])
    time.sleep(45)
    res["mft_retry_after_45s"] = run(["curl", "-sS", "-o", "/dev/null", "--max-time", "30", "-A", UA, "-w",
                                      "%{http_code}", "https://mft.rrc.texas.gov/link/beeeab0c-7d07-4111-af88-783c93677b2c"])
    # If an RRC GIS REST endpoint answers, list its services
    for k in ("RRC GIS REST (server)", "RRC GIS REST (arcgis)"):
        try:
            j = requests.get(urls[k], headers={"User-Agent": UA}, timeout=30).json()
            res.setdefault("gis_services", {})[k] = {"folders": j.get("folders"),
                                                     "services": [s.get("name") for s in j.get("services", [])][:50]}
        except Exception as e:
            res.setdefault("gis_services", {})[k] = {"error": repr(e)[:200]}
    return res


# ---------------- B) New Mexico OCD ----------------
def nm_query(params):
    base = {"f": "json", "where": "1=1"}
    base.update(params)
    r = requests.get(f"{NM_LAYER}/query", params=base, headers={"User-Agent": UA}, timeout=90)
    return r.json()


def new_mexico():
    res = {}
    try:
        meta = requests.get(f"{NM_LAYER}?f=json", headers={"User-Agent": UA}, timeout=60).json()
        res["field_types"] = {f["name"]: f["type"].replace("esriFieldType", "") for f in meta.get("fields", [])}
        res["max_record_count"] = meta.get("maxRecordCount")
        res["supports_statistics"] = meta.get("advancedQueryCapabilities", {}).get("supportsStatistics")
    except Exception as e:
        res["meta_error"] = repr(e)[:300]

    def stat(where, out):
        return nm_query({"where": where, "outStatistics": json.dumps(out)})

    try:
        j = stat("1=1", [{"statisticType": "max", "onStatisticField": "spud_date", "outStatisticFieldName": "max_spud"},
                         {"statisticType": "max", "onStatisticField": "last_production_date",
                          "outStatisticFieldName": "max_lastprod"}])
        feats = j.get("features", [{}])
        a = feats[0].get("attributes", {}) if feats else j
        for k, v in list(a.items()):
            if isinstance(v, (int, float)) and v > 1e11:
                a[k + "_utc"] = dt.datetime.utcfromtimestamp(v / 1000).strftime("%Y-%m-%d")
        res["latest_dates"] = a
    except Exception as e:
        res["latest_dates_error"] = repr(e)[:300]

    # Distinct county values (to learn the format)
    try:
        j = nm_query({"outStatistics": json.dumps([{"statisticType": "count", "onStatisticField": "OBJECTID",
                                                    "outStatisticFieldName": "n"}]),
                      "groupByFieldsForStatistics": "county"})
        res["counties"] = {f["attributes"]["county"]: f["attributes"]["n"] for f in j.get("features", [])}
    except Exception as e:
        res["counties_error"] = repr(e)[:300]

    # Spuds by year, Eddy + Lea
    where = "UPPER(county) IN ('EDDY','LEA')"
    try:
        j = nm_query({"where": where,
                      "outStatistics": json.dumps([{"statisticType": "count", "onStatisticField": "OBJECTID",
                                                    "outStatisticFieldName": "n"}]),
                      "groupByFieldsForStatistics": "year_spudded"})
        rows = {str(f["attributes"]["year_spudded"]): f["attributes"]["n"] for f in j.get("features", [])}
        res["eddy_lea_spuds_by_year"] = {y: rows[y] for y in sorted(rows) if y not in ("None", "") and y >= "2010"}
        if not j.get("features"):
            res["eddy_lea_raw"] = j
    except Exception as e:
        res["eddy_lea_error"] = repr(e)[:300]

    # Status and type mix (Eddy + Lea)
    for fld in ("status", "type"):
        try:
            j = nm_query({"where": where,
                          "outStatistics": json.dumps([{"statisticType": "count", "onStatisticField": "OBJECTID",
                                                        "outStatisticFieldName": "n"}]),
                          "groupByFieldsForStatistics": fld})
            res[f"eddy_lea_by_{fld}"] = {str(f["attributes"][fld]): f["attributes"]["n"] for f in j.get("features", [])}
        except Exception as e:
            res[f"eddy_lea_by_{fld}_error"] = repr(e)[:300]

    # Five most recent spuds (sample records)
    try:
        j = nm_query({"where": where + " AND spud_date IS NOT NULL", "orderByFields": "spud_date DESC",
                      "resultRecordCount": 5, "returnGeometry": "false",
                      "outFields": "id,name,ogrid_name,county,type,status,spud_date,last_production_date"})
        recs = []
        for f in j.get("features", []):
            a = f["attributes"]
            for k in ("spud_date", "last_production_date"):
                if isinstance(a.get(k), (int, float)):
                    a[k] = dt.datetime.utcfromtimestamp(a[k] / 1000).strftime("%Y-%m-%d")
            recs.append(a)
        res["latest_spuds_sample"] = recs or j
    except Exception as e:
        res["sample_error"] = repr(e)[:300]
    return res


# ---------------- C) FracFocus ----------------
def fracfocus():
    res = {}
    zpath = TMP / "ff.zip"
    t0 = time.time()
    try:
        with requests.get(FF_CSV, headers={"User-Agent": UA}, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(zpath, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
        res["download_seconds"] = round(time.time() - t0)
        res["zip_mb"] = round(zpath.stat().st_size / 1e6, 1)
    except Exception as e:
        res["download_error"] = repr(e)[:300]
        return res

    z = zipfile.ZipFile(zpath)
    res["members"] = [{"name": i.filename, "mb": round(i.file_size / 1e6, 1)} for i in z.infolist()][:80]
    headers = {}
    jobs = {}           # key -> (state, county, year, operator)
    max_end = ""
    t1 = time.time()
    for info in z.infolist():
        if not info.filename.lower().endswith(".csv"):
            continue
        with z.open(info) as fh:
            rd = csv.reader(io.TextIOWrapper(fh, encoding="utf-8", errors="replace", newline=""))
            hdr = next(rd, [])
            headers[info.filename] = hdr
            idx = {h.strip().lower(): i for i, h in enumerate(hdr)}
            need = ("jobenddate", "statename", "countyname")
            if not all(n in idx for n in need):
                continue
            key_col = idx.get("disclosureid", idx.get("pkey", idx.get("uploadkey", idx.get("apinumber"))))
            iy, ist, ico = idx["jobenddate"], idx["statename"], idx["countyname"]
            iop = idx.get("operatorname")
            for row in rd:
                if len(row) <= max(iy, ist, ico):
                    continue
                st = row[ist].strip().upper()
                if st not in ("TEXAS", "NEW MEXICO"):
                    continue
                co = row[ico].strip().upper().replace(" COUNTY", "")
                if co not in (TX_PERMIAN if st == "TEXAS" else NM_PERMIAN):
                    continue
                key = row[key_col] if key_col is not None else (row[idx.get("apinumber", 0)], row[iy])
                if key in jobs:
                    continue
                d = row[iy].strip()
                m = re.search(r"(\d{4})", d.split(" ")[0][-4:]) or re.search(r"(\d{4})", d)
                yr = m.group(1) if m else "?"
                jobs[key] = (st, co, yr, row[iop].strip() if iop is not None else "")
                try:
                    iso = dt.datetime.strptime(d.split(" ")[0], "%m/%d/%Y").strftime("%Y-%m-%d")
                except ValueError:
                    iso = d[:10]
                if iso > max_end and iso <= dt.date.today().isoformat():
                    max_end = iso
    res["scan_seconds"] = round(time.time() - t1)
    res["headers_first_file"] = next(iter(headers.values()), [])
    res["files_scanned"] = len(headers)
    res["permian_jobs_total"] = len(jobs)
    res["latest_job_end_date"] = max_end
    by = defaultdict(Counter)
    for st, co, yr, op in jobs.values():
        by[st][yr] += 1
    res["permian_jobs_by_state_year"] = {st: {y: c[y] for y in sorted(c) if y >= "2014"} for st, c in by.items()}
    recent = Counter(op for st, co, yr, op in jobs.values() if yr in ("2025", "2026"))
    res["top_operators_2025_2026"] = recent.most_common(15)
    zpath.unlink(missing_ok=True)
    return res


def main():
    report = {"run_utc": dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}
    for name, fn in (("texas", texas), ("new_mexico", new_mexico), ("fracfocus", fracfocus)):
        print("running", name, flush=True)
        try:
            report[name] = fn()
        except Exception as e:
            report[name] = {"fatal_error": repr(e)[:400]}
    (OUT / "report_v2.json").write_text(json.dumps(report, indent=2, default=str))

    tx, nm, ff = report["texas"], report["new_mexico"], report["fracfocus"]
    L = [f"# Diagnostic probe v2 - {report['run_utc']}", "", "## A) Texas RRC connectivity", "",
         "| Target | Variant | Result | Error |", "|---|---|---|---|"]
    for m in tx.get("matrix", []):
        L.append(f"| {m['target']} | {m['variant']} | {m['result']} | {m['error'][:90].replace('|', '/')} |")
    L += ["", f"MFT retry after 45s: {tx.get('mft_retry_after_45s')}", "",
          "## B) New Mexico OCD", "", f"Latest dates: {nm.get('latest_dates', nm.get('latest_dates_error'))}", "",
          f"Eddy+Lea spuds by year: {nm.get('eddy_lea_spuds_by_year', nm.get('eddy_lea_error'))}", "",
          "## C) FracFocus", "",
          f"Zip: {ff.get('zip_mb')} MB, download {ff.get('download_seconds')}s, scan {ff.get('scan_seconds')}s",
          f"Latest job end date: {ff.get('latest_job_end_date')}",
          f"Permian jobs by state/year: {ff.get('permian_jobs_by_state_year', ff.get('download_error'))}", "",
          "Full details: report_v2.json"]
    md = "\n".join(L)
    (OUT / "report_v2.md").write_text(md)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(md)
    print(md)


if __name__ == "__main__":
    main()
