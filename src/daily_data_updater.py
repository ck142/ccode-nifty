#!/usr/bin/env python3
"""
Daily Data Updater Module
Downloads latest trading data from DhanHQ API and updates database
Maintains IST timezone consistency with existing data
"""

import os
import psycopg2
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, date
from dotenv import load_dotenv
import logging
import requests
import time

load_dotenv()

class DailyDataUpdater:
    def __init__(self, progress_callback=None):
        """Initialize the daily data updater
        
        Args:
            progress_callback: Function to call with progress updates
        """
        self.api_token = os.getenv('DHAN_API_TOKEN')
        self.client_id = os.getenv('DHAN_CLIENT_ID')
        self.progress_callback = progress_callback
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        
        # Database connection parameters
        self.db_params = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': os.getenv('DB_PORT', 5432),
            'database': os.getenv('DB_NAME', 'trading_db'),
            'user': os.getenv('DB_USER'),
            'password': os.getenv('DB_PASSWORD')
        }
        
        # Security ID for MANKIND
        self.security_id = '15380'
        
    def log_progress(self, message, level='info'):
        """Log progress and call callback if provided"""
        if level == 'info':
            self.logger.info(message)
        elif level == 'error':
            self.logger.error(message)
        elif level == 'warning':
            self.logger.warning(message)
            
        if self.progress_callback:
            self.progress_callback({
                'timestamp': datetime.now().isoformat(),
                'level': level,
                'message': message
            })
    
    def get_db_connection(self):
        """Create database connection"""
        return psycopg2.connect(**self.db_params)
    
    def get_last_timestamp(self, interval_minutes):
        """Get the last timestamp in database for given interval"""
        conn = self.get_db_connection()
        cur = conn.cursor()
        
        try:
            # Determine table and column based on interval
            if interval_minutes == 'daily':
                table = 'price_data_daily'
                date_column = 'date'
                query = f"""
                    SELECT MAX({date_column}) 
                    FROM dhanhq.{table}
                    WHERE security_id = %s
                """
                cur.execute(query, (self.security_id,))
            elif interval_minutes == 'weekly':
                table = 'price_data_weekly'
                date_column = 'date'
                query = f"""
                    SELECT MAX({date_column}) 
                    FROM dhanhq.{table}
                    WHERE security_id = %s
                """
                cur.execute(query, (self.security_id,))
            elif interval_minutes == 'monthly':
                table = 'price_data_monthly'
                date_column = 'date'
                query = f"""
                    SELECT MAX({date_column}) 
                    FROM dhanhq.{table}
                    WHERE security_id = %s
                """
                cur.execute(query, (self.security_id,))
            else:
                query = """
                    SELECT MAX(datetime) 
                    FROM dhanhq.price_data
                    WHERE security_id = %s AND interval_minutes = %s
                """
                cur.execute(query, (self.security_id, interval_minutes))
            
            result = cur.fetchone()
            last_timestamp = result[0] if result and result[0] else None
            
            return last_timestamp
            
        finally:
            cur.close()
            conn.close()
    
    def fetch_historical_data(self, interval, from_date, to_date):
        """Fetch historical data from DhanHQ API"""
        url = "https://api.dhan.co/charts/historical"
        
        # Map interval to DhanHQ format
        interval_map = {
            1: '1',      # 1 minute
            5: '5',      # 5 minutes
            15: '15',    # 15 minutes
            60: '60',    # 1 hour
            'daily': 'D', # Daily
            'weekly': 'W', # Weekly
            'monthly': 'M' # Monthly
        }
        
        headers = {
            'access-token': self.api_token,
            'Content-Type': 'application/json'
        }
        
        params = {
            'symbol': 'MANKIND',
            'exchangeSegment': 'NSE_EQ',
            'instrument': 'EQUITY',
            'expiryCode': '0',
            'fromDate': from_date.strftime('%Y-%m-%d'),
            'toDate': to_date.strftime('%Y-%m-%d'),
            'interval': interval_map[interval]
        }
        
        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            if 'data' in data and 'candles' in data['data']:
                candles = data['data']['candles']
                
                # Convert to DataFrame
                df = pd.DataFrame(candles, columns=[
                    'timestamp', 'open', 'high', 'low', 'close', 'volume'
                ])
                
                # Convert timestamp to datetime (assuming DhanHQ returns IST timestamps)
                # Just convert epoch to datetime without any timezone conversions
                df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
                
                df = df.drop('timestamp', axis=1)
                
                return df
            else:
                self.log_progress(f"No data returned for interval {interval}", 'warning')
                return pd.DataFrame()
                
        except Exception as e:
            self.log_progress(f"Error fetching data: {e}", 'error')
            return pd.DataFrame()
    
    def save_to_database(self, df, interval_minutes):
        """Save data to database maintaining existing schema"""
        if df.empty:
            return 0
        
        conn = self.get_db_connection()
        cur = conn.cursor()
        saved_count = 0
        
        try:
            # Determine table and query based on interval
            if interval_minutes == 'daily':
                table = 'price_data_daily'
                insert_query = f"""
                    INSERT INTO dhanhq.{table} 
                    (security_id, date, open, high, low, close, volume)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (security_id, date) DO NOTHING
                """
            elif interval_minutes == 'weekly':
                table = 'price_data_weekly'
                insert_query = f"""
                    INSERT INTO dhanhq.{table} 
                    (security_id, date, open, high, low, close, volume)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (security_id, date) DO NOTHING
                """
            elif interval_minutes == 'monthly':
                table = 'price_data_monthly'
                insert_query = f"""
                    INSERT INTO dhanhq.{table} 
                    (security_id, date, open, high, low, close, volume)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (security_id, date) DO NOTHING
                """
            else:
                insert_query = """
                    INSERT INTO dhanhq.price_data 
                    (security_id, interval_minutes, datetime, open, high, low, close, volume)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (security_id, interval_minutes, datetime) DO NOTHING
                """
            
            # Insert data
            for _, row in df.iterrows():
                if interval_minutes in ['daily', 'weekly', 'monthly']:
                    values = (
                        self.security_id,
                        row['datetime'],
                        float(row['open']),
                        float(row['high']),
                        float(row['low']),
                        float(row['close']),
                        int(row['volume'])
                    )
                else:
                    values = (
                        self.security_id,
                        interval_minutes,
                        row['datetime'],
                        float(row['open']),
                        float(row['high']),
                        float(row['low']),
                        float(row['close']),
                        int(row['volume'])
                    )
                
                cur.execute(insert_query, values)
                
                if cur.rowcount > 0:
                    saved_count += 1
            
            conn.commit()
            return saved_count
            
        except Exception as e:
            conn.rollback()
            self.log_progress(f"Error saving to database: {e}", 'error')
            raise
        finally:
            cur.close()
            conn.close()
    
    def update_single_interval(self, interval):
        """Update data for a single interval"""
        interval_name = {
            1: '1-minute',
            5: '5-minute',
            15: '15-minute',
            60: '1-hour',
            'daily': 'daily',
            'weekly': 'weekly',
            'monthly': 'monthly'
        }[interval]
        
        self.log_progress(f"Processing {interval_name} data...")
        
        # Get last timestamp
        last_timestamp = self.get_last_timestamp(interval)
        
        if last_timestamp:
            # Remove timezone info if present (keep the time as-is)
            if hasattr(last_timestamp, 'tzinfo') and last_timestamp.tzinfo is not None:
                last_timestamp = last_timestamp.replace(tzinfo=None)
            
            # Add 1 minute/day to avoid duplicate
            if interval in [1, 5, 15, 60]:
                from_date = last_timestamp + timedelta(minutes=1)
            else:
                # For daily/weekly/monthly, last_timestamp is a date object
                # Convert it to datetime for consistent comparison
                if isinstance(last_timestamp, datetime):
                    from_date = last_timestamp + timedelta(days=1)
                else:
                    # Convert date to datetime at start of day
                    from_date = datetime.combine(last_timestamp, datetime.min.time()) + timedelta(days=1)
            
            self.log_progress(f"Last {interval_name} data: {last_timestamp}")
        else:
            # If no data, start from 30 days ago
            from_date = datetime.now() - timedelta(days=30)
            self.log_progress(f"No existing {interval_name} data, starting from {from_date}")
        
        # To date is current time (no timezone)
        to_date = datetime.now()
        
        # Check if update needed
        if from_date >= to_date:
            self.log_progress(f"{interval_name} data is up to date")
            return 0
        
        # Fetch new data
        self.log_progress(f"Fetching {interval_name} data from {from_date} to {to_date}")
        df = self.fetch_historical_data(interval, from_date, to_date)
        
        if df.empty:
            self.log_progress(f"No new {interval_name} data available")
            return 0
        
        # Filter to only new data
        if last_timestamp:
            df = df[df['datetime'] > last_timestamp]
        
        if df.empty:
            self.log_progress(f"No new {interval_name} data after filtering")
            return 0
        
        # Save to database
        saved_count = self.save_to_database(df, interval)
        self.log_progress(f"Saved {saved_count} new {interval_name} records")
        
        return saved_count
    
    def run_daily_update(self):
        """Run the complete daily update process"""
        self.log_progress("="*60)
        self.log_progress("Starting Daily Data Update")
        self.log_progress("="*60)
        
        start_time = datetime.now()
        total_saved = 0
        
        try:
            # Update each interval
            intervals = [1, 5, 15, 60, 'daily', 'weekly', 'monthly']
            
            for interval in intervals:
                saved = self.update_single_interval(interval)
                total_saved += saved
                time.sleep(0.5)  # Rate limiting
            
            elapsed = datetime.now() - start_time
            
            self.log_progress("="*60)
            self.log_progress(f"Daily update completed successfully!")
            self.log_progress(f"Total new records: {total_saved}")
            self.log_progress(f"Time taken: {elapsed}")
            self.log_progress("="*60)
            
            return {
                'status': 'success',
                'total_records': total_saved,
                'duration': str(elapsed)
            }
            
        except Exception as e:
            self.log_progress(f"Daily update failed: {e}", 'error')
            return {
                'status': 'error',
                'error': str(e)
            }

if __name__ == "__main__":
    # Test the updater
    def print_progress(progress):
        print(f"[{progress['level'].upper()}] {progress['message']}")
    
    updater = DailyDataUpdater(progress_callback=print_progress)
    result = updater.run_daily_update()
    print(f"\nResult: {result}")