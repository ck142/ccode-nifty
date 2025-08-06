#!/usr/bin/env python3
"""
Daily Data Updater Module V2
Downloads latest trading data from DhanHQ API v2 and updates database
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
import json

load_dotenv()

class DailyDataUpdaterV2:
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
                # Weekly table uses week_start_date and week_end_date
                date_column = 'week_end_date'
                query = f"""
                    SELECT MAX({date_column}) 
                    FROM dhanhq.{table}
                    WHERE security_id = %s
                """
                cur.execute(query, (self.security_id,))
            elif interval_minutes == 'monthly':
                table = 'price_data_monthly'
                # Monthly table uses month column
                date_column = 'month'
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
    
    def fetch_intraday_data(self, interval, from_date, to_date):
        """Fetch intraday data from DhanHQ API v2
        
        Note: Intraday data is limited to last 5 trading days per request
        """
        # Check if API token exists
        if not self.api_token:
            self.log_progress("API Token not found! Please set DHAN_API_TOKEN in .env file", 'error')
            return pd.DataFrame()
            
        url = "https://api.dhan.co/v2/charts/intraday"
        
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'access-token': self.api_token
        }
        
        # Convert interval to string format as per API docs
        interval_str = str(interval)
        
        payload = {
            'securityId': self.security_id,
            'exchangeSegment': 'NSE_EQ',
            'instrument': 'EQUITY',
            'interval': interval_str,  # String format: "1", "5", "15", or "60"
            'fromDate': from_date.strftime('%Y-%m-%d'),
            'toDate': to_date.strftime('%Y-%m-%d')  # Non-inclusive end date
        }
        
        try:
            self.log_progress(f"Fetching {interval}-minute data from {from_date.strftime('%Y-%m-%d')} to {to_date.strftime('%Y-%m-%d')}", 'info')
            response = requests.post(url, headers=headers, json=payload)
            
            # Log response details if error
            if response.status_code != 200:
                self.log_progress(f"API Error Response: Status={response.status_code}, Body={response.text}", 'error')
                response.raise_for_status()
            
            data = response.json()
            
            # The v2 API returns data directly, not nested
            if isinstance(data, dict) and 'timestamp' in data:
                # Data comes as dict with arrays for each field
                timestamps = data.get('timestamp', [])
                opens = data.get('open', [])
                highs = data.get('high', [])
                lows = data.get('low', [])
                closes = data.get('close', [])
                volumes = data.get('volume', [])
                
                if timestamps:
                    # Create DataFrame from arrays
                    df = pd.DataFrame({
                        'timestamp': timestamps,
                        'open': opens,
                        'high': highs,
                        'low': lows,
                        'close': closes,
                        'volume': volumes
                    })
                    
                    # Convert timestamp to datetime (epoch seconds to datetime)
                    df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
                    df = df.drop('timestamp', axis=1)
                    
                    self.log_progress(f"Received {len(df)} candles for interval {interval}", 'info')
                    return df
                else:
                    self.log_progress(f"No data returned for interval {interval}", 'warning')
                    return pd.DataFrame()
            else:
                self.log_progress(f"Unexpected response format for interval {interval}", 'warning')
                self.log_progress(f"Response keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}", 'info')
                return pd.DataFrame()
                
        except Exception as e:
            self.log_progress(f"Error fetching intraday data: {e}", 'error')
            return pd.DataFrame()
    
    def fetch_historical_data(self, interval, from_date, to_date):
        """Fetch historical (daily/weekly/monthly) data from DhanHQ API v2"""
        url = "https://api.dhan.co/v2/charts/historical"
        
        # Map interval to DhanHQ format
        interval_map = {
            'daily': 'D',
            'weekly': 'W', 
            'monthly': 'M'
        }
        
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'access-token': self.api_token
        }
        
        payload = {
            'securityId': self.security_id,
            'exchangeSegment': 'NSE_EQ',
            'instrument': 'EQUITY',
            'expiryCode': '0',
            'fromDate': from_date.strftime('%Y-%m-%d'),
            'toDate': to_date.strftime('%Y-%m-%d'),
            'interval': interval_map[interval]
        }
        
        try:
            self.log_progress(f"Fetching {interval} data from {from_date.strftime('%Y-%m-%d')} to {to_date.strftime('%Y-%m-%d')}", 'info')
            response = requests.post(url, headers=headers, json=payload)
            
            if response.status_code != 200:
                self.log_progress(f"API Error Response: Status={response.status_code}, Body={response.text}", 'error')
                response.raise_for_status()
            
            data = response.json()
            
            # The v2 API returns data directly, not nested
            if isinstance(data, dict) and 'timestamp' in data:
                # Data comes as dict with arrays for each field
                timestamps = data.get('timestamp', [])
                opens = data.get('open', [])
                highs = data.get('high', [])
                lows = data.get('low', [])
                closes = data.get('close', [])
                volumes = data.get('volume', [])
                
                if timestamps:
                    # Create DataFrame from arrays
                    df = pd.DataFrame({
                        'timestamp': timestamps,
                        'open': opens,
                        'high': highs,
                        'low': lows,
                        'close': closes,
                        'volume': volumes
                    })
                    
                    # Convert timestamp to datetime
                    df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
                    df = df.drop('timestamp', axis=1)
                    
                    self.log_progress(f"Received {len(df)} {interval} candles", 'info')
                    return df
                else:
                    self.log_progress(f"No data returned for interval {interval}", 'warning')
                    return pd.DataFrame()
            else:
                self.log_progress(f"Unexpected response format for interval {interval}", 'warning')
                self.log_progress(f"Response keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}", 'info')
                return pd.DataFrame()
                
        except Exception as e:
            self.log_progress(f"Error fetching historical data: {e}", 'error')
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
                
                # Insert data
                for _, row in df.iterrows():
                    # For daily data, adjust the date if it's showing previous day at 18:30
                    trade_date = row['datetime']
                    if trade_date.hour >= 18:  # If time is 18:30 or later, it's actually next day's data
                        trade_date = trade_date + timedelta(days=1)
                    
                    values = (
                        self.security_id,
                        trade_date.date(),  # Convert to date for daily table
                        float(row['open']),
                        float(row['high']),
                        float(row['low']),
                        float(row['close']),
                        int(row['volume'])
                    )
                    cur.execute(insert_query, values)
                    if cur.rowcount > 0:
                        saved_count += 1
                        
            elif interval_minutes == 'weekly':
                table = 'price_data_weekly'
                # Weekly table has week_start_date and week_end_date
                insert_query = f"""
                    INSERT INTO dhanhq.{table} 
                    (security_id, week_start_date, week_end_date, open, high, low, close, volume)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (security_id, week_start_date) DO NOTHING
                """
                
                # Insert data
                for _, row in df.iterrows():
                    # Calculate week start (Monday) and end (Friday) dates
                    week_end = row['datetime'].date()
                    week_start = week_end - timedelta(days=week_end.weekday())
                    
                    values = (
                        self.security_id,
                        week_start,
                        week_end,
                        float(row['open']),
                        float(row['high']),
                        float(row['low']),
                        float(row['close']),
                        int(row['volume'])
                    )
                    cur.execute(insert_query, values)
                    if cur.rowcount > 0:
                        saved_count += 1
                        
            elif interval_minutes == 'monthly':
                table = 'price_data_monthly'
                # Monthly table uses year and month columns (integers)
                insert_query = f"""
                    INSERT INTO dhanhq.{table} 
                    (security_id, year, month, first_date, last_date, open, high, low, close, volume)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (security_id, year, month) DO NOTHING
                """
                
                # Insert data
                for _, row in df.iterrows():
                    # Extract year and month from datetime
                    trade_date = row['datetime']
                    if trade_date.hour >= 18:  # Adjust date if needed
                        trade_date = trade_date + timedelta(days=1)
                    
                    year = trade_date.year
                    month = trade_date.month
                    
                    # Calculate first and last dates of the month
                    first_date = trade_date.date().replace(day=1)
                    if month == 12:
                        last_date = date(year, 12, 31)
                    else:
                        last_date = date(year, month + 1, 1) - timedelta(days=1)
                    
                    values = (
                        self.security_id,
                        year,
                        month,
                        first_date,
                        last_date,
                        float(row['open']),
                        float(row['high']),
                        float(row['low']),
                        float(row['close']),
                        int(row['volume'])
                    )
                    cur.execute(insert_query, values)
                    if cur.rowcount > 0:
                        saved_count += 1
                        
            else:
                # Intraday data
                insert_query = """
                    INSERT INTO dhanhq.price_data 
                    (security_id, interval_minutes, datetime, open, high, low, close, volume)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (security_id, interval_minutes, datetime) DO NOTHING
                """
                
                # Insert data
                for _, row in df.iterrows():
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
    
    def update_intraday_batch(self, interval, from_date, to_date):
        """Update intraday data in batches of 5 days (API limitation)"""
        current_date = from_date
        total_saved = 0
        
        while current_date < to_date:
            # Calculate batch end date (max 5 days)
            batch_end = min(current_date + timedelta(days=5), to_date)
            
            self.log_progress(f"Fetching {interval}-minute data from {current_date.date()} to {batch_end.date()}")
            
            # Fetch data for this batch
            df = self.fetch_intraday_data(interval, current_date, batch_end)
            
            if not df.empty:
                # Filter to only new data
                last_timestamp = self.get_last_timestamp(interval)
                if last_timestamp:
                    if hasattr(last_timestamp, 'tzinfo') and last_timestamp.tzinfo is not None:
                        last_timestamp = last_timestamp.replace(tzinfo=None)
                    df = df[df['datetime'] > last_timestamp]
                
                if not df.empty:
                    saved = self.save_to_database(df, interval)
                    total_saved += saved
                    self.log_progress(f"Saved {saved} records for batch {current_date.date()} to {batch_end.date()}")
            
            # Move to next batch
            current_date = batch_end
            time.sleep(0.5)  # Rate limiting
        
        return total_saved
    
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
            # Remove timezone info if present
            if hasattr(last_timestamp, 'tzinfo') and last_timestamp.tzinfo is not None:
                last_timestamp = last_timestamp.replace(tzinfo=None)
            
            # Add appropriate time delta to avoid duplicate
            if interval in [1, 5, 15, 60]:
                from_date = last_timestamp + timedelta(minutes=1)
            else:
                # For daily/weekly/monthly, handle different data types
                if isinstance(last_timestamp, datetime):
                    from_date = last_timestamp + timedelta(days=1)
                elif isinstance(last_timestamp, date):
                    # Convert date to datetime at start of day
                    from_date = datetime.combine(last_timestamp, datetime.min.time()) + timedelta(days=1)
                elif isinstance(last_timestamp, int):
                    # Monthly table returns month as integer (1-12)
                    # Assume current year and get first day of next month
                    current_year = datetime.now().year
                    if last_timestamp == 12:
                        from_date = datetime(current_year + 1, 1, 1)
                    else:
                        from_date = datetime(current_year, last_timestamp + 1, 1)
                else:
                    # Fallback to 2 years ago
                    from_date = datetime.now() - timedelta(days=730)
            
            self.log_progress(f"Last {interval_name} data: {last_timestamp}")
        else:
            # If no data, start from 30 days ago for intraday, 2 years for daily
            if interval in [1, 5, 15, 60]:
                from_date = datetime.now() - timedelta(days=30)
            else:
                from_date = datetime.now() - timedelta(days=730)  # 2 years
            self.log_progress(f"No existing {interval_name} data, starting from {from_date}")
        
        # To date is current time
        to_date = datetime.now()
        
        # Check if market is closed (after 3:30 PM IST = 10:00 AM UTC/6:00 AM EST)
        current_hour = datetime.now().hour
        if interval in [1, 5, 15, 60] and current_hour >= 10:  # After market close
            # For intraday, check if we have today's closing data
            if last_timestamp and last_timestamp.date() == datetime.now().date():
                if last_timestamp.hour == 9 and last_timestamp.minute >= 59:  # Have closing data (3:29 PM IST)
                    self.log_progress(f"{interval_name} data is complete for today (market closed)")
                    return 0
        
        # Check if update needed
        if from_date >= to_date:
            self.log_progress(f"{interval_name} data is up to date")
            return 0
        
        # Fetch and save data
        if interval in [1, 5, 15, 60]:
            # Intraday data - use batch processing
            saved_count = self.update_intraday_batch(interval, from_date, to_date)
        else:
            # Historical data - single request
            self.log_progress(f"Fetching {interval_name} data from {from_date.date()} to {to_date.date()}")
            df = self.fetch_historical_data(interval, from_date, to_date)
            
            if df.empty:
                self.log_progress(f"No new {interval_name} data available")
                return 0
            
            # Filter to only new data
            if last_timestamp:
                # Convert last_timestamp to datetime if it's a date object
                if isinstance(last_timestamp, date) and not isinstance(last_timestamp, datetime):
                    last_timestamp = datetime.combine(last_timestamp, datetime.min.time())
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
        self.log_progress("Starting Daily Data Update (v2 API)")
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
    
    updater = DailyDataUpdaterV2(progress_callback=print_progress)
    result = updater.run_daily_update()
    print(f"\nResult: {result}")