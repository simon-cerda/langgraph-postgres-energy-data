CREATE OR REPLACE VIEW smart_buildings.energy_consumption_monthly_metrics AS
WITH base_data AS (
    SELECT
        cups,
        DATE(date) AS full_date,
        DATE_TRUNC('month', date) AS year_month,
        EXTRACT(DAY FROM date) AS day_in_month,
        consumption_kwh
    FROM raw.energy_consumption
),
current_day_of_month AS (
    SELECT EXTRACT(DAY FROM CURRENT_DATE)::int AS day_cutoff,
           DATE_TRUNC('month', CURRENT_DATE)::date AS current_month
),
filtered_data AS (
    SELECT
        b.*
    FROM base_data b
    JOIN current_day_of_month d ON TRUE
    WHERE
        -- Para el mes actual: limitar hasta el día actual
        (b.year_month = d.current_month AND b.day_in_month <= d.day_cutoff)
        -- Para meses anteriores: dejar pasar todo
        OR (b.year_month < d.current_month)
),
daily_agg AS (
    SELECT
        cups,
        year_month,
        full_date,
        SUM(consumption_kwh) AS daily_consumption_kwh
    FROM filtered_data
    GROUP BY cups, year_month, full_date
),
monthly_agg AS (
    SELECT
        cups,
        year_month,
        COUNT(DISTINCT full_date) AS days_in_month,
        SUM(daily_consumption_kwh) AS total_consumption_kwh,
        AVG(daily_consumption_kwh) AS daily_consumption_kwh,
        STDDEV(daily_consumption_kwh) AS std_daily_consumption_kwh
    FROM daily_agg
    GROUP BY cups, year_month
),
with_lags AS (
    SELECT
        m.*,
        LAG(total_consumption_kwh) OVER (PARTITION BY cups ORDER BY year_month) AS total_consumption_prev_month_kwh,
        LAG(total_consumption_kwh, 12) OVER (PARTITION BY cups ORDER BY year_month) AS total_consumption_prev_year_same_month_kwh
    FROM monthly_agg m
),
with_diff AS (
    SELECT *,
        CASE
            WHEN total_consumption_prev_month_kwh IS NOT NULL AND total_consumption_prev_month_kwh != 0 THEN
                100.0 * (total_consumption_kwh - total_consumption_prev_month_kwh) / total_consumption_prev_month_kwh
            ELSE NULL
        END AS diff_pct_consumption_prev_month
    FROM with_lags
),
with_ytd AS (
    SELECT *,
        SUM(total_consumption_kwh) OVER (
            PARTITION BY cups, EXTRACT(YEAR FROM year_month)
            ORDER BY year_month
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS ytd_consumption_kwh
    FROM with_diff
),
with_ytd_prev_year AS (
    SELECT
        w.*,
        ytd_prev.ytd_consumption_kwh AS ytd_prev_year_consumption_kwh
    FROM with_ytd w
    LEFT JOIN (
        SELECT *,
            SUM(total_consumption_kwh) OVER (
                PARTITION BY cups, EXTRACT(YEAR FROM year_month)
                ORDER BY year_month
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS ytd_consumption_kwh
        FROM monthly_agg
    ) ytd_prev
      ON ytd_prev.cups = w.cups
      AND EXTRACT(YEAR FROM ytd_prev.year_month) = EXTRACT(YEAR FROM w.year_month) - 1
      AND EXTRACT(MONTH FROM ytd_prev.year_month) = EXTRACT(MONTH FROM w.year_month)
),
final AS (
    SELECT
        cups,
        year_month::date AS year_month,
        total_consumption_kwh,
        daily_consumption_kwh,
        total_consumption_prev_month_kwh,
        diff_pct_consumption_prev_month,
        std_daily_consumption_kwh,
        ytd_consumption_kwh,
        ytd_prev_year_consumption_kwh,
        total_consumption_prev_year_same_month_kwh,
        NOW() AS date_insert,
        CASE
            WHEN year_month = DATE_TRUNC('month', CURRENT_DATE) THEN TRUE
            ELSE FALSE
        END AS is_partial_month
    FROM with_ytd_prev_year
)
SELECT * FROM final;
