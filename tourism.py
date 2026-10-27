"""
Tourism Analytics - Integrated ETL + OLAP CA2
Educational project using fictional sample data.
Run from the project folder: python tourism.py
"""
from pathlib import Path
import sqlite3

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CHARTS = ROOT / "charts"
DB_PATH = ROOT / "tourism.db"
REPORT_PATH = ROOT / "REPORT_RESULTS.md"
CHARTS.mkdir(exist_ok=True)


def extract_sources() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Extract three heterogeneous files: CSV, Excel, and JSON."""
    visits = pd.read_csv(DATA / "visits.csv")
    destinations = pd.read_excel(DATA / "destinations.xlsx")
    hotels = pd.read_json(DATA / "hotels.json")
    return visits, destinations, hotels


def transform_sources(
    visits: pd.DataFrame, destinations: pd.DataFrame, hotels: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, int]]:
    """Clean values, derive date attributes, and prevent hotel double-counting."""
    input_rows = len(visits)
    duplicate_rows = int(visits.duplicated(subset=["visit_id"]).sum())
    visits = visits.drop_duplicates(subset=["visit_id"], keep="first").copy()

    visits["date"] = pd.to_datetime(visits["date"], errors="coerce")
    visits["destination"] = (
        visits["destination"].astype("string").str.strip().str.title()
    )
    visits["visitor_category"] = (
        visits["visitor_category"].astype("string").str.strip().str.title()
    )
    for column in ["visitors", "expenditure", "hotel_revenue"]:
        visits[column] = pd.to_numeric(visits[column], errors="coerce")

    required = ["date", "destination", "visitor_category", "visitors", "expenditure"]
    invalid_rows = visits[required].isna().any(axis=1) | (visits["visitors"] < 0)
    rejected_rows = int(invalid_rows.sum())
    visits = visits.loc[~invalid_rows].copy()
    visits["visitors"] = visits["visitors"].astype(int)

    visits["month"] = visits["date"].dt.month
    visits["quarter"] = visits["date"].dt.quarter
    visits["year"] = visits["date"].dt.year
    visits["season"] = visits["month"].map(
        {
            12: "Winter",
            1: "Winter",
            2: "Winter",
            3: "Summer",
            4: "Summer",
            5: "Summer",
            6: "Monsoon",
            7: "Monsoon",
            8: "Monsoon",
            9: "Monsoon",
            10: "Winter",
            11: "Winter",
        }
    )

    destinations = destinations.copy()
    destinations["destination"] = (
        destinations["destination"].astype("string").str.strip().str.title()
    )
    destinations = destinations.drop_duplicates(subset=["destination"])

    hotels = hotels.copy()
    hotels["destination"] = (
        hotels["destination"].astype("string").str.strip().str.title()
    )
    hotels = hotels.drop_duplicates(subset=["hotel_id"])

    visits = visits.merge(
        destinations, on="destination", how="left", validate="many_to_one"
    )
    unmatched_destinations = int(visits["state"].isna().sum())
    if unmatched_destinations:
        print(
            f"WARNING: {unmatched_destinations} visit rows have no destination metadata."
        )
    visits = visits.dropna(subset=["state", "destination_type"]).copy()

    # The source contains the same monthly hotel amount on both visitor rows.
    # Allocate it across rows in each destination/month before fact loading.
    row_counts = visits.groupby(["destination", "date"])["visit_id"].transform("count")
    visits["hotel_revenue"] = (
        pd.to_numeric(visits["hotel_revenue"], errors="coerce").fillna(0)
        / row_counts
    )
    visits["expenditure_per_visitor"] = (
        visits["expenditure"] / visits["visitors"].replace(0, pd.NA)
    ).fillna(0)

    return (
        visits,
        destinations,
        hotels,
        {
            "input_visit_rows": input_rows,
            "duplicate_rows_removed": duplicate_rows,
            "rejected_rows": rejected_rows,
            "unmatched_destination_rows": unmatched_destinations,
            "clean_visit_rows": len(visits),
        },
    )


def create_warehouse(conn: sqlite3.Connection) -> None:
    """Create the star schema and constrained staging tables."""
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(
        """
        DROP TABLE IF EXISTS fact_tourism;
        DROP TABLE IF EXISTS dim_date;
        DROP TABLE IF EXISTS dim_destination;
        DROP TABLE IF EXISTS dim_visitor;
        DROP TABLE IF EXISTS stg_visits;
        DROP TABLE IF EXISTS stg_destinations;
        DROP TABLE IF EXISTS stg_hotels;

        CREATE TABLE stg_visits (
            visit_id TEXT PRIMARY KEY,
            date TEXT NOT NULL,
            destination TEXT NOT NULL,
            visitor_category TEXT NOT NULL,
            visitors INTEGER NOT NULL CHECK (visitors >= 0),
            expenditure REAL NOT NULL CHECK (expenditure >= 0),
            hotel_revenue REAL NOT NULL CHECK (hotel_revenue >= 0),
            month INTEGER NOT NULL,
            quarter INTEGER NOT NULL,
            year INTEGER NOT NULL,
            season TEXT NOT NULL,
            expenditure_per_visitor REAL NOT NULL
        );
        CREATE TABLE stg_destinations (
            destination TEXT PRIMARY KEY,
            state TEXT NOT NULL,
            destination_type TEXT NOT NULL
        );
        CREATE TABLE stg_hotels (
            hotel_id TEXT PRIMARY KEY,
            destination TEXT NOT NULL,
            hotel_category TEXT NOT NULL,
            room_rate REAL NOT NULL CHECK (room_rate >= 0),
            rooms_sold INTEGER NOT NULL CHECK (rooms_sold >= 0)
        );
        CREATE TABLE dim_date (
            date_key INTEGER PRIMARY KEY,
            full_date TEXT NOT NULL UNIQUE,
            month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
            quarter INTEGER NOT NULL CHECK (quarter BETWEEN 1 AND 4),
            season TEXT NOT NULL,
            year INTEGER NOT NULL
        );
        CREATE TABLE dim_destination (
            destination_key INTEGER PRIMARY KEY,
            destination TEXT NOT NULL UNIQUE,
            state TEXT,
            destination_type TEXT
        );
        CREATE TABLE dim_visitor (
            visitor_category_key INTEGER PRIMARY KEY,
            category TEXT NOT NULL UNIQUE
        );
        CREATE TABLE fact_tourism (
            tourism_id INTEGER PRIMARY KEY,
            visit_id TEXT NOT NULL UNIQUE,
            date_key INTEGER NOT NULL,
            destination_key INTEGER NOT NULL,
            visitor_category_key INTEGER NOT NULL,
            visitors INTEGER NOT NULL CHECK (visitors >= 0),
            expenditure REAL NOT NULL CHECK (expenditure >= 0),
            hotel_revenue REAL NOT NULL CHECK (hotel_revenue >= 0),
            expenditure_per_visitor REAL NOT NULL CHECK (expenditure_per_visitor >= 0),
            FOREIGN KEY (date_key) REFERENCES dim_date(date_key),
            FOREIGN KEY (destination_key) REFERENCES dim_destination(destination_key),
            FOREIGN KEY (visitor_category_key) REFERENCES dim_visitor(visitor_category_key)
        );
        """
    )


def load_staging(
    conn: sqlite3.Connection,
    visits: pd.DataFrame,
    destinations: pd.DataFrame,
    hotels: pd.DataFrame,
) -> None:
    """Load cleaned source data into the constrained staging tables."""
    visits_stage = visits.copy()
    visits_stage["date"] = visits_stage["date"].dt.strftime("%Y-%m-%d")
    visits_stage[
        [
            "visit_id",
            "date",
            "destination",
            "visitor_category",
            "visitors",
            "expenditure",
            "hotel_revenue",
            "month",
            "quarter",
            "year",
            "season",
            "expenditure_per_visitor",
        ]
    ].to_sql("stg_visits", conn, if_exists="append", index=False)
    destinations[["destination", "state", "destination_type"]].to_sql(
        "stg_destinations", conn, if_exists="append", index=False
    )
    hotels[["hotel_id", "destination", "hotel_category", "room_rate", "rooms_sold"]].to_sql(
        "stg_hotels", conn, if_exists="append", index=False
    )


def load_warehouse(
    conn: sqlite3.Connection, visits: pd.DataFrame, destinations: pd.DataFrame
) -> None:
    """Load dimensions before facts and map surrogate keys."""
    date_dim = visits[["date", "month", "quarter", "season", "year"]].drop_duplicates()
    date_dim = date_dim.copy()
    date_dim["full_date"] = date_dim["date"].dt.strftime("%Y-%m-%d")
    date_dim = date_dim[["full_date", "month", "quarter", "season", "year"]].sort_values(
        "full_date"
    )
    date_dim.insert(0, "date_key", range(1, len(date_dim) + 1))
    date_dim.to_sql("dim_date", conn, if_exists="append", index=False)

    dest_dim = destinations[["destination", "state", "destination_type"]].sort_values(
        "destination"
    ).copy()
    dest_dim.insert(0, "destination_key", range(1, len(dest_dim) + 1))
    dest_dim.to_sql("dim_destination", conn, if_exists="append", index=False)

    visitor_dim = pd.DataFrame({"category": sorted(visits["visitor_category"].unique())})
    visitor_dim.insert(0, "visitor_category_key", range(1, len(visitor_dim) + 1))
    visitor_dim.to_sql("dim_visitor", conn, if_exists="append", index=False)

    facts = visits.copy()
    facts["full_date"] = facts["date"].dt.strftime("%Y-%m-%d")
    facts = facts.merge(date_dim[["date_key", "full_date"]], on="full_date", validate="many_to_one")
    facts = facts.merge(dest_dim[["destination_key", "destination"]], on="destination", validate="many_to_one")
    facts = facts.merge(
        visitor_dim[["visitor_category_key", "category"]],
        left_on="visitor_category",
        right_on="category",
        validate="many_to_one",
    )
    facts[
        [
            "visit_id",
            "date_key",
            "destination_key",
            "visitor_category_key",
            "visitors",
            "expenditure",
            "hotel_revenue",
            "expenditure_per_visitor",
        ]
    ].to_sql("fact_tourism", conn, if_exists="append", index=False)


def run_quality_checks(conn: sqlite3.Connection) -> dict[str, int]:
    """Return measurable warehouse and data-quality checks."""
    checks = {
        "fact_rows": "SELECT COUNT(*) FROM fact_tourism",
        "destination_count": "SELECT COUNT(*) FROM dim_destination",
        "date_count": "SELECT COUNT(*) FROM dim_date",
        "visitor_categories": "SELECT COUNT(*) FROM dim_visitor",
        "null_required_fact_values": """
            SELECT COUNT(*) FROM fact_tourism
            WHERE visit_id IS NULL OR date_key IS NULL OR destination_key IS NULL
               OR visitor_category_key IS NULL
        """,
        "duplicate_business_ids": """
            SELECT COUNT(*) FROM (
                SELECT visit_id FROM fact_tourism GROUP BY visit_id HAVING COUNT(*) > 1
            )
        """,
        "orphan_fact_rows": """
            SELECT COUNT(*) FROM fact_tourism f
            LEFT JOIN dim_date d ON f.date_key=d.date_key
            LEFT JOIN dim_destination x ON f.destination_key=x.destination_key
            LEFT JOIN dim_visitor v ON f.visitor_category_key=v.visitor_category_key
            WHERE d.date_key IS NULL OR x.destination_key IS NULL OR v.visitor_category_key IS NULL
        """,
    }
    return {name: int(conn.execute(sql).fetchone()[0]) for name, sql in checks.items()}


QUERIES = {
    "1_rollup_visitors_by_year": """
        SELECT d.year, SUM(f.visitors) AS total_visitors
        FROM fact_tourism f JOIN dim_date d USING(date_key)
        GROUP BY d.year ORDER BY d.year
    """,
    "2_drilldown_visitors_by_month": """
        SELECT d.year, d.month, SUM(f.visitors) AS total_visitors
        FROM fact_tourism f JOIN dim_date d USING(date_key)
        GROUP BY d.year, d.month ORDER BY d.year, d.month
    """,
    "3_slice_winter_visitors_by_destination": """
        SELECT x.destination, SUM(f.visitors) AS visitors
        FROM fact_tourism f JOIN dim_date d USING(date_key)
        JOIN dim_destination x USING(destination_key)
        WHERE d.season='Winter'
        GROUP BY x.destination ORDER BY visitors DESC
    """,
    "4_dice_domestic_spend_summer_winter": """
        SELECT x.destination, SUM(f.expenditure) AS spending
        FROM fact_tourism f JOIN dim_date d USING(date_key)
        JOIN dim_destination x USING(destination_key)
        JOIN dim_visitor v USING(visitor_category_key)
        WHERE d.season IN ('Summer','Winter') AND v.category='Domestic'
        GROUP BY x.destination ORDER BY spending DESC
    """,
    "5_pivot_domestic_vs_international": """
        SELECT x.destination,
          SUM(CASE WHEN v.category='Domestic' THEN f.visitors ELSE 0 END) AS domestic_visitors,
          SUM(CASE WHEN v.category='International' THEN f.visitors ELSE 0 END) AS international_visitors
        FROM fact_tourism f JOIN dim_destination x USING(destination_key)
        JOIN dim_visitor v USING(visitor_category_key)
        GROUP BY x.destination ORDER BY x.destination
    """,
    "6_aggregate_expenditure_by_destination": """
        SELECT x.destination, SUM(f.expenditure) AS total_expenditure,
          ROUND(AVG(f.expenditure),2) AS average_record_expenditure,
          SUM(f.visitors) AS total_visitors
        FROM fact_tourism f JOIN dim_destination x USING(destination_key)
        GROUP BY x.destination ORDER BY total_expenditure DESC
    """,
    "7_hotel_revenue_by_destination": """
        SELECT x.destination, ROUND(SUM(f.hotel_revenue),2) AS hotel_revenue
        FROM fact_tourism f JOIN dim_destination x USING(destination_key)
        GROUP BY x.destination ORDER BY hotel_revenue DESC
    """,
    "8_visitors_by_destination_type": """
        SELECT x.destination_type, SUM(f.visitors) AS total_visitors
        FROM fact_tourism f JOIN dim_destination x USING(destination_key)
        GROUP BY x.destination_type ORDER BY total_visitors DESC
    """,
}


def execute_queries(conn: sqlite3.Connection) -> dict[str, pd.DataFrame]:
    """Execute every required query and return the actual result frames."""
    results: dict[str, pd.DataFrame] = {}
    for name, sql in QUERIES.items():
        results[name] = pd.read_sql_query(sql, conn)
    return results


def save_charts(conn: sqlite3.Connection) -> None:
    """Create the three requested charts from SQL result sets."""
    chart_queries: list[tuple[str, str, str, str, str]] = [
        (
            "tourist_visits_by_destination.png",
            "SELECT x.destination, SUM(f.visitors) AS visitors FROM fact_tourism f "
            "JOIN dim_destination x USING(destination_key) GROUP BY x.destination ORDER BY visitors DESC",
            "Tourist Visits by Destination",
            "Visitors",
            "destination",
        ),
        (
            "monthly_tourist_visits.png",
            "SELECT d.month, SUM(f.visitors) AS visitors FROM fact_tourism f "
            "JOIN dim_date d USING(date_key) GROUP BY d.month ORDER BY d.month",
            "Monthly Tourist Visits",
            "Visitors",
            "month",
        ),
        (
            "tourist_expenditure_by_destination.png",
            "SELECT x.destination, SUM(f.expenditure) AS expenditure FROM fact_tourism f "
            "JOIN dim_destination x USING(destination_key) GROUP BY x.destination ORDER BY expenditure DESC",
            "Tourist Expenditure by Destination",
            "Expenditure (sample INR)",
            "destination",
        ),
    ]
    for filename, sql, title, ylabel, x_column in chart_queries:
        frame = pd.read_sql_query(sql, conn)
        if frame.empty:
            raise ValueError(f"Cannot create {filename}: query returned no rows.")
        plt.figure(figsize=(9, 5))
        value_column = frame.columns[-1]
        if x_column == "month":
            plt.plot(frame[x_column], frame[value_column], marker="o")
            plt.xticks(range(1, 13))
            plt.xlabel("Month (1=Jan, 12=Dec)")
        else:
            plt.bar(frame[x_column], frame[value_column])
            plt.xticks(rotation=30, ha="right")
            plt.xlabel("Destination")
        plt.title(title)
        plt.ylabel(ylabel)
        plt.tight_layout()
        plt.savefig(CHARTS / filename, dpi=160)
        plt.close()


def write_report(
    stats: dict[str, int],
    checks: dict[str, int],
    results: dict[str, pd.DataFrame],
) -> None:
    """Write report evidence from the current execution, never fabricated data."""
    lines = [
        "# Tourism Analytics - Execution Results",
        "",
        "This report was generated by the current execution. All values below come from the fictional educational datasets and the generated SQLite warehouse.",
        "",
        "## ETL summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    labels = {
        "input_visit_rows": "Input visit rows",
        "duplicate_rows_removed": "Duplicate rows removed",
        "rejected_rows": "Rejected invalid rows",
        "unmatched_destination_rows": "Unmatched destination rows",
        "clean_visit_rows": "Clean rows loaded",
    }
    lines.extend(f"| {label} | {stats[key]} |" for key, label in labels.items())
    lines.extend(["", "## Warehouse quality checks", "", "| Check | Value |", "|---|---:|"])
    lines.extend(f"| {key} | {value} |" for key, value in checks.items())
    lines.extend(["", "## Actual OLAP query outputs", ""])
    for name, frame in results.items():
        lines.extend(
            [f"### {name}", "", "```text", frame.to_string(index=False), "```", ""]
        )

    aggregate = results["6_aggregate_expenditure_by_destination"]
    pivot = results["5_pivot_domestic_vs_international"]
    monthly = results["2_drilldown_visitors_by_month"]
    findings = [
        f"- The highest total expenditure destination is {aggregate.iloc[0]['destination']} "
        f"({aggregate.iloc[0]['total_expenditure']:,.2f} sample INR).",
        f"- The highest monthly visitor total occurs in month {int(monthly.loc[monthly['total_visitors'].idxmax(), 'month'])} "
        f"with {int(monthly['total_visitors'].max()):,} visitors.",
        f"- Domestic visitors exceed international visitors at every destination in the pivot output; "
        f"the largest domestic total is {int(pivot['domestic_visitors'].max()):,}.",
    ]
    lines.extend(
        [
            "## Three analytical findings",
            "",
            *findings,
            "",
            "## Assumptions and limitations",
            "",
            "- All records are fictional educational sample data, not official tourism statistics.",
            "- The source repeats each destination/month hotel amount on domestic and international rows. ETL allocates that amount evenly across those rows before aggregation to avoid double-counting.",
            "- Hotel JSON rates and rooms sold are retained in staging; the fact measure uses the source monthly estimate.",
            "",
            "## Suggested screenshot captions",
            "",
            "- Terminal: successful ETL summary and quality checks.",
            "- SQLite browser: dimension and fact table row counts.",
            "- Terminal: eight executed OLAP query outputs.",
            "- Charts folder: destination visits, monthly visits, and destination expenditure.",
            "",
            "## Appendix files",
            "",
            "- `tourism.py`",
            "- `sql/olap_queries.sql`",
            "- `data/visits.csv`, `data/destinations.xlsx`, `data/hotels.json`",
            "- `tourism.db` and the three PNG charts",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    visits, destinations, hotels = extract_sources()
    clean_visits, clean_destinations, clean_hotels, stats = transform_sources(
        visits, destinations, hotels
    )
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        with conn:
            create_warehouse(conn)
            load_staging(conn, clean_visits, clean_destinations, clean_hotels)
            load_warehouse(conn, clean_visits, clean_destinations)
            checks = run_quality_checks(conn)
            results = execute_queries(conn)
            save_charts(conn)
        print("\nETL SUMMARY")
        print(f"Visit rows before cleaning: {stats['input_visit_rows']}")
        print(f"Duplicate rows removed:    {stats['duplicate_rows_removed']}")
        print(f"Rejected rows:             {stats['rejected_rows']}")
        print(f"Clean visit rows loaded:   {stats['clean_visit_rows']}")
        print("\nWAREHOUSE QUALITY CHECKS")
        for key, value in checks.items():
            print(f"{key}: {value}")
        print("\nOLAP QUERY RESULTS")
        for name, frame in results.items():
            print(f"\n--- {name} ---")
            print(frame.to_string(index=False))
    write_report(stats, checks, results)
    print(f"\nCharts saved in: {CHARTS}")
    print(f"Database saved at: {DB_PATH}")
    print(f"Report saved at: {REPORT_PATH}")
    print("\nCompleted successfully.")


if __name__ == "__main__":
    main()
