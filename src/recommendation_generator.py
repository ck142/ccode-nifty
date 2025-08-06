#!/usr/bin/env python3
"""
Recommendation Generator Module
Generates trading recommendations and stores them in database
"""

import os
import psycopg2
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
from dotenv import load_dotenv
import logging
from src.trend_detector import SimpleTrendDetector
from src.simple_sr_detector import SimpleSRDetector as SupportResistanceDetector
# from src.askgpt_integration import TradingGPTAdvisor  # Temporarily disabled

load_dotenv()

class RecommendationGenerator:
    def __init__(self):
        """Initialize the recommendation generator"""
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
        
        # Security details
        self.security_id = '15380'
        self.symbol = 'MANKIND'
        
        # Initialize detectors (will pass connection when needed)
        self.sr_detector = SupportResistanceDetector()
        # self.gpt_advisor = TradingGPTAdvisor()  # Temporarily disabled
    
    def get_db_connection(self):
        """Create database connection"""
        return psycopg2.connect(**self.db_params)
    
    def get_latest_data(self, interval_minutes, limit=500):
        """Get latest price data for analysis"""
        conn = self.get_db_connection()
        cur = conn.cursor()
        
        try:
            if interval_minutes == 'daily':
                query = """
                    SELECT date as datetime, open, high, low, close, volume,
                           simple_trend, simple_trend_strength
                    FROM dhanhq.price_data_daily
                    WHERE security_id = %s
                    ORDER BY date DESC
                    LIMIT %s
                """
                cur.execute(query, (self.security_id, limit))
            elif interval_minutes == 'weekly':
                query = """
                    SELECT week_end_date as datetime, open, high, low, close, volume,
                           simple_trend, simple_trend_strength
                    FROM dhanhq.price_data_weekly
                    WHERE security_id = %s
                    ORDER BY week_end_date DESC
                    LIMIT %s
                """
                cur.execute(query, (self.security_id, limit))
            elif interval_minutes == 'monthly':
                query = """
                    SELECT last_date as datetime, open, high, low, close, volume,
                           simple_trend, simple_trend_strength
                    FROM dhanhq.price_data_monthly
                    WHERE security_id = %s
                    ORDER BY year DESC, month DESC
                    LIMIT %s
                """
                cur.execute(query, (self.security_id, limit))
            else:
                query = """
                    SELECT datetime, open, high, low, close, volume,
                           simple_trend, simple_trend_strength
                    FROM dhanhq.price_data
                    WHERE security_id = %s AND interval_minutes = %s
                    ORDER BY datetime DESC
                    LIMIT %s
                """
                cur.execute(query, (self.security_id, interval_minutes, limit))
            
            columns = ['datetime', 'open', 'high', 'low', 'close', 'volume', 
                      'simple_trend', 'simple_trend_strength']
            data = cur.fetchall()
            
            if data:
                df = pd.DataFrame(data, columns=columns)
                df = df.sort_values('datetime').reset_index(drop=True)
                return df
            else:
                return pd.DataFrame()
                
        finally:
            cur.close()
            conn.close()
    
    def get_current_trends(self):
        """Get current trends for all timeframes"""
        trends = {}
        
        timeframes = [
            (1, '1min'),
            (5, '5min'),
            (15, '15min'),
            (60, '60min'),
            ('daily', 'daily'),
            ('weekly', 'weekly'),
            ('monthly', 'monthly')
        ]
        
        for interval, name in timeframes:
            df = self.get_latest_data(interval, limit=10)
            if not df.empty and 'simple_trend' in df.columns:
                latest_trend = df.iloc[-1]['simple_trend']
                trends[f'trend_{name}'] = latest_trend
            else:
                trends[f'trend_{name}'] = 'UNKNOWN'
        
        return trends
    
    def calculate_support_resistance(self):
        """Calculate support and resistance levels"""
        # Get 15-minute data for S/R calculation
        df = self.get_latest_data(15, limit=200)
        
        if df.empty:
            return {
                'support_1': None, 'support_2': None, 'support_3': None,
                'resistance_1': None, 'resistance_2': None, 'resistance_3': None
            }
        
        # Detect S/R levels using SimpleSRDetector
        support_levels_obj, resistance_levels_obj = self.sr_detector.detect_sr_levels(df, max_support=3, max_resistance=3)
        
        # Get current price
        current_price = float(df.iloc[-1]['close'])
        
        # Extract support and resistance prices
        support_levels = [float(s.price) for s in support_levels_obj] if support_levels_obj else []
        resistance_levels = [float(r.price) for r in resistance_levels_obj] if resistance_levels_obj else []
        
        # Pad with None if not enough levels
        while len(support_levels) < 3:
            support_levels.append(None)
        while len(resistance_levels) < 3:
            resistance_levels.append(None)
        
        return {
            'support_1': support_levels[0],
            'support_2': support_levels[1],
            'support_3': support_levels[2],
            'resistance_1': resistance_levels[0],
            'resistance_2': resistance_levels[1],
            'resistance_3': resistance_levels[2]
        }
    
    def generate_recommendation(self):
        """Generate a complete trading recommendation"""
        self.logger.info("Generating trading recommendation...")
        
        # Get current market data
        df_15min = self.get_latest_data(15, limit=100)
        if df_15min.empty:
            raise ValueError("No data available for analysis")
        
        current_price = float(df_15min.iloc[-1]['close'])
        
        # Get trends
        trends = self.get_current_trends()
        
        # Get S/R levels
        sr_levels = self.calculate_support_resistance()
        
        # Prepare market context for GPT
        market_context = {
            'symbol': self.symbol,
            'current_price': current_price,
            'trends': trends,
            'support_levels': [sr_levels['support_1'], sr_levels['support_2'], sr_levels['support_3']],
            'resistance_levels': [sr_levels['resistance_1'], sr_levels['resistance_2'], sr_levels['resistance_3']],
            'recent_price_action': df_15min.tail(20)[['datetime', 'open', 'high', 'low', 'close', 'volume']].to_dict('records')
        }
        
        # Generate recommendation based on trends and S/R
        recommendation_text = self.generate_simple_recommendation(market_context)
        
        # Create recommendation data
        recommendation_data = {
            'action': self.determine_action(trends, sr_levels, current_price),
            'entry_price': current_price,
            'stop_loss': self.calculate_stop_loss(current_price, sr_levels),
            'target_1': self.calculate_target(current_price, sr_levels, 1),
            'target_2': self.calculate_target(current_price, sr_levels, 2),
            'confidence': self.calculate_confidence(trends)
        }
        
        # Add additional fields
        recommendation_data.update({
            'security_id': self.security_id,
            'symbol': self.symbol,
            'generated_at': datetime.now(),
            'current_price': current_price,
            **trends,
            **sr_levels,
            'recommendation_text': recommendation_text
        })
        
        return recommendation_data
    
    def generate_simple_recommendation(self, context):
        """Generate a simple text recommendation based on market context"""
        trends = context['trends']
        current_price = context['current_price']
        support = context['support_levels']
        resistance = context['resistance_levels']
        
        # Count trend alignment
        uptrends = sum(1 for k, v in trends.items() if v == 'UPTREND')
        downtrends = sum(1 for k, v in trends.items() if v == 'DOWNTREND')
        
        recommendation = f"""Trading Recommendation for {context['symbol']}

Current Price: ₹{current_price:.2f}

Trend Analysis:
"""
        
        if uptrends > downtrends:
            recommendation += "• Overall BULLISH bias - Multiple timeframes showing uptrend\n"
            recommendation += "• Consider LONG positions on pullbacks to support\n"
        elif downtrends > uptrends:
            recommendation += "• Overall BEARISH bias - Multiple timeframes showing downtrend\n"
            recommendation += "• Consider SHORT positions on rallies to resistance\n"
        else:
            recommendation += "• NEUTRAL market - Mixed signals across timeframes\n"
            recommendation += "• Wait for clearer trend alignment\n"
        
        # Add S/R levels
        recommendation += f"\nKey Levels:\n"
        if resistance[0]:
            recommendation += f"• Resistance: ₹{resistance[0]:.2f}\n"
        if support[0]:
            recommendation += f"• Support: ₹{support[0]:.2f}\n"
        
        return recommendation
    
    def determine_action(self, trends, sr_levels, current_price):
        """Determine trading action based on trends"""
        uptrends = sum(1 for k, v in trends.items() if v == 'UPTREND')
        downtrends = sum(1 for k, v in trends.items() if v == 'DOWNTREND')
        
        if uptrends > downtrends:
            return 'BUY'
        elif downtrends > uptrends:
            return 'SELL'
        else:
            return 'HOLD'
    
    def calculate_stop_loss(self, current_price, sr_levels):
        """Calculate stop loss based on support levels"""
        if sr_levels.get('support_1'):
            return sr_levels['support_1'] * 0.995  # 0.5% below support
        else:
            return current_price * 0.98  # 2% stop loss
    
    def calculate_target(self, current_price, sr_levels, target_num):
        """Calculate target prices based on resistance levels"""
        if target_num == 1 and sr_levels.get('resistance_1'):
            return sr_levels['resistance_1'] * 0.995  # Just below resistance
        elif target_num == 2 and sr_levels.get('resistance_2'):
            return sr_levels['resistance_2'] * 0.995
        else:
            # Default targets
            if target_num == 1:
                return current_price * 1.01  # 1% target
            else:
                return current_price * 1.02  # 2% target
    
    def calculate_confidence(self, trends):
        """Calculate confidence score based on trend alignment"""
        trend_values = list(trends.values())
        uptrends = trend_values.count('UPTREND')
        downtrends = trend_values.count('DOWNTREND')
        
        # Max alignment gives high confidence
        alignment = max(uptrends, downtrends) / len(trend_values) if trend_values else 0
        return round(alignment * 100, 1)
    
    def parse_gpt_recommendation(self, text, context):
        """Parse GPT recommendation to extract structured data"""
        # This is a simplified parser - you may want to make it more robust
        data = {
            'intraday_action': 'HOLD',
            'intraday_entry': None,
            'intraday_stoploss': None,
            'intraday_target1': None,
            'intraday_target2': None,
            'intraday_risk_reward': None,
            'intraday_rationale': '',
            'swing_action': 'HOLD',
            'swing_entry': None,
            'swing_stoploss': None,
            'swing_target1': None,
            'swing_target2': None,
            'swing_target3': None,
            'swing_risk_reward': None,
            'swing_rationale': ''
        }
        
        # Look for BUY/SELL signals in the text
        text_lower = text.lower()
        
        if 'short' in text_lower or 'sell' in text_lower:
            if 'intraday' in text_lower:
                data['intraday_action'] = 'SELL'
            if 'swing' in text_lower:
                data['swing_action'] = 'SELL'
        elif 'long' in text_lower or 'buy' in text_lower:
            if 'intraday' in text_lower:
                data['intraday_action'] = 'BUY'
            if 'swing' in text_lower:
                data['swing_action'] = 'BUY'
        
        # Extract price levels using regex (simplified)
        import re
        
        # Look for entry points
        entry_pattern = r'entry[:\s]+₹?([\d,]+\.?\d*)'
        matches = re.findall(entry_pattern, text_lower)
        if matches:
            try:
                entry_price = float(matches[0].replace(',', ''))
                data['intraday_entry'] = entry_price
            except:
                pass
        
        # Look for stop loss
        sl_pattern = r'stop\s*loss[:\s]+₹?([\d,]+\.?\d*)'
        matches = re.findall(sl_pattern, text_lower)
        if matches:
            try:
                sl_price = float(matches[0].replace(',', ''))
                data['intraday_stoploss'] = sl_price
            except:
                pass
        
        # Look for targets
        target_pattern = r'target[:\s]+₹?([\d,]+\.?\d*)'
        matches = re.findall(target_pattern, text_lower)
        if matches:
            try:
                data['intraday_target1'] = float(matches[0].replace(',', ''))
                if len(matches) > 1:
                    data['intraday_target2'] = float(matches[1].replace(',', ''))
            except:
                pass
        
        # Extract rationale (first paragraph after "Intraday" or "Swing")
        if 'intraday' in text_lower:
            intraday_idx = text_lower.index('intraday')
            intraday_section = text[intraday_idx:intraday_idx+500]
            data['intraday_rationale'] = intraday_section[:200]
        
        return data
    
    def save_recommendation(self, recommendation):
        """Save recommendation to database"""
        conn = self.get_db_connection()
        cur = conn.cursor()
        
        try:
            insert_query = """
                INSERT INTO dhanhq.trading_recommendations (
                    security_id, symbol, generated_at, current_price,
                    trend_1min, trend_5min, trend_15min, trend_60min,
                    trend_daily, trend_weekly, trend_monthly,
                    support_1, support_2, support_3,
                    resistance_1, resistance_2, resistance_3,
                    intraday_action, intraday_entry, intraday_stoploss,
                    intraday_target1, intraday_target2, intraday_risk_reward,
                    intraday_rationale,
                    swing_action, swing_entry, swing_stoploss,
                    swing_target1, swing_target2, swing_target3,
                    swing_risk_reward, swing_rationale,
                    recommendation_text, confidence_score
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                RETURNING id
            """
            
            values = (
                recommendation['security_id'],
                recommendation['symbol'],
                recommendation['generated_at'],
                recommendation['current_price'],
                recommendation.get('trend_1min'),
                recommendation.get('trend_5min'),
                recommendation.get('trend_15min'),
                recommendation.get('trend_60min'),
                recommendation.get('trend_daily'),
                recommendation.get('trend_weekly'),
                recommendation.get('trend_monthly'),
                recommendation.get('support_1'),
                recommendation.get('support_2'),
                recommendation.get('support_3'),
                recommendation.get('resistance_1'),
                recommendation.get('resistance_2'),
                recommendation.get('resistance_3'),
                recommendation.get('action', 'HOLD'),  # intraday_action
                recommendation.get('entry_price'),  # intraday_entry
                recommendation.get('stop_loss'),  # intraday_stoploss
                recommendation.get('target_1'),  # intraday_target1
                recommendation.get('target_2'),  # intraday_target2
                None,  # intraday_risk_reward
                '',  # intraday_rationale
                recommendation.get('action', 'HOLD'),  # swing_action
                recommendation.get('entry_price'),  # swing_entry
                recommendation.get('stop_loss'),  # swing_stoploss
                recommendation.get('target_1'),  # swing_target1
                recommendation.get('target_2'),  # swing_target2
                None,  # swing_target3
                None,  # swing_risk_reward
                '',  # swing_rationale
                recommendation.get('recommendation_text'),
                recommendation.get('confidence')  # confidence_score
            )
            
            cur.execute(insert_query, values)
            recommendation_id = cur.fetchone()[0]
            conn.commit()
            
            self.logger.info(f"Saved recommendation with ID: {recommendation_id}")
            return recommendation_id
            
        except Exception as e:
            conn.rollback()
            self.logger.error(f"Error saving recommendation: {e}")
            raise
        finally:
            cur.close()
            conn.close()
    
    def get_latest_recommendation(self):
        """Get the most recent recommendation from database"""
        conn = self.get_db_connection()
        cur = conn.cursor()
        
        try:
            query = """
                SELECT * FROM dhanhq.trading_recommendations
                WHERE security_id = %s
                ORDER BY generated_at DESC
                LIMIT 1
            """
            cur.execute(query, (self.security_id,))
            
            columns = [desc[0] for desc in cur.description]
            result = cur.fetchone()
            
            if result:
                return dict(zip(columns, result))
            else:
                return None
                
        finally:
            cur.close()
            conn.close()

if __name__ == "__main__":
    # Test the generator
    generator = RecommendationGenerator()
    
    try:
        recommendation = generator.generate_recommendation()
        recommendation_id = generator.save_recommendation(recommendation)
        print(f"Generated and saved recommendation ID: {recommendation_id}")
        
        # Retrieve and display
        latest = generator.get_latest_recommendation()
        if latest:
            print(f"\nLatest recommendation:")
            print(f"Generated at: {latest['generated_at']}")
            print(f"Current price: {latest['current_price']}")
            print(f"Intraday action: {latest['intraday_action']}")
            
    except Exception as e:
        print(f"Error: {e}")