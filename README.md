# MANKIND Display Dashboard

A minimal Flask dashboard for displaying MANKIND PHARMA trading data with support/resistance levels and trend analysis.

## Setup

1. Install dependencies:
```bash
pip install -r requirements_minimal.txt
```

2. Configure database connection in `.env`:
```
DB_HOST=localhost
DB_PORT=5432
DB_NAME=trading_db
DB_USER=your_user
DB_PASSWORD=your_password
```

3. Run the dashboard:
```bash
python simple_dashboard.py
```

4. Open browser to: http://localhost:5001

## Features

- Real-time price chart with candlesticks
- Support and Resistance levels visualization
- Multi-timeframe trend analysis (5m, 15m, 1h, Daily)
- Trading recommendations based on S/R levels
- Current price and trend status

## Database Requirements

The dashboard expects MANKIND data in PostgreSQL with:
- `dhanhq.price_data` table with OHLC data
- Support/Resistance levels calculated
- Trend analysis completed

## Files

- `simple_dashboard.py` - Main Flask application
- `src/config.py` - Configuration management
- `src/database.py` - Database utilities
- `.env` - Environment variables