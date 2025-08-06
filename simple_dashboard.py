#!/usr/bin/env python3
"""
Minimalistic MANKIND Trading Dashboard
"""

from flask import Flask, jsonify, request
import psycopg2
import os
from datetime import datetime, timedelta
import pytz
from dotenv import load_dotenv
import threading
import json
import pandas as pd
from src.trend_detector import SimpleTrendDetector

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Store progress messages
progress_messages = []
calculation_running = False

# Admin HTML template
ADMIN_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Admin - Trend Calculation</title>
    <style>
        body {
            font-family: monospace;
            margin: 20px;
            background: #f5f5f5;
            color: black;
        }
        h1 {
            font-size: 20px;
            margin-bottom: 20px;
        }
        .button {
            background: #4CAF50;
            color: white;
            padding: 10px 20px;
            border: none;
            cursor: pointer;
            font-size: 14px;
            margin: 10px 0;
        }
        .button:hover {
            background: #45a049;
        }
        .button:disabled {
            background: #cccccc;
            cursor: not-allowed;
        }
        .console {
            background: #1e1e1e;
            color: #00ff00;
            padding: 15px;
            height: 400px;
            overflow-y: auto;
            font-family: 'Courier New', monospace;
            font-size: 12px;
            border: 1px solid #333;
            margin-top: 20px;
        }
        .console-line {
            margin: 2px 0;
        }
        .status {
            margin: 10px 0;
            padding: 10px;
            background: white;
            border: 1px solid #ddd;
        }
        .running {
            color: orange;
            font-weight: bold;
        }
        .complete {
            color: green;
            font-weight: bold;
        }
        .error {
            color: red;
            font-weight: bold;
        }
        .back-link {
            display: inline-block;
            margin-top: 20px;
            color: #0066cc;
            text-decoration: none;
        }
        .back-link:hover {
            text-decoration: underline;
        }
    </style>
</head>
<body>
    <h1>Admin Panel - Trend Calculation</h1>
    
    <div class="status">
        Status: <span id="status">Ready</span>
    </div>
    
    <button id="runButton" class="button" onclick="startCalculation()">
        Run Trend Calculation for MANKIND
    </button>
    
    <button class="button" onclick="clearConsole()">
        Clear Console
    </button>
    
    <div class="console" id="console">
        <div class="console-line">Console ready...</div>
    </div>
    
    <a href="/" class="back-link">← Back to Dashboard</a>
    
    <script>
        let isRunning = false;
        let lastMessageCount = 0;
        
        function startCalculation() {
            if (isRunning) return;
            
            isRunning = true;
            document.getElementById('runButton').disabled = true;
            document.getElementById('status').className = 'running';
            document.getElementById('status').textContent = 'Running...';
            
            // Clear console
            clearConsole();
            addConsoleMessage('Starting trend calculation...');
            
            // Start calculation
            fetch('/admin/calculate-trends', {
                method: 'POST'
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'started') {
                    // Start polling for progress
                    pollProgress();
                } else {
                    addConsoleMessage('Error: ' + data.message);
                    resetButton();
                }
            })
            .catch(error => {
                addConsoleMessage('Error: ' + error);
                resetButton();
            });
        }
        
        function pollProgress() {
            fetch('/admin/progress')
            .then(response => response.json())
            .then(data => {
                // Add new messages to console
                if (data.messages && data.messages.length > lastMessageCount) {
                    for (let i = lastMessageCount; i < data.messages.length; i++) {
                        addConsoleMessage(data.messages[i]);
                    }
                    lastMessageCount = data.messages.length;
                }
                
                // Check if still running
                if (data.running) {
                    setTimeout(pollProgress, 500); // Poll every 500ms
                } else {
                    document.getElementById('status').className = 'complete';
                    document.getElementById('status').textContent = 'Complete';
                    resetButton();
                }
            })
            .catch(error => {
                addConsoleMessage('Polling error: ' + error);
                resetButton();
            });
        }
        
        function resetButton() {
            isRunning = false;
            document.getElementById('runButton').disabled = false;
            lastMessageCount = 0;
        }
        
        function addConsoleMessage(message) {
            const console = document.getElementById('console');
            const line = document.createElement('div');
            line.className = 'console-line';
            const timestamp = new Date().toLocaleTimeString();
            line.textContent = '[' + timestamp + '] ' + message;
            console.appendChild(line);
            console.scrollTop = console.scrollHeight;
        }
        
        function clearConsole() {
            document.getElementById('console').innerHTML = '<div class="console-line">Console cleared...</div>';
        }
    </script>
