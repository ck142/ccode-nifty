#!/usr/bin/env python3
"""
Test script to debug DhanHQ API v2 issues
"""

import requests
import json
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()

def test_intraday_api():
    """Test the intraday API endpoint with various configurations"""
    
    api_token = os.getenv('DHAN_API_TOKEN')
    
    if not api_token:
        print("❌ ERROR: DHAN_API_TOKEN not found in .env file!")
        print("\nPlease add the following to your .env file:")
        print("DHAN_API_TOKEN=your_actual_api_token_here")
        return
    
    print("✅ API Token found")
    
    # Test configurations
    url = "https://api.dhan.co/v2/charts/intraday"
    
    # Calculate dates
    to_date = datetime.now()
    from_date = to_date - timedelta(days=1)
    
    # Different payload variations to test
    test_cases = [
        {
            "name": "Test 1: With securityId as string",
            "payload": {
                'securityId': '15380',
                'exchangeSegment': 'NSE_EQ',
                'instrument': 'EQUITY',
                'interval': '1',
                'fromDate': from_date.strftime('%Y-%m-%d'),
                'toDate': to_date.strftime('%Y-%m-%d')
            }
        },
        {
            "name": "Test 2: With integer interval",
            "payload": {
                'securityId': '15380',
                'exchangeSegment': 'NSE_EQ',
                'instrument': 'EQUITY',
                'interval': 1,
                'fromDate': from_date.strftime('%Y-%m-%d'),
                'toDate': to_date.strftime('%Y-%m-%d')
            }
        },
        {
            "name": "Test 3: With oi field",
            "payload": {
                'securityId': '15380',
                'exchangeSegment': 'NSE_EQ',
                'instrument': 'EQUITY',
                'interval': '1',
                'oi': False,
                'fromDate': from_date.strftime('%Y-%m-%d'),
                'toDate': to_date.strftime('%Y-%m-%d')
            }
        },
        {
            "name": "Test 4: Using symbol instead of securityId",
            "payload": {
                'symbol': 'MANKIND',
                'exchangeSegment': 'NSE_EQ',
                'instrument': 'EQUITY',
                'interval': '1',
                'fromDate': from_date.strftime('%Y-%m-%d'),
                'toDate': to_date.strftime('%Y-%m-%d')
            }
        }
    ]
    
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'access-token': api_token
    }
    
    print(f"\nTesting endpoint: {url}")
    print(f"Date range: {from_date.strftime('%Y-%m-%d')} to {to_date.strftime('%Y-%m-%d')}")
    print("="*60)
    
    for test in test_cases:
        print(f"\n{test['name']}")
        print(f"Payload: {json.dumps(test['payload'], indent=2)}")
        
        try:
            response = requests.post(url, headers=headers, json=test['payload'])
            
            print(f"Status Code: {response.status_code}")
            
            if response.status_code == 200:
                print("✅ SUCCESS!")
                data = response.json()
                if 'data' in data:
                    candles = data.get('data', [])
                    print(f"Received {len(candles)} candles")
                    if candles and len(candles) > 0:
                        print(f"First candle: {candles[0]}")
                else:
                    print(f"Response structure: {list(data.keys())}")
            else:
                print(f"❌ ERROR: {response.status_code}")
                print(f"Response: {response.text}")
                
        except Exception as e:
            print(f"❌ Exception: {e}")
        
        print("-"*40)

def test_historical_api():
    """Test the historical API endpoint"""
    
    api_token = os.getenv('DHAN_API_TOKEN')
    
    if not api_token:
        print("❌ ERROR: DHAN_API_TOKEN not found!")
        return
    
    url = "https://api.dhan.co/v2/charts/historical"
    
    to_date = datetime.now()
    from_date = to_date - timedelta(days=30)
    
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'access-token': api_token
    }
    
    payload = {
        'securityId': '15380',
        'exchangeSegment': 'NSE_EQ',
        'instrument': 'EQUITY',
        'expiryCode': '0',
        'fromDate': from_date.strftime('%Y-%m-%d'),
        'toDate': to_date.strftime('%Y-%m-%d'),
        'interval': 'D'
    }
    
    print("\n" + "="*60)
    print("Testing Historical API")
    print(f"Endpoint: {url}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ SUCCESS!")
            data = response.json()
            if 'data' in data:
                candles = data.get('data', [])
                print(f"Received {len(candles)} daily candles")
        else:
            print(f"❌ ERROR: {response.text}")
    except Exception as e:
        print(f"❌ Exception: {e}")

if __name__ == "__main__":
    print("="*60)
    print("DhanHQ API v2 Test Script")
    print("="*60)
    
    test_intraday_api()
    test_historical_api()
    
    print("\n" + "="*60)
    print("Test Complete")
    print("="*60)
    print("\nIf all tests failed with 400/401 errors:")
    print("1. Check your DHAN_API_TOKEN in .env file")
    print("2. Verify the token is active and has proper permissions")
    print("3. Check if MANKIND (15380) is the correct security ID")
    print("\nYou can find your API token at:")
    print("https://dhan.co/user/api")