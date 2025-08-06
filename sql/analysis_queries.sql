-- Analysis queries for DhanHQ market data
-- All timestamps are in IST (Asia/Kolkata)

-- 1. Get latest price for a security
SELECT 
    s.symbol,
    s.name,
    p.datetime AT TIME ZONE 'Asia/Kolkata' as ist_time,
    p.open,
    p.high,
    p.low,
    p.close,
    p.volume
FROM dhanhq.price_data p
JOIN dhanhq.securities s ON p.security_id = s.security_id
WHERE s.symbol = 'MANKIND'
ORDER BY p.datetime DESC
LIMIT 1;

-- 2. Daily OHLC aggregation
WITH daily_data AS (
    SELECT 
        DATE(datetime AT TIME ZONE 'Asia/Kolkata') as trading_date,
        open,
        high,
        low,
        close,
        volume,
        datetime,
        ROW_NUMBER() OVER (PARTITION BY DATE(datetime AT TIME ZONE 'Asia/Kolkata') ORDER BY datetime ASC) as rn_first,
        ROW_NUMBER() OVER (PARTITION BY DATE(datetime AT TIME ZONE 'Asia/Kolkata') ORDER BY datetime DESC) as rn_last
    FROM dhanhq.price_data
    WHERE security_id = (SELECT security_id FROM dhanhq.securities WHERE symbol = 'MANKIND')
    AND interval_minutes = 1
)
SELECT 
    trading_date,
    MAX(CASE WHEN rn_first = 1 THEN open END) as open,
    MAX(high) as high,
    MIN(low) as low,
    MAX(CASE WHEN rn_last = 1 THEN close END) as close,
    SUM(volume) as volume,
    COUNT(*) as candles_count
FROM daily_data
GROUP BY trading_date
ORDER BY trading_date DESC
LIMIT 30;

-- 3. Moving averages (using 1-minute data)
WITH price_data AS (
    SELECT 
        datetime AT TIME ZONE 'Asia/Kolkata' as ist_time,
        close,
        AVG(close) OVER (ORDER BY datetime ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) as sma_20,
        AVG(close) OVER (ORDER BY datetime ROWS BETWEEN 49 PRECEDING AND CURRENT ROW) as sma_50,
        AVG(close) OVER (ORDER BY datetime ROWS BETWEEN 199 PRECEDING AND CURRENT ROW) as sma_200
    FROM dhanhq.price_data
    WHERE security_id = (SELECT security_id FROM dhanhq.securities WHERE symbol = 'MANKIND')
    AND interval_minutes = 1
)
SELECT * FROM price_data
WHERE ist_time >= CURRENT_TIMESTAMP - INTERVAL '7 days'
ORDER BY ist_time DESC
LIMIT 100;

-- 4. Volume analysis by hour
SELECT 
    DATE(datetime AT TIME ZONE 'Asia/Kolkata') as trading_date,
    EXTRACT(HOUR FROM datetime AT TIME ZONE 'Asia/Kolkata') as hour,
    SUM(volume) as hourly_volume,
    AVG(volume) as avg_volume_per_minute,
    COUNT(*) as candles
FROM dhanhq.price_data
WHERE security_id = (SELECT security_id FROM dhanhq.securities WHERE symbol = 'MANKIND')
AND interval_minutes = 1
AND datetime >= CURRENT_TIMESTAMP - INTERVAL '5 days'
GROUP BY trading_date, hour
ORDER BY trading_date DESC, hour;

-- 5. Intraday volatility
SELECT 
    DATE(datetime AT TIME ZONE 'Asia/Kolkata') as trading_date,
    MAX(high) as day_high,
    MIN(low) as day_low,
    MAX(high) - MIN(low) as range,
    ROUND(((MAX(high) - MIN(low)) / MIN(low) * 100)::numeric, 2) as range_percent,
    STDDEV(close) as price_stddev
FROM dhanhq.price_data
WHERE security_id = (SELECT security_id FROM dhanhq.securities WHERE symbol = 'MANKIND')
AND interval_minutes = 1
GROUP BY trading_date
ORDER BY trading_date DESC
LIMIT 30;

