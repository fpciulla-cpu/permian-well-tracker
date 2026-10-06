# Diagnostic probe v2 - 2026-10-06 16:55 UTC

## A) Texas RRC connectivity

| Target | Variant | Result | Error |
|---|---|---|---|
| RRC main website | default | 200 | ip=150.171.109.150 | 0.536863s |  |
| RRC data-sets page | default | 200 | ip=150.171.109.150 | 0.404802s |  |
| MFT root (https) | default | 302 | ip=52.238.113.119 | 1.242246s |  |
| MFT root (https) | browser UA | 302 | ip=52.238.113.119 | 0.995558s |  |
| MFT root (https) | TLS 1.2 only | 302 | ip=52.238.113.119 | 1.102582s |  |
| MFT root (https) | HTTP/1.1 | 302 | ip=52.238.113.119 | 1.087430s |  |
| MFT root (http) | default | 000 | ip=52.238.113.119 | 30.001035s | curl: (28) Operation timed out after 30001 milliseconds with 0 bytes received |
| MFT root (http) | browser UA | 000 | ip=52.238.113.119 | 30.002294s | curl: (28) Operation timed out after 30002 milliseconds with 0 bytes received |
| MFT root (http) | TLS 1.2 only | 000 | ip=52.238.113.119 | 30.001669s | curl: (28) Operation timed out after 30001 milliseconds with 0 bytes received |
| MFT root (http) | HTTP/1.1 | 000 | ip=52.238.113.119 | 30.001258s | curl: (28) Operation timed out after 30001 milliseconds with 0 bytes received |
| MFT permit link | default | 200 | ip=52.238.113.119 | 1.160414s |  |
| MFT permit link | browser UA | 200 | ip=52.238.113.119 | 1.079084s |  |
| MFT permit link | TLS 1.2 only | 200 | ip=52.238.113.119 | 1.289181s |  |
| MFT permit link | HTTP/1.1 | 200 | ip=52.238.113.119 | 1.118605s |  |
| RRC webapps (PDQ online) | default | 200 | ip=168.44.248.181 | 0.357137s |  |
| RRC GIS viewer | default | 200 | ip=168.44.248.173 | 0.228408s |  |
| RRC GIS REST (server) | default | 200 | ip=168.44.248.173 | 0.237803s |  |
| RRC GIS REST (arcgis) | default | 404 | ip=168.44.248.173 | 0.182642s |  |

MFT retry after 45s: {'rc': 0, 'out': '200', 'err': ''}

## B) New Mexico OCD

Latest dates: {'max_spud': 253402214400000, 'max_lastprod': 253402214400000, 'max_spud_utc': '9999-12-31', 'max_lastprod_utc': '9999-12-31'}

Eddy+Lea spuds by year: {'2010': 906, '2011': 1094, '2012': 1181, '2013': 1105, '2014': 1200, '2015': 687, '2016': 377, '2017': 897, '2018': 1211, '2019': 1344, '2020': 993, '2021': 1500, '2022': 1703, '2023': 1702, '2024': 1880, '2025': 1927, '2026': 1081, '9999': 29341}

## C) FracFocus

Zip: 442.2 MB, download 9s, scan 49s
Latest job end date: 2026-09-29
Permian jobs by state/year: {'TEXAS': {'2014': 7118, '2015': 3823, '2016': 2633, '2017': 3979, '2018': 5036, '2019': 5125, '2020': 2843, '2021': 4124, '2022': 4670, '2023': 4650, '2024': 4410, '2025': 4162, '2026': 2280, '3012': 1}, 'NEW MEXICO': {'2014': 559, '2015': 535, '2016': 320, '2017': 561, '2018': 1023, '2019': 1064, '2020': 847, '2021': 1318, '2022': 1660, '2023': 1679, '2024': 1878, '2025': 1921, '2026': 1168}}

Full details: report_v2.json