# MANKIND Trading Display Dashboard - Architecture

## Overview
A minimal Flask-based web dashboard for displaying MANKIND PHARMA LIMITED trading data with support/resistance levels and trend analysis.

## Current Status (August 6, 2025)
- **Purpose**: Display-only dashboard for MANKIND trading data
- **Data**: 268,563 records of MANKIND PHARMA LIMITED in PostgreSQL
- **Features**: Real-time charts, S/R levels, multi-timeframe trends

## Architecture

### Files Structure
```
.
├── simple_dashboard.py      # Main Flask application (port 8083)
├── src/
│   ├── __init__.py         # Package initialization
│   ├── config.py           # Configuration management
│   └── database.py         # Database connection utilities
├── .env                    # Environment variables
├── .env.example           # Example environment configuration
├── requirements.txt       # Minimal dependencies
└── README_DISPLAY.md      # Display setup documentation
```

### Database Schema
- **Database**: PostgreSQL (`dhanhq` schema)
- **Main Table**: `dhanhq.price_data`
  - OHLC data with timestamps
  - Support/Resistance levels (resistance_1/2/3, support_1/2/3)
  - Trend information (simple_trend, simple_trend_strength)
  - Interval-based data (1m, 5m, 15m, 60m)

### Key Components

1. **simple_dashboard.py**
   - Flask web server on port 8083
   - Self-contained HTML/JS/CSS in single file
   - Uses lightweight-charts for visualization
   - API endpoints:
     - `/` - Main dashboard page
     - `/api/price_data` - OHLC data with S/R levels
     - `/api/trend_status` - Multi-timeframe trend analysis

2. **Configuration** (.env)
   ```
   DB_HOST=localhost
   DB_PORT=5432
   DB_NAME=trading_db
   DB_USER=your_user
   DB_PASSWORD=your_password
   ```

3. **Dependencies** (requirements.txt)
   - flask==3.1.1
   - psycopg2-binary==2.9.7
   - python-dotenv==1.0.0

## Features

### Display Components
- **Price Chart**: Candlestick chart with real-time updates
- **S/R Levels**: Visual representation of support and resistance
- **Trend Analysis**: 
  - 5-minute
  - 15-minute
  - 1-hour
  - Daily
- **Trading Signals**: Based on price position relative to S/R levels
- **Current Status**: Price, trend direction, and strength

### Data Flow
1. Dashboard queries PostgreSQL for latest MANKIND data
2. Retrieves OHLC, S/R levels, and trend information
3. Renders interactive chart with overlays
4. Updates every 30 seconds automatically

## Running the Application

```bash
# Install dependencies
pip install -r requirements.txt

# Configure database in .env file

# Start the dashboard
python3 simple_dashboard.py

# Access at http://localhost:8083
```

## Important Notes

1. **Display Only**: This is a read-only dashboard. No data processing or calculation features are included.

2. **Single Security**: Configured specifically for MANKIND PHARMA LIMITED (security_id: 15380)

3. **Pre-calculated Data**: Assumes S/R levels and trends are already calculated in the database

4. **Archived Components**: All data download, processing, and analysis components have been archived in `archived_code/`

5. **Minimal Footprint**: Only 8 files total, focused solely on data visualization

## Security Considerations
- Database credentials stored in .env (not committed to version control)
- Read-only database access recommended
- No external API calls or data modifications
- Flask development server (use production WSGI for deployment)