-- 6. Market open and close analysis
WITH daily_open_close AS (
    SELECT 
        DATE(datetime AT TIME ZONE 'Asia/Kolkata') as trading_date,
        FIRST_VALUE(open) OVER (PARTITION BY DATE(datetime AT TIME ZONE 'Asia/Kolkata') ORDER BY datetime) as day_open,
        LAST_VALUE(close) OVER (PARTITION BY DATE(datetime AT TIME ZONE 'Asia/Kolkata') ORDER BY datetime RANGE BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) as day_close
    FROM dhanhq.price_data
    WHERE security_id = (SELECT security_id FROM dhanhq.securities WHERE symbol = 'MANKIND')
    AND interval_minutes = 1
)
SELECT DISTINCT
    trading_date,
    day_open,
    day_close,
    day_close - day_open as change,
    ROUND(((day_close - day_open) / day_open * 100)::numeric, 2) as change_percent,
    CASE 
        WHEN day_close > day_open THEN 'Bullish'
        WHEN day_close < day_open THEN 'Bearish'
        ELSE 'Neutral'
    END as day_type
FROM daily_open_close
ORDER BY trading_date DESC
LIMIT 20;

-- 7. VWAP calculation
SELECT 
    DATE(datetime AT TIME ZONE 'Asia/Kolkata') as trading_date,
    ROUND((SUM(close * volume) / NULLIF(SUM(volume), 0))::numeric, 2) as daily_vwap,
    SUM(volume) as total_volume,
    COUNT(*) as total_candles
FROM dhanhq.price_data
WHERE security_id = (SELECT security_id FROM dhanhq.securities WHERE symbol = 'MANKIND')
AND interval_minutes = 1
AND datetime >= CURRENT_TIMESTAMP - INTERVAL '10 days'
GROUP BY trading_date
ORDER BY trading_date DESC;

-- 8. Price levels frequency (support/resistance)
WITH price_levels AS (
    SELECT 
        ROUND(close::numeric, 0) as price_level,
        COUNT(*) as frequency,
        SUM(volume) as total_volume
    FROM dhanhq.price_data
    WHERE security_id = (SELECT security_id FROM dhanhq.securities WHERE symbol = 'MANKIND')
    AND interval_minutes = 1
    AND datetime >= CURRENT_TIMESTAMP - INTERVAL '30 days'
    GROUP BY ROUND(close::numeric, 0)
)
SELECT 
    price_level,
    frequency,
    total_volume,
    ROUND((frequency::numeric / SUM(frequency) OVER () * 100), 2) as frequency_percent
FROM price_levels
WHERE frequency > 10
ORDER BY frequency DESC
LIMIT 20;

-- 9. Download history summary
SELECT 
    s.symbol,
    dh.interval_minutes,
    COUNT(*) as download_attempts,
    SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) as successful,
    SUM(CASE WHEN status = 'ERROR' THEN 1 ELSE 0 END) as failed,
    SUM(records_downloaded) as total_records,
    MAX(dh.created_at AT TIME ZONE 'Asia/Kolkata') as last_download
FROM dhanhq.download_history dh
JOIN dhanhq.securities s ON dh.security_id = s.security_id
GROUP BY s.symbol, dh.interval_minutes
ORDER BY s.symbol, dh.interval_minutes;

-- 10. Data completeness check
WITH expected_minutes AS (
    SELECT 
        generate_series(
            DATE_TRUNC('day', MIN(datetime))::timestamp AT TIME ZONE 'Asia/Kolkata' + INTERVAL '9 hours 15 minutes',
            DATE_TRUNC('day', MAX(datetime))::timestamp AT TIME ZONE 'Asia/Kolkata' + INTERVAL '15 hours 30 minutes',
            INTERVAL '1 minute'
        ) as expected_time
    FROM dhanhq.price_data
    WHERE security_id = (SELECT security_id FROM dhanhq.securities WHERE symbol = 'MANKIND')
    AND interval_minutes = 1
),
market_minutes AS (
    SELECT expected_time
    FROM expected_minutes
    WHERE EXTRACT(hour FROM expected_time) * 60 + EXTRACT(minute FROM expected_time) 
          BETWEEN 9 * 60 + 15 AND 15 * 60 + 30
    AND EXTRACT(dow FROM expected_time) BETWEEN 1 AND 5
)
SELECT 
    DATE(expected_time) as date,
    COUNT(*) as expected_candles,
    COUNT(p.datetime) as actual_candles,
    COUNT(*) - COUNT(p.datetime) as missing_candles,
    ROUND((COUNT(p.datetime)::numeric / COUNT(*) * 100), 2) as completeness_percent
FROM market_minutes m
LEFT JOIN dhanhq.price_data p 
    ON DATE_TRUNC('minute', p.datetime AT TIME ZONE 'Asia/Kolkata') = m.expected_time
    AND p.security_id = (SELECT security_id FROM dhanhq.securities WHERE symbol = 'MANKIND')
    AND p.interval_minutes = 1
GROUP BY DATE(expected_time)
HAVING COUNT(*) - COUNT(p.datetime) > 0
ORDER BY date DESC
LIMIT 20;