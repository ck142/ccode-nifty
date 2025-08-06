#!/usr/bin/env python3
"""
S/R Database Updater - Calculates and stores support/resistance levels in database
Uses the SimpleSRDetector for actual S/R detection
"""

import psycopg2
import pandas as pd
from datetime import datetime
import logging
import os
from dotenv import load_dotenv
from .simple_sr_detector import SimpleSRDetector

load_dotenv()

class SRDatabaseUpdater:
    def __init__(self, conn=None):
        """Initialize with database connection"""
        self.logger = logging.getLogger(__name__)
        
        if conn:
            self.conn = conn
        else:
            self.conn = psycopg2.connect(
                host=os.getenv('DB_HOST', 'localhost'),
                port=os.getenv('DB_PORT', 5432),
                database=os.getenv('DB_NAME', 'market_data'),
                user=os.getenv('DB_USER'),
                password=os.getenv('DB_PASSWORD')
            )
        
        self.security_id = '15380'  # MANKIND
        self.symbol = 'MANKIND'
        
    def fetch_price_data(self, interval_minutes=15, limit=500):
        """Fetch price data for S/R calculation"""
        cur = self.conn.cursor()
        
        try:
            cur.execute("""
                SELECT datetime, open, high, low, close, volume
                FROM dhanhq.price_data
                WHERE security_id = %s AND interval_minutes = %s
                ORDER BY datetime DESC
                LIMIT %s
            """, (self.security_id, interval_minutes, limit))
            
            rows = cur.fetchall()
            
            if not rows:
                self.logger.warning(f"No data found for security {self.security_id}")
                return None
                
            df = pd.DataFrame(rows, columns=['datetime', 'open', 'high', 'low', 'close', 'volume'])
            df = df.sort_values('datetime')  # Sort ascending for analysis
            
            return df
            
        finally:
            cur.close()
    
    def save_sr_levels(self, support_levels, resistance_levels, current_price):
        """Save S/R levels to database"""
        cur = self.conn.cursor()
        
        try:
            # Clear existing levels for this security
            cur.execute("""
                DELETE FROM dhanhq.support_resistance_levels
                WHERE security_id = %s
            """, (self.security_id,))
            
            # Insert support levels
            for level in support_levels:
                distance_pct = ((level.price - current_price) / current_price) * 100
                
                cur.execute("""
                    INSERT INTO dhanhq.support_resistance_levels
                    (security_id, symbol, level_type, price, touches, is_round_number,
                     first_seen, last_seen, current_price, distance_percent)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    self.security_id,
                    self.symbol,
                    'support',
                    float(level.price),
                    level.touches,
                    level.is_round_number,
                    level.first_seen,
                    level.last_seen,
                    float(current_price),
                    float(distance_pct)
                ))
            
            # Insert resistance levels
            for level in resistance_levels:
                distance_pct = ((level.price - current_price) / current_price) * 100
                
                cur.execute("""
                    INSERT INTO dhanhq.support_resistance_levels
                    (security_id, symbol, level_type, price, touches, is_round_number,
                     first_seen, last_seen, current_price, distance_percent)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    self.security_id,
                    self.symbol,
                    'resistance',
                    float(level.price),
                    level.touches,
                    level.is_round_number,
                    level.first_seen,
                    level.last_seen,
                    float(current_price),
                    float(distance_pct)
                ))
            
            self.conn.commit()
            
            total_saved = len(support_levels) + len(resistance_levels)
            self.logger.info(f"Saved {total_saved} S/R levels to database")
            
            return total_saved
            
        except Exception as e:
            self.conn.rollback()
            self.logger.error(f"Error saving S/R levels: {e}")
            raise
        finally:
            cur.close()
    
    def update_sr_levels(self, lookback_bars=200):
        """Main method to update S/R levels in database"""
        try:
            # Fetch price data
            df = self.fetch_price_data(interval_minutes=15, limit=lookback_bars)
            
            if df is None or df.empty:
                self.logger.warning("No price data available for S/R calculation")
                return 0
            
            # Get current price
            current_price = float(df.iloc[-1]['close'])
            
            # Initialize S/R detector
            sr_detector = SimpleSRDetector(
                lookback_bars=min(lookback_bars, len(df)),
                min_touches=2,
                cluster_threshold_atr=0.5,
                include_round_numbers=True
            )
            
            # Detect S/R levels
            support_levels, resistance_levels = sr_detector.detect_sr_levels(df, max_support=5, max_resistance=5)
            
            # Save to database
            saved_count = self.save_sr_levels(support_levels, resistance_levels, current_price)
            
            self.logger.info(f"S/R update complete. Found {len(support_levels)} support and {len(resistance_levels)} resistance levels")
            
            return saved_count
            
        except Exception as e:
            self.logger.error(f"Error updating S/R levels: {e}")
            raise
    
    def get_current_sr_levels(self):
        """Get current S/R levels from database"""
        cur = self.conn.cursor()
        
        try:
            cur.execute("""
                SELECT level_type, price, touches, distance_percent
                FROM dhanhq.support_resistance_levels
                WHERE security_id = %s
                ORDER BY level_type DESC, ABS(distance_percent) ASC
            """, (self.security_id,))
            
            rows = cur.fetchall()
            
            support = []
            resistance = []
            
            for row in rows:
                if row[0] == 'support':
                    support.append(float(row[1]))
                else:
                    resistance.append(float(row[1]))
            
            return support[:3], resistance[:3]  # Return top 3 of each
            
        finally:
            cur.close()