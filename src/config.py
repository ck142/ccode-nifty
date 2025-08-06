import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Config:
    """Configuration management for the application"""
    # DhanHQ settings
    dhan_client_id: str = os.getenv('DHAN_CLIENT_ID', '')
    dhan_access_token: str = os.getenv('DHAN_ACCESS_TOKEN', '')
    
    # Database settings
    db_host: str = os.getenv('DB_HOST', 'localhost')
    db_port: int = int(os.getenv('DB_PORT', '5432'))
    db_name: str = os.getenv('DB_NAME', 'market_data')
    db_user: str = os.getenv('DB_USER', 'postgres')
    db_password: str = os.getenv('DB_PASSWORD', '')
    
    # Data settings
    default_exchange: str = os.getenv('DEFAULT_EXCHANGE', 'NSE_EQ')
    default_interval: int = int(os.getenv('DEFAULT_INTERVAL', '1'))
    max_retries: int = int(os.getenv('MAX_RETRIES', '3'))
    retry_delay: int = int(os.getenv('RETRY_DELAY', '5'))
    batch_size: int = int(os.getenv('BATCH_SIZE', '5000'))
    
    @property
    def db_url(self) -> str:
        """Generate PostgreSQL connection URL"""
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
    
    def validate(self):
        """Validate required configuration"""
        if not self.dhan_client_id or not self.dhan_access_token:
            raise ValueError("DhanHQ credentials not configured. Please set DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN")
        
        if not self.db_password:
            raise ValueError("Database password not configured. Please set DB_PASSWORD")