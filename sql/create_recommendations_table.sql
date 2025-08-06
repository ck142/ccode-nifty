-- Create table for storing trading recommendations
CREATE SCHEMA IF NOT EXISTS dhanhq;

-- Drop existing table if needed for clean setup
DROP TABLE IF EXISTS dhanhq.trading_recommendations CASCADE;

-- Create recommendations table
CREATE TABLE dhanhq.trading_recommendations (
    id SERIAL PRIMARY KEY,
    security_id VARCHAR(20) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    generated_at TIMESTAMP NOT NULL,
    current_price DECIMAL(10, 2),
    
    -- Market context
    trend_1min VARCHAR(20),
    trend_5min VARCHAR(20),
    trend_15min VARCHAR(20),
    trend_60min VARCHAR(20),
    trend_daily VARCHAR(20),
    trend_weekly VARCHAR(20),
    trend_monthly VARCHAR(20),
    
    -- Support/Resistance levels
    support_1 DECIMAL(10, 2),
    support_2 DECIMAL(10, 2),
    support_3 DECIMAL(10, 2),
    resistance_1 DECIMAL(10, 2),
    resistance_2 DECIMAL(10, 2),
    resistance_3 DECIMAL(10, 2),
    
    -- Intraday recommendation
    intraday_action VARCHAR(10), -- BUY, SELL, HOLD
    intraday_entry DECIMAL(10, 2),
    intraday_stoploss DECIMAL(10, 2),
    intraday_target1 DECIMAL(10, 2),
    intraday_target2 DECIMAL(10, 2),
    intraday_risk_reward VARCHAR(20),
    intraday_rationale TEXT,
    
    -- Swing recommendation
    swing_action VARCHAR(10), -- BUY, SELL, HOLD
    swing_entry DECIMAL(10, 2),
    swing_stoploss DECIMAL(10, 2),
    swing_target1 DECIMAL(10, 2),
    swing_target2 DECIMAL(10, 2),
    swing_target3 DECIMAL(10, 2),
    swing_risk_reward VARCHAR(20),
    swing_rationale TEXT,
    
    -- Full recommendation text
    recommendation_text TEXT,
    
    -- GPT validation
    gpt_validation TEXT,
    gpt_validated_at TIMESTAMP,
    gpt_validation_score INTEGER, -- 1-10 rating
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for faster queries
CREATE INDEX idx_recommendations_security_id ON dhanhq.trading_recommendations(security_id);
CREATE INDEX idx_recommendations_generated_at ON dhanhq.trading_recommendations(generated_at DESC);
CREATE INDEX idx_recommendations_symbol ON dhanhq.trading_recommendations(symbol);

-- Create trigger to update updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_recommendations_updated_at 
    BEFORE UPDATE ON dhanhq.trading_recommendations 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();