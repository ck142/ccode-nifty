#!/usr/bin/env python3
"""
Simple Support/Resistance Detection based on Adam Grimes' principles
- Focus on swing-based S/R with optional round numbers
- No complex scoring, just touch counting
- Returns only top 3 support + 3 resistance levels
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)

@dataclass
class SimpleSRLevel:
    """Simple representation of a support/resistance level"""
    price: float
    type: str  # 'support' or 'resistance'
    touches: int
    first_seen: pd.Timestamp
    last_seen: pd.Timestamp
    is_round_number: bool = False
    
    def __repr__(self):
        return f"SR({self.type[0].upper()} @ {self.price:.2f}, touches={self.touches})"


class SimpleSRDetector:
    """
    Simplified S/R detection following Adam Grimes' recommendations:
    - Swing-based horizontal levels
    - Optional round number inclusion
    - Touch counting for strength
    - Returns only most relevant levels
    """
    
    def __init__(self, 
                 lookback_bars: int = 100,
                 min_touches: int = 2,
                 cluster_threshold_atr: float = 0.5,
                 include_round_numbers: bool = True):
        """
        Initialize detector
        
        Args:
            lookback_bars: Number of bars to look back for swings (50-200 recommended)
            min_touches: Minimum touches to qualify as S/R level
            cluster_threshold_atr: Cluster levels within this many ATRs
            include_round_numbers: Whether to include psychological round numbers
        """
        self.lookback_bars = lookback_bars
        self.min_touches = min_touches
        self.cluster_threshold_atr = cluster_threshold_atr
        self.include_round_numbers = include_round_numbers
        
    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate Average True Range"""
        high = df['high']
        low = df['low']
        close = df['close'].shift(1)
        
        tr1 = high - low
        tr2 = abs(high - close)
        tr3 = abs(low - close)
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        
        return atr
    
    def find_swing_points(self, df: pd.DataFrame) -> Tuple[List[dict], List[dict]]:
        """Find swing highs and lows using simple peak/valley detection"""
        highs = []
        lows = []
        
        # Need enough data
        if len(df) < self.lookback_bars:
            return highs, lows
        
        # Use last lookback_bars of data
        recent_df = df.tail(self.lookback_bars).reset_index()
        
        # Simple swing detection - look for local extremes
        for i in range(5, len(recent_df) - 5):  # Need 5 bars on each side
            # Swing high: higher than 5 bars before and after
            if (recent_df.iloc[i]['high'] > recent_df.iloc[i-5:i]['high'].max() and
                recent_df.iloc[i]['high'] > recent_df.iloc[i+1:i+6]['high'].max()):
                
                highs.append({
                    'index': i,
                    'price': float(recent_df.iloc[i]['high']),
                    'date': recent_df.iloc[i].name if recent_df.index.name else recent_df.iloc[i].get('datetime', recent_df.index[i])
                })
            
            # Swing low: lower than 5 bars before and after
            if (recent_df.iloc[i]['low'] < recent_df.iloc[i-5:i]['low'].min() and
                recent_df.iloc[i]['low'] < recent_df.iloc[i+1:i+6]['low'].min()):
                
                lows.append({
                    'index': i,
                    'price': float(recent_df.iloc[i]['low']),
                    'date': recent_df.iloc[i].name if recent_df.index.name else recent_df.iloc[i].get('datetime', recent_df.index[i])
                })
        
        return highs, lows
    
    def find_round_numbers(self, price_range: Tuple[float, float]) -> List[float]:
        """Find psychological round numbers in price range"""
        if not self.include_round_numbers:
            return []
        
        min_price, max_price = price_range
        round_numbers = []
        
        # Determine appropriate increment based on price level
        if max_price > 10000:
            increment = 500  # For high-priced stocks
        elif max_price > 1000:
            increment = 50   # For mid-priced stocks
        elif max_price > 100:
            increment = 5    # For normal stocks
        else:
            increment = 1    # For penny stocks
        
        # Find round numbers in range
        start = int(min_price / increment) * increment
        current = start
        
        while current <= max_price:
            if min_price <= current <= max_price:
                # Extra round numbers (multiples of 10x increment) are more significant
                if current % (increment * 10) == 0:
                    round_numbers.append(current)
            current += increment
        
        return round_numbers
    
    def cluster_levels(self, levels: List[dict], atr: float) -> List[dict]:
        """Cluster nearby levels based on ATR"""
        if not levels:
            return []
        
        # Sort by price
        sorted_levels = sorted(levels, key=lambda x: x['price'])
        clusters = []
        current_cluster = [sorted_levels[0]]
        cluster_threshold = atr * self.cluster_threshold_atr
        
        for level in sorted_levels[1:]:
            cluster_center = np.mean([l['price'] for l in current_cluster])
            
            if abs(level['price'] - cluster_center) <= cluster_threshold:
                current_cluster.append(level)
            else:
                # Process current cluster
                clusters.append(self._merge_cluster(current_cluster))
                current_cluster = [level]
        
        # Don't forget last cluster
        if current_cluster:
            clusters.append(self._merge_cluster(current_cluster))
        
        return clusters
    
    def _merge_cluster(self, cluster: List[dict]) -> dict:
        """Merge levels in a cluster into single level"""
        avg_price = np.mean([l['price'] for l in cluster])
        touches = len(cluster)
        dates = [l.get('date') for l in cluster if l.get('date') is not None]
        
        return {
            'price': avg_price,
            'touches': touches,
            'first_seen': min(dates) if dates else None,
            'last_seen': max(dates) if dates else None
        }
    
    def count_touches(self, df: pd.DataFrame, level_price: float, atr: float) -> int:
        """Count how many times price touched a level"""
        threshold = atr * self.cluster_threshold_atr
        
        # Check both highs and lows near the level
        high_touches = ((df['high'] >= level_price - threshold) & 
                       (df['high'] <= level_price + threshold)).sum()
        
        low_touches = ((df['low'] >= level_price - threshold) & 
                      (df['low'] <= level_price + threshold)).sum()
        
        return high_touches + low_touches
    
    def detect_sr_levels(self, df: pd.DataFrame, 
                        max_support: int = 3, 
                        max_resistance: int = 3) -> Tuple[List[SimpleSRLevel], List[SimpleSRLevel]]:
        """
        Main method to detect S/R levels
        
        Returns:
            Tuple of (support_levels, resistance_levels)
        """
        if len(df) < 50:  # Need minimum data
            return [], []
        
        # Calculate ATR for clustering
        atr = self.calculate_atr(df).iloc[-1]
        if pd.isna(atr):
            atr = float(df['high'].std())  # Fallback to standard deviation
        else:
            atr = float(atr)
        
        current_price = float(df.iloc[-1]['close'])
        
        # Find swing points
        highs, lows = self.find_swing_points(df)
        
        # Find round numbers if enabled
        round_numbers = []
        if self.include_round_numbers:
            price_range = (float(df['low'].min()) * 0.95, float(df['high'].max()) * 1.05)
            round_numbers = self.find_round_numbers(price_range)
        
        # Separate into support and resistance based on current price
        resistance_levels = []
        support_levels = []
        
        # Process swing highs as resistance
        if highs:
            clustered_highs = self.cluster_levels(highs, atr)
            for level in clustered_highs:
                if level['price'] > current_price and level['touches'] >= self.min_touches:
                    resistance_levels.append(SimpleSRLevel(
                        price=level['price'],
                        type='resistance',
                        touches=level['touches'],
                        first_seen=level.get('first_seen'),
                        last_seen=level.get('last_seen'),
                        is_round_number=False
                    ))
        
        # Process swing lows as support
        if lows:
            clustered_lows = self.cluster_levels(lows, atr)
            for level in clustered_lows:
                if level['price'] < current_price and level['touches'] >= self.min_touches:
                    support_levels.append(SimpleSRLevel(
                        price=level['price'],
                        type='support',
                        touches=level['touches'],
                        first_seen=level.get('first_seen'),
                        last_seen=level.get('last_seen'),
                        is_round_number=False
                    ))
        
        # Add round numbers
        for round_price in round_numbers:
            touches = self.count_touches(df, round_price, atr)
            
            if touches >= self.min_touches:
                level = SimpleSRLevel(
                    price=round_price,
                    type='resistance' if round_price > current_price else 'support',
                    touches=touches,
                    first_seen=df.index[0],
                    last_seen=df.index[-1],
                    is_round_number=True
                )
                
                if round_price > current_price:
                    resistance_levels.append(level)
                else:
                    support_levels.append(level)
        
        # Sort by distance from current price and touches
        resistance_levels.sort(key=lambda x: (x.price - current_price, -x.touches))
        support_levels.sort(key=lambda x: (current_price - x.price, -x.touches))
        
        # Return only top N levels
        return (support_levels[:max_support], 
                resistance_levels[:max_resistance])
    
    def get_sr_summary(self, df: pd.DataFrame) -> dict:
        """Get a simple summary of S/R levels"""
        support, resistance = self.detect_sr_levels(df)
        current_price = float(df.iloc[-1]['close'])
        
        summary = {
            'current_price': current_price,
            'support_levels': [],
            'resistance_levels': []
        }
        
        for s in support:
            summary['support_levels'].append({
                'price': s.price,
                'distance': f"{(current_price - s.price) / s.price * 100:.1f}%",
                'touches': s.touches,
                'round': s.is_round_number
            })
        
        for r in resistance:
            summary['resistance_levels'].append({
                'price': r.price,
                'distance': f"{(r.price - current_price) / current_price * 100:.1f}%",
                'touches': r.touches,
                'round': r.is_round_number
            })
        
        return summary