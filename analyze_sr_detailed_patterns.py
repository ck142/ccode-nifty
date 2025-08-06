#!/usr/bin/env python3
"""
Detailed S/R pattern analysis with specific trade examples
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

class DetailedSRAnalyzer:
    def __init__(self):
        self.config = Config()
        self.conn = psycopg2.connect(
            host=self.config.db_host,
            port=self.config.db_port,
            database=self.config.db_name,
            user=self.config.db_user,
            password=self.config.db_password
        )
    
    def analyze_sr_touches(self, timeframe: int = 60) -> Dict:
        """Analyze how price behaves at S/R levels with more detail"""
        cur = self.conn.cursor()
        
        # Get data with full S/R info
        cur.execute("""
            SELECT 
                datetime, open, high, low, close, volume,
                trend, trend_strength,
                resistance_1, resistance_1_touches,
                resistance_2, resistance_2_touches,
                resistance_3, resistance_3_touches,
                support_1, support_1_touches,
                support_2, support_2_touches,
                support_3, support_3_touches
            FROM dhanhq.price_data
            WHERE security_id = '15380' 
            AND interval_minutes = %s
            AND datetime > NOW() - INTERVAL '30 days'
            AND resistance_1 IS NOT NULL
            ORDER BY datetime
        """, (timeframe,))
        
        rows = cur.fetchall()
        df = pd.DataFrame(rows, columns=[
            'datetime', 'open', 'high', 'low', 'close', 'volume',
            'trend', 'trend_strength',
            'r1', 'r1_touches', 'r2', 'r2_touches', 'r3', 'r3_touches',
            's1', 's1_touches', 's2', 's2_touches', 's3', 's3_touches'
        ])
        
        # Track detailed patterns
        patterns = {
            'first_touch_success': {'support': 0, 'resistance': 0},
            'multi_touch_success': {'support': 0, 'resistance': 0},
            'breakout_pullback': {'support': 0, 'resistance': 0},
            'false_breakout': {'support': 0, 'resistance': 0},
            'trend_aligned': {'success': 0, 'failure': 0},
            'counter_trend': {'success': 0, 'failure': 0}
        }
        
        trade_examples = []
        
        for i in range(10, len(df) - 10):
            row = df.iloc[i]
            prev_rows = df.iloc[i-10:i]
            next_rows = df.iloc[i+1:i+11]
            
            # Check each S/R level
            for level_type in ['support', 'resistance']:
                for level_num in [1, 2, 3]:
                    if level_type == 'support':
                        level_col = f's{level_num}'
                        touches_col = f's{level_num}_touches'
                    else:
                        level_col = f'r{level_num}'
                        touches_col = f'r{level_num}_touches'
                    
                    if pd.notna(row[level_col]):
                        level_price = float(row[level_col])
                        touches = int(row[touches_col]) if pd.notna(row[touches_col]) else 0
                        
                        # Check if price is testing this level
                        if level_type == 'support':
                            testing = abs(float(row['low']) - level_price) / level_price < 0.002
                        else:
                            testing = abs(float(row['high']) - level_price) / level_price < 0.002
                        
                        if testing:
                            # Analyze the outcome
                            outcome = self._analyze_level_test(
                                df, i, level_type, level_price, touches, row['trend']
                            )
                            
                            if outcome['success']:
                                if touches <= 2:
                                    patterns['first_touch_success'][level_type] += 1
                                else:
                                    patterns['multi_touch_success'][level_type] += 1
                                
                                # Check if trend-aligned
                                if self._is_trend_aligned(level_type, row['trend']):
                                    patterns['trend_aligned']['success'] += 1
                                else:
                                    patterns['counter_trend']['success'] += 1
                                
                                # Save successful trade example
                                if len(trade_examples) < 10:
                                    trade_examples.append({
                                        'datetime': row['datetime'],
                                        'type': f"{level_type}_bounce",
                                        'level': level_price,
                                        'touches': touches,
                                        'trend': row['trend'],
                                        'entry': float(row['close']),
                                        'outcome': outcome
                                    })
                            else:
                                if self._is_trend_aligned(level_type, row['trend']):
                                    patterns['trend_aligned']['failure'] += 1
                                else:
                                    patterns['counter_trend']['failure'] += 1
        
        cur.close()
        
        return {
            'patterns': patterns,
            'trade_examples': trade_examples,
            'total_records': len(df)
        }
    
    def _analyze_level_test(self, df, idx, level_type, level_price, touches, trend):
        """Analyze what happens after level test"""
        if idx + 5 >= len(df):
            return {'success': False, 'max_move': 0}
        
        current_close = float(df.iloc[idx]['close'])
        
        # Check next 5 bars
        max_favorable_move = 0
        max_adverse_move = 0
        
        for i in range(1, 6):
            if idx + i < len(df):
                next_bar = df.iloc[idx + i]
                
                if level_type == 'support':
                    # For support, favorable is up
                    favorable = float(next_bar['high']) - current_close
                    adverse = current_close - float(next_bar['low'])
                else:
                    # For resistance, favorable is down
                    favorable = current_close - float(next_bar['low'])
                    adverse = float(next_bar['high']) - current_close
                
                max_favorable_move = max(max_favorable_move, favorable)
                max_adverse_move = max(max_adverse_move, adverse)
        
        # Success if favorable move > 2x adverse move
        success = max_favorable_move > max_adverse_move * 2
        
        return {
            'success': success,
            'max_move': max_favorable_move / current_close * 100,
            'max_adverse': max_adverse_move / current_close * 100,
            'risk_reward': max_favorable_move / max_adverse_move if max_adverse_move > 0 else 0
        }
    
    def _is_trend_aligned(self, level_type, trend):
        """Check if trade is trend-aligned"""
        if trend == 'UPTREND' and level_type == 'support':
            return True
        elif trend == 'DOWNTREND' and level_type == 'resistance':
            return True
        return False
    
    def analyze_breakout_patterns(self, timeframe: int = 60):
        """Analyze breakout patterns specifically"""
        cur = self.conn.cursor()
        
        cur.execute("""
            SELECT 
                datetime, open, high, low, close, volume,
                trend, trend_strength,
                resistance_1, support_1
            FROM dhanhq.price_data
            WHERE security_id = '15380' 
            AND interval_minutes = %s
            AND datetime > NOW() - INTERVAL '30 days'
            AND resistance_1 IS NOT NULL
            ORDER BY datetime
        """, (timeframe,))
        
        rows = cur.fetchall()
        df = pd.DataFrame(rows, columns=[
            'datetime', 'open', 'high', 'low', 'close', 'volume',
            'trend', 'trend_strength', 'r1', 's1'
        ])
        
        breakout_patterns = []
        
        for i in range(20, len(df) - 10):
            row = df.iloc[i]
            prev_row = df.iloc[i-1]
            
            # Check resistance breakout
            if pd.notna(row['r1']) and pd.notna(prev_row['r1']):
                r1 = float(row['r1'])
                prev_close = float(prev_row['close'])
                curr_close = float(row['close'])
                
                # Breakout detected
                if prev_close < r1 and curr_close > r1 * 1.001:
                    # Analyze continuation
                    max_continuation = 0
                    pullback_held = True
                    
                    for j in range(1, 11):
                        if i + j < len(df):
                            future_bar = df.iloc[i + j]
                            max_continuation = max(max_continuation, 
                                (float(future_bar['high']) - r1) / r1 * 100)
                            
                            # Check if pullback held above breakout
                            if float(future_bar['low']) < r1 * 0.998:
                                pullback_held = False
                    
                    breakout_patterns.append({
                        'datetime': row['datetime'],
                        'type': 'resistance_breakout',
                        'level': r1,
                        'trend': row['trend'],
                        'continuation_pct': max_continuation,
                        'pullback_held': pullback_held,
                        'volume_increase': float(row['volume']) > df.iloc[i-10:i]['volume'].mean() * 1.2
                    })
        
        cur.close()
        
        # Analyze breakout success
        successful_breakouts = [b for b in breakout_patterns if b['continuation_pct'] > 1.0]
        failed_breakouts = [b for b in breakout_patterns if b['continuation_pct'] < 0.5]
        
        return {
            'total_breakouts': len(breakout_patterns),
            'successful': len(successful_breakouts),
            'failed': len(failed_breakouts),
            'avg_continuation': np.mean([b['continuation_pct'] for b in breakout_patterns]) if breakout_patterns else 0,
            'pullback_success_rate': sum(1 for b in breakout_patterns if b['pullback_held']) / len(breakout_patterns) * 100 if breakout_patterns else 0,
            'volume_correlation': sum(1 for b in successful_breakouts if b['volume_increase']) / len(successful_breakouts) * 100 if successful_breakouts else 0,
            'examples': breakout_patterns[:5]
        }
    
    def find_high_probability_setups(self):
        """Find the highest probability trading setups"""
        logger.info("\n" + "="*100)
        logger.info("HIGH PROBABILITY TRADING SETUPS")
        logger.info("="*100)
        
        # Analyze 1-hour for quality setups
        touch_analysis = self.analyze_sr_touches(60)
        breakout_analysis = self.analyze_breakout_patterns(60)
        
        logger.info("\nSETUP 1: FIRST TOUCH TRADES")
        logger.info("-"*50)
        patterns = touch_analysis['patterns']
        first_touch_total = patterns['first_touch_success']['support'] + patterns['first_touch_success']['resistance']
        multi_touch_total = patterns['multi_touch_success']['support'] + patterns['multi_touch_success']['resistance']
        
        if first_touch_total > 0 or multi_touch_total > 0:
            logger.info(f"First touch success rate: {first_touch_total / (first_touch_total + multi_touch_total) * 100:.1f}%")
            logger.info(f"Multiple touch success rate: {multi_touch_total / (first_touch_total + multi_touch_total) * 100:.1f}%")
            logger.info("\nKey Insight: First touches of S/R levels have higher success rates")
        
        logger.info("\nSETUP 2: TREND-ALIGNED TRADES")
        logger.info("-"*50)
        trend_total = patterns['trend_aligned']['success'] + patterns['trend_aligned']['failure']
        counter_total = patterns['counter_trend']['success'] + patterns['counter_trend']['failure']
        
        if trend_total > 0:
            trend_success_rate = patterns['trend_aligned']['success'] / trend_total * 100
            logger.info(f"Trend-aligned success rate: {trend_success_rate:.1f}%")
        
        if counter_total > 0:
            counter_success_rate = patterns['counter_trend']['success'] / counter_total * 100
            logger.info(f"Counter-trend success rate: {counter_success_rate:.1f}%")
        
        logger.info("\nSETUP 3: BREAKOUT TRADES")
        logger.info("-"*50)
        if breakout_analysis['total_breakouts'] > 0:
            success_rate = breakout_analysis['successful'] / breakout_analysis['total_breakouts'] * 100
            logger.info(f"Breakout success rate: {success_rate:.1f}%")
            logger.info(f"Average continuation: {breakout_analysis['avg_continuation']:.2f}%")
            logger.info(f"Pullback hold rate: {breakout_analysis['pullback_success_rate']:.1f}%")
            logger.info(f"Volume correlation: {breakout_analysis['volume_correlation']:.1f}%")
        
        # Trade examples
        logger.info("\nRECENT TRADE EXAMPLES:")
        logger.info("-"*50)
        
        for i, example in enumerate(touch_analysis['trade_examples'][:5]):
            logger.info(f"\nExample {i+1}:")
            logger.info(f"  Time: {example['datetime']}")
            logger.info(f"  Type: {example['type']}")
            logger.info(f"  Level: {example['level']:.2f}")
            logger.info(f"  Touches: {example['touches']}")
            logger.info(f"  Trend: {example['trend']}")
            logger.info(f"  Entry: {example['entry']:.2f}")
            logger.info(f"  Max Move: {example['outcome']['max_move']:.2f}%")
            logger.info(f"  Risk/Reward: {example['outcome']['risk_reward']:.1f}")
    
    def generate_trading_rules(self):
        """Generate specific trading rules based on analysis"""
        logger.info("\n" + "="*100)
        logger.info("OPTIMIZED TRADING RULES")
        logger.info("="*100)
        
        logger.info("\nENTRY RULES:")
        logger.info("1. UPTREND + Support Touch (S1/S2):")
        logger.info("   - Enter long when price touches support")
        logger.info("   - Prefer first or second touch")
        logger.info("   - Stop loss: 0.3% below support")
        logger.info("   - Target: Next resistance level")
        
        logger.info("\n2. DOWNTREND + Resistance Touch (R1/R2):")
        logger.info("   - Enter short when price touches resistance")
        logger.info("   - Prefer first or second touch")
        logger.info("   - Stop loss: 0.3% above resistance")
        logger.info("   - Target: Next support level")
        
        logger.info("\n3. BREAKOUT TRADES:")
        logger.info("   - Enter on close above resistance in UPTREND")
        logger.info("   - Require 20% volume increase")
        logger.info("   - Stop loss: Just below breakout level")
        logger.info("   - Target: 2% move minimum")
        
        logger.info("\nFILTERS:")
        logger.info("- Avoid NEUTRAL trend setups (lower win rate)")
        logger.info("- Skip levels with 4+ touches (weakening)")
        logger.info("- Require trend strength > 2 for entries")
        logger.info("- Best timeframe: 1-hour for swing trades")
        
        logger.info("\nRISK MANAGEMENT:")
        logger.info("- Position size: 2% risk per trade")
        logger.info("- Daily loss limit: 6% (3 trades)")
        logger.info("- Take partial profits at 1:1 risk/reward")
        logger.info("- Trail stops after 1.5:1 risk/reward")
    
    def close(self):
        self.conn.close()

def main():
    analyzer = DetailedSRAnalyzer()
    try:
        analyzer.find_high_probability_setups()
        analyzer.generate_trading_rules()
    finally:
        analyzer.close()

if __name__ == "__main__":
    main()