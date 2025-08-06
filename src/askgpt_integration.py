#!/usr/bin/env python3
"""
Integration module for AskGPT with trading analysis
Provides easy-to-use functions for common trading queries
"""

from typing import Dict, List, Optional
import pandas as pd
from .askgpt import AskGPT, GPTResponse
from .config import Config
import psycopg2
import json

class TradingGPTAdvisor:
    """
    High-level interface for trading-specific GPT interactions
    """
    
    def __init__(self, config: Optional[Config] = None):
        """Initialize with config"""
        self.config = config or Config()
        self.gpt = AskGPT()
        
    def analyze_current_setup(self, security_id: str = '15380') -> str:
        """
        Analyze current market setup for a security
        
        Args:
            security_id: Security ID to analyze
            
        Returns:
            GPT analysis as string
        """
        # Fetch current data from database
        conn = psycopg2.connect(
            host=self.config.db_host,
            port=self.config.db_port,
            database=self.config.db_name,
            user=self.config.db_user,
            password=self.config.db_password
        )
        
        cur = conn.cursor()
        
        # Get symbol name
        cur.execute("""
            SELECT symbol, name FROM dhanhq.securities 
            WHERE security_id = %s
        """, (security_id,))
        symbol, name = cur.fetchone()
        
        # Get latest trends across timeframes
        trend_info = {}
        
        # Intraday
        for interval, tf_name in [(1, '1min'), (5, '5min'), (15, '15min'), (60, '1hr')]:
            cur.execute("""
                SELECT trend, trend_strength, trend_confidence, swing_ratio, 
                       market_regime, close
                FROM dhanhq.price_data
                WHERE security_id = %s AND interval_minutes = %s
                ORDER BY datetime DESC LIMIT 1
            """, (security_id, interval))
            
            result = cur.fetchone()
            if result:
                trend_info[tf_name] = {
                    'trend': result[0],
                    'strength': result[1],
                    'confidence': result[2],
                    'swing_ratio': result[3],
                    'market_regime': result[4],
                    'price': result[5]
                }
        
        # Daily
        cur.execute("""
            SELECT trend, trend_strength, trend_confidence, swing_ratio, 
                   market_regime, close
            FROM dhanhq.price_data_daily
            WHERE security_id = %s
            ORDER BY date DESC LIMIT 1
        """, (security_id,))
        
        result = cur.fetchone()
        if result:
            trend_info['daily'] = {
                'trend': result[0],
                'strength': result[1],
                'confidence': result[2],
                'swing_ratio': result[3],
                'market_regime': result[4],
                'price': result[5]
            }
        
        # Get S/R levels
        cur.execute("""
            SELECT price, level_type, strength
            FROM dhanhq.support_resistance_levels
            WHERE security_id = %s AND is_active = true
            ORDER BY strength DESC
            LIMIT 5
        """, (security_id,))
        
        sr_levels = []
        for row in cur.fetchall():
            sr_levels.append({
                'price': float(row[0]),
                'type': row[1],
                'strength': float(row[2])
            })
        
        conn.close()
        
        # Get current price
        current_price = trend_info.get('1min', {}).get('price', 0)
        
        # Get trading advice
        response = self.gpt.get_trading_advice(
            symbol=symbol,
            current_price=current_price,
            trend_info=trend_info,
            support_resistance=sr_levels,
            risk_tolerance='moderate'
        )
        
        if response.success:
            return f"Analysis for {symbol} ({name}):\n\n{response.content}"
        else:
            return f"Error getting analysis: {response.error}"
    
    def explain_current_trends(self, security_id: str = '15380') -> str:
        """
        Explain the current trend situation across timeframes
        
        Args:
            security_id: Security ID to analyze
            
        Returns:
            GPT explanation as string
        """
        # Fetch trend data
        conn = psycopg2.connect(
            host=self.config.db_host,
            port=self.config.db_port,
            database=self.config.db_name,
            user=self.config.db_user,
            password=self.config.db_password
        )
        
        cur = conn.cursor()
        
        # Get comprehensive trend data
        cur.execute("""
            WITH trend_summary AS (
                SELECT 
                    '1min' as timeframe,
                    trend,
                    AVG(trend_confidence) as avg_confidence,
                    AVG(swing_ratio) as avg_swing_ratio,
                    COUNT(*) as sample_size
                FROM dhanhq.price_data
                WHERE security_id = %s 
                AND interval_minutes = 1
                AND datetime > NOW() - INTERVAL '1 day'
                GROUP BY trend
                
                UNION ALL
                
                SELECT 
                    '5min' as timeframe,
                    trend,
                    AVG(trend_confidence) as avg_confidence,
                    AVG(swing_ratio) as avg_swing_ratio,
                    COUNT(*) as sample_size
                FROM dhanhq.price_data
                WHERE security_id = %s 
                AND interval_minutes = 5
                AND datetime > NOW() - INTERVAL '5 days'
                GROUP BY trend
                
                UNION ALL
                
                SELECT 
                    'daily' as timeframe,
                    trend,
                    AVG(trend_confidence) as avg_confidence,
                    AVG(swing_ratio) as avg_swing_ratio,
                    COUNT(*) as sample_size
                FROM dhanhq.price_data_daily
                WHERE security_id = %s
                AND date > NOW() - INTERVAL '30 days'
                GROUP BY trend
            )
            SELECT * FROM trend_summary
            ORDER BY timeframe, sample_size DESC
        """, (security_id, security_id, security_id))
        
        trend_distribution = {}
        for row in cur.fetchall():
            tf = row[0]
            if tf not in trend_distribution:
                trend_distribution[tf] = []
            trend_distribution[tf].append({
                'trend': row[1],
                'avg_confidence': float(row[2]),
                'avg_swing_ratio': float(row[3]),
                'sample_size': row[4]
            })
        
        conn.close()
        
        # Format data for GPT
        analysis_data = {
            'symbol': 'MANKIND',
            'trend_distribution': trend_distribution
        }
        
        question = """Based on the trend distribution data across timeframes:

1. What story do these trends tell about the market structure?
2. Are the timeframes aligned or showing divergence?
3. What does the confidence and swing ratio data suggest about trend quality?
4. What trading approach would be most suitable given this analysis?
5. Are there any warning signs or opportunities in the data?

Please provide practical insights for a trader."""
        
        response = self.gpt.ask(
            question=question,
            context='analysis',
            additional_context=f"Trend Distribution Data:\n{json.dumps(analysis_data, indent=2)}",
            temperature=0.6
        )
        
        if response.success:
            return response.content
        else:
            return f"Error: {response.error}"
    
    def get_market_regime_advice(self, security_id: str = '15380') -> str:
        """
        Get advice based on current market regime
        
        Args:
            security_id: Security ID to analyze
            
        Returns:
            GPT advice as string
        """
        # Get market regime data
        conn = psycopg2.connect(
            host=self.config.db_host,
            port=self.config.db_port,
            database=self.config.db_name,
            user=self.config.db_user,
            password=self.config.db_password
        )
        
        cur = conn.cursor()
        
        # Get regime distribution
        cur.execute("""
            SELECT 
                market_regime,
                COUNT(*) * 100.0 / SUM(COUNT(*)) OVER () as percentage,
                AVG(swing_ratio) as avg_swing_ratio,
                AVG(move_quality) as avg_move_quality
            FROM dhanhq.price_data
            WHERE security_id = %s 
            AND market_regime IS NOT NULL
            AND datetime > NOW() - INTERVAL '30 days'
            GROUP BY market_regime
            ORDER BY percentage DESC
        """, (security_id,))
        
        regime_data = []
        for row in cur.fetchall():
            regime_data.append({
                'regime': row[0],
                'percentage': float(row[1]),
                'avg_swing_ratio': float(row[2]),
                'avg_move_quality': float(row[3])
            })
        
        # Get current regime
        cur.execute("""
            SELECT market_regime, trend, swing_ratio, move_quality
            FROM dhanhq.price_data
            WHERE security_id = %s
            ORDER BY datetime DESC
            LIMIT 1
        """, (security_id,))
        
        current = cur.fetchone()
        current_regime = {
            'regime': current[0],
            'trend': current[1],
            'swing_ratio': float(current[2]),
            'move_quality': float(current[3])
        }
        
        conn.close()
        
        question = """As a market regime specialist, analyze this data and provide:

1. Assessment of the dominant market regime and what it means
2. How should trading strategies be adjusted for this regime?
3. What are the key risks in the current regime?
4. What signals would indicate a regime change?
5. Specific tactics for trading in this environment

Focus on practical, actionable advice."""
        
        context = f"""
Market Regime Analysis for MANKIND:

Current Regime: {current_regime['regime']}
Current Trend: {current_regime['trend']}
Current Swing Ratio: {current_regime['swing_ratio']:.2f}
Current Move Quality: {current_regime['move_quality']:.1f}%

Historical Distribution (30 days):
{json.dumps(regime_data, indent=2)}
"""
        
        response = self.gpt.ask(
            question=question,
            context='trading',
            additional_context=context,
            temperature=0.6
        )
        
        if response.success:
            return response.content
        else:
            return f"Error: {response.error}"

# Convenience functions for quick access
def get_gpt_analysis(security_id: str = '15380') -> str:
    """Quick function to get current market analysis"""
    advisor = TradingGPTAdvisor()
    return advisor.analyze_current_setup(security_id)

def explain_trends(security_id: str = '15380') -> str:
    """Quick function to explain current trends"""
    advisor = TradingGPTAdvisor()
    return advisor.explain_current_trends(security_id)

def get_regime_advice(security_id: str = '15380') -> str:
    """Quick function to get market regime advice"""
    advisor = TradingGPTAdvisor()
    return advisor.get_market_regime_advice(security_id)

if __name__ == "__main__":
    # Example usage
    print("Trading GPT Advisor - Example Usage\n")
    
    try:
        advisor = TradingGPTAdvisor()
        
        # Get current analysis
        print("1. Current Market Analysis:")
        print("-" * 80)
        print(advisor.analyze_current_setup())
        
        print("\n2. Trend Explanation:")
        print("-" * 80)
        print(advisor.explain_current_trends())
        
        print("\n3. Market Regime Advice:")
        print("-" * 80)
        print(advisor.get_market_regime_advice())
        
    except Exception as e:
        print(f"Error: {e}")
        print("\nMake sure to set OPENAI_API_KEY in your .env file")