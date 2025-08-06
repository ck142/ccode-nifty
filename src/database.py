import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool
import psycopg2
from psycopg2.extras import execute_values

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Handles all database operations"""
    
    def __init__(self, config):
        self.config = config
        self.engine = create_engine(
            config.db_url,
            poolclass=QueuePool,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True
        )
    
    def test_connection(self) -> bool:
        """Test database connection"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                return result.scalar() == 1
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            return False
    
    def create_schema(self):
        """Create database schema"""
        try:
            with open('sql/schema.sql', 'r') as f:
                schema_sql = f.read()
            
            with self.engine.connect() as conn:
                conn.execute(text(schema_sql))
                conn.commit()
            logger.info("Database schema created successfully")
        except Exception as e:
            logger.error(f"Error creating schema: {e}")
            raise
    
    def upsert_security(self, security_data: Dict) -> None:
        """Insert or update security information"""
        sql = """
            INSERT INTO dhanhq.securities (security_id, symbol, name, exchange, instrument_type, isin)
            VALUES (:security_id, :symbol, :name, :exchange, :instrument_type, :isin)
            ON CONFLICT (security_id) 
            DO UPDATE SET 
                symbol = EXCLUDED.symbol,
                name = EXCLUDED.name,
                updated_at = CURRENT_TIMESTAMP
        """
        
        with self.engine.connect() as conn:
            conn.execute(text(sql), security_data)
            conn.commit()
    
    def insert_price_data(self, df: pd.DataFrame, security_id: str, interval: int) -> int:
        """Bulk insert price data using psycopg2 for better performance"""
        if df.empty:
            return 0
        
        # Prepare data for insertion
        data = []
        for _, row in df.iterrows():
            data.append((
                security_id,
                row['datetime'],
                float(row['open']),
                float(row['high']),
                float(row['low']),
                float(row['close']),
                int(row['volume']),
                interval
            ))
        
        insert_sql = """
            INSERT INTO dhanhq.price_data 
            (security_id, datetime, open, high, low, close, volume, interval_minutes)
            VALUES %s
            ON CONFLICT (security_id, datetime, interval_minutes) 
            DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume
        """
        
        conn = psycopg2.connect(
            host=self.config.db_host,
            port=self.config.db_port,
            database=self.config.db_name,
            user=self.config.db_user,
            password=self.config.db_password
        )
        
        try:
            with conn.cursor() as cursor:
                # Process in batches
                batch_size = self.config.batch_size
                for i in range(0, len(data), batch_size):
                    batch = data[i:i + batch_size]
                    execute_values(
                        cursor,
                        insert_sql,
                        batch,
                        template="(%s, %s, %s, %s, %s, %s, %s, %s)",
                        page_size=1000
                    )
                conn.commit()
                return len(data)
        except Exception as e:
            conn.rollback()
            logger.error(f"Error inserting price data: {e}")
            raise
        finally:
            conn.close()
    
    def get_latest_data_date(self, security_id: str, interval: int) -> Optional[datetime]:
        """Get the latest date for which we have data"""
        sql = """
            SELECT MAX(datetime) 
            FROM dhanhq.price_data 
            WHERE security_id = :security_id 
            AND interval_minutes = :interval
        """
        
        with self.engine.connect() as conn:
            result = conn.execute(
                text(sql), 
                {"security_id": security_id, "interval": interval}
            )
            latest = result.scalar()
            return latest
    
    def log_download(self, security_id: str, from_date: datetime, to_date: datetime, 
                    interval: int, records: int, status: str, error: str = None):
        """Log download history"""
        sql = """
            INSERT INTO dhanhq.download_history 
            (security_id, from_date, to_date, interval_minutes, records_downloaded, status, error_message)
            VALUES (:security_id, :from_date, :to_date, :interval, :records, :status, :error)
        """
        
        with self.engine.connect() as conn:
            conn.execute(text(sql), {
                "security_id": security_id,
                "from_date": from_date,
                "to_date": to_date,
                "interval": interval,
                "records": records,
                "status": status,
                "error": error
            })
            conn.commit()
    
    def get_security_by_symbol(self, symbol: str) -> Optional[Dict]:
        """Get security details by symbol"""
        sql = """
            SELECT security_id, symbol, name, exchange, instrument_type
            FROM dhanhq.securities
            WHERE symbol = :symbol
        """
        
        with self.engine.connect() as conn:
            result = conn.execute(text(sql), {"symbol": symbol})
            row = result.fetchone()
            if row:
                return dict(row._mapping)
            return None
    
    def get_data_summary(self, security_id: str) -> Optional[Dict]:
        """Get summary statistics for a security"""
        sql = """
            SELECT 
                COUNT(*) as total_records,
                MIN(datetime) as first_date,
                MAX(datetime) as last_date,
                COUNT(DISTINCT DATE(datetime)) as trading_days
            FROM dhanhq.price_data
            WHERE security_id = :security_id
        """
        
        with self.engine.connect() as conn:
            result = conn.execute(text(sql), {"security_id": security_id})
            row = result.fetchone()
            if row:
                return dict(row._mapping)
            return None