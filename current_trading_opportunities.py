#!/usr/bin/env python3
"""
Identify current trading opportunities based on S/R and trend analysis
"""

import psycopg2
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
from src.config import Config

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

class TradingOpportunityScanner:
    def __init__(self):
        self.config = Config()
        self.conn = psycopg2.connect(
            host=self.config.db_host,
            port=self.config.db_port,
            database=self.config.db_name,
            user=self.config.db_user,
            password=self.config.db_password
        )
    
    def scan_current_setups(self):
        """Scan for current trading opportunities"""
        logger.info("="*100)
        logger.info("CURRENT TRADING OPPORTUNITY SCAN")
        logger.info("="*100)
        logger.info(f"Scan Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        # Check multiple timeframes
        timeframes = [
            (60, '1-hour', 0.003),    # 0.3% threshold
            (15, '15-minute', 0.002), # 0.2% threshold
            (5, '5-minute', 0.001)    # 0.1% threshold
        ]
        
        opportunities = []
        
        for interval, name, threshold in timeframes:
            cur = self.conn.cursor()
            
            # Get latest data
            cur.execute("""
                SELECT 
                    datetime, open, high, low, close, volume,
                    trend, trend_strength,
                    resistance_1, resistance_1_touches,
                    resistance_2, resistance_2_touches,
                    support_1, support_1_touches,
                    support_2, support_2_touches
                FROM dhanhq.price_data
                WHERE security_id = '15380' 
                AND interval_minutes = %s
                AND resistance_1 IS NOT NULL
                ORDER BY datetime DESC
                LIMIT 100
            """, (interval,))
            
            rows = cur.fetchall()
            if not rows:
                continue
            
            # Latest bar
            latest = rows[0]
            dt, o, h, l, c, vol = latest[0:6]
            trend, trend_str = latest[6:8]
            r1, r1_touches = latest[8:10]
            r2, r2_touches = latest[10:12]
            s1, s1_touches = latest[12:14]
            s2, s2_touches = latest[14:16]
            
            close_price = float(c)
            
            logger.info(f"\n{name.upper()} TIMEFRAME")
            logger.info("-"*80)
            logger.info(f"Current Price: {close_price:.2f}")
            logger.info(f"Trend: {trend} (Strength: {trend_str})")
            
            # Check for setups
            setups = []
            
            # Support levels
            if s1:
                s1_price = float(s1)
                distance_pct = (close_price - s1_price) / close_price * 100
                
                logger.info(f"\nSupport 1: {s1_price:.2f} ({distance_pct:+.2f}%, {s1_touches} touches)")
                
                if 0 < distance_pct < threshold * 100:
                    setup = {
                        'timeframe': name,
                        'type': 'Near Support',
                        'level': s1_price,
                        'distance_pct': distance_pct,
                        'touches': s1_touches,
                        'trend': trend,
                        'action': 'BUY' if trend == 'UPTREND' else 'WAIT'
                    }
                    setups.append(setup)
                    opportunities.append(setup)
                    logger.info(f"  → SETUP: Price approaching S1 in {trend}")
            
            if s2:
                s2_price = float(s2)
                distance_pct = (close_price - s2_price) / close_price * 100
                logger.info(f"Support 2: {s2_price:.2f} ({distance_pct:+.2f}%, {s2_touches} touches)")
            
            # Resistance levels
            if r1:
                r1_price = float(r1)
                distance_pct = (r1_price - close_price) / close_price * 100
                
                logger.info(f"\nResistance 1: {r1_price:.2f} ({distance_pct:+.2f}%, {r1_touches} touches)")
                
                if 0 < distance_pct < threshold * 100:
                    setup = {
                        'timeframe': name,
                        'type': 'Near Resistance',
                        'level': r1_price,
                        'distance_pct': distance_pct,
                        'touches': r1_touches,
                        'trend': trend,
                        'action': 'SHORT' if trend == 'DOWNTREND' else 'WAIT'
                    }
                    setups.append(setup)
                    opportunities.append(setup)
                    logger.info(f"  → SETUP: Price approaching R1 in {trend}")
            
            if r2:
                r2_price = float(r2)
                distance_pct = (r2_price - close_price) / close_price * 100
                logger.info(f"Resistance 2: {r2_price:.2f} ({distance_pct:+.2f}%, {r2_touches} touches)")
            
            # Check for recent breakouts
            if len(rows) > 5:
                prev_5_bars = rows[1:6]
                
                # Resistance breakout
                if r1 and trend == 'UPTREND':
                    r1_price = float(r1)
                    prev_closes = [float(row[4]) for row in prev_5_bars]
                    
                    if close_price > r1_price and max(prev_closes) < r1_price:
                        logger.info(f"\n  → BREAKOUT: Price broke above R1 at {r1_price:.2f}")
                        setup = {
                            'timeframe': name,
                            'type': 'Resistance Breakout',
                            'level': r1_price,
                            'distance_pct': (close_price - r1_price) / r1_price * 100,
                            'touches': r1_touches,
                            'trend': trend,
                            'action': 'BUY on pullback to R1'
                        }
                        setups.append(setup)
                        opportunities.append(setup)
            
            cur.close()
        
        # Summary of opportunities
        logger.info("\n" + "="*100)
        logger.info("TRADING OPPORTUNITIES SUMMARY")
        logger.info("="*100)
        
        if opportunities:
            # Sort by priority (trend-aligned first)
            trend_aligned = [o for o in opportunities if 
                           (o['trend'] == 'UPTREND' and 'Support' in o['type']) or
                           (o['trend'] == 'DOWNTREND' and 'Resistance' in o['type'])]
            
            logger.info("\nHIGH PRIORITY (Trend-Aligned):")
            for opp in trend_aligned:
                logger.info(f"\n{opp['timeframe']} - {opp['type']}:")
                logger.info(f"  Level: {opp['level']:.2f} ({opp['distance_pct']:+.2f}% away)")
                logger.info(f"  Trend: {opp['trend']}")
                logger.info(f"  Action: {opp['action']}")
                logger.info(f"  Touches: {opp['touches']}")
                
                # Add specific trade plan
                if 'Support' in opp['type'] and opp['trend'] == 'UPTREND':
                    logger.info(f"  Entry: Limit buy at {opp['level']:.2f}")
                    logger.info(f"  Stop: {opp['level'] * 0.997:.2f} (-0.3%)")
                    logger.info(f"  Target: Previous resistance or +1%")
                elif 'Resistance' in opp['type'] and opp['trend'] == 'DOWNTREND':
                    logger.info(f"  Entry: Limit short at {opp['level']:.2f}")
                    logger.info(f"  Stop: {opp['level'] * 1.003:.2f} (+0.3%)")
                    logger.info(f"  Target: Previous support or -1%")
        else:
            logger.info("\nNo immediate high-probability setups found.")
            logger.info("Continue monitoring for price to approach key S/R levels.")
        
        # Market context
        self._analyze_market_context()
    
    def _analyze_market_context(self):
        """Analyze overall market context"""
        cur = self.conn.cursor()
        
        logger.info("\n" + "="*100)
        logger.info("MARKET CONTEXT")
        logger.info("="*100)
        
        # Get trend distribution
        cur.execute("""
            SELECT 
                trend,
                COUNT(*) as count
            FROM (
                SELECT DISTINCT ON (date_trunc('hour', datetime))
                    datetime, trend
                FROM dhanhq.price_data
                WHERE security_id = '15380'
                AND interval_minutes = 60
                AND datetime > NOW() - INTERVAL '7 days'
                ORDER BY date_trunc('hour', datetime), datetime DESC
            ) t
            GROUP BY trend
        """)
        
        trend_dist = cur.fetchall()
        
        logger.info("\n7-Day Trend Distribution (Hourly):")
        total_hours = sum(count for _, count in trend_dist)
        for trend, count in trend_dist:
            pct = count / total_hours * 100
            logger.info(f"  {trend}: {count} hours ({pct:.1f}%)")
        
        # Get recent volatility
        cur.execute("""
            SELECT 
                AVG((high - low) / close * 100) as avg_range,
                MAX((high - low) / close * 100) as max_range
            FROM dhanhq.price_data
            WHERE security_id = '15380'
            AND interval_minutes = 60
            AND datetime > NOW() - INTERVAL '24 hours'
        """)
        
        avg_range, max_range = cur.fetchone()
        
        logger.info(f"\n24-Hour Volatility (1-hour bars):")
        logger.info(f"  Average Range: {avg_range:.2f}%")
        logger.info(f"  Maximum Range: {max_range:.2f}%")
        
        # Trading recommendations based on context
        logger.info("\nCONTEXT-BASED RECOMMENDATIONS:")
        
        if avg_range < 0.5:
            logger.info("- Low volatility: Use tighter stops, expect smaller moves")
        elif avg_range > 1.0:
            logger.info("- High volatility: Use wider stops, expect larger moves")
        
        # Check most common trend
        most_common_trend = max(trend_dist, key=lambda x: x[1])[0]
        logger.info(f"- Market has been mostly {most_common_trend} recently")
        logger.info(f"- Focus on {most_common_trend}-aligned setups for higher probability")
        
        cur.close()
    
    def close(self):
        self.conn.close()

def main():
    scanner = TradingOpportunityScanner()
    try:
        scanner.scan_current_setups()
    finally:
        scanner.close()

if __name__ == "__main__":
    main()