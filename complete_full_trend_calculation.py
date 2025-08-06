#!/usr/bin/env python3
"""
Complete trend calculation for ENTIRE historical data series
This will process ALL data, not just recent bars
"""

import psycopg2
import pandas as pd
import numpy as np
import os
from datetime import datetime
from dotenv import load_dotenv
from src.trend_detector import SimpleTrendDetector
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

def get_db_connection():
    """Create database connection"""
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', 5432),
        database=os.getenv('DB_NAME', 'trading_db'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD')
    )

def process_timeframe_complete(interval_minutes, interval_name):
    """Process ALL data for a timeframe, not just recent"""
    logger.info(f"\nProcessing {interval_name} data...")
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Get ALL data for this interval
        query = """
            SELECT datetime, open, high, low, close, volume
            FROM dhanhq.price_data
            WHERE security_id = '15380'
              AND interval_minutes = %s
            ORDER BY datetime
        """
        
        cur.execute(query, (interval_minutes,))
        rows = cur.fetchall()
        
        if not rows:
            logger.warning(f"No data found for {interval_name}")
            return
        
        # Convert to DataFrame
        df = pd.DataFrame(rows, columns=['datetime', 'open', 'high', 'low', 'close', 'volume'])
        df = df.sort_values('datetime')
        df.reset_index(drop=True, inplace=True)
        
        logger.info(f"Loaded {len(df)} rows for {interval_name}")
        
        # Initialize trend detector
        detector = SimpleTrendDetector(swing_lookback=5, min_swing_percent=0.5)
        
        # Analyze entire dataframe
        logger.info(f"Calculating trends for ALL {len(df)} bars...")
        df = detector.analyze_dataframe(df)
        
        # Update ALL rows in database
        logger.info(f"Updating database with trends for ALL {len(df)} rows...")
        
        updated = 0
        batch_size = 100
        
        for i in range(0, len(df), batch_size):
            batch_end = min(i + batch_size, len(df))
            batch = df.iloc[i:batch_end]
            
            for _, row in batch.iterrows():
                update_query = """
                    UPDATE dhanhq.price_data
                    SET simple_trend = %s,
                        simple_trend_strength = %s,
                        swing_count = %s,
                        last_swing_high = %s,
                        last_swing_low = %s
                    WHERE security_id = '15380'
                      AND interval_minutes = %s
                      AND datetime = %s
                """
                
                values = (
                    row.get('simple_trend', 'NEUTRAL'),
                    float(row.get('simple_trend_strength', 0)),
                    int(row.get('swing_count', 0)),
                    float(row['last_swing_high']) if pd.notna(row.get('last_swing_high')) else None,
                    float(row['last_swing_low']) if pd.notna(row.get('last_swing_low')) else None,
                    interval_minutes,
                    row['datetime']
                )
                
                cur.execute(update_query, values)
                updated += 1
            
            conn.commit()
            
            if updated % 1000 == 0:
                logger.info(f"  Updated {updated}/{len(df)} rows...")
        
        logger.info(f"✓ Completed {interval_name}: Updated {updated} rows")
        
    except Exception as e:
        logger.error(f"Error processing {interval_name}: {e}")
        conn.rollback()
        raise
    
    finally:
        cur.close()
        conn.close()

def verify_trend_coverage():
    """Verify trend calculation coverage"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    logger.info("\n" + "=" * 80)
    logger.info("VERIFICATION: Trend Coverage After Update")
    logger.info("=" * 80)
    
    for interval in [1, 5, 15, 60]:
        cur.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(simple_trend) as with_trend,
                COUNT(simple_trend) * 100.0 / COUNT(*) as coverage_pct
            FROM dhanhq.price_data
            WHERE security_id = '15380'
              AND interval_minutes = %s
        """, (interval,))
        
        result = cur.fetchone()
        total, with_trend, coverage = result
        
        logger.info(f"{interval:3}-minute: {with_trend:,}/{total:,} rows have trends ({coverage:.1f}% coverage)")
    
    # Check trend distribution
    logger.info("\nTrend Distribution (15-minute):")
    cur.execute("""
        SELECT simple_trend, COUNT(*) as count
        FROM dhanhq.price_data
        WHERE security_id = '15380'
          AND interval_minutes = 15
          AND simple_trend IS NOT NULL
        GROUP BY simple_trend
        ORDER BY count DESC
    """)
    
    for row in cur.fetchall():
        trend, count = row
        logger.info(f"  {trend:10}: {count:,} bars")
    
    cur.close()
    conn.close()

def main():
    """Main execution function"""
    start_time = datetime.now()
    
    logger.info("=" * 80)
    logger.info("COMPLETE TREND CALCULATION FOR ENTIRE DATA SERIES")
    logger.info("=" * 80)
    logger.info(f"Start Time: {start_time}")
    
    try:
        # Process each timeframe COMPLETELY
        timeframes = [
            (1, '1-minute'),
            (5, '5-minute'),
            (15, '15-minute'),
            (60, '1-hour')
        ]
        
        for interval, name in timeframes:
            process_timeframe_complete(interval, name)
        
        # Verify coverage
        verify_trend_coverage()
        
        elapsed = datetime.now() - start_time
        logger.info("\n" + "=" * 80)
        logger.info(f"✓ COMPLETED SUCCESSFULLY!")
        logger.info(f"Total Time: {elapsed}")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise

if __name__ == "__main__":
    main()