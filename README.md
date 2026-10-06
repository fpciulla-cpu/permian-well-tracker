# Permian Well Tracker

Automated tracker of Permian Basin wells **drilled (spuds)**, **completed**, and **active**, segmented by
basin, operator, and product type, built entirely from public sources:

- Texas Railroad Commission (RRC): drilling permits, completions, wellbore, production
- New Mexico Oil Conservation Division (OCD): well data and C-115 production
- FracFocus: hydraulic-fracturing (completion) disclosures

Pipelines run on a schedule with GitHub Actions; no manual downloads.

## Status
- Step 1 (current): **Source probe** - confirms every source can be fetched by a script.
  Run it from the **Actions** tab -> "01 - Source probe" -> "Run workflow".
  Results are saved to `probe/output/report.md`.

## Agreed definitions (pilot)
- Drilled well: new wellbore with a spud date (re-entries/recompletions tracked separately)
- Completed well: first FracFocus job end date; RRC/OCD completion date as fallback
- Active well: production > 0 in the month (administrative status kept as secondary field)
- Product class: Oil if oil > 50% of BOE (6:1) over first 12 months, else Gas; state label retained
- Operator: as-reported name, current parent (M&A roll-ups), archetype
- Basins: Delaware, Midland, Central Basin Platform, Other Permian
- History: 2014 to present

Note: no licensed (e.g., Enverus) data is ever stored in this repository.
