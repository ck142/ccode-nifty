-- Create a comprehensive view of all timeframe data
CREATE OR REPLACE VIEW dhanhq.data_summary AS
WITH intraday_summary AS (
    SELECT 
        CASE interval_minutes 
            WHEN 1 THEN '1 Minute'
            WHEN 5 THEN '5 Minutes'
            WHEN 15 THEN '15 Minutes'
            WHEN 60 THEN '1 Hour'
            ELSE interval_minutes || ' Minutes'
        END as timeframe,
        COUNT(*) as record_count,
        MIN(datetime AT TIME ZONE 'Asia/Kolkata') as earliest_data,
        MAX(datetime AT TIME ZONE 'Asia/Kolkata') as latest_data,
        COUNT(DISTINCT DATE(datetime AT TIME ZONE 'Asia/Kolkata')) as trading_days
    FROM dhanhq.price_data
    WHERE security_id = '15380'
    GROUP BY interval_minutes
),
daily_summary AS (
    SELECT 
        'Daily' as timeframe,
        COUNT(*) as record_count,
        MIN(date)::timestamp as earliest_data,
        MAX(date)::timestamp as latest_data,
        COUNT(*) as trading_days
    FROM dhanhq.price_data_daily
    WHERE security_id = '15380'
),
weekly_summary AS (
    SELECT 
        'Weekly' as timeframe,
        COUNT(*) as record_count,
        MIN(week_start_date)::timestamp as earliest_data,
        MAX(week_end_date)::timestamp as latest_data,
        COUNT(*) as trading_days
    FROM dhanhq.price_data_weekly
    WHERE security_id = '15380'
),
monthly_summary AS (
    SELECT 
        'Monthly' as timeframe,
        COUNT(*) as record_count,
        MIN(first_date)::timestamp as earliest_data,
        MAX(last_date)::timestamp as latest_data,
        COUNT(*) as trading_days
    FROM dhanhq.price_data_monthly
    WHERE security_id = '15380'
)
SELECT * FROM intraday_summary
UNION ALL
SELECT * FROM daily_summary
UNION ALL
SELECT * FROM weekly_summary
UNION ALL
SELECT * FROM monthly_summary
ORDER BY 
    CASE timeframe
        WHEN '1 Minute' THEN 1
        WHEN '5 Minutes' THEN 2
        WHEN '15 Minutes' THEN 3
        WHEN '1 Hour' THEN 4
        WHEN 'Daily' THEN 5
        WHEN 'Weekly' THEN 6
        WHEN 'Monthly' THEN 7
    END;