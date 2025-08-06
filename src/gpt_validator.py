#!/usr/bin/env python3
"""
GPT Validator Module
Validates trading recommendations using Adam Grimes' perspective
"""

import os
import json
from openai import OpenAI
from datetime import datetime
import psycopg2
from dotenv import load_dotenv
import logging

load_dotenv()

class AdamGrimesValidator:
    def __init__(self):
        """Initialize the validator with Adam Grimes persona"""
        self.api_key = os.getenv('OPENAI_API_KEY')
        self.client = OpenAI(api_key=self.api_key)
        
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
        
        # Adam Grimes persona
        self.system_prompt = """You are Adam Grimes, a highly experienced trader and author of "The Art and Science of Technical Analysis". 
You are known for your systematic, probability-based approach to trading and your emphasis on:

1. Market structure and swing points
2. Trend continuation vs reversal patterns
3. Risk management and position sizing
4. Statistical edge and pattern validation
5. The importance of context in technical analysis
6. Avoiding over-optimization and keeping things simple
7. Understanding market psychology and participant behavior

Your trading philosophy emphasizes:
- Trading with the trend is easier than fighting it
- Failed patterns often provide the best opportunities
- The first test of support/resistance often holds
- Pullbacks in trends are high-probability entries
- Risk management is more important than entry signals
- Multiple timeframe alignment increases probability

Review the following trading recommendation and provide your expert opinion. Be critical but constructive.
Rate the recommendation from 1-10 and explain your reasoning using your systematic approach.
Focus on:
1. Is this trade aligned with market structure?
2. Does it have a clear statistical edge?
3. Is the risk/reward favorable?
4. Are the entry and exit levels logical?
5. Does it consider multiple timeframes?
6. What could go wrong with this trade?
"""
    
    def get_db_connection(self):
        """Create database connection"""
        return psycopg2.connect(**self.db_params)
    
    def validate_recommendation(self, recommendation_id):
        """Validate a specific recommendation"""
        # Get recommendation from database
        recommendation = self.get_recommendation(recommendation_id)
        if not recommendation:
            raise ValueError(f"Recommendation {recommendation_id} not found")
        
        # Prepare the recommendation for validation
        recommendation_text = self.format_recommendation_for_validation(recommendation)
        
        # Get Adam Grimes' perspective
        validation = self.get_adam_grimes_perspective(recommendation_text)
        
        # Parse the validation
        score, analysis = self.parse_validation(validation)
        
        # Save validation to database
        self.save_validation(recommendation_id, validation, score)
        
        return {
            'recommendation_id': recommendation_id,
            'score': score,
            'analysis': analysis,
            'full_validation': validation
        }
    
    def get_recommendation(self, recommendation_id):
        """Get recommendation from database"""
        conn = self.get_db_connection()
        cur = conn.cursor()
        
        try:
            query = """
                SELECT * FROM dhanhq.trading_recommendations
                WHERE id = %s
            """
            cur.execute(query, (recommendation_id,))
            
            columns = [desc[0] for desc in cur.description]
            result = cur.fetchone()
            
            if result:
                return dict(zip(columns, result))
            else:
                return None
                
        finally:
            cur.close()
            conn.close()
    
    def format_recommendation_for_validation(self, rec):
        """Format recommendation for GPT validation"""
        text = f"""
Trading Recommendation for {rec['symbol']}
Generated: {rec['generated_at']}

Current Market Context:
- Price: ₹{rec['current_price']}
- 1-min Trend: {rec['trend_1min']}
- 5-min Trend: {rec['trend_5min']}
- 15-min Trend: {rec['trend_15min']}
- 60-min Trend: {rec['trend_60min']}
- Daily Trend: {rec['trend_daily']}

Support/Resistance Levels:
- Resistance: R1=₹{rec['resistance_1']}, R2=₹{rec['resistance_2']}, R3=₹{rec['resistance_3']}
- Support: S1=₹{rec['support_1']}, S2=₹{rec['support_2']}, S3=₹{rec['support_3']}

Intraday Recommendation:
- Action: {rec['intraday_action']}
- Entry: ₹{rec['intraday_entry']}
- Stop Loss: ₹{rec['intraday_stoploss']}
- Target 1: ₹{rec['intraday_target1']}
- Target 2: ₹{rec['intraday_target2']}
- Risk/Reward: {rec['intraday_risk_reward']}
- Rationale: {rec['intraday_rationale']}

Swing Trading Recommendation:
- Action: {rec['swing_action']}
- Entry: ₹{rec['swing_entry']}
- Stop Loss: ₹{rec['swing_stoploss']}
- Targets: ₹{rec['swing_target1']}, ₹{rec['swing_target2']}, ₹{rec['swing_target3']}
- Risk/Reward: {rec['swing_risk_reward']}
- Rationale: {rec['swing_rationale']}

Full Analysis:
{rec['recommendation_text']}
"""
        return text
    
    def get_adam_grimes_perspective(self, recommendation_text):
        """Get Adam Grimes' perspective on the recommendation"""
        try:
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": f"Please review this trading recommendation:\n\n{recommendation_text}"}
                ],
                temperature=0.7,
                max_tokens=1500
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            self.logger.error(f"Error getting GPT validation: {e}")
            raise
    
    def parse_validation(self, validation_text):
        """Parse validation to extract score and key points"""
        score = 5  # Default score
        
        # Try to extract score from text
        import re
        
        # Look for patterns like "7/10", "8 out of 10", "score: 7"
        score_patterns = [
            r'(\d+)/10',
            r'(\d+)\s+out\s+of\s+10',
            r'score[:\s]+(\d+)',
            r'rating[:\s]+(\d+)'
        ]
        
        for pattern in score_patterns:
            matches = re.findall(pattern, validation_text.lower())
            if matches:
                try:
                    score = int(matches[0])
                    break
                except:
                    pass
        
        # Extract key points (first 500 chars for summary)
        analysis = validation_text[:500] if len(validation_text) > 500 else validation_text
        
        return score, analysis
    
    def save_validation(self, recommendation_id, validation_text, score):
        """Save validation to database"""
        conn = self.get_db_connection()
        cur = conn.cursor()
        
        try:
            update_query = """
                UPDATE dhanhq.trading_recommendations
                SET gpt_validation = %s,
                    gpt_validated_at = %s,
                    gpt_validation_score = %s
                WHERE id = %s
            """
            
            cur.execute(update_query, (
                validation_text,
                datetime.now(),
                score,
                recommendation_id
            ))
            
            conn.commit()
            self.logger.info(f"Saved validation for recommendation {recommendation_id}")
            
        except Exception as e:
            conn.rollback()
            self.logger.error(f"Error saving validation: {e}")
            raise
        finally:
            cur.close()
            conn.close()

if __name__ == "__main__":
    # Test the validator
    validator = AdamGrimesValidator()
    
    # This would validate the latest recommendation
    # You need to have a recommendation ID to test
    # result = validator.validate_recommendation(1)
    # print(f"Validation result: {result}")