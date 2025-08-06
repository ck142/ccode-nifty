#!/usr/bin/env python3
"""
Comprehensive script to calculate trends and S/R levels for ALL historical data
This will process all timeframes and ensure complete coverage
"""

import psycopg2
import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta
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

class SupportResistanceDetector:
    """Calculate support and resistance levels"""
    
    def __init__(self, lookback_periods=100, touch_threshold=0.02):
        self.lookback_periods = lookback_periods
        self.touch_threshold = touch_threshold  # 2% threshold for considering a touch
    
    def calculate_levels(self, df):
        """Calculate S/R levels from price data"""
        if len(df) < 20:
            return None
            
        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values
        
        # Find local peaks and troughs
        resistance_levels = []
        support_levels = []
        
        # Use a simple method: find local maxima/minima
        for i in range(10, len(df) - 10):
            # Check for local maximum (resistance)
            if highs[i] == max(highs[i-10:i+11]):
                resistance_levels.append(highs[i])
            
            # Check for local minimum (support)
            if lows[i] == min(lows[i-10:i+11]):
                support_levels.append(lows[i])
        
        # Cluster nearby levels
        def cluster_levels(levels, threshold_pct=1.0):
            if not levels:
                return []
            
            levels = sorted(levels)
            clustered = []
            current_cluster = [levels[0]]
            
            for level in levels[1:]:
                if (level - current_cluster[0]) / current_cluster[0] * 100 <= threshold_pct:
                    current_cluster.append(level)
                else:
                    clustered.append(np.mean(current_cluster))
                    current_cluster = [level]
            
            if current_cluster:
                clustered.append(np.mean(current_cluster))
            
            return clustered
        
        resistance_levels = cluster_levels(resistance_levels)
        support_levels = cluster_levels(support_levels)
        
        # Get top 3 resistance and support levels
        current_price = closes[-1]
        
        # Resistance levels (above current price)
        res_above = [r for r in resistance_levels if r > current_price]
        res_above = sorted(res_above)[:3]
        
        # Support levels (below current price)
        sup_below = [s for s in support_levels if s < current_price]
        sup_below = sorted(sup_below, reverse=True)[:3]
        
        # Pad with None if we don't have 3 levels
        while len(res_above) < 3:
            res_above.append(None)
        while len(sup_below) < 3:
            sup_below.append(None)
        
        # Count touches for each level
        def count_touches(level, prices, threshold_pct):
            if level is None:
                return 0
            touches = 0
            for price in prices:
                if abs(price - level) / level * 100 <= threshold_pct:
                    touches += 1
            return touches
        
        result = {
            'resistance_1': res_above[0],
            'resistance_2': res_above[1],
            'resistance_3': res_above[2],
            'support_1': sup_below[0],
            'support_2': sup_below[1],
            'support_3': sup_below[2],
        }
        
        # Add touch counts
        all_prices = np.concatenate([highs, lows, closes])
        for i in range(1, 4):
            if result[f'resistance_{i}'] is not None:
                result[f'resistance_{i}_touches'] = count_touches(
                    result[f'resistance_{i}'], all_prices, self.touch_threshold * 100
                )
            else:
                result[f'resistance_{i}_touches'] = 0
                
            if result[f'support_{i}'] is not None:
                result[f'support_{i}_touches'] = count_touches(
                    result[f'support_{i}'], all_prices, self.touch_threshold * 100
                )
            else:
                result[f'support_{i}_touches'] = 0
        
        return result


def get_db_connection():
    """Create database connection"""
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', 5432),
        database=os.getenv('DB_NAME', 'trading_db'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD')
    )