</body>
</html>
'''

# Minimal HTML template
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>MANKIND Trading Info</title>
    <style>
        body {
            font-family: monospace;
            margin: 20px;
            background: white;
            color: black;
            line-height: 1.6;
        }
        h1 {
            font-size: 18px;
            margin-bottom: 20px;
        }
        .section {
            margin-bottom: 20px;
            border-bottom: 1px solid #ccc;
            padding-bottom: 10px;
        }
        .label {
            font-weight: bold;
            display: inline-block;
            width: 200px;
        }
        .value {
            color: #333;
        }
        .uptrend {
            color: green;
        }
        .downtrend {
            color: red;
        }
        .sideways {
            color: gray;
        }
    </style>
</head>
<body>
    <h1>MANKIND PHARMA LIMITED - Trading Information</h1>
    
    <div class="section">
        <div><span class="label">Last Data Update:</span><span class="value">{{ last_update }}</span></div>
    </div>
    
    <div class="section">
        <h2 style="font-size: 16px;">Support & Resistance Levels</h2>
        <div><span class="label">Resistance 3:</span><span class="value">₹{{ r3 }}</span></div>
        <div><span class="label">Resistance 2:</span><span class="value">₹{{ r2 }}</span></div>
        <div><span class="label">Resistance 1:</span><span class="value">₹{{ r1 }}</span></div>
        <div style="margin: 10px 0; padding: 5px 0; border-top: 1px dashed #999; border-bottom: 1px dashed #999;">
            <span class="label" style="font-weight: bold; color: #0066cc;">CURRENT PRICE:</span>
            <span class="value" style="font-weight: bold; color: #0066cc;">₹{{ current_price }}</span>
        </div>
        <div><span class="label">Support 1:</span><span class="value">₹{{ s1 }}</span></div>
        <div><span class="label">Support 2:</span><span class="value">₹{{ s2 }}</span></div>
        <div><span class="label">Support 3:</span><span class="value">₹{{ s3 }}</span></div>
    </div>
    
    <div class="section">
        <h2 style="font-size: 16px;">Trend Analysis</h2>
        <h3 style="font-size: 14px; margin-top: 10px;">Intraday Trends:</h3>
        <div><span class="label">5-Minute Trend:</span><span class="value {{ trend_5m_class }}">{{ trend_5m }}</span></div>
        <div><span class="label">15-Minute Trend:</span><span class="value {{ trend_15m_class }}">{{ trend_15m }}</span></div>
        <div><span class="label">1-Hour Trend:</span><span class="value {{ trend_1h_class }}">{{ trend_1h }}</span></div>
        
        <h3 style="font-size: 14px; margin-top: 15px;">Higher Timeframe Trends:</h3>
        <div><span class="label">Daily Trend:</span><span class="value {{ trend_daily_class }}">{{ trend_daily }}</span></div>
        <div><span class="label">Weekly Trend:</span><span class="value {{ trend_weekly_class }}">{{ trend_weekly }}</span></div>
        <div><span class="label">Monthly Trend:</span><span class="value {{ trend_monthly_class }}">{{ trend_monthly }}</span></div>
        
        <div style="margin-top: 10px; font-size: 12px; color: #666; font-style: italic;">
            Note: Run trend calculation from Admin Panel to update trends
        </div>
    </div>
    
    <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #ccc;">
        <a href="/admin" style="color: #0066cc; text-decoration: none;">Admin Panel →</a>
    </div>
    
    <script>
        // Auto-refresh every 30 seconds
        setTimeout(function(){
            location.reload();
        }, 30000);
    </script>
</body>
</html>
'''

def get_db_connection():
    """Create database connection"""
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', 5432),
        database=os.getenv('DB_NAME', 'trading_db'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD')
    )

