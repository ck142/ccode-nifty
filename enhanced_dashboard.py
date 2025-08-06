#!/usr/bin/env python3
"""
Enhanced MANKIND Trading Dashboard with Daily Updates and Recommendations
"""

from flask import Flask, jsonify, request, render_template_string
import psycopg2
import os
from datetime import datetime, timedelta
import pytz
from dotenv import load_dotenv
import threading
import json
import pandas as pd
from src.trend_detector import SimpleTrendDetector
from src.daily_data_updater_v2 import DailyDataUpdaterV2 as DailyDataUpdater
from src.recommendation_generator import RecommendationGenerator
from src.simple_sr_detector import SimpleSRDetector
from src.sr_database_updater import SRDatabaseUpdater
# from src.gpt_validator import AdamGrimesValidator  # Commented out - OpenAI not installed

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Store progress messages
progress_messages = []
calculation_running = False
update_running = False
recommendation_generating = False

# Database configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', 5432),
    'database': os.getenv('DB_NAME', 'trading_db'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD')
}

def get_db_connection():
    """Create database connection"""
    return psycopg2.connect(**DB_CONFIG)

# Main Dashboard HTML
DASHBOARD_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>MANKIND Trading Dashboard</title>
    <style>
        body {
            font-family: 'Courier New', monospace;
            margin: 0;
            padding: 20px;
            background: #ffffff;
            color: #000000;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        h1 {
            color: #000000;
            border-bottom: 2px solid #000000;
            padding-bottom: 10px;
        }
        .nav {
            margin: 20px 0;
            padding: 10px;
            background: #f5f5f5;
            border-radius: 5px;
            border: 1px solid #000000;
        }
        .nav a {
            color: #000000;
            text-decoration: none;
            margin-right: 20px;
            padding: 5px 10px;
            border: 1px solid #000000;
            border-radius: 3px;
        }
        .nav a:hover {
            background: #000000;
            color: #ffffff;
        }
        .chart-container {
            background: #ffffff;
            border-radius: 5px;
            padding: 20px;
            margin: 20px 0;
            height: 600px;
            border: 1px solid #000000;
        }
        .info-panel {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }
        .info-card {
            background: #ffffff;
            padding: 15px;
            border-radius: 5px;
            border: 1px solid #000000;
        }
        .info-card h3 {
            margin-top: 0;
            color: #000000;
        }
        .trend-up { color: #00c851; font-weight: bold; }
        .trend-up::after { content: ' ↑'; }
        .trend-down { color: #ff4444; font-weight: bold; }
        .trend-down::after { content: ' ↓'; }
        .trend-neutral { color: #999999; font-weight: bold; }
        .price-value { color: #0066cc; font-size: 24px; font-weight: bold; }
        .price-change-positive { color: #00c851; font-weight: bold; }
        .price-change-negative { color: #ff4444; font-weight: bold; }
        .button {
            background: #000000;
            color: #ffffff;
            padding: 10px 20px;
            border: 1px solid #000000;
            cursor: pointer;
            font-weight: bold;
            border-radius: 3px;
            margin: 5px;
        }
        .button:hover {
            background: #333333;
        }
        .button:disabled {
            background: #cccccc;
            color: #999999;
            cursor: not-allowed;
            border: 1px solid #cccccc;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>MANKIND PHARMA Trading Dashboard</h1>
        
        <div class="nav">
            <a href="/">Dashboard</a>
            <a href="/admin">Admin Panel</a>
            <a href="/recommendations">Recommendations</a>
            <a href="/api/latest-data">API Data</a>
        </div>
        
        <div class="info-panel">
            <div class="info-card">
                <h3>Current Price <span id="price-timestamp" style="font-size: 16px; font-weight: normal; color: #333;"></span></h3>
                <div id="current-price">Loading...</div>
            </div>
            <div class="info-card">
                <h3>Trends</h3>
                <div id="trends">Loading...</div>
            </div>
            <div class="info-card">
                <h3>S/R</h3>
                <div id="sr-levels">Loading...</div>
            </div>
        </div>
        
        <div class="info-panel" style="margin-top: 20px;">
            <div class="info-card" style="width: 100%;">
                <h3>Trade Recommendations</h3>
                <div id="recommendations" style="font-size: 16px; line-height: 1.6;">Loading...</div>
            </div>
        </div>
    </div>
    
    <script>
        function loadDashboardData() {
            fetch('/api/dashboard-data')
                .then(response => response.json())
                .then(data => {
                    // Update current price with color coding
                    const changeClass = data.price_change > 0 ? 'price-change-positive' : 'price-change-negative';
                    const changeSymbol = data.price_change > 0 ? '+' : '';
                    const priceColor = data.price_change > 0 ? '#00c851' : data.price_change < 0 ? '#ff4444' : '#0066cc';
                    
                    // Format timestamp (data is in EST/EDT -4, convert to IST +5:30)
                    const updateTime = new Date(data.last_update);
                    // Add 9.5 hours to convert from EST to IST
                    const istTime = new Date(updateTime.getTime() + (9.5 * 60 * 60 * 1000));
                    const date = istTime.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
                    const hours = istTime.getHours();
                    const minutes = istTime.getMinutes().toString().padStart(2, '0');
                    const displayHour = hours > 12 ? hours - 12 : (hours === 0 ? 12 : hours);
                    const timeStr = `${displayHour}:${minutes} ${hours >= 12 ? 'PM' : 'AM'} IST`;
                    
                    // Update timestamp in header
                    document.getElementById('price-timestamp').innerHTML = `(${date} ${timeStr})`;
                    
                    // Find next support and resistance relative to current price
                    let nextResistance = null;
                    let nextSupport = null;
                    
                    // Always show the first (closest) support and resistance levels
                    // Support S1 is the immediate support level
                    if (data.support && data.support.length > 0 && data.support[0]) {
                        nextSupport = data.support[0];
                    }
                    
                    // Resistance R1 is the immediate resistance level
                    if (data.resistance && data.resistance.length > 0 && data.resistance[0]) {
                        nextResistance = data.resistance[0];
                    }
                    
                    document.getElementById('current-price').innerHTML = 
                        `<span style="font-size: 14px; color: #666;">
                            ${nextResistance ? `R: ₹${Math.round(nextResistance)}` : 'No resistance above'}
                         </span><br>
                         <span class="price-value" style="color: ${priceColor}">₹${data.current_price.toFixed(2)}</span><br>
                         <span style="font-size: 14px; color: #666;">
                            ${nextSupport ? `S: ₹${Math.round(nextSupport)}` : 'No support below'}
                         </span><br>
                         <span style="color: #000000;">vs Prev Close (${data.previous_date}):</span> 
                         <span class="${changeClass}">${changeSymbol}${data.price_change.toFixed(2)} 
                         (${changeSymbol}${data.price_change_pct.toFixed(2)}%)</span>`;
                    
                    // Update trends with arrows
                    let trendsHtml = '';
                    for (const [timeframe, trend] of Object.entries(data.trends)) {
                        const trendClass = trend === 'UPTREND' ? 'trend-up' : 
                                          trend === 'DOWNTREND' ? 'trend-down' : 'trend-neutral';
                        trendsHtml += `<div>${timeframe}: <span class="${trendClass}">${trend}</span></div>`;
                    }
                    document.getElementById('trends').innerHTML = trendsHtml;
                    
                    // Update S/R levels with horizontal layout
                    let srHtml = '<div style="display: flex; justify-content: space-between; font-size: 16px;">';
                    
                    // Resistance column
                    srHtml += '<div style="flex: 1; padding-right: 10px;">';
                    srHtml += '<strong style="font-size: 18px;">R:</strong><br>';
                    if (data.resistance && data.resistance.length > 0) {
                        data.resistance.forEach((r, i) => {
                            if (r) srHtml += `<span style="font-size: 18px;">R${i+1}: ₹${Math.round(r)}</span><br>`;
                        });
                    } else {
                        srHtml += '<span style="font-size: 18px;">Calculating...</span>';
                    }
                    srHtml += '</div>';
                    
                    // Support column
                    srHtml += '<div style="flex: 1; padding-left: 10px; border-left: 1px solid #ccc;">';
                    srHtml += '<strong style="font-size: 18px;">S:</strong><br>';
                    if (data.support && data.support.length > 0) {
                        data.support.forEach((s, i) => {
                            if (s) srHtml += `<span style="font-size: 18px;">S${i+1}: ₹${Math.round(s)}</span><br>`;
                        });
                    } else {
                        srHtml += '<span style="font-size: 18px;">Calculating...</span>';
                    }
                    srHtml += '</div>';
                    srHtml += '</div>';
                    
                    document.getElementById('sr-levels').innerHTML = srHtml;
                    
                    // Generate trade recommendations based on trends
                    generateRecommendations(data);
                });
        }
        
        function generateRecommendations(data) {
            let recommendation = '';
            const dailyTrend = data.trends['Daily'];
            const hourlyTrend = data.trends['60-min'];
            const fifteenMinTrend = data.trends['15-min'];
            const currentPrice = data.current_price;
            const changePercent = data.price_change_pct;
            
            // Determine overall market sentiment
            if (dailyTrend === 'DOWNTREND' && hourlyTrend === 'DOWNTREND') {
                recommendation = '<strong style="color: #ff4444;">⚠️ BEARISH SIGNAL</strong><br>';
                recommendation += 'Market showing weakness across multiple timeframes.<br>';
                recommendation += '<br><strong>Recommendation:</strong><br>';
                recommendation += '• Avoid fresh long positions<br>';
                recommendation += '• Consider booking profits in existing longs<br>';
                recommendation += `• Wait for support at ₹${data.support[0] ? data.support[0].toFixed(2) : 'N/A'}<br>`;
                recommendation += '• Short-term traders may consider short positions with strict stop-loss<br>';
            } else if (dailyTrend === 'UPTREND' && hourlyTrend === 'UPTREND') {
                recommendation = '<strong style="color: #00c851;">✓ BULLISH SIGNAL</strong><br>';
                recommendation += 'Market showing strength across multiple timeframes.<br>';
                recommendation += '<br><strong>Recommendation:</strong><br>';
                recommendation += '• Good opportunity for fresh long positions<br>';
                recommendation += '• Hold existing positions<br>';
                recommendation += `• Target resistance at ₹${data.resistance[0] ? data.resistance[0].toFixed(2) : 'N/A'}<br>`;
                recommendation += `• Place stop-loss below ₹${data.support[0] ? data.support[0].toFixed(2) : 'N/A'}<br>`;
            } else if (dailyTrend === 'SIDEWAYS' || (dailyTrend !== hourlyTrend)) {
                recommendation = '<strong style="color: #ff9800;">⚡ NEUTRAL/MIXED SIGNAL</strong><br>';
                recommendation += 'Market showing mixed signals across timeframes.<br>';
                recommendation += '<br><strong>Recommendation:</strong><br>';
                recommendation += '• Wait for clear directional move<br>';
                recommendation += '• Trade within range with smaller positions<br>';
                recommendation += `• Buy near support ₹${data.support[0] ? data.support[0].toFixed(2) : 'N/A'}<br>`;
                recommendation += `• Sell near resistance ₹${data.resistance[0] ? data.resistance[0].toFixed(2) : 'N/A'}<br>`;
            }
            
            // Add risk management note
            recommendation += '<br><small style="color: #666;"><em>Note: Always use proper risk management. Never risk more than 2% per trade.</em></small>';
            
            document.getElementById('recommendations').innerHTML = recommendation;
        }
        
        function refreshData() {
            loadDashboardData();
        }
        
        // Load data on page load
        loadDashboardData();
        
        // Auto-refresh every 30 seconds
        setInterval(loadDashboardData, 30000);
    </script>
</body>
</html>
'''

# Admin Panel HTML
ADMIN_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Admin Panel - Data Management</title>
    <style>
        body {
            font-family: 'Courier New', monospace;
            margin: 0;
            padding: 20px;
            background: #ffffff;
            color: #000000;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        h1 {
            color: #000000;
            border-bottom: 2px solid #000000;
            padding-bottom: 10px;
        }
        .nav {
            margin: 20px 0;
            padding: 10px;
            background: #f5f5f5;
            border-radius: 5px;
            border: 1px solid #000000;
        }
        .nav a {
            color: #000000;
            text-decoration: none;
            margin-right: 20px;
            padding: 5px 10px;
            border: 1px solid #000000;
            border-radius: 3px;
        }
        .nav a:hover {
            background: #000000;
            color: #ffffff;
        }
        .action-panel {
            background: #f5f5f5;
            padding: 20px;
            border-radius: 5px;
            margin: 20px 0;
            border: 1px solid #000000;
        }
        .button {
            background: #000000;
            color: #ffffff;
            padding: 10px 20px;
            border: 1px solid #000000;
            cursor: pointer;
            font-weight: bold;
            border-radius: 3px;
            margin: 5px;
        }
        .button:hover {
            background: #333333;
        }
        .button:disabled {
            background: #cccccc;
            color: #999999;
            cursor: not-allowed;
            border: 1px solid #cccccc;
        }
        .console-container {
            position: relative;
            margin-top: 20px;
        }
        .console {
            background: #ffffff;
            color: #000000;
            padding: 15px;
            border-radius: 5px;
            height: 400px;
            overflow-y: auto;
            font-family: monospace;
            font-size: 12px;
            border: 2px solid #000000;
        }
        .copy-button {
            position: absolute;
            top: 10px;
            right: 10px;
            background: #000000;
            color: #ffffff;
            padding: 5px 10px;
            border: none;
            border-radius: 3px;
            cursor: pointer;
            font-size: 12px;
            z-index: 10;
        }
        .copy-button:hover {
            background: #333333;
        }
        .copy-success {
            background: #4CAF50 !important;
        }
        .console-line {
            margin: 2px 0;
        }
        .error { color: #666666; font-weight: bold; }
        .warning { color: #999999; font-weight: bold; }
        .success { color: #000000; font-weight: bold; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Admin Panel - Data Management</h1>
        
        <div class="nav">
            <a href="/">Dashboard</a>
            <a href="/admin">Admin Panel</a>
            <a href="/recommendations">Recommendations</a>
        </div>
        
        <div class="action-panel">
            <h2>Data Updates</h2>
            <button id="update-btn" class="button" onclick="startDailyUpdate()">
                Download Latest Data
            </button>
            <button id="intraday-btn" class="button" onclick="loadIntradayData()">
                Load 1-Min Intraday Data
            </button>
            <button id="trend-btn" class="button" onclick="calculateTrends()">
                Calculate Trends
            </button>
            <button id="sr-full-btn" class="button" onclick="calculateSRFull()">
                Refresh All S/R Levels
            </button>
            <button id="sr-update-btn" class="button" onclick="updateSRLatest()">
                Update S/R (Latest)
            </button>
            <button class="button" onclick="clearConsole()">
                Clear Console
            </button>
            
            <div class="console-container">
                <button class="copy-button" id="copyBtn" onclick="copyConsole()">Copy</button>
                <div class="console" id="console">
                    <div class="console-line">Admin console ready...</div>
                </div>
            </div>
        </div>
        
        <div class="action-panel">
            <h2>Database Status</h2>
            <div id="db-status">Loading...</div>
        </div>
    </div>
    
    <script>
        let updateInterval = null;
        let trendInterval = null;
        
        function startDailyUpdate() {
            document.getElementById('update-btn').disabled = true;
            addConsoleMessage('Starting daily data update...', 'info');
            
            fetch('/api/daily-update', {method: 'POST'})
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'started') {
                        addConsoleMessage('Update process started', 'success');
                        pollUpdateProgress();
                    }
                });
        }
        
        function loadIntradayData() {
            document.getElementById('intraday-btn').disabled = true;
            addConsoleMessage('Starting 1-minute intraday data update...', 'info');
            
            fetch('/api/intraday-update', {method: 'POST'})
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'started') {
                        addConsoleMessage('Intraday update process started', 'success');
                        pollIntradayProgress();
                    }
                });
        }
        
        function pollUpdateProgress() {
            updateInterval = setInterval(() => {
                fetch('/api/update-progress')
                    .then(response => response.json())
                    .then(data => {
                        data.messages.forEach(msg => {
                            addConsoleMessage(msg.message, msg.level);
                        });
                        
                        if (data.completed) {
                            clearInterval(updateInterval);
                            document.getElementById('update-btn').disabled = false;
                            addConsoleMessage('Update completed!', 'success');
                            loadDatabaseStatus();
                        }
                    });
            }, 1000);
        }
        
        function calculateTrends() {
            document.getElementById('trend-btn').disabled = true;
            clearConsole();
            addConsoleMessage('Starting trend calculation for missing data...', 'info');
            
            fetch('/api/calculate-trends', {method: 'POST'})
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'started') {
                        addConsoleMessage('Trend calculation started', 'success');
                        pollTrendProgress();
                    } else if (data.status === 'already_running') {
                        addConsoleMessage('Trend calculation already in progress', 'warning');
                    }
                });
        }
        
        function pollTrendProgress() {
            trendInterval = setInterval(() => {
                fetch('/api/trend-progress')
                    .then(response => response.json())
                    .then(data => {
                        data.messages.forEach(msg => {
                            // Fix: Extract message from object
                            const message = typeof msg === 'object' ? msg.message : msg;
                            const level = typeof msg === 'object' ? msg.level : 'info';
                            addConsoleMessage(message, level);
                        });
                        
                        if (data.completed) {
                            clearInterval(trendInterval);
                            document.getElementById('trend-btn').disabled = false;
                            addConsoleMessage('Trend calculation completed!', 'success');
                            loadDatabaseStatus();
                        }
                    });
            }, 1000);
        }
        
        function pollIntradayProgress() {
            updateInterval = setInterval(() => {
                fetch('/api/intraday-progress')
                    .then(response => response.json())
                    .then(data => {
                        data.messages.forEach(msg => {
                            addConsoleMessage(msg.message, msg.level);
                        });
                        
                        if (data.completed) {
                            clearInterval(updateInterval);
                            document.getElementById('intraday-btn').disabled = false;
                            addConsoleMessage('Intraday data update completed!', 'success');
                            loadDatabaseStatus();
                        }
                    });
            }, 1000);
        }
        
        function calculateTrends() {
            document.getElementById('trend-btn').disabled = true;
            addConsoleMessage('Starting trend calculation...', 'info');
            
            fetch('/api/calculate-trends', {method: 'POST'})
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'started') {
                        addConsoleMessage('Trend calculation started', 'success');
                        pollTrendProgress();
                    }
                });
        }
        
        function pollTrendProgress() {
            trendInterval = setInterval(() => {
                fetch('/api/trend-progress')
                    .then(response => response.json())
                    .then(data => {
                        data.messages.forEach(msg => {
                            addConsoleMessage(msg, 'info');
                        });
                        
                        if (!data.running) {
                            clearInterval(trendInterval);
                            document.getElementById('trend-btn').disabled = false;
                            addConsoleMessage('Trend calculation completed!', 'success');
                        }
                    });
            }, 1000);
        }
        
        function addConsoleMessage(message, level = 'info') {
            const console = document.getElementById('console');
            const line = document.createElement('div');
            line.className = 'console-line ' + level;
            const timestamp = new Date().toLocaleTimeString();
            line.textContent = `[${timestamp}] ${message}`;
            console.appendChild(line);
            console.scrollTop = console.scrollHeight;
        }
        
        function clearConsole() {
            document.getElementById('console').innerHTML = 
                '<div class="console-line success">Console cleared</div>';
        }
        
        function copyConsole() {
            const consoleElement = document.getElementById('console');
            const text = consoleElement.innerText;
            
            navigator.clipboard.writeText(text).then(function() {
                // Show success feedback
                const copyBtn = document.getElementById('copyBtn');
                const originalText = copyBtn.innerText;
                copyBtn.innerText = 'Copied!';
                copyBtn.classList.add('copy-success');
                
                // Reset after 2 seconds
                setTimeout(function() {
                    copyBtn.innerText = originalText;
                    copyBtn.classList.remove('copy-success');
                }, 2000);
            }).catch(function(err) {
                console.error('Failed to copy: ', err);
                alert('Failed to copy console content');
            });
        }
        
        function loadDatabaseStatus() {
            fetch('/api/database-status')
                .then(response => response.json())
                .then(data => {
                    let statusHtml = '<table style="width:100%; color:#000000; border-collapse: collapse;">';
                    statusHtml += '<tr style="border-bottom: 1px solid #000000;"><th style="padding: 8px; text-align: left;">Timeframe</th><th style="padding: 8px; text-align: left;">Records</th><th style="padding: 8px; text-align: left;">Latest Data</th><th style="padding: 8px; text-align: left;">Coverage</th></tr>';
                    
                    for (const [timeframe, info] of Object.entries(data)) {
                        statusHtml += `<tr style="border-bottom: 1px solid #e0e0e0;">
                            <td style="padding: 8px;">${timeframe}</td>
                            <td style="padding: 8px;">${info.count}</td>
                            <td style="padding: 8px;">${info.latest ? new Date(info.latest).toLocaleString() : 'N/A'}</td>
                            <td style="padding: 8px;">${info.coverage}%</td>
                        </tr>`;
                    }
                    
                    statusHtml += '</table>';
                    document.getElementById('db-status').innerHTML = statusHtml;
                });
        }
        
        function calculateSRFull() {
            addConsoleMessage('Starting full S/R level refresh...');
            fetch('/api/calculate-sr-full', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'success') {
                        addConsoleMessage(`SUCCESS: ${data.message}`, 'success');
                    } else {
                        addConsoleMessage(`ERROR: ${data.message}`, 'error');
                    }
                })
                .catch(error => {
                    addConsoleMessage(`ERROR: ${error}`, 'error');
                });
        }
        
        function updateSRLatest() {
            addConsoleMessage('Updating S/R levels with latest data...');
            fetch('/api/calculate-sr-latest', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'success') {
                        addConsoleMessage(`SUCCESS: ${data.message}`, 'success');
                    } else {
                        addConsoleMessage(`ERROR: ${data.message}`, 'error');
                    }
                })
                .catch(error => {
                    addConsoleMessage(`ERROR: ${error}`, 'error');
                });
        }
        
        // Load initial status
        loadDatabaseStatus();
    </script>
</body>
</html>
'''

# Recommendations Page HTML
RECOMMENDATIONS_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Trading Recommendations</title>
    <style>
        body {
            font-family: 'Courier New', monospace;
            margin: 0;
            padding: 20px;
            background: #ffffff;
            color: #000000;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        h1 {
            color: #000000;
            border-bottom: 2px solid #000000;
            padding-bottom: 10px;
        }
        .nav {
            margin: 20px 0;
            padding: 10px;
            background: #f5f5f5;
            border-radius: 5px;
            border: 1px solid #000000;
        }
        .nav a {
            color: #000000;
            text-decoration: none;
            margin-right: 20px;
            padding: 5px 10px;
            border: 1px solid #000000;
            border-radius: 3px;
        }
        .nav a:hover {
            background: #000000;
            color: #ffffff;
        }
        .button {
            background: #000000;
            color: #ffffff;
            padding: 10px 20px;
            border: 1px solid #000000;
            cursor: pointer;
            font-weight: bold;
            border-radius: 3px;
            margin: 5px;
        }
        .button:hover {
            background: #333333;
        }
        .button:disabled {
            background: #cccccc;
            color: #999999;
            cursor: not-allowed;
            border: 1px solid #cccccc;
        }
        .recommendation-panel {
            background: #f5f5f5;
            padding: 20px;
            border-radius: 5px;
            margin: 20px 0;
            border: 1px solid #000000;
        }
        .recommendation-text {
            background: #ffffff;
            color: #000000;
            padding: 15px;
            border-radius: 5px;
            margin: 10px 0;
            white-space: pre-wrap;
            font-size: 14px;
            border: 1px solid #000000;
        }
        .validation-panel {
            background: #f5f5f5;
            padding: 20px;
            border-radius: 5px;
            margin: 20px 0;
            border: 2px solid #000000;
        }
        .validation-score {
            font-size: 24px;
            font-weight: bold;
            margin: 10px 0;
        }
        .score-high { color: #000000; }
        .score-medium { color: #666666; }
        .score-low { color: #999999; }
        .loading {
            color: #666666;
            animation: blink 1s infinite;
        }
        @keyframes blink {
            0% { opacity: 1; }
            50% { opacity: 0.3; }
            100% { opacity: 1; }
        }
        .trade-setup {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin: 20px 0;
        }
        .setup-card {
            background: #ffffff;
            padding: 15px;
            border-radius: 5px;
            border: 1px solid #000000;
        }
        .buy { border-left: 3px solid #000000; }
        .sell { border-left: 3px solid #666666; }
        .hold { border-left: 3px solid #999999; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Trading Recommendations</h1>
        
        <div class="nav">
            <a href="/">Dashboard</a>
            <a href="/admin">Admin Panel</a>
            <a href="/recommendations">Recommendations</a>
        </div>
        
        <div class="recommendation-panel">
            <h2>Generate New Recommendation</h2>
            <button id="gen-btn" class="button" onclick="generateRecommendation()">
                Generate Recommendation
            </button>
            <button id="validate-btn" class="button" onclick="validateRecommendation()" disabled>
                Get Adam Grimes Perspective
            </button>
            
            <div id="status" style="margin-top: 10px;"></div>
        </div>
        
        <div id="recommendation-content"></div>
        <div id="validation-content"></div>
        
        <div class="recommendation-panel">
            <h2>Previous Recommendations</h2>
            <div id="history">Loading...</div>
        </div>
    </div>
    
    <script>
        let currentRecommendationId = null;
        
        function generateRecommendation() {
            console.log('Generate recommendation clicked');
            document.getElementById('gen-btn').disabled = true;
            document.getElementById('status').innerHTML = '<span class="loading">Generating recommendation...</span>';
            document.getElementById('recommendation-content').innerHTML = '';
            document.getElementById('validation-content').innerHTML = '';
            
            fetch('/api/generate-recommendation', {method: 'POST'})
                .then(response => {
                    console.log('Response received:', response);
                    return response.json();
                })
                .then(data => {
                    console.log('Data received:', data);
                    document.getElementById('gen-btn').disabled = false;
                    document.getElementById('status').innerHTML = '';
                    
                    if (data.success) {
                        currentRecommendationId = data.recommendation_id;
                        displayRecommendation(data.recommendation);
                        document.getElementById('validate-btn').disabled = false;
                        loadHistory();
                    } else {
                        document.getElementById('status').innerHTML = 
                            '<span style="color:#ff0000;">Error: ' + data.error + '</span>';
                    }
                })
                .catch(error => {
                    document.getElementById('gen-btn').disabled = false;
                    document.getElementById('status').innerHTML = 
                        '<span style="color:#ff0000;">Error: ' + error + '</span>';
                    console.error('Error generating recommendation:', error);
                });
        }
        
        function validateRecommendation() {
            if (!currentRecommendationId) return;
            
            document.getElementById('validate-btn').disabled = true;
            document.getElementById('validation-content').innerHTML = 
                '<div class="validation-panel"><span class="loading">Getting Adam Grimes perspective...</span></div>';
            
            fetch('/api/validate-recommendation', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({recommendation_id: currentRecommendationId})
            })
                .then(response => response.json())
                .then(data => {
                    document.getElementById('validate-btn').disabled = false;
                    
                    if (data.success) {
                        displayValidation(data.validation);
                    } else {
                        document.getElementById('validation-content').innerHTML = 
                            '<div class="validation-panel"><span style="color:#ff0000;">Error: ' + data.error + '</span></div>';
                    }
                });
        }
        
        function displayRecommendation(rec) {
            let html = '<div class="recommendation-panel">';
            html += '<h2>Current Recommendation</h2>';
            html += '<p>Generated: ' + new Date(rec.generated_at).toLocaleString() + '</p>';
            html += '<p>Current Price: ₹' + rec.current_price.toFixed(2) + '</p>';
            
            // Trade setup
            html += '<div class="trade-setup">';
            html += '<div class="setup-card ' + rec.action.toLowerCase() + '">';
            html += '<h3>Trading Signal: ' + rec.action + '</h3>';
            html += '<p>Entry Price: ₹' + rec.entry_price.toFixed(2) + '</p>';
            html += '<p>Stop Loss: ₹' + rec.stop_loss.toFixed(2) + '</p>';
            html += '<p>Target 1: ₹' + rec.target_1.toFixed(2) + '</p>';
            html += '<p>Target 2: ₹' + rec.target_2.toFixed(2) + '</p>';
            html += '<p>Confidence: ' + rec.confidence + '%</p>';
            html += '</div>';
            
            // Show trend alignment
            html += '<div class="trend-alignment">';
            html += '<h4>Trend Analysis:</h4>';
            if (rec.trend_1min) html += '<p>1-min: ' + rec.trend_1min + '</p>';
            if (rec.trend_5min) html += '<p>5-min: ' + rec.trend_5min + '</p>';
            if (rec.trend_15min) html += '<p>15-min: ' + rec.trend_15min + '</p>';
            if (rec.trend_60min) html += '<p>60-min: ' + rec.trend_60min + '</p>';
            if (rec.trend_daily) html += '<p>Daily: ' + rec.trend_daily + '</p>';
            html += '</div>';
            html += '</div>';
            
            // Full recommendation text
            html += '<h3>Full Analysis</h3>';
            html += '<div class="recommendation-text">' + rec.recommendation_text + '</div>';
            
            html += '</div>';
            
            document.getElementById('recommendation-content').innerHTML = html;
        }
        
        function displayValidation(val) {
            let scoreClass = val.score >= 7 ? 'score-high' : 
                           val.score >= 5 ? 'score-medium' : 'score-low';
            
            let html = '<div class="validation-panel">';
            html += '<h2>Adam Grimes Perspective</h2>';
            html += '<div class="validation-score ' + scoreClass + '">Score: ' + val.score + '/10</div>';
            html += '<h3>Analysis</h3>';
            html += '<div class="recommendation-text">' + val.full_validation + '</div>';
            html += '</div>';
            
            document.getElementById('validation-content').innerHTML = html;
        }
        
        function loadHistory() {
            fetch('/api/recommendation-history')
                .then(response => response.json())
                .then(data => {
                    if (data.length === 0) {
                        document.getElementById('history').innerHTML = '<p>No recommendations yet</p>';
                        return;
                    }
                    
                    let html = '<table style="width:100%; border-collapse: collapse;">';
                    html += '<thead style="background: #f0f0f0;">';
                    html += '<tr>';
                    html += '<th style="padding: 10px; border: 1px solid #ddd;">Date/Time</th>';
                    html += '<th style="padding: 10px; border: 1px solid #ddd;">Action</th>';
                    html += '<th style="padding: 10px; border: 1px solid #ddd;">Entry Price</th>';
                    html += '<th style="padding: 10px; border: 1px solid #ddd;">Stop Loss</th>';
                    html += '<th style="padding: 10px; border: 1px solid #ddd;">Target 1</th>';
                    html += '<th style="padding: 10px; border: 1px solid #ddd;">Target 2</th>';
                    html += '<th style="padding: 10px; border: 1px solid #ddd;">Confidence</th>';
                    html += '<th style="padding: 10px; border: 1px solid #ddd;">Analysis</th>';
                    html += '</tr>';
                    html += '</thead>';
                    html += '<tbody>';
                    
                    data.forEach(rec => {
                        const actionClass = rec.intraday_action === 'BUY' ? 'color: green;' : 
                                          rec.intraday_action === 'SELL' ? 'color: red;' : '';
                        
                        html += '<tr>';
                        html += '<td style="padding: 8px; border: 1px solid #ddd;">' + 
                                new Date(rec.generated_at).toLocaleString() + '</td>';
                        html += '<td style="padding: 8px; border: 1px solid #ddd; font-weight: bold; ' + actionClass + '">' + 
                                rec.intraday_action + '</td>';
                        html += '<td style="padding: 8px; border: 1px solid #ddd;">₹' + 
                                (rec.intraday_entry ? rec.intraday_entry.toFixed(2) : 'N/A') + '</td>';
                        html += '<td style="padding: 8px; border: 1px solid #ddd;">₹' + 
                                (rec.intraday_stoploss ? rec.intraday_stoploss.toFixed(2) : 'N/A') + '</td>';
                        html += '<td style="padding: 8px; border: 1px solid #ddd;">₹' + 
                                (rec.intraday_target1 ? rec.intraday_target1.toFixed(2) : 'N/A') + '</td>';
                        html += '<td style="padding: 8px; border: 1px solid #ddd;">₹' + 
                                (rec.intraday_target2 ? rec.intraday_target2.toFixed(2) : 'N/A') + '</td>';
                        html += '<td style="padding: 8px; border: 1px solid #ddd;">' + 
                                (rec.confidence_score ? rec.confidence_score + '%' : '-') + '</td>';
                        html += '<td style="padding: 8px; border: 1px solid #ddd; max-width: 300px; overflow: hidden; text-overflow: ellipsis;" title="' + 
                                (rec.recommendation_text || '').replace(/"/g, '&quot;') + '">' + 
                                (rec.recommendation_text ? rec.recommendation_text.substring(0, 100) + '...' : 'N/A') + '</td>';
                        html += '</tr>';
                    });
                    
                    html += '</tbody>';
                    html += '</table>';
                    document.getElementById('history').innerHTML = html;
                });
        }
        
        // Load history on page load
        loadHistory();
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    """Main dashboard"""
    return render_template_string(DASHBOARD_TEMPLATE)

@app.route('/admin')
def admin():
    """Admin panel"""
    return render_template_string(ADMIN_TEMPLATE)

@app.route('/recommendations')
def recommendations():
    """Recommendations page"""
    return render_template_string(RECOMMENDATIONS_TEMPLATE)

@app.route('/api/dashboard-data')
def get_dashboard_data():
    """Get dashboard data"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Get latest price from 1-minute data (most current)
        cur.execute("""
            SELECT datetime, close
            FROM dhanhq.price_data
            WHERE security_id = '15380' AND interval_minutes = 1
            ORDER BY datetime DESC LIMIT 1
        """)
        
        latest_row = cur.fetchone()
        
        # Get previous trading session's close (excluding today)
        cur.execute("""
            SELECT date, close
            FROM dhanhq.price_data_daily
            WHERE security_id = '15380'
            AND date < CURRENT_DATE
            ORDER BY date DESC LIMIT 1
        """)
        
        previous_session = cur.fetchone()
        
        if latest_row and previous_session:
            current_price = float(latest_row[1])
            previous_close = float(previous_session[1])
            price_change = current_price - previous_close
            price_change_pct = (price_change / previous_close) * 100
            last_update_time = latest_row[0]
            previous_date = previous_session[0]
            
            # Get trends
            trends = {}
            timeframes = [(1, '1-min'), (5, '5-min'), (15, '15-min'), (60, '60-min')]
            
            for interval, name in timeframes:
                cur.execute("""
                    SELECT simple_trend FROM dhanhq.price_data
                    WHERE security_id = '15380' AND interval_minutes = %s
                    ORDER BY datetime DESC LIMIT 1
                """, (interval,))
                
                result = cur.fetchone()
                trends[name] = result[0] if result else 'UNKNOWN'
            
            # Get daily trend
            cur.execute("""
                SELECT simple_trend FROM dhanhq.price_data_daily
                WHERE security_id = '15380'
                ORDER BY date DESC LIMIT 1
            """)
            result = cur.fetchone()
            trends['Daily'] = result[0] if result else 'UNKNOWN'
            
            # Get S/R levels from database
            cur.execute("""
                SELECT level_type, price 
                FROM dhanhq.support_resistance_levels
                WHERE security_id = '15380'
                ORDER BY level_type DESC, ABS(distance_percent) ASC
            """)
            
            rows = cur.fetchall()
            support = []
            resistance = []
            
            for row in rows:
                if row[0] == 'support' and len(support) < 3:
                    support.append(float(row[1]))
                elif row[0] == 'resistance' and len(resistance) < 3:
                    resistance.append(float(row[1]))
            
            # Sort for display
            support = sorted(support)
            resistance = sorted(resistance)
            
            # Get data coverage
            cur.execute("""
                SELECT COUNT(*) as total,
                       COUNT(simple_trend) as with_trend
                FROM dhanhq.price_data
                WHERE security_id = '15380' AND interval_minutes = 15
            """)
            
            coverage_result = cur.fetchone()
            coverage = (coverage_result[1] / coverage_result[0] * 100) if coverage_result[0] > 0 else 0
            
            return jsonify({
                'current_price': current_price,
                'price_change': price_change,
                'price_change_pct': price_change_pct,
                'previous_close': previous_close,
                'previous_date': str(previous_date),
                'trends': trends,
                'support': support,
                'resistance': resistance,
                'last_update': str(last_update_time),
                'total_records': coverage_result[0],
                'data_coverage': round(coverage, 1),
                'available_timeframes': len(trends)
            })
        else:
            return jsonify({'error': 'No data available'}), 404
            
    finally:
        cur.close()
        conn.close()

@app.route('/api/daily-update', methods=['POST'])
def start_daily_update():
    """Start daily data update"""
    global update_running, progress_messages
    
    if update_running:
        return jsonify({'status': 'already_running'})
    
    update_running = True
    progress_messages = []
    
    def update_progress(msg):
        progress_messages.append(msg)
    
    def run_update():
        global update_running
        try:
            updater = DailyDataUpdater(progress_callback=update_progress)
            updater.run_daily_update()
        finally:
            update_running = False
    
    thread = threading.Thread(target=run_update)
    thread.start()
    
    return jsonify({'status': 'started'})

@app.route('/api/calculate-trends', methods=['POST'])
def start_trend_calculation():
    """Calculate trends for records with missing trend data"""
    global calculation_running, progress_messages
    
    if calculation_running:
        return jsonify({'status': 'already_running'})
    
    calculation_running = True
    progress_messages = []
    
    def update_progress(msg):
        progress_messages.append(msg)
    
    def run_calculation():
        global calculation_running
        conn = get_db_connection()
        cur = conn.cursor()
        
        try:
            from src.trend_detector import SimpleTrendDetector
            detector = SimpleTrendDetector(conn)
            
            # Process each timeframe
            timeframes = [
                (1, '1-minute'),
                (5, '5-minute'),
                (15, '15-minute'),
                (60, '1-hour')
            ]
            
            total_updated = 0
            
            for interval, name in timeframes:
                # Count records with missing trends
                cur.execute("""
                    SELECT COUNT(*) 
                    FROM dhanhq.price_data 
                    WHERE security_id = '15380' 
                    AND interval_minutes = %s 
                    AND simple_trend IS NULL
                """, (interval,))
                
                missing_count = cur.fetchone()[0]
                
                if missing_count > 0:
                    update_progress({
                        'timestamp': datetime.now().isoformat(),
                        'level': 'info',
                        'message': f'Processing {name}: {missing_count} records need trends'
                    })
                    
                    # Update trends only for records with NULL trends
                    updated = detector.update_missing_trends('15380', interval)
                    total_updated += updated
                    
                    update_progress({
                        'timestamp': datetime.now().isoformat(),
                        'level': 'success',
                        'message': f'{name}: Updated {updated} records'
                    })
                else:
                    update_progress({
                        'timestamp': datetime.now().isoformat(),
                        'level': 'info',
                        'message': f'{name}: All records have trends'
                    })
            
            # Process daily data
            cur.execute("""
                SELECT COUNT(*) 
                FROM dhanhq.price_data_daily 
                WHERE security_id = '15380' 
                AND simple_trend IS NULL
            """)
            
            daily_missing = cur.fetchone()[0]
            if daily_missing > 0:
                update_progress({
                    'timestamp': datetime.now().isoformat(),
                    'level': 'info',
                    'message': f'Processing daily: {daily_missing} records need trends'
                })
                
                daily_updated = detector.update_missing_daily_trends('15380')
                total_updated += daily_updated
                
                update_progress({
                    'timestamp': datetime.now().isoformat(),
                    'level': 'success',
                    'message': f'Daily: Updated {daily_updated} records'
                })
            
            update_progress({
                'timestamp': datetime.now().isoformat(),
                'level': 'success',
                'message': f'Total trends calculated: {total_updated}'
            })
            
        except Exception as e:
            update_progress({
                'timestamp': datetime.now().isoformat(),
                'level': 'error',
                'message': f'Error: {str(e)}'
            })
        finally:
            cur.close()
            conn.close()
            calculation_running = False
    
    thread = threading.Thread(target=run_calculation)
    thread.start()
    
    return jsonify({'status': 'started'})

@app.route('/api/trend-progress')
def get_trend_progress():
    """Get trend calculation progress"""
    global calculation_running, progress_messages
    
    # Return all messages since last check
    messages = progress_messages.copy()
    progress_messages = []  # Clear after sending
    
    return jsonify({
        'messages': messages,
        'completed': not calculation_running
    })

@app.route('/api/intraday-update', methods=['POST'])
def start_intraday_update():
    """Start intraday 1-minute data update only"""
    global update_running, progress_messages
    
    if update_running:
        return jsonify({'status': 'already_running'})
    
    update_running = True
    progress_messages = []
    
    def update_progress(msg):
        progress_messages.append(msg)
    
    def run_intraday_update():
        global update_running
        try:
            updater = DailyDataUpdater(progress_callback=update_progress)
            # Only update 1-minute interval
            updater.update_single_interval(1)
        finally:
            update_running = False
    
    thread = threading.Thread(target=run_intraday_update)
    thread.start()
    
    return jsonify({'status': 'started'})

@app.route('/api/update-progress')
def get_update_progress():
    """Get update progress"""
    global update_running, progress_messages
    
    # Return new messages since last check
    messages = progress_messages[-20:]  # Last 20 messages
    
    return jsonify({
        'running': update_running,
        'completed': not update_running,
        'messages': messages
    })

@app.route('/api/intraday-progress')
def get_intraday_progress():
    """Get intraday update progress"""
    global update_running, progress_messages
    
    # Return new messages since last check
    messages = progress_messages[-20:]  # Last 20 messages
    
    return jsonify({
        'running': update_running,
        'completed': not update_running,
        'messages': messages
    })

@app.route('/api/generate-recommendation', methods=['POST'])
def generate_recommendation():
    """Generate new trading recommendation"""
    global recommendation_generating
    
    if recommendation_generating:
        return jsonify({'success': False, 'error': 'Already generating'})
    
    recommendation_generating = True
    
    try:
        generator = RecommendationGenerator()
        recommendation = generator.generate_recommendation()
        recommendation_id = generator.save_recommendation(recommendation)
        
        return jsonify({
            'success': True,
            'recommendation_id': recommendation_id,
            'recommendation': recommendation
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    finally:
        recommendation_generating = False

@app.route('/api/validate-recommendation', methods=['POST'])
def validate_recommendation():
    """Validate recommendation with Adam Grimes perspective"""
    # Temporarily disabled - OpenAI module not installed
    return jsonify({
        'success': True,
        'validation': {
            'score': 'N/A',
            'critique': 'GPT validation temporarily disabled - OpenAI module not installed. Please install "openai" package to enable Adam Grimes validation.'
        }
    })

@app.route('/api/recommendation-history')
def get_recommendation_history():
    """Get recommendation history"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            SELECT id, generated_at, intraday_action, intraday_entry,
                   gpt_validation_score
            FROM dhanhq.trading_recommendations
            WHERE security_id = '15380'
            ORDER BY generated_at DESC
            LIMIT 10
        """)
        
        columns = ['id', 'generated_at', 'intraday_action', 'intraday_entry', 
                  'gpt_validation_score']
        results = cur.fetchall()
        
        history = []
        for row in results:
            rec = dict(zip(columns, row))
            rec['generated_at'] = rec['generated_at'].isoformat() if rec['generated_at'] else None
            history.append(rec)
        
        return jsonify(history)
        
    finally:
        cur.close()
        conn.close()

@app.route('/api/database-status')
def get_database_status():
    """Get database status"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        status = {}
        
        # Check each timeframe
        timeframes = [
            (1, '1-minute'),
            (5, '5-minute'),
            (15, '15-minute'),
            (60, '60-minute')
        ]
        
        for interval, name in timeframes:
            cur.execute("""
                SELECT COUNT(*) as count,
                       MAX(datetime) as latest,
                       COUNT(simple_trend) as with_trend
                FROM dhanhq.price_data
                WHERE security_id = '15380' AND interval_minutes = %s
            """, (interval,))
            
            result = cur.fetchone()
            coverage = (result[2] / result[0] * 100) if result[0] > 0 else 0
            
            status[name] = {
                'count': result[0],
                'latest': result[1].isoformat() if result[1] else None,
                'coverage': round(coverage, 1)
            }
        
        # Check daily data
        cur.execute("""
            SELECT COUNT(*) as count,
                   MAX(date) as latest,
                   COUNT(simple_trend) as with_trend
            FROM dhanhq.price_data_daily
            WHERE security_id = '15380'
        """)
        
        result = cur.fetchone()
        coverage = (result[2] / result[0] * 100) if result[0] > 0 else 0
        
        status['daily'] = {
            'count': result[0],
            'latest': result[1].isoformat() if result[1] else None,
            'coverage': round(coverage, 1)
        }
        
        return jsonify(status)
        
    finally:
        cur.close()
        conn.close()

@app.route('/api/calculate-sr-full', methods=['POST'])
def calculate_sr_full():
    """Calculate S/R levels for entire dataset"""
    conn = get_db_connection()
    
    try:
        sr_updater = SRDatabaseUpdater(conn)
        saved_count = sr_updater.update_sr_levels(lookback_bars=500)
        
        return jsonify({
            'status': 'success',
            'message': f'Refreshed all S/R levels. Saved {saved_count} levels.',
            'count': saved_count
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500
    finally:
        conn.close()

@app.route('/api/calculate-sr-latest', methods=['POST'])
def calculate_sr_latest():
    """Update S/R levels with latest data"""
    conn = get_db_connection()
    
    try:
        sr_updater = SRDatabaseUpdater(conn)
        saved_count = sr_updater.update_sr_levels(lookback_bars=200)
        
        return jsonify({
            'status': 'success',
            'message': f'Updated S/R levels with latest data. Saved {saved_count} levels.',
            'count': saved_count
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500
    finally:
        conn.close()


if __name__ == '__main__':
    app.run(debug=True, port=5001)