#!/usr/bin/env python3
"""
AskGPT Module - Interface for ChatGPT API integration
Provides trading advice, analysis, and insights using OpenAI's GPT models
"""

import os
import json
import logging
from typing import Dict, List, Optional, Union
from datetime import datetime
import requests
from dataclasses import dataclass
import time

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class GPTResponse:
    """Structure for GPT responses"""
    content: str
    model: str
    usage: Dict[str, int]
    timestamp: datetime
    success: bool
    error: Optional[str] = None

class AskGPT:
    """
    Interface for OpenAI's ChatGPT API
    Provides trading analysis and advice
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize AskGPT with API key
        
        Args:
            api_key: OpenAI API key (if not provided, reads from environment)
        """
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError("OpenAI API key not provided. Set OPENAI_API_KEY environment variable or pass api_key parameter.")
        
        self.base_url = "https://api.openai.com/v1/chat/completions"
        self.default_model = "gpt-4"  # or "gpt-3.5-turbo" for faster/cheaper responses
        self.max_retries = 3
        self.retry_delay = 1  # seconds
        
        # System prompts for different contexts
        self.system_prompts = {
            'trading': """You are an expert quantitative trading analyst with deep knowledge of:
- Technical analysis and market structure (especially Adam Grimes methodology)
- Statistical analysis and backtesting
- Risk management and position sizing
- Market microstructure and order flow
- Indian stock markets (NSE/BSE)

Provide clear, actionable insights based on data. Be specific and practical.""",
            
            'analysis': """You are a financial data scientist specializing in:
- Time series analysis
- Pattern recognition in financial markets
- Statistical validation of trading strategies
- Market regime identification
- Correlation and causation analysis

Focus on data-driven insights and statistical significance.""",
            
            'risk': """You are a risk management expert focusing on:
- Portfolio risk assessment
- Position sizing strategies
- Drawdown management
- Risk-adjusted returns
- Tail risk and black swan events

Prioritize capital preservation and sustainable trading practices."""
        }
    
    def ask(self, question: str, context: str = 'trading', 
            additional_context: Optional[str] = None,
            temperature: float = 0.7,
            max_tokens: int = 1000) -> GPTResponse:
        """
        Ask ChatGPT a question
        
        Args:
            question: The question to ask
            context: Context type ('trading', 'analysis', 'risk')
            additional_context: Additional context information (e.g., current market data)
            temperature: Response creativity (0-1, lower = more focused)
            max_tokens: Maximum response length
            
        Returns:
            GPTResponse object with the answer
        """
        # Prepare messages
        messages = [
            {"role": "system", "content": self.system_prompts.get(context, self.system_prompts['trading'])}
        ]
        
        # Add additional context if provided
        if additional_context:
            messages.append({
                "role": "system", 
                "content": f"Additional context:\n{additional_context}"
            })
        
        # Add the user question
        messages.append({"role": "user", "content": question})
        
        # Prepare request
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": self.default_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        # Make request with retries
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    self.base_url,
                    headers=headers,
                    json=data,
                    timeout=30
                )
                
                if response.status_code == 200:
                    result = response.json()
                    
                    return GPTResponse(
                        content=result['choices'][0]['message']['content'],
                        model=result['model'],
                        usage=result['usage'],
                        timestamp=datetime.now(),
                        success=True
                    )
                else:
                    error_msg = f"API error: {response.status_code} - {response.text}"
                    logger.error(error_msg)
                    
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay * (attempt + 1))
                        continue
                    
                    return GPTResponse(
                        content="",
                        model=self.default_model,
                        usage={},
                        timestamp=datetime.now(),
                        success=False,
                        error=error_msg
                    )
                    
            except Exception as e:
                error_msg = f"Request failed: {str(e)}"
                logger.error(error_msg)
                
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (attempt + 1))
                    continue
                
                return GPTResponse(
                    content="",
                    model=self.default_model,
                    usage={},
                    timestamp=datetime.now(),
                    success=False,
                    error=error_msg
                )
    
    def analyze_trend_data(self, trend_data: Dict) -> GPTResponse:
        """
        Analyze trend data and provide insights
        
        Args:
            trend_data: Dictionary containing trend information
            
        Returns:
            GPTResponse with analysis
        """
        # Format trend data for context
        context = f"""
Current Market Data:
- Symbol: {trend_data.get('symbol', 'Unknown')}
- Timeframe: {trend_data.get('timeframe', 'Unknown')}
- Current Trend: {trend_data.get('trend', 'Unknown')}
- Trend Strength: {trend_data.get('strength', 0)}%
- Trend Confidence: {trend_data.get('confidence', 0)}%
- Swing Ratio: {trend_data.get('swing_ratio', 1.0)}
- Market Regime: {trend_data.get('market_regime', 'Unknown')}
- Recent Price: {trend_data.get('price', 0)}
"""
        
        question = """Based on the current market data:
1. What is your assessment of the current trend quality?
2. Are there any warning signs or confirmations in the data?
3. What would be appropriate trading actions or considerations?
4. What additional data points would strengthen this analysis?"""
        
        return self.ask(
            question=question,
            context='analysis',
            additional_context=context,
            temperature=0.5  # Lower temperature for more focused analysis
        )
    
    def get_trading_advice(self, 
                          symbol: str,
                          current_price: float,
                          trend_info: Dict,
                          support_resistance: Optional[List[Dict]] = None,
                          risk_tolerance: str = 'moderate') -> GPTResponse:
        """
        Get specific trading advice for a symbol
        
        Args:
            symbol: Trading symbol
            current_price: Current market price
            trend_info: Trend information across timeframes
            support_resistance: List of S/R levels
            risk_tolerance: 'conservative', 'moderate', 'aggressive'
            
        Returns:
            GPTResponse with trading advice
        """
        # Build comprehensive context
        context_parts = [
            f"Symbol: {symbol}",
            f"Current Price: {current_price}",
            f"Risk Tolerance: {risk_tolerance}",
            "\nTrend Analysis:"
        ]
        
        # Add trend info
        for timeframe, info in trend_info.items():
            context_parts.append(
                f"- {timeframe}: {info['trend']} "
                f"(Strength: {info['strength']}%, Confidence: {info['confidence']}%)"
            )
        
        # Add S/R levels if provided
        if support_resistance:
            context_parts.append("\nKey Levels:")
            for level in support_resistance[:5]:  # Top 5 levels
                context_parts.append(
                    f"- {level['type']}: {level['price']} "
                    f"(Strength: {level['strength']})"
                )
        
        context = "\n".join(context_parts)
        
        question = f"""As a trading advisor, provide specific guidance for {symbol}:

1. Entry Strategy: Should I enter a position? If yes, at what levels?
2. Position Sizing: What percentage of capital would be appropriate?
3. Stop Loss: Where should protective stops be placed?
4. Target Levels: What are realistic profit targets?
5. Time Horizon: What holding period makes sense given the current setup?
6. Risk Factors: What could invalidate this trade idea?

Please be specific with price levels and percentages where applicable."""
        
        return self.ask(
            question=question,
            context='trading',
            additional_context=context,
            temperature=0.6
        )
    
    def explain_market_concept(self, concept: str) -> GPTResponse:
        """
        Explain a trading or market concept
        
        Args:
            concept: The concept to explain
            
        Returns:
            GPTResponse with explanation
        """
        question = f"""Please explain the following trading/market concept in clear, practical terms:

Concept: {concept}

Include:
1. Simple definition
2. How it works in practice
3. Real-world example
4. Common misconceptions
5. How to use it in trading decisions"""
        
        return self.ask(
            question=question,
            context='trading',
            temperature=0.7,
            max_tokens=1500
        )
    
    def validate_strategy(self, strategy_description: str, 
                         backtest_results: Optional[Dict] = None) -> GPTResponse:
        """
        Validate a trading strategy
        
        Args:
            strategy_description: Description of the strategy
            backtest_results: Optional backtest performance metrics
            
        Returns:
            GPTResponse with validation insights
        """
        context = f"Strategy Description:\n{strategy_description}"
        
        if backtest_results:
            context += f"\n\nBacktest Results:\n"
            for metric, value in backtest_results.items():
                context += f"- {metric}: {value}\n"
        
        question = """Please provide a comprehensive validation of this trading strategy:

1. Logical Assessment: Does the strategy logic make sense?
2. Edge Identification: What is the potential edge or inefficiency being exploited?
3. Risk Analysis: What are the main risks and drawdowns to expect?
4. Market Conditions: In what market conditions will this strategy perform well/poorly?
5. Improvements: What modifications could enhance the strategy?
6. Reality Check: What practical issues might arise in live trading?"""
        
        return self.ask(
            question=question,
            context='analysis',
            additional_context=context,
            temperature=0.5,
            max_tokens=2000
        )