def process_intraday_data(interval_minutes):
    """Process intraday data for trends and S/R"""
    logger.info(f"Processing {interval_minutes}-minute data...")
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Get all data for this interval
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
            logger.warning(f"No data found for {interval_minutes}-minute interval")
            return
        
        # Convert to DataFrame
        df = pd.DataFrame(rows, columns=['datetime', 'open', 'high', 'low', 'close', 'volume'])
        df = df.sort_values('datetime')
        df.reset_index(drop=True, inplace=True)
        
        logger.info(f"Loaded {len(df)} rows for {interval_minutes}-minute data")
        
        # Initialize detectors
        trend_detector = SimpleTrendDetector(swing_lookback=5, min_swing_percent=0.5)
        sr_detector = SupportResistanceDetector(lookback_periods=100)
        
        # Process in sliding windows for better accuracy
        window_size = 500  # Process 500 bars at a time
        step_size = 100    # Move forward 100 bars each time
        
        updates = []
        
        for start_idx in range(0, len(df), step_size):
            end_idx = min(start_idx + window_size, len(df))
            window_df = df.iloc[start_idx:end_idx].copy()
            
            if len(window_df) < 50:  # Need minimum data for analysis
                continue
            
            # Calculate trends for this window
            window_df = trend_detector.analyze_dataframe(window_df)
            
            # Calculate S/R levels
            sr_levels = sr_detector.calculate_levels(window_df)
            
            # Prepare updates for the last 'step_size' rows of this window
            update_start = max(0, len(window_df) - step_size)
            for i in range(update_start, len(window_df)):
                row = window_df.iloc[i]
                update = {
                    'datetime': row['datetime'],
                    'trend': row.get('simple_trend', 'NEUTRAL'),
                    'trend_strength': row.get('simple_trend_strength', 0),
                    'swing_count': row.get('swing_count', 0),
                    'last_swing_high': row.get('last_swing_high'),
                    'last_swing_low': row.get('last_swing_low'),
                }
                
                # Add S/R levels (use same levels for all rows in this batch)
                if sr_levels:
                    update.update(sr_levels)
                
                updates.append(update)
            
            if len(updates) >= 1000:  # Batch update every 1000 rows
                logger.info(f"Updating {len(updates)} rows...")
                batch_update_intraday(cur, conn, updates, interval_minutes)
                updates = []
        
        # Update remaining rows
        if updates:
            logger.info(f"Updating final {len(updates)} rows...")
            batch_update_intraday(cur, conn, updates, interval_minutes)
        
        conn.commit()
        logger.info(f"Completed {interval_minutes}-minute data processing")
        
    except Exception as e:
        logger.error(f"Error processing {interval_minutes}-minute data: {e}")
        conn.rollback()
        raise
    
    finally:
        cur.close()
        conn.close()


def batch_update_intraday(cur, conn, updates, interval_minutes):
    """Batch update intraday data"""
    for update in updates:
        query = """
            UPDATE dhanhq.price_data
            SET simple_trend = %s,
                simple_trend_strength = %s,
                swing_count = %s,
                last_swing_high = %s,
                last_swing_low = %s,
                resistance_1 = %s,
                resistance_1_touches = %s,
                resistance_2 = %s,
                resistance_2_touches = %s,
                resistance_3 = %s,
                resistance_3_touches = %s,
                support_1 = %s,
                support_1_touches = %s,
                support_2 = %s,
                support_2_touches = %s,
                support_3 = %s,
                support_3_touches = %s,
                sr_levels_updated_at = CURRENT_TIMESTAMP
            WHERE security_id = '15380'
              AND interval_minutes = %s
              AND datetime = %s
        """
        
        # Convert numpy types to Python native types
        def convert_value(val):
            if val is None:
                return None
            if isinstance(val, (np.integer, np.int64)):
                return int(val)
            if isinstance(val, (np.floating, np.float64)):
                return float(val)
            return val
        
        values = (
            update['trend'],
            float(update['trend_strength']),
            int(update.get('swing_count', 0)),
            convert_value(update.get('last_swing_high')),
            convert_value(update.get('last_swing_low')),
            convert_value(update.get('resistance_1')),
            int(update.get('resistance_1_touches', 0)),
            convert_value(update.get('resistance_2')),
            int(update.get('resistance_2_touches', 0)),
            convert_value(update.get('resistance_3')),
            int(update.get('resistance_3_touches', 0)),
            convert_value(update.get('support_1')),
            int(update.get('support_1_touches', 0)),
            convert_value(update.get('support_2')),
            int(update.get('support_2_touches', 0)),
            convert_value(update.get('support_3')),
            int(update.get('support_3_touches', 0)),
            interval_minutes,
            update['datetime']
        )
        
        cur.execute(query, values)
    
    conn.commit()


