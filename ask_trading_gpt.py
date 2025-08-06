#!/usr/bin/env python3
"""
Interactive AskGPT Trading Assistant
Simple command-line interface for getting trading advice from ChatGPT
"""

import sys
import os
from src.askgpt import AskGPT
from src.askgpt_integration import TradingGPTAdvisor
from src import Config

def print_menu():
    """Print the main menu"""
    print("\n" + "=" * 60)
    print("ASKGPT TRADING ASSISTANT")
    print("=" * 60)
    print("1. Get Current Market Analysis (MANKIND)")
    print("2. Explain Current Trends")
    print("3. Get Market Regime Advice")
    print("4. Ask Custom Trading Question")
    print("5. Explain Trading Concept")
    print("6. Exit")
    print("-" * 60)

def main():
    """Main interactive loop"""
    # Check API key
    if not os.getenv('OPENAI_API_KEY'):
        print("ERROR: OPENAI_API_KEY not found")
        print("Please set it in your .env file")
        sys.exit(1)
    
    print("Welcome to AskGPT Trading Assistant!")
    print("Powered by GPT-4 for intelligent trading insights\n")
    
    advisor = TradingGPTAdvisor()
    gpt = AskGPT()
    
    while True:
        print_menu()
        choice = input("Select an option (1-6): ").strip()
        
        if choice == '1':
            print("\nFetching current market analysis...")
            print("-" * 60)
            try:
                analysis = advisor.analyze_current_setup()
                print(analysis)
            except Exception as e:
                print(f"Error: {e}")
                
        elif choice == '2':
            print("\nAnalyzing trend patterns...")
            print("-" * 60)
            try:
                explanation = advisor.explain_current_trends()
                print(explanation)
            except Exception as e:
                print(f"Error: {e}")
                
        elif choice == '3':
            print("\nGetting market regime advice...")
            print("-" * 60)
            try:
                advice = advisor.get_market_regime_advice()
                print(advice)
            except Exception as e:
                print(f"Error: {e}")
                
        elif choice == '4':
            print("\nAsk any trading question:")
            question = input("Your question: ").strip()
            if question:
                print("\nThinking...")
                print("-" * 60)
                try:
                    response = gpt.ask(question, context='trading')
                    if response.success:
                        print(response.content)
                    else:
                        print(f"Error: {response.error}")
                except Exception as e:
                    print(f"Error: {e}")
                    
        elif choice == '5':
            print("\nWhat trading concept would you like explained?")
            concept = input("Concept: ").strip()
            if concept:
                print("\nExplaining...")
                print("-" * 60)
                try:
                    response = gpt.explain_market_concept(concept)
                    if response.success:
                        print(response.content)
                    else:
                        print(f"Error: {response.error}")
                except Exception as e:
                    print(f"Error: {e}")
                    
        elif choice == '6':
            print("\nThank you for using AskGPT Trading Assistant!")
            print("Happy trading!")
            break
            
        else:
            print("\nInvalid choice. Please select 1-6.")
        
        input("\nPress Enter to continue...")

if __name__ == "__main__":
    main()