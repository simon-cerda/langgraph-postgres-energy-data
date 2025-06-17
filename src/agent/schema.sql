CREATE TABLE smart_buildings.building (
    cups TEXT PRIMARY KEY,         -- building unique identifier
    name TEXT NOT NULL,          
    address TEXT,                  
    type TEXT                      -- Type of building ( Administración, Comercio, etc.)
);

CREATE TABLE smart_buildings.energy_consumption_monthly_metrics (
    cups TEXT NULL,                                           -- cups of the building
    year_month DATE NULL,                                     -- Year and month of the record, first day of month (yyyy-MM-01)
    -- The combination of cups and year_month must be unique per building per month
    total_consumption_kwh numeric(20, 2) NULL,                       
    avg_daily_consumption_kwh numeric(38, 20) NULL,           -- Average daily consumption for the month
    std_daily_consumption_kwh FLOAT8 NULL,                    -- Standard deviation of daily consumption
    total_consumption_prev_month_kwh numeric(20, 2) NULL,     -- Total consumption in the previous month
    total_consumption_prev_year_same_month_kwh numeric(20, 2) NULL,   -- Total consumption in the same month of the previous year
    diff_pct_consumption_prev_month numeric(38, 13) NULL,              -- Percentage difference from the previous month
    ytd_consumption_kwh NUMERIC(38, 6) NULL,                  -- Year-to-date consumption up to this month
    ytd_prev_year_consumption_kwh NUMERIC(38, 6) NULL,        -- YTD consumption at this point in the previous year
    diff_pct_consumption_prev_year_same_month numeric(38, 13) NULL     -- Percentage difference from the same month last year
    diff_consumo_grupo numeric(25, 6) NULL,                    -- Difference in consumption compared to the group average      
	avg_group_consumption_kwh numeric(24, 6) NULL,              -- Average consumption of the group

);

CREATE TABLE smart_buildings.energy_consumption_weekly_metrics (
    cups TEXT NOT NULL,                                       -- cups of the building
    week_start DATE NOT NULL,                                 -- Start date of the week (e.g., 2024-03-04)
    total_consumption_kwh DOUBLE PRECISION,                   
    daily_consumption_kwh DOUBLE PRECISION,                   -- Average daily consumption during the week
    total_consumption_prev_week_kwh DOUBLE PRECISION,         -- Total consumption in the previous week
    diff_pct_consumption_prev_week DOUBLE PRECISION,          -- Percentage difference from the previous week
    std_daily_consumption_kwh DOUBLE PRECISION,               -- Standard deviation of daily consumption during the week
    date_insert TIMESTAMP DEFAULT CURRENT_TIMESTAMP,          -- Timestamp when the record was inserted
    PRIMARY KEY (cups, week_start),                           -- Composite primary key. CUPS and week start date
    FOREIGN KEY (cups) REFERENCES smart_buildings.building(cups)  -- Foreign key linking to the buildings table
);