# Convenience functions
def ask_gpt(question: str, api_key: Optional[str] = None, **kwargs) -> str:
    """
    Simple function to ask GPT a question
    
    Args:
        question: The question to ask
        api_key: Optional API key
        **kwargs: Additional parameters for the ask method
        
    Returns:
        String response from GPT
    """
    try:
        gpt = AskGPT(api_key=api_key)
        response = gpt.ask(question, **kwargs)
        
        if response.success:
            return response.content
        else:
            return f"Error: {response.error}"
            
    except Exception as e:
        return f"Error initializing GPT: {str(e)}"

def main():
    """Example usage"""
    # Example questions
    example_questions = [
        "What are the key principles of Adam Grimes' market structure analysis?",
        "How should I interpret a swing ratio of 1.5 in an uptrend?",
        "What's the difference between trend strength and trend confidence?"
    ]
    
    print("AskGPT Module - Example Usage\n")
    print("Note: Requires OPENAI_API_KEY environment variable to be set\n")
    
    try:
        gpt = AskGPT()
        
        for i, question in enumerate(example_questions, 1):
            print(f"\nQuestion {i}: {question}")
            print("-" * 80)
            
            response = gpt.ask(question, context='trading')
            
            if response.success:
                print(f"Answer: {response.content}")
                print(f"\nTokens used: {response.usage.get('total_tokens', 'N/A')}")
            else:
                print(f"Error: {response.error}")
                
    except Exception as e:
        print(f"Error: {str(e)}")
        print("\nTo use this module, set your OpenAI API key:")
        print("export OPENAI_API_KEY='your-api-key-here'")

if __name__ == "__main__":
    main()