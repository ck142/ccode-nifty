-- Schema for multiple timeframe data
-- All timestamps stored in IST (Asia/Kolkata)

-- Daily OHLC table
CREATE TABLE IF NOT EXISTS dhanhq.price_data_daily (
    id BIGSERIAL PRIMARY KEY,
    security_id VARCHAR(50) NOT NULL,
    date DATE NOT NULL,
    open DECIMAL(10, 2) NOT NULL,
    high DECIMAL(10, 2) NOT NULL,
    low DECIMAL(10, 2) NOT NULL,
    close DECIMAL(10, 2) NOT NULL,
    volume BIGINT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(security_id, date)
);

-- Weekly OHLC table
CREATE TABLE IF NOT EXISTS dhanhq.price_data_weekly (
    id BIGSERIAL PRIMARY KEY,
    security_id VARCHAR(50) NOT NULL,
    week_start_date DATE NOT NULL,
    week_end_date DATE NOT NULL,
    open DECIMAL(10, 2) NOT NULL,
    high DECIMAL(10, 2) NOT NULL,
    low DECIMAL(10, 2) NOT NULL,
    close DECIMAL(10, 2) NOT NULL,
    volume BIGINT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(security_id, week_start_date)
);

-- Monthly OHLC table
CREATE TABLE IF NOT EXISTS dhanhq.price_data_monthly (
    id BIGSERIAL PRIMARY KEY,
    security_id VARCHAR(50) NOT NULL,
    year INT NOT NULL,
    month INT NOT NULL,
    first_date DATE NOT NULL,
    last_date DATE NOT NULL,
    open DECIMAL(10, 2) NOT NULL,
    high DECIMAL(10, 2) NOT NULL,
    low DECIMAL(10, 2) NOT NULL,
    close DECIMAL(10, 2) NOT NULL,
    volume BIGINT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(security_id, year, month)
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_price_daily_security_date 
ON dhanhq.price_data_daily(security_id, date DESC);

CREATE INDEX IF NOT EXISTS idx_price_weekly_security_date 
ON dhanhq.price_data_weekly(security_id, week_start_date DESC);

CREATE INDEX IF NOT EXISTS idx_price_monthly_security_date 
ON dhanhq.price_data_monthly(security_id, year DESC, month DESC);

-- Function to aggregate intraday data to daily
CREATE OR REPLACE FUNCTION dhanhq.aggregate_to_daily(p_security_id VARCHAR, p_from_date DATE DEFAULT NULL, p_to_date DATE DEFAULT NULL)
RETURNS TABLE(inserted_count INT) AS $$
DECLARE
    v_inserted_count INT;
BEGIN
    WITH daily_data AS (
        SELECT 
            security_id,
            DATE(datetime AT TIME ZONE 'Asia/Kolkata') as trading_date,
            FIRST_VALUE(open) OVER (PARTITION BY DATE(datetime AT TIME ZONE 'Asia/Kolkata') ORDER BY datetime) as open,
            MAX(high) OVER (PARTITION BY DATE(datetime AT TIME ZONE 'Asia/Kolkata')) as high,
            MIN(low) OVER (PARTITION BY DATE(datetime AT TIME ZONE 'Asia/Kolkata')) as low,
            LAST_VALUE(close) OVER (PARTITION BY DATE(datetime AT TIME ZONE 'Asia/Kolkata') ORDER BY datetime RANGE BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) as close,
            SUM(volume) OVER (PARTITION BY DATE(datetime AT TIME ZONE 'Asia/Kolkata')) as volume
        FROM dhanhq.price_data
        WHERE security_id = p_security_id
        AND interval_minutes = 1
        AND (p_from_date IS NULL OR DATE(datetime AT TIME ZONE 'Asia/Kolkata') >= p_from_date)
        AND (p_to_date IS NULL OR DATE(datetime AT TIME ZONE 'Asia/Kolkata') <= p_to_date)
    )
    INSERT INTO dhanhq.price_data_daily (security_id, date, open, high, low, close, volume)
    SELECT DISTINCT 
        security_id,
        trading_date,
        open,
        high,
        low,
        close,
        volume
    FROM daily_data
    ON CONFLICT (security_id, date) 
    DO UPDATE SET
        open = EXCLUDED.open,
        high = EXCLUDED.high,
        low = EXCLUDED.low,
        close = EXCLUDED.close,
        volume = EXCLUDED.volume;
    
    GET DIAGNOSTICS v_inserted_count = ROW_COUNT;
    RETURN QUERY SELECT v_inserted_count;
END;
$$ LANGUAGE plpgsql;

-- Function to aggregate daily data to weekly
CREATE OR REPLACE FUNCTION dhanhq.aggregate_to_weekly(p_security_id VARCHAR)
RETURNS TABLE(inserted_count INT) AS $$
DECLARE
    v_inserted_count INT;
BEGIN
    WITH weekly_data AS (
        SELECT 
            security_id,
            DATE_TRUNC('week', date)::DATE as week_start,
            DATE_TRUNC('week', date)::DATE + INTERVAL '6 days' as week_end,
            FIRST_VALUE(open) OVER (PARTITION BY DATE_TRUNC('week', date) ORDER BY date) as open,
            MAX(high) OVER (PARTITION BY DATE_TRUNC('week', date)) as high,
            MIN(low) OVER (PARTITION BY DATE_TRUNC('week', date)) as low,
            LAST_VALUE(close) OVER (PARTITION BY DATE_TRUNC('week', date) ORDER BY date RANGE BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) as close,
            SUM(volume) OVER (PARTITION BY DATE_TRUNC('week', date)) as volume
        FROM dhanhq.price_data_daily
        WHERE security_id = p_security_id
    )
    INSERT INTO dhanhq.price_data_weekly (security_id, week_start_date, week_end_date, open, high, low, close, volume)
    SELECT DISTINCT 
        security_id,
        week_start,
        week_end,
        open,
        high,
        low,
        close,
        volume
    FROM weekly_data
    ON CONFLICT (security_id, week_start_date) 
    DO UPDATE SET
        high = EXCLUDED.high,
        low = EXCLUDED.low,
        close = EXCLUDED.close,
        volume = EXCLUDED.volume;
    
    GET DIAGNOSTICS v_inserted_count = ROW_COUNT;
    RETURN QUERY SELECT v_inserted_count;
END;
$$ LANGUAGE plpgsql;

-- Function to aggregate daily data to monthly
CREATE OR REPLACE FUNCTION dhanhq.aggregate_to_monthly(p_security_id VARCHAR)
RETURNS TABLE(inserted_count INT) AS $$
DECLARE
    v_inserted_count INT;
BEGIN
    WITH monthly_data AS (
        SELECT 
            security_id,
            EXTRACT(YEAR FROM date)::INT as year,
            EXTRACT(MONTH FROM date)::INT as month,
            MIN(date) as first_date,
            MAX(date) as last_date,
            FIRST_VALUE(open) OVER (PARTITION BY DATE_TRUNC('month', date) ORDER BY date) as open,
            MAX(high) OVER (PARTITION BY DATE_TRUNC('month', date)) as high,
            MIN(low) OVER (PARTITION BY DATE_TRUNC('month', date)) as low,
            LAST_VALUE(close) OVER (PARTITION BY DATE_TRUNC('month', date) ORDER BY date RANGE BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) as close,
            SUM(volume) OVER (PARTITION BY DATE_TRUNC('month', date)) as volume
        FROM dhanhq.price_data_daily
        WHERE security_id = p_security_id
    )
    INSERT INTO dhanhq.price_data_monthly (security_id, year, month, first_date, last_date, open, high, low, close, volume)
    SELECT DISTINCT 
        security_id,
        year,
        month,
        first_date,
        last_date,
        open,
        high,
        low,
        close,
        volume
    FROM monthly_data
    ON CONFLICT (security_id, year, month) 
    DO UPDATE SET
        first_date = EXCLUDED.first_date,
        last_date = EXCLUDED.last_date,
        high = EXCLUDED.high,
        low = EXCLUDED.low,
        close = EXCLUDED.close,
        volume = EXCLUDED.volume;
    
    GET DIAGNOSTICS v_inserted_count = ROW_COUNT;
    RETURN QUERY SELECT v_inserted_count;
END;
$$ LANGUAGE plpgsql;