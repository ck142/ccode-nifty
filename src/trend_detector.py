#!/usr/bin/env python3
"""
Simple Trend Detector
Calculates trends based on price action only
"""

import pandas as pd
import numpy as np
from datetime import datetime
import logging

class SimpleTrendDetector:
    def __init__(self, conn):
        """Initialize the trend detector with database connection"""
        self.conn = conn
        self.logger = logging.getLogger(__name__)
        
    def calculate_simple_trend(self, df):
        """
        Calculate simple trend based on price action
        Returns: trend direction and strength
        """
        if len(df) < 20:
            return 'NEUTRAL', 0.0
            
        # Calculate EMAs with more responsive settings
        df['ema_3'] = df['close'].ewm(span=3, adjust=False).mean()
        df['ema_8'] = df['close'].ewm(span=8, adjust=False).mean()
        df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
        
        # Get latest values
        latest = df.iloc[-1]
        close = latest['close']
        ema_3 = latest['ema_3']
        ema_8 = latest['ema_8']
        ema_20 = latest['ema_20']
        
        # Also check recent price action (last 5 bars)
        recent_prices = df['close'].tail(5)
        price_trend = recent_prices.iloc[-1] - recent_prices.iloc[0]
        price_change_pct = (price_trend / recent_prices.iloc[0]) * 100
        
        # More responsive trend detection
        # Strong downtrend if price below all EMAs and declining
        if close < ema_3 < ema_8 < ema_20 and price_change_pct < -1:
            trend = 'DOWNTREND'
            strength = abs((ema_20 - close) / ema_20) * 100
        # Strong uptrend if price above all EMAs and rising  
        elif close > ema_3 > ema_8 > ema_20 and price_change_pct > 1:
            trend = 'UPTREND'
            strength = ((close - ema_20) / ema_20) * 100
        # Weak downtrend if price below 8 and 20 EMA
        elif close < ema_8 and close < ema_20:
            trend = 'DOWNTREND'
            strength = abs((ema_20 - close) / ema_20) * 100 * 0.7  # Lower strength
        # Weak uptrend if price above 8 and 20 EMA
        elif close > ema_8 and close > ema_20:
            trend = 'UPTREND'
            strength = ((close - ema_20) / ema_20) * 100 * 0.7  # Lower strength
        else:
            trend = 'SIDEWAYS'
            strength = abs((close - ema_20) / ema_20) * 100
            
        return trend, min(strength, 100.0)
    
    def update_missing_trends(self, security_id, interval_minutes):
        """Update trends only for records where simple_trend is NULL"""
        cur = self.conn.cursor()
        updated_count = 0
        
        try:
            # Get records with missing trends
            cur.execute("""
                SELECT datetime 
                FROM dhanhq.price_data 
                WHERE security_id = %s 
                AND interval_minutes = %s 
                AND simple_trend IS NULL
                ORDER BY datetime
            """, (security_id, interval_minutes))
            
            missing_dates = [row[0] for row in cur.fetchall()]
            
            if not missing_dates:
                return 0
            
            # Process in batches
            for target_date in missing_dates:
                # Get 50 records before target date for context
                cur.execute("""
                    SELECT datetime, open, high, low, close, volume
                    FROM dhanhq.price_data
                    WHERE security_id = %s 
                    AND interval_minutes = %s
                    AND datetime <= %s
                    ORDER BY datetime DESC
                    LIMIT 50
                """, (security_id, interval_minutes, target_date))
                
                rows = cur.fetchall()
                
                if len(rows) < 20:
                    # Not enough data for trend calculation
                    cur.execute("""
                        UPDATE dhanhq.price_data
                        SET simple_trend = 'NEUTRAL',
                            simple_trend_strength = 0
                        WHERE security_id = %s 
                        AND interval_minutes = %s
                        AND datetime = %s
                    """, (security_id, interval_minutes, target_date))
                else:
                    # Create DataFrame and calculate trend
                    df = pd.DataFrame(rows, columns=['datetime', 'open', 'high', 'low', 'close', 'volume'])
                    df = df.sort_values('datetime')
                    df['close'] = df['close'].astype(float)
                    
                    trend, strength = self.calculate_simple_trend(df)
                    
                    # Update the specific record
                    cur.execute("""
                        UPDATE dhanhq.price_data
                        SET simple_trend = %s,
                            simple_trend_strength = %s
                        WHERE security_id = %s 
                        AND interval_minutes = %s
                        AND datetime = %s
                    """, (trend, float(strength), security_id, interval_minutes, target_date))
                
                updated_count += cur.rowcount
                
                # Commit every 100 records
                if updated_count % 100 == 0:
                    self.conn.commit()
            
            # Final commit
            self.conn.commit()
            
        except Exception as e:
            self.conn.rollback()
            self.logger.error(f"Error updating trends: {e}")
            raise
        
        return updated_count
    
    def update_missing_daily_trends(self, security_id):
        """Update trends only for daily records where simple_trend is NULL"""
        cur = self.conn.cursor()
        updated_count = 0
        
        try:
            # Get records with missing trends
            cur.execute("""
                SELECT date 
                FROM dhanhq.price_data_daily 
                WHERE security_id = %s 
                AND simple_trend IS NULL
                ORDER BY date
            """, (security_id,))
            
            missing_dates = [row[0] for row in cur.fetchall()]
            
            if not missing_dates:
                return 0
            
            # Process each date
            for target_date in missing_dates:
                # Get 50 records before target date for context
                cur.execute("""
                    SELECT date, open, high, low, close, volume
                    FROM dhanhq.price_data_daily
                    WHERE security_id = %s 
                    AND date <= %s
                    ORDER BY date DESC
                    LIMIT 50
                """, (security_id, target_date))
                
                rows = cur.fetchall()
                
                if len(rows) < 20:
                    # Not enough data for trend calculation
                    cur.execute("""
                        UPDATE dhanhq.price_data_daily
                        SET simple_trend = 'NEUTRAL',
                            simple_trend_strength = 0
                        WHERE security_id = %s 
                        AND date = %s
                    """, (security_id, target_date))
                else:
                    # Create DataFrame and calculate trend
                    df = pd.DataFrame(rows, columns=['datetime', 'open', 'high', 'low', 'close', 'volume'])
                    df = df.sort_values('datetime')
                    df['close'] = df['close'].astype(float)
                    
                    trend, strength = self.calculate_simple_trend(df)
                    
                    # Update the specific record
                    cur.execute("""
                        UPDATE dhanhq.price_data_daily
                        SET simple_trend = %s,
                            simple_trend_strength = %s
                        WHERE security_id = %s 
                        AND date = %s
                    """, (trend, float(strength), security_id, target_date))
                
                updated_count += cur.rowcount
            
            # Commit all changes
            self.conn.commit()
            
        except Exception as e:
            self.conn.rollback()
            self.logger.error(f"Error updating daily trends: {e}")
            raise
        
        return updated_count
    
    def get_current_trend(self, df: pd.DataFrame) -> dict:
        """Get current trend from DataFrame"""
        trend, strength = self.calculate_simple_trend(df)
        
        return {
            'trend': trend,
            'strength': strength,
            'timestamp': datetime.now().isoformat()
        }