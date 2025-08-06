#!/usr/bin/env python3
"""
Test script to verify all system components
"""

import requests
import json
from datetime import datetime

BASE_URL = "http://localhost:5001"

def test_dashboard():
    """Test main dashboard"""
    print("Testing Dashboard...")
    response = requests.get(f"{BASE_URL}/")
    if response.status_code == 200 and "MANKIND" in response.text:
        print("✓ Dashboard is accessible")
    else:
        print("✗ Dashboard failed")
    
def test_admin_panel():
    """Test admin panel"""
    print("\nTesting Admin Panel...")
    response = requests.get(f"{BASE_URL}/admin")
    if response.status_code == 200 and "Admin Panel" in response.text:
        print("✓ Admin panel is accessible")
    else:
        print("✗ Admin panel failed")

def test_recommendations_page():
    """Test recommendations page"""
    print("\nTesting Recommendations Page...")
    response = requests.get(f"{BASE_URL}/recommendations")
    if response.status_code == 200 and "Trading Recommendations" in response.text:
        print("✓ Recommendations page is accessible")
    else:
        print("✗ Recommendations page failed")

def test_api_endpoints():
    """Test API endpoints"""
    print("\nTesting API Endpoints...")
    
    # Test dashboard data API
    response = requests.get(f"{BASE_URL}/api/dashboard-data")
    if response.status_code == 200:
        data = response.json()
        if 'current_price' in data:
            print(f"✓ Dashboard API working - Current Price: ₹{data['current_price']}")
        else:
            print("✗ Dashboard API returned incomplete data")
    else:
        print("✗ Dashboard API failed")
    
    # Test database status API
    response = requests.get(f"{BASE_URL}/api/database-status")
    if response.status_code == 200:
        data = response.json()
        print("✓ Database Status API working")
        for timeframe, info in data.items():
            print(f"  - {timeframe}: {info['count']} records, {info['coverage']}% coverage")
    else:
        print("✗ Database Status API failed")

def main():
    print("="*60)
    print("ENHANCED TRADING SYSTEM TEST")
    print("="*60)
    print(f"Time: {datetime.now()}")
    print(f"Testing URL: {BASE_URL}")
    print("="*60)
    
    test_dashboard()
    test_admin_panel()
    test_recommendations_page()
    test_api_endpoints()
    
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print("""
Available Features:
1. Main Dashboard: http://localhost:5001/
   - Real-time price display
   - Multi-timeframe trends
   - Support/Resistance levels
   - Interactive charts

2. Admin Panel: http://localhost:5001/admin
   - Download latest data button
   - Calculate trends button
   - Progress console
   - Database status

3. Recommendations: http://localhost:5001/recommendations
   - Generate new recommendations
   - Get Adam Grimes validation
   - View recommendation history
   - Store in database

API Endpoints:
- /api/dashboard-data - Get current market data
- /api/daily-update - Trigger data update
- /api/generate-recommendation - Generate trading recommendation
- /api/validate-recommendation - Get GPT validation
- /api/database-status - Check database status
""")

if __name__ == "__main__":
    main()