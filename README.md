# Tourism Analytics - Integrated ETL + OLAP

This is a runnable Advanced Database Management Technologies (ADMT) CA2
practical implementation. It integrates fictional educational tourism records
from CSV, Excel, and JSON sources into a SQLite star schema, executes eight
analytical queries, and generates three Matplotlib charts.

The datasets are fictional sample data for demonstration and are not official
tourism statistics.

## Requirements

- Python 3.10 or newer
- pandas, matplotlib, and openpyxl (installed from `requirements.txt`)
- SQLite support included with Python

## Folder structure

```text
TourismAnalytics_CA2/
|-- tourism.py
|-- run_project.bat
|-- requirements.txt
|-- data/
|   |-- visits.csv
|   |-- destinations.xlsx
|   `-- hotels.json
|-- sql/olap_queries.sql
|-- charts/                         Generated PNG charts
|-- tourism.db                      Generated SQLite warehouse
`-- REPORT_RESULTS.md               Generated execution evidence
```

## Installation and execution

From this folder in a VS Code terminal:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe tourism.py
```

If the `py` launcher is unavailable, use an installed `python` command in the
first two commands. The script reads all source files, recreates the warehouse
inside a transaction, executes every query, saves charts, and writes
`REPORT_RESULTS.md`.

### One-click Windows run

Double-click `run_project.bat`, or run it from Command Prompt. It changes to
its own directory, creates `.venv` if necessary, checks imports, installs
requirements only when the imports are missing, runs the project, preserves
the exit code, and pauses so the output can be read.

## ETL process

1. **Extract:** read visits from CSV, destination metadata from Excel, and
   hotel details from JSON.
2. **Transform:** standardize names, parse dates, coerce numeric values,
   remove duplicate visit IDs, reject invalid required records, derive month,
   quarter, year, and season, and calculate expenditure per visitor safely.
3. **Validate relationships:** unmatched visit destinations are reported and
   are not loaded into the fact table without dimension metadata.
4. **Load:** insert cleaned source rows into constrained staging tables,
   populate dimensions, map surrogate keys, and insert facts with foreign
   keys. Rerunning the script recreates the generated tables, so facts are not
   duplicated.

The source repeats each destination/month hotel amount on both visitor-category
rows. The ETL divides that amount across the rows before loading so hotel
revenue is not double-counted. The JSON room rates and rooms sold remain in
staging for source comparison; the fact measure uses the monthly source
estimate.

## Star schema

- `dim_date`: date key, date, month, quarter, season, and year.
- `dim_destination`: destination key, destination, state, and destination type.
- `dim_visitor`: visitor category key and category.
- `fact_tourism`: one cleaned visit record with visitor count, expenditure,
  allocated hotel revenue, expenditure per visitor, and dimension foreign keys.
- `stg_visits`, `stg_destinations`, `stg_hotels`: constrained cleaned source
  tables retained as ETL evidence.

Foreign-key enforcement is enabled and checked during loading.

## OLAP operations

`sql/olap_queries.sql` documents the same SQL executed by `tourism.py`:

1. Roll-up: visitors by year.
2. Drill-down: visitors by month.
3. Slice: winter visitors by destination.
4. Dice: domestic expenditure in selected seasons.
5. Pivot: domestic versus international visitors by destination.
6. Aggregation: expenditure, average record expenditure, and visitor totals.
7. Hotel revenue by destination.
8. Visitors by destination type.

Actual result tables are written to `REPORT_RESULTS.md` after each successful
execution.

## Charts

The script creates these files from SQL result sets:

- `charts/tourist_visits_by_destination.png`
- `charts/monthly_tourist_visits.png`
- `charts/tourist_expenditure_by_destination.png`

## Troubleshooting

- If Python is not found, install Python 3.10+ and enable the Windows PATH
  option, then reopen VS Code.
- If `No module named pandas`, `matplotlib`, or `openpyxl` appears, run
  `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`.
- If Excel loading fails, verify that `openpyxl` is installed and that
  `data/destinations.xlsx` exists.
- If the database is locked, close database viewers and rerun.
- If a chart is not produced, inspect the query output and traceback; the
  script refuses to create a misleading chart from an empty result.

## Report evidence and limitations

`REPORT_RESULTS.md` is generated from actual query output and includes the ETL
summary, row counts, quality checks, all eight query results, three findings,
assumptions, suggested screenshot captions, and appendix files. Do not copy
results into a report until the script has been executed successfully in the
local environment.
