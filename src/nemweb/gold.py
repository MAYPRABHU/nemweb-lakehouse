"""Gold layer: analytics views over the silver tables.

Views (not tables), so they're always in sync with silver and cost nothing to refresh.
Dates use the calendar day of the interval *start* (SETTLEMENTDATE is interval-ending).
"""

from __future__ import annotations

from nemweb.warehouse import Warehouse

VIEWS: dict[str, tuple[str, str]] = {
    # view name: (required silver table, SQL)
    "daily_region_price": (
        "dispatch_price",
        """
        SELECT
            CAST(SETTLEMENTDATE - INTERVAL 5 MINUTE AS DATE) AS trading_date,
            REGIONID                                         AS region,
            COUNT(*)                                         AS intervals,
            ROUND(AVG(RRP), 2)                               AS avg_price,
            ROUND(MIN(RRP), 2)                               AS min_price,
            ROUND(MAX(RRP), 2)                               AS max_price,
            COUNT(*) FILTER (WHERE RRP < 0)                  AS negative_price_intervals,
            COUNT(*) FILTER (WHERE RRP >= 300)               AS intervals_above_300
        FROM silver.dispatch_price
        WHERE INTERVENTION = 0
        GROUP BY ALL
        """,
    ),
    "daily_region_demand": (
        "dispatch_regionsum",
        """
        SELECT
            CAST(SETTLEMENTDATE - INTERVAL 5 MINUTE AS DATE) AS trading_date,
            REGIONID                                         AS region,
            ROUND(AVG(TOTALDEMAND), 1)                       AS avg_demand_mw,
            ROUND(MAX(TOTALDEMAND), 1)                       AS peak_demand_mw
        FROM silver.dispatch_regionsum
        WHERE INTERVENTION = 0
        GROUP BY ALL
        """,
    ),
    "daily_unit_energy": (
        "dispatch_unit_scada",
        """
        -- 5-min MW readings -> MWh. Negative values = charging/consumption (e.g. batteries).
        SELECT
            CAST(SETTLEMENTDATE - INTERVAL 5 MINUTE AS DATE)            AS trading_date,
            DUID                                                        AS duid,
            ROUND(SUM(GREATEST(SCADAVALUE, 0)) / 12, 2)                 AS energy_out_mwh,
            ROUND(SUM(LEAST(SCADAVALUE, 0)) / 12, 2)                    AS energy_in_mwh,
            COUNT(*)                                                    AS intervals
        FROM silver.dispatch_unit_scada
        GROUP BY ALL
        """,
    ),
}


def build_views(wh: Warehouse) -> list[str]:
    """(Re)create every gold view whose source table exists. Returns the views built."""
    built = []
    for view, (source_table, sql) in VIEWS.items():
        if wh.table_exists(source_table):
            wh.con.execute(f"CREATE OR REPLACE VIEW gold.{view} AS {sql}")
            built.append(view)
    return built
