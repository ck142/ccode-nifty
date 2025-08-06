#!/usr/bin/env python3
"""
Admin Dashboard - Trend Analysis Module
"""

from flask import Flask, jsonify, request
import psycopg2
import os
from datetime import datetime
import threading
import queue
import logging
from dotenv import load_dotenv
from src.trend_detector import SimpleTrendDetector
import pandas as pd

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Global queue for log messages
log_queue = queue.Queue(maxsize=1000)

# Minimal HTML template
ADMIN_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>Admin - Trend Analysis</title>
    <style>
        body {
            font-family: monospace;
            margin: 20px;
            background: #f0f0f0;
        }
        .container {
            max-width: 1000px;
            margin: 0 auto;
            background: white;
            padding: 20px;
            border-radius: 5px;
        }
        h1 {
            font-size: 20px;
            color: #333;
        }
        button {
            background: #4CAF50;
            color: white;
            padding: 10px 20px;
            border: none;
            border-radius: 3px;
            cursor: pointer;
            font-size: 14px;
        }
        button:hover {
            background: #45a049;
        }
        button:disabled {
            background: #ccc;
            cursor: not-allowed;
        }
        #console {
            background: #000;
            color: #0f0;
            padding: 10px;
            height: 400px;
            overflow-y: auto;
            font-size: 12px;
            margin-top: 20px;
            border-radius: 3px;
        }
        .log-line {
            margin: 2px 0;
        }
        .info { color: #0f0; }
        .warning { color: #ff0; }
        .error { color: #f00; }
        .status {
            margin: 10px 0;
            padding: 10px;
            background: #e0e0e0;
            border-radius: 3px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Admin Dashboard - Trend Analysis</h1>
        
        <div class="status">
            <strong>Status:</strong> <span id="status">Ready</span>
        </div>
        
        <button id="startBtn" onclick="startAnalysis()">Start Trend Analysis</button>
        
        <div id="console"></div>
    </div>
    
    <script>
        let isRunning = false;
        let eventSource = null;
        
        function addLog(message, level = 'info') {
            const console = document.getElementById('console');
            const line = document.createElement('div');
            line.className = 'log-line ' + level;
            line.textContent = new Date().toISOString().substr(11, 8) + ' - ' + message;
            console.appendChild(line);
            console.scrollTop = console.scrollHeight;
        }
        
        function updateStatus(status) {
            document.getElementById('status').textContent = status;
        }
        
        function startAnalysis() {
            if (isRunning) return;
            
            isRunning = true;
            document.getElementById('startBtn').disabled = true;
            updateStatus('Running trend analysis...');
            addLog('Starting trend analysis for MANKIND data', 'info');
            
            // Start SSE connection for logs
            eventSource = new EventSource('/admin/logs');
            eventSource.onmessage = function(event) {
                const data = JSON.parse(event.data);
                addLog(data.message, data.level);
            };
            
            // Start the analysis
            fetch('/admin/start_analysis', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'completed') {
                        addLog('Analysis completed successfully!', 'info');
                        updateStatus('Completed');
                    } else {
                        addLog('Analysis failed: ' + data.message, 'error');
                        updateStatus('Failed');
                    }
                    
                    // Cleanup
                    isRunning = false;
                    document.getElementById('startBtn').disabled = false;
                    if (eventSource) {
                        eventSource.close();
                        eventSource = null;
                    }
                })
                .catch(error => {
                    addLog('Error: ' + error, 'error');
                    updateStatus('Error');
                    isRunning = false;
                    document.getElementById('startBtn').disabled = false;
                    if (eventSource) {
                        eventSource.close();
                        eventSource = null;
                    }
                });
        }
        
        // Add initial log
        addLog('Admin dashboard ready', 'info');
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

def log_message(message, level='info'):
    """Add message to log queue"""
    try:
        log_queue.put_nowait({'message': message, 'level': level})
    except queue.Full:
        pass
    
    # Also log to console
    if level == 'error':
        logger.error(message)
    elif level == 'warning':
        logger.warning(message)
    else:
        logger.info(message)

def calculate_trends_for_interval(interval_minutes):
    """Calculate trends for a specific interval"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Get data for this interval
        log_message(f"Fetching {interval_minutes}m data...")
        cur.execute("""
            SELECT datetime, open, high, low, close, volume
            FROM dhanhq.price_data
            WHERE security_id = '15380' 
              AND interval_minutes = %s
            ORDER BY datetime ASC
        """, (interval_minutes,))
        
        data = cur.fetchall()
        if not data:
            log_message(f"No data found for {interval_minutes}m interval", 'warning')
            return 0
        
        # Convert to DataFrame
        df = pd.DataFrame(data, columns=['datetime', 'open', 'high', 'low', 'close', 'volume'])
        log_message(f"Processing {len(df)} records for {interval_minutes}m interval")
        
        # Initialize detector
        detector = SimpleTrendDetector(
            swing_lookback=5 if interval_minutes <= 15 else 10,
            min_swing_percent=0.5 if interval_minutes <= 15 else 1.0
        )
        
        # Analyze dataframe
        df_with_trend = detector.analyze_dataframe(df)
        
        # Update database
        log_message(f"Updating database with trend data...")
        updated = 0
        
        for idx, row in df_with_trend.iterrows():
            if pd.notna(row['simple_trend']):
                cur.execute("""
                    UPDATE dhanhq.price_data
                    SET simple_trend = %s,
                        simple_trend_strength = %s,
                        trend_updated_at = CURRENT_TIMESTAMP
                    WHERE security_id = '15380'
                      AND interval_minutes = %s
                      AND datetime = %s
                """, (
                    row['simple_trend'],
                    row['simple_trend_strength'],
                    interval_minutes,
                    row['datetime']
                ))
                updated += cur.rowcount
        
        conn.commit()
        log_message(f"Updated {updated} records for {interval_minutes}m interval")
        return updated
        
    except Exception as e:
        conn.rollback()
        log_message(f"Error processing {interval_minutes}m: {str(e)}", 'error')
        return 0
    finally:
        cur.close()
        conn.close()

def run_trend_analysis():
    """Run trend analysis for all timeframes"""
    log_message("="*50)
    log_message("Starting trend analysis for MANKIND")
    log_message("="*50)
    
    timeframes = [1, 5, 15, 60]
    total_updated = 0
    
    for interval in timeframes:
        log_message(f"\nProcessing {interval}-minute timeframe...")
        updated = calculate_trends_for_interval(interval)
        total_updated += updated
    
    log_message("="*50)
    log_message(f"Trend analysis completed! Total records updated: {total_updated}")
    log_message("="*50)
    
    return total_updated

@app.route('/admin')
def admin_page():
    """Admin dashboard page"""
    return ADMIN_HTML

@app.route('/admin/start_analysis', methods=['POST'])
def start_analysis():
    """Start trend analysis in background thread"""
    def run_analysis():
        try:
            total = run_trend_analysis()
            log_message(f"Analysis completed. {total} records updated.", 'info')
        except Exception as e:
            log_message(f"Analysis failed: {str(e)}", 'error')
    
    # Run in background thread
    thread = threading.Thread(target=run_analysis)
    thread.daemon = True
    thread.start()
    
    return jsonify({'status': 'started'})

@app.route('/admin/logs')
def stream_logs():
    """Stream log messages via Server-Sent Events"""
    def generate():
        while True:
            try:
                # Get log message with timeout
                log = log_queue.get(timeout=30)
                yield f"data: {jsonify(log).get_data(as_text=True)}\n\n"
            except queue.Empty:
                # Send keepalive
                yield f"data: {jsonify({'message': '', 'level': 'keepalive'}).get_data(as_text=True)}\n\n"
    
    return app.response_class(generate(), mimetype='text/event-stream')

if __name__ == '__main__':
    print("\n" + "="*50)
    print("Admin Dashboard - Trend Analysis")
    print("="*50)
    print(f"\nStarting server on http://localhost:8084/admin")
    print("Open your browser and go to: http://localhost:8084/admin")
    print("\nPress Ctrl+C to stop the server")
    print("="*50 + "\n")
    
    app.run(host='127.0.0.1', port=8084, threaded=True)