@app.route('/')
def index():
    """Main dashboard page with minimal info"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get latest data timestamp and price
    cur.execute("""
        SELECT datetime, close 
        FROM dhanhq.price_data 
        WHERE security_id = '15380' 
        ORDER BY datetime DESC 
        LIMIT 1
    """)
    result = cur.fetchone()
    if result:
        # Convert to IST
        ist = pytz.timezone('Asia/Kolkata')
        dt_utc = result[0]
        dt_ist = dt_utc.astimezone(ist)
        last_update = dt_ist.strftime("%Y-%m-%d %H:%M:%S IST")
        current_price = f"{result[1]:.2f}"
    else:
        last_update = "No data"
        current_price = "N/A"
    
    # Get current S/R levels (from most recent data with S/R)
    cur.execute("""
        SELECT resistance_1, resistance_2, resistance_3, 
               support_1, support_2, support_3
        FROM dhanhq.price_data 
        WHERE security_id = '15380' 
          AND resistance_1 IS NOT NULL
        ORDER BY datetime DESC 
        LIMIT 1
    """)
    sr_result = cur.fetchone()
    
    if sr_result:
        r1, r2, r3, s1, s2, s3 = sr_result
        r1 = f"{r1:.2f}" if r1 is not None else "N/A"
        r2 = f"{r2:.2f}" if r2 is not None else "N/A"
        r3 = f"{r3:.2f}" if r3 is not None else "N/A"
        s1 = f"{s1:.2f}" if s1 is not None else "N/A"
        s2 = f"{s2:.2f}" if s2 is not None else "N/A"
        s3 = f"{s3:.2f}" if s3 is not None else "N/A"
    else:
        r1 = r2 = r3 = s1 = s2 = s3 = "N/A"
    
    # Get trend info for different timeframes
    trends = {}
    trend_classes = {}
    
    for interval, label in [(5, '5m'), (15, '15m'), (60, '1h')]:
        cur.execute("""
            SELECT simple_trend 
            FROM dhanhq.price_data 
            WHERE security_id = '15380' 
              AND interval_minutes = %s
              AND simple_trend IS NOT NULL
            ORDER BY datetime DESC 
            LIMIT 1
        """, (interval,))
        trend_result = cur.fetchone()
        
        if trend_result and trend_result[0]:
            trend = trend_result[0].upper()
            trends[f'trend_{label}'] = trend
            if trend == 'UPTREND':
                trend_classes[f'trend_{label}_class'] = 'uptrend'
            elif trend == 'DOWNTREND':
                trend_classes[f'trend_{label}_class'] = 'downtrend'
            else:
                trend_classes[f'trend_{label}_class'] = 'sideways'
        else:
            trends[f'trend_{label}'] = 'N/A'
            trend_classes[f'trend_{label}_class'] = ''
    
    # Get daily trend from real daily data
    cur.execute("""
        SELECT trend 
        FROM dhanhq.price_data_daily 
        WHERE security_id = '15380' 
          AND trend IS NOT NULL
        ORDER BY date DESC 
        LIMIT 1
    """)
    daily_result = cur.fetchone()
    
    if daily_result and daily_result[0]:
        trend = daily_result[0].upper()
        trends['trend_daily'] = trend
        if trend == 'UPTREND':
            trend_classes['trend_daily_class'] = 'uptrend'
        elif trend == 'DOWNTREND':
            trend_classes['trend_daily_class'] = 'downtrend'
        else:
            trend_classes['trend_daily_class'] = 'sideways'
    else:
        trends['trend_daily'] = 'Not calculated'
        trend_classes['trend_daily_class'] = ''
    
    # Get weekly trend
    cur.execute("""
        SELECT trend 
        FROM dhanhq.price_data_weekly 
        WHERE security_id = '15380' 
          AND trend IS NOT NULL
        ORDER BY week_start_date DESC 
        LIMIT 1
    """)
    weekly_result = cur.fetchone()
    
    if weekly_result and weekly_result[0]:
        trend = weekly_result[0].upper()
        trends['trend_weekly'] = trend
        if trend == 'UPTREND':
            trend_classes['trend_weekly_class'] = 'uptrend'
        elif trend == 'DOWNTREND':
            trend_classes['trend_weekly_class'] = 'downtrend'
        else:
            trend_classes['trend_weekly_class'] = 'sideways'
    else:
        trends['trend_weekly'] = 'Not calculated'
        trend_classes['trend_weekly_class'] = ''
    
    # Get monthly trend
    cur.execute("""
        SELECT trend 
        FROM dhanhq.price_data_monthly 
        WHERE security_id = '15380' 
          AND trend IS NOT NULL
        ORDER BY year DESC, month DESC 
        LIMIT 1
    """)
    monthly_result = cur.fetchone()
    
    if monthly_result and monthly_result[0]:
        trend = monthly_result[0].upper()
        trends['trend_monthly'] = trend
        if trend == 'UPTREND':
            trend_classes['trend_monthly_class'] = 'uptrend'
        elif trend == 'DOWNTREND':
            trend_classes['trend_monthly_class'] = 'downtrend'
        else:
            trend_classes['trend_monthly_class'] = 'sideways'
    else:
        trends['trend_monthly'] = 'Not calculated'
        trend_classes['trend_monthly_class'] = ''
    
    cur.close()
    conn.close()
    
    # Render template with data
    html = HTML_TEMPLATE
    html = html.replace('{{ last_update }}', last_update)
    html = html.replace('{{ current_price }}', current_price)
    html = html.replace('{{ r1 }}', r1)
    html = html.replace('{{ r2 }}', r2)
    html = html.replace('{{ r3 }}', r3)
    html = html.replace('{{ s1 }}', s1)
    html = html.replace('{{ s2 }}', s2)
    html = html.replace('{{ s3 }}', s3)
    
    # Replace trends
    for key, value in trends.items():
        html = html.replace('{{ ' + key + ' }}', value)
    
    # Replace trend classes
    for key, value in trend_classes.items():
        html = html.replace('{{ ' + key + ' }}', value)
    
    return html

@app.route('/admin')
def admin():
    """Admin page for trend calculation"""
    return ADMIN_TEMPLATE

@app.route('/admin/calculate-trends', methods=['POST'])
def calculate_trends():
    """Start trend calculation in background"""
    global calculation_running, progress_messages
    
    if calculation_running:
        return jsonify({'status': 'error', 'message': 'Calculation already running'})
    
    # Clear previous messages
    progress_messages = []
    calculation_running = True
    
    # Start calculation in background thread
    thread = threading.Thread(target=run_trend_calculation)
    thread.daemon = True
    thread.start()
    
    return jsonify({'status': 'started'})

@app.route('/admin/progress')
def get_progress():
    """Get calculation progress"""
    global calculation_running, progress_messages
    return jsonify({
        'running': calculation_running,
        'messages': progress_messages
    })

def add_progress(message):
    """Add progress message"""
    global progress_messages
    progress_messages.append(message)
    print(f"[Trend Calc] {message}")

def run_trend_calculation():
    """Run trend calculation for MANKIND"""
    global calculation_running
    
    try:
        add_progress("Connecting to database...")
        conn = get_db_connection()
        cur = conn.cursor()
        
        
        # Initialize trend detector
        add_progress("Initializing SimpleTrendDetector...")
        detector = SimpleTrendDetector(swing_lookback=5, min_swing_percent=0.5)
        
        # Process each timeframe
        timeframes = [
            (5, 'price_data', '5-minute'),
            (15, 'price_data', '15-minute'), 
            (60, 'price_data', '1-hour'),
            ('daily', 'price_data_daily', 'daily'),
            ('weekly', 'price_data_weekly', 'weekly'),
            ('monthly', 'price_data_monthly', 'monthly')
        ]
        
        for timeframe_info in timeframes:
            if len(timeframe_info) == 3:
                interval, table, label = timeframe_info
            else:
                interval = timeframe_info
                table = 'price_data'
                label = f"{interval}-minute"
            
            add_progress(f"Processing {label} timeframe...")
            
            if interval == 'daily':
                # Get real daily data
                query = """
                    SELECT date as datetime, open, high, low, close, volume
                    FROM dhanhq.price_data_daily
                    WHERE security_id = '15380'
                    ORDER BY date DESC
                    LIMIT 100
                """
                cur.execute(query)
                rows = cur.fetchall()
                
            elif interval == 'weekly':
                # Get real weekly data
                query = """
                    SELECT week_start_date as datetime, open, high, low, close, volume
                    FROM dhanhq.price_data_weekly
                    WHERE security_id = '15380'
                    ORDER BY week_start_date DESC
                    LIMIT 100
                """
                cur.execute(query)
                rows = cur.fetchall()
                
            elif interval == 'monthly':
                # Get real monthly data
                query = """
                    SELECT first_date as datetime, open, high, low, close, volume
                    FROM dhanhq.price_data_monthly
                    WHERE security_id = '15380'
                    ORDER BY year DESC, month DESC
                    LIMIT 50
                """
                cur.execute(query)
                rows = cur.fetchall()
            else:
                # Get data for MANKIND
                query = """
                    SELECT datetime, open, high, low, close, volume
                    FROM dhanhq.price_data
                    WHERE security_id = '15380'
                      AND interval_minutes = %s
                    ORDER BY datetime DESC
                    LIMIT 500
                """
                
                cur.execute(query, (interval,))
                rows = cur.fetchall()
            
            if not rows:
                add_progress(f"No data found for {interval}-minute timeframe")
                continue
            
            # Convert to DataFrame
            df = pd.DataFrame(rows, columns=['datetime', 'open', 'high', 'low', 'close', 'volume'])
            df = df.sort_values('datetime')  # Sort chronologically
            
            timeframe_label = "daily" if interval == 'daily' else f"{interval}-minute"
            add_progress(f"Loaded {len(df)} rows for {timeframe_label} timeframe")
            
            # Detect swings and analyze trend
            timeframe_label = "daily" if interval == 'daily' else f"{interval}-minute"
            add_progress(f"Detecting swings for {timeframe_label} data...")
            swings = detector.detect_swings(df)
            add_progress(f"Found {len(swings)} swing points")
            
            if swings:
                # Get trend for latest data
                trend, strength = detector.analyze_swing_pattern(swings)
                add_progress(f"{label} trend: {trend} (strength: {strength})")
                
                if interval == 'daily':
                    # Update daily table
                    add_progress(f"Updating daily trend...")
                    update_query = """
                        UPDATE dhanhq.price_data_daily
                        SET trend = %s,
                            trend_strength = %s
                        WHERE security_id = '15380'
                          AND date >= CURRENT_DATE - INTERVAL '10 days'
                    """
                    cur.execute(update_query, (trend, float(strength)))
                    conn.commit()
                    add_progress(f"Updated {cur.rowcount} daily records")
                    
                elif interval == 'weekly':
                    # Update weekly table
                    add_progress(f"Updating weekly trend...")
                    update_query = """
                        UPDATE dhanhq.price_data_weekly
                        SET trend = %s,
                            trend_strength = %s
                        WHERE security_id = '15380'
                          AND week_start_date >= CURRENT_DATE - INTERVAL '4 weeks'
                    """
                    cur.execute(update_query, (trend, float(strength)))
                    conn.commit()
                    add_progress(f"Updated {cur.rowcount} weekly records")
                    
                elif interval == 'monthly':
                    # Update monthly table
                    add_progress(f"Updating monthly trend...")
                    update_query = """
                        UPDATE dhanhq.price_data_monthly
                        SET trend = %s,
                            trend_strength = %s
                        WHERE security_id = '15380'
                          AND first_date >= CURRENT_DATE - INTERVAL '3 months'
                    """
                    cur.execute(update_query, (trend, float(strength)))
                    conn.commit()
                    add_progress(f"Updated {cur.rowcount} monthly records")
                    
                else:
                    # Update intraday data
                    add_progress(f"Updating database with {label} trend...")
                    update_query = """
                        UPDATE dhanhq.price_data
                        SET simple_trend = %s,
                            simple_trend_strength = %s
                        WHERE security_id = '15380'
                          AND interval_minutes = %s
                          AND datetime >= %s
                    """
                    
                    # Update last 10 bars with current trend
                    last_datetime = df.iloc[-10]['datetime'] if len(df) >= 10 else df.iloc[0]['datetime']
                    cur.execute(update_query, (trend, float(strength), interval, last_datetime))
                    conn.commit()
                    
                    add_progress(f"Updated {cur.rowcount} rows for {label} timeframe")
            else:
                add_progress(f"No swings detected for {label} timeframe")
        
        add_progress("Trend calculation completed successfully!")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        add_progress(f"Error: {str(e)}")
        import traceback
        add_progress(f"Traceback: {traceback.format_exc()}")
    
    finally:
        calculation_running = False

if __name__ == '__main__':
    print("\n" + "="*50)
    print("Minimalistic MANKIND Trading Dashboard")
    print("="*50)
    print(f"\nStarting server on http://localhost:8083")
    print("Open your browser and go to: http://localhost:8083")
    print("\nPress Ctrl+C to stop the server")
    print("="*50 + "\n")
    
    app.run(host='127.0.0.1', port=8083)