def process_daily_data():
    """Process daily data for S/R levels (trends already exist)"""
    logger.info("Processing daily data for S/R levels...")
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Get all daily data
        query = """
            SELECT date, open, high, low, close, volume
            FROM dhanhq.price_data_daily
            WHERE security_id = '15380'
            ORDER BY date
        """
        
        cur.execute(query)
        rows = cur.fetchall()
        
        df = pd.DataFrame(rows, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
        logger.info(f"Loaded {len(df)} daily records")
        
        # Calculate S/R levels
        sr_detector = SupportResistanceDetector(lookback_periods=100)
        
        # Process in sliding windows
        for i in range(20, len(df)):
            window_df = df.iloc[max(0, i-100):i+1]
            sr_levels = sr_detector.calculate_levels(window_df)
            
            if sr_levels:
                # Update the current date with S/R levels
                update_query = """
                    UPDATE dhanhq.price_data_daily
                    SET resistance_1 = %s,
                        resistance_1_touches = %s,
                        resistance_2 = %s,
                        resistance_2_touches = %s,
                        resistance_3 = %s,
                        resistance_3_touches = %s,
                        support_1 = %s,
                        support_1_touches = %s,
                        support_2 = %s,
                        support_2_touches = %s,
                        support_3 = %s,
                        support_3_touches = %s,
                        sr_levels_updated_at = CURRENT_TIMESTAMP
                    WHERE security_id = '15380'
                      AND date = %s
                """
                
                values = (
                    sr_levels.get('resistance_1'),
                    sr_levels.get('resistance_1_touches', 0),
                    sr_levels.get('resistance_2'),
                    sr_levels.get('resistance_2_touches', 0),
                    sr_levels.get('resistance_3'),
                    sr_levels.get('resistance_3_touches', 0),
                    sr_levels.get('support_1'),
                    sr_levels.get('support_1_touches', 0),
                    sr_levels.get('support_2'),
                    sr_levels.get('support_2_touches', 0),
                    sr_levels.get('support_3'),
                    sr_levels.get('support_3_touches', 0),
                    df.iloc[i]['date']
                )
                
                cur.execute(update_query, values)
        
        conn.commit()
        logger.info("Completed daily S/R calculation")
        
    except Exception as e:
        logger.error(f"Error processing daily data: {e}")
        conn.rollback()
        raise
    
    finally:
        cur.close()
        conn.close()


def process_weekly_data():
    """Process weekly data for S/R levels"""
    logger.info("Processing weekly data for S/R levels...")
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Get all weekly data
        query = """
            SELECT week_start_date, open, high, low, close, volume
            FROM dhanhq.price_data_weekly
            WHERE security_id = '15380'
            ORDER BY week_start_date
        """
        
        cur.execute(query)
        rows = cur.fetchall()
        
        df = pd.DataFrame(rows, columns=['week_start_date', 'open', 'high', 'low', 'close', 'volume'])
        logger.info(f"Loaded {len(df)} weekly records")
        
        # Calculate S/R levels
        sr_detector = SupportResistanceDetector(lookback_periods=52)  # 52 weeks lookback
        
        for i in range(10, len(df)):
            window_df = df.iloc[max(0, i-52):i+1]
            sr_levels = sr_detector.calculate_levels(window_df)
            
            if sr_levels:
                # Update the current week with S/R levels
                update_query = """
                    UPDATE dhanhq.price_data_weekly
                    SET resistance_1 = %s,
                        resistance_1_touches = %s,
                        resistance_2 = %s,
                        resistance_2_touches = %s,
                        resistance_3 = %s,
                        resistance_3_touches = %s,
                        support_1 = %s,
                        support_1_touches = %s,
                        support_2 = %s,
                        support_2_touches = %s,
                        support_3 = %s,
                        support_3_touches = %s,
                        sr_levels_updated_at = CURRENT_TIMESTAMP
                    WHERE security_id = '15380'
                      AND week_start_date = %s
                """
                
                values = (
                    sr_levels.get('resistance_1'),
                    sr_levels.get('resistance_1_touches', 0),
                    sr_levels.get('resistance_2'),
                    sr_levels.get('resistance_2_touches', 0),
                    sr_levels.get('resistance_3'),
                    sr_levels.get('resistance_3_touches', 0),
                    sr_levels.get('support_1'),
                    sr_levels.get('support_1_touches', 0),
                    sr_levels.get('support_2'),
                    sr_levels.get('support_2_touches', 0),
                    sr_levels.get('support_3'),
                    sr_levels.get('support_3_touches', 0),
                    df.iloc[i]['week_start_date']
                )
                
                cur.execute(update_query, values)
        
        conn.commit()
        logger.info("Completed weekly S/R calculation")
        
    except Exception as e:
        logger.error(f"Error processing weekly data: {e}")
        conn.rollback()
        raise
    
    finally:
        cur.close()
        conn.close()


def main():
    """Main execution function"""
    logger.info("=" * 80)
    logger.info("STARTING COMPREHENSIVE TREND AND S/R CALCULATION")
    logger.info("=" * 80)
    
    start_time = datetime.now()
    
    try:
        # Process intraday data
        logger.info("\n--- Processing Intraday Data ---")
        for interval in [5, 15, 60]:  # Skip 1-minute for now (too much data)
            process_intraday_data(interval)
        
        # Process daily data for S/R
        logger.info("\n--- Processing Daily Data ---")
        process_daily_data()
        
        # Process weekly data for S/R
        logger.info("\n--- Processing Weekly Data ---")
        process_weekly_data()
        
        # Note: Monthly data columns might need to be added first
        logger.info("\nMonthly S/R calculation skipped (columns may need to be added)")
        
        elapsed = datetime.now() - start_time
        logger.info("=" * 80)
        logger.info(f"COMPLETED! Total time: {elapsed}")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise


if __name__ == "__main__":
    main()