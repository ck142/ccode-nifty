#!/usr/bin/env python3
"""
Analyze price movement between S/R levels and trend effects
Looking for simple tradable patterns
"""

import psycopg2
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import logging
from src.config import Config

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

class SRPatternAnalyzer:
    def __init__(self):
        self.config = Config()
        self.conn = psycopg2.connect(
            host=self.config.db_host,
            port=self.config.db_port,
            database=self.config.db_name,
            user=self.config.db_user,
            password=self.config.db_password
        )
        
    def analyze_sr_interactions(self, timeframe: int, days: int = 30) -> Dict:
        """Analyze how price interacts with S/R levels in different trend contexts"""
        cur = self.conn.cursor()
        
        # Get data with S/R and trend
        cur.execute("""
            SELECT 
                datetime,
                open, high, low, close,
                trend,
                resistance_1, resistance_2, resistance_3,
                support_1, support_2, support_3
            FROM dhanhq.price_data
            WHERE security_id = '15380' 
            AND interval_minutes = %s
            AND datetime > NOW() - INTERVAL '%s days'
            AND resistance_1 IS NOT NULL
            AND trend IS NOT NULL
            ORDER BY datetime
        """, (timeframe, days))
        
        rows = cur.fetchall()
        if not rows:
            return {}
            
        df = pd.DataFrame(rows, columns=[
            'datetime', 'open', 'high', 'low', 'close', 'trend',
            'r1', 'r2', 'r3', 's1', 's2', 's3'
        ])
        
        # Analyze patterns
        patterns = {
            'support_bounce': {'uptrend': 0, 'downtrend': 0, 'neutral': 0},
            'support_break': {'uptrend': 0, 'downtrend': 0, 'neutral': 0},
            'resistance_reject': {'uptrend': 0, 'downtrend': 0, 'neutral': 0},
            'resistance_break': {'uptrend': 0, 'downtrend': 0, 'neutral': 0},
            'total_tests': {'uptrend': 0, 'downtrend': 0, 'neutral': 0}
        }
        
        # Success rates
        success_rates = {
            'support_bounce_rate': {'uptrend': [], 'downtrend': [], 'neutral': []},
            'resistance_reject_rate': {'uptrend': [], 'downtrend': [], 'neutral': []},
            'breakout_continuation': {'uptrend': [], 'downtrend': [], 'neutral': []}
        }
        
        for i in range(1, len(df)):
            row = df.iloc[i]
            prev_row = df.iloc[i-1]
            trend = row['trend'].lower()
            
            # Check support interactions
            for s_level in ['s1', 's2', 's3']:
                if pd.notna(row[s_level]):
                    support = float(row[s_level])
                    
                    # Did price test support? (low within 0.1% of support)
                    if abs(float(row['low']) - support) / support < 0.001:
                        patterns['total_tests'][trend] += 1
                        
                        # Check if it bounced (close > support)
                        if float(row['close']) > support:
                            patterns['support_bounce'][trend] += 1
                            
                            # Measure bounce strength
                            if i < len(df) - 1:
                                next_row = df.iloc[i+1]
                                bounce_pct = (float(next_row['high']) - support) / support * 100
                                success_rates['support_bounce_rate'][trend].append(bounce_pct)
                        else:
                            patterns['support_break'][trend] += 1
            
            # Check resistance interactions  
            for r_level in ['r1', 'r2', 'r3']:
                if pd.notna(row[r_level]):
                    resistance = float(row[r_level])
                    
                    # Did price test resistance? (high within 0.1% of resistance)
                    if abs(float(row['high']) - resistance) / resistance < 0.001:
                        patterns['total_tests'][trend] += 1
                        
                        # Check if it got rejected (close < resistance)
                        if float(row['close']) < resistance:
                            patterns['resistance_reject'][trend] += 1
                            
                            # Measure rejection strength
                            if i < len(df) - 1:
                                next_row = df.iloc[i+1]
                                reject_pct = (resistance - float(next_row['low'])) / resistance * 100
                                success_rates['resistance_reject_rate'][trend].append(reject_pct)
                        else:
                            patterns['resistance_break'][trend] += 1
                            
                            # Measure breakout continuation
                            if i < len(df) - 1:
                                next_row = df.iloc[i+1]
                                continuation_pct = (float(next_row['high']) - resistance) / resistance * 100
                                success_rates['breakout_continuation'][trend].append(continuation_pct)
        
        cur.close()
        
        return {
            'patterns': patterns,
            'success_rates': success_rates,
            'timeframe': timeframe,
            'days': days,
            'total_records': len(df)
        }
    
    def calculate_pattern_statistics(self, results: Dict) -> Dict:
        """Calculate success rates and statistics for patterns"""
        patterns = results['patterns']
        rates = results['success_rates']
        
        stats = {}
        
        for trend in ['uptrend', 'downtrend', 'neutral']:
            total_tests = patterns['total_tests'][trend]
            
            if total_tests > 0:
                # Calculate success rates
                support_bounce_rate = patterns['support_bounce'][trend] / max(
                    patterns['support_bounce'][trend] + patterns['support_break'][trend], 1
                ) * 100
                
                resistance_reject_rate = patterns['resistance_reject'][trend] / max(
                    patterns['resistance_reject'][trend] + patterns['resistance_break'][trend], 1
                ) * 100
                
                stats[trend] = {
                    'total_tests': total_tests,
                    'support_bounce_rate': support_bounce_rate,
                    'resistance_reject_rate': resistance_reject_rate,
                    'avg_bounce_move': np.mean(rates['support_bounce_rate'][trend]) if rates['support_bounce_rate'][trend] else 0,
                    'avg_reject_move': np.mean(rates['resistance_reject_rate'][trend]) if rates['resistance_reject_rate'][trend] else 0,
                    'avg_breakout_move': np.mean(rates['breakout_continuation'][trend]) if rates['breakout_continuation'][trend] else 0
                }
            else:
                stats[trend] = {
                    'total_tests': 0,
                    'support_bounce_rate': 0,
                    'resistance_reject_rate': 0,
                    'avg_bounce_move': 0,
                    'avg_reject_move': 0,
                    'avg_breakout_move': 0
                }
        
        return stats
    
    def find_tradable_patterns(self, timeframe: int = 60) -> Dict:
        """Find the most reliable tradable patterns"""
        cur = self.conn.cursor()
        
        # Get recent data for pattern analysis
        cur.execute("""
            SELECT 
                datetime, open, high, low, close, volume,
                trend, trend_strength,
                resistance_1, resistance_2, resistance_3,
                support_1, support_2, support_3
            FROM dhanhq.price_data
            WHERE security_id = '15380' 
            AND interval_minutes = %s
            AND datetime > NOW() - INTERVAL '30 days'
            AND resistance_1 IS NOT NULL
            AND trend IS NOT NULL
            ORDER BY datetime
        """, (timeframe,))
        
        rows = cur.fetchall()
        df = pd.DataFrame(rows, columns=[
            'datetime', 'open', 'high', 'low', 'close', 'volume',
            'trend', 'trend_strength', 'r1', 'r2', 'r3', 's1', 's2', 's3'
        ])
        
        # Track specific pattern setups
        pattern_results = []
        
        for i in range(10, len(df) - 5):  # Need lookback and forward data
            row = df.iloc[i]
            
            # Pattern 1: Support bounce in uptrend
            if row['trend'] == 'UPTREND' and pd.notna(row['s1']):
                s1 = float(row['s1'])
                low = float(row['low'])
                close = float(row['close'])
                
                # Check if price touched support
                if abs(low - s1) / s1 < 0.002:  # Within 0.2%
                    # Did it bounce?
                    if close > s1:
                        # Check next 5 bars for profit
                        max_profit = 0
                        for j in range(1, 6):
                            if i + j < len(df):
                                future_high = float(df.iloc[i + j]['high'])
                                profit = (future_high - close) / close * 100
                                max_profit = max(max_profit, profit)
                        
                        pattern_results.append({
                            'pattern': 'uptrend_support_bounce',
                            'entry_time': row['datetime'],
                            'entry_price': close,
                            'support_level': s1,
                            'max_profit_pct': max_profit,
                            'trend_strength': row['trend_strength']
                        })
            
            # Pattern 2: Resistance break in uptrend
            if row['trend'] == 'UPTREND' and pd.notna(row['r1']):
                r1 = float(row['r1'])
                high = float(row['high'])
                close = float(row['close'])
                prev_close = float(df.iloc[i-1]['close'])
                
                # Check if price broke resistance
                if prev_close < r1 and close > r1 and high > r1 * 1.001:
                    # Check continuation
                    max_profit = 0
                    for j in range(1, 6):
                        if i + j < len(df):
                            future_high = float(df.iloc[i + j]['high'])
                            profit = (future_high - close) / close * 100
                            max_profit = max(max_profit, profit)
                    
                    pattern_results.append({
                        'pattern': 'uptrend_resistance_break',
                        'entry_time': row['datetime'],
                        'entry_price': close,
                        'resistance_level': r1,
                        'max_profit_pct': max_profit,
                        'trend_strength': row['trend_strength']
                    })
            
            # Pattern 3: Resistance rejection in downtrend
            if row['trend'] == 'DOWNTREND' and pd.notna(row['r1']):
                r1 = float(row['r1'])
                high = float(row['high'])
                close = float(row['close'])
                
                # Check if price tested resistance
                if abs(high - r1) / r1 < 0.002:  # Within 0.2%
                    # Did it get rejected?
                    if close < r1:
                        # Check next 5 bars for profit (short)
                        max_profit = 0
                        for j in range(1, 6):
                            if i + j < len(df):
                                future_low = float(df.iloc[i + j]['low'])
                                profit = (close - future_low) / close * 100
                                max_profit = max(max_profit, profit)
                        
                        pattern_results.append({
                            'pattern': 'downtrend_resistance_reject',
                            'entry_time': row['datetime'],
                            'entry_price': close,
                            'resistance_level': r1,
                            'max_profit_pct': max_profit,
                            'trend_strength': row['trend_strength']
                        })
        
        cur.close()
        
        # Analyze pattern performance
        pattern_stats = {}
        for pattern_name in ['uptrend_support_bounce', 'uptrend_resistance_break', 'downtrend_resistance_reject']:
            pattern_data = [p for p in pattern_results if p['pattern'] == pattern_name]
            
            if pattern_data:
                profits = [p['max_profit_pct'] for p in pattern_data]
                winning_trades = [p for p in profits if p > 0.5]  # 0.5% threshold
                
                pattern_stats[pattern_name] = {
                    'count': len(pattern_data),
                    'win_rate': len(winning_trades) / len(pattern_data) * 100,
                    'avg_profit': np.mean(profits),
                    'max_profit': max(profits),
                    'min_profit': min(profits),
                    'profitable_trades': len(winning_trades)
                }
            else:
                pattern_stats[pattern_name] = {
                    'count': 0,
                    'win_rate': 0,
                    'avg_profit': 0,
                    'max_profit': 0,
                    'min_profit': 0,
                    'profitable_trades': 0
                }
        
        return {
            'pattern_stats': pattern_stats,
            'detailed_results': pattern_results[:20]  # Sample of recent patterns
        }
    
    def generate_report(self):
        """Generate comprehensive S/R pattern analysis report"""
        logger.info("="*100)
        logger.info("S/R AND TREND PATTERN ANALYSIS")
        logger.info("="*100)
        logger.info(f"Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        # Analyze multiple timeframes
        timeframes = [(60, '1-hour'), (15, '15-minute'), (5, '5-minute')]
        
        for interval, name in timeframes:
            logger.info(f"\n{name.upper()} ANALYSIS")
            logger.info("-"*80)
            
            # Get interaction analysis
            results = self.analyze_sr_interactions(interval, days=30)
            if not results:
                logger.info("No data available for analysis")
                continue
                
            stats = self.calculate_pattern_statistics(results)
            
            # Display results by trend
            for trend in ['uptrend', 'downtrend', 'neutral']:
                trend_stats = stats[trend]
                if trend_stats['total_tests'] > 0:
                    logger.info(f"\n{trend.upper()}:")
                    logger.info(f"  Total S/R tests: {trend_stats['total_tests']}")
                    logger.info(f"  Support bounce rate: {trend_stats['support_bounce_rate']:.1f}%")
                    logger.info(f"  Resistance rejection rate: {trend_stats['resistance_reject_rate']:.1f}%")
                    logger.info(f"  Avg bounce move: {trend_stats['avg_bounce_move']:.2f}%")
                    logger.info(f"  Avg rejection move: {trend_stats['avg_reject_move']:.2f}%")
                    logger.info(f"  Avg breakout move: {trend_stats['avg_breakout_move']:.2f}%")
            
            # Find tradable patterns
            logger.info(f"\nTRADABLE PATTERNS ({name}):")
            pattern_analysis = self.find_tradable_patterns(interval)
            
            for pattern_name, stats in pattern_analysis['pattern_stats'].items():
                if stats['count'] > 0:
                    logger.info(f"\n{pattern_name.replace('_', ' ').title()}:")
                    logger.info(f"  Occurrences: {stats['count']}")
                    logger.info(f"  Win rate: {stats['win_rate']:.1f}%")
                    logger.info(f"  Avg profit: {stats['avg_profit']:.2f}%")
                    logger.info(f"  Max profit: {stats['max_profit']:.2f}%")
                    logger.info(f"  Profitable trades: {stats['profitable_trades']}")
        
        # Key findings
        logger.info("\n" + "="*100)
        logger.info("KEY FINDINGS & TRADABLE PATTERNS")
        logger.info("="*100)
        
        # Best patterns based on 1-hour analysis
        results_1h = self.analyze_sr_interactions(60, days=30)
        if results_1h:
            stats_1h = self.calculate_pattern_statistics(results_1h)
            patterns_1h = self.find_tradable_patterns(60)
            
            logger.info("\nMOST RELIABLE PATTERNS:")
            
            # Find best patterns
            best_patterns = []
            
            # Check uptrend support bounce
            if stats_1h['uptrend']['support_bounce_rate'] > 60:
                best_patterns.append(f"1. Uptrend Support Bounce: {stats_1h['uptrend']['support_bounce_rate']:.1f}% success rate")
            
            # Check downtrend resistance rejection
            if stats_1h['downtrend']['resistance_reject_rate'] > 60:
                best_patterns.append(f"2. Downtrend Resistance Rejection: {stats_1h['downtrend']['resistance_reject_rate']:.1f}% success rate")
            
            # Check breakout patterns
            for pattern, stats in patterns_1h['pattern_stats'].items():
                if stats['win_rate'] > 65 and stats['count'] > 5:
                    best_patterns.append(f"3. {pattern.replace('_', ' ').title()}: {stats['win_rate']:.1f}% win rate")
            
            for pattern in best_patterns:
                logger.info(f"  {pattern}")
            
            logger.info("\nRECOMMENDED TRADING RULES:")
            logger.info("1. In UPTREND: Buy at support levels (S1/S2), especially first touch")
            logger.info("2. In DOWNTREND: Short at resistance levels (R1/R2), especially first touch")
            logger.info("3. In UPTREND: Buy breakouts above resistance with volume confirmation")
            logger.info("4. Avoid trading S/R levels in NEUTRAL trends (lower success rate)")
            logger.info("5. Use tighter stops in counter-trend trades")
    
    def close(self):
        """Close database connection"""
        self.conn.close()

def main():
    analyzer = SRPatternAnalyzer()
    try:
        analyzer.generate_report()
    finally:
        analyzer.close()

if __name__ == "__main__":
    main()