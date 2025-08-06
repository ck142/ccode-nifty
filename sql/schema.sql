-- Create schema for market data
CREATE SCHEMA IF NOT EXISTS dhanhq;

-- Securities master table
CREATE TABLE IF NOT EXISTS dhanhq.securities (
    id SERIAL PRIMARY KEY,
    security_id VARCHAR(50) UNIQUE NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    name VARCHAR(255),
    exchange VARCHAR(20),
    instrument_type VARCHAR(50),
    isin VARCHAR(20),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Historical price data table (storing in IST)
CREATE TABLE IF NOT EXISTS dhanhq.price_data (
    id BIGSERIAL PRIMARY KEY,
    security_id VARCHAR(50) NOT NULL,
    datetime TIMESTAMP WITH TIME ZONE NOT NULL,  -- Stored with timezone (IST)
    open DECIMAL(10, 2) NOT NULL,
    high DECIMAL(10, 2) NOT NULL,
    low DECIMAL(10, 2) NOT NULL,
    close DECIMAL(10, 2) NOT NULL,
    volume BIGINT NOT NULL,
    interval_minutes INT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(security_id, datetime, interval_minutes)
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_price_data_security_datetime 
ON dhanhq.price_data(security_id, datetime DESC);

CREATE INDEX IF NOT EXISTS idx_price_data_datetime 
ON dhanhq.price_data(datetime DESC);

CREATE INDEX IF NOT EXISTS idx_price_data_security_interval 
ON dhanhq.price_data(security_id, interval_minutes);

CREATE INDEX IF NOT EXISTS idx_securities_symbol 
ON dhanhq.securities(symbol);

-- Download history tracking
CREATE TABLE IF NOT EXISTS dhanhq.download_history (
    id SERIAL PRIMARY KEY,
    security_id VARCHAR(50) NOT NULL,
    from_date TIMESTAMP WITH TIME ZONE NOT NULL,
    to_date TIMESTAMP WITH TIME ZONE NOT NULL,
    interval_minutes INT NOT NULL,
    records_downloaded INT,
    status VARCHAR(20),
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create index on download history
CREATE INDEX IF NOT EXISTS idx_download_history_security 
ON dhanhq.download_history(security_id, created_at DESC);

-- Add comments
COMMENT ON SCHEMA dhanhq IS 'Schema for DhanHQ market data';
COMMENT ON TABLE dhanhq.securities IS 'Master table for securities/instruments';
COMMENT ON TABLE dhanhq.price_data IS 'Historical price data in IST timezone';
COMMENT ON TABLE dhanhq.download_history IS 'Track data download attempts and status';

COMMENT ON COLUMN dhanhq.price_data.datetime IS 'Timestamp in IST (Asia/Kolkata) timezone';
COMMENT ON COLUMN dhanhq.price_data.interval_minutes IS 'Time interval: 1, 5, 15, 25, or 60 minutes';