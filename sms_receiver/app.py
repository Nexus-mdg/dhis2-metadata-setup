#!/usr/bin/env python3
"""
DHIS2 SMS Gateway Receiver with Web UI
A Bottle application that receives SMS messages from DHIS2 and provides a web interface to view them.
"""

import os
import json
import logging
from datetime import datetime
from bottle import Bottle, request, response, run, static_file, template

# Configure logging
log_level = os.environ.get('LOG_LEVEL', 'info').upper()
log_file = "/var/log/sms_receiver/sms_receiver.log"
os.makedirs(os.path.dirname(log_file), exist_ok=True)

logging.basicConfig(
    level=getattr(logging, log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('dhis2_sms_receiver')

# SMS port setting
SMS_PORT = int(os.environ.get('SMS_PORT', 8002))

# SMS storage file
SMS_STORAGE_FILE = "/var/log/sms_receiver/sms_messages.json"

# Initialize Bottle app
app = Bottle()


def load_sms_messages():
    """Load SMS messages from storage file"""
    try:
        if os.path.exists(SMS_STORAGE_FILE):
            with open(SMS_STORAGE_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading SMS messages: {e}")
    return []


def save_sms_message(sms_data):
    """Save SMS message to storage file"""
    try:
        messages = load_sms_messages()
        # Add unique ID and insert at beginning (newest first)
        sms_data['id'] = len(messages) + 1
        messages.insert(0, sms_data)

        # Keep only last 1000 messages
        if len(messages) > 1000:
            messages = messages[:1000]

        with open(SMS_STORAGE_FILE, 'w') as f:
            json.dump(messages, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving SMS message: {e}")
        return False


@app.route('/')
def dashboard():
    """Main dashboard showing SMS messages"""
    messages = load_sms_messages()

    html = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>DHIS2 SMS Gateway Dashboard</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; 
                background: #f5f7fa; 
                color: #333;
            }
            .header { 
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white; 
                padding: 2rem; 
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
            .header h1 { 
                font-size: 2rem; 
                margin-bottom: 0.5rem; 
                font-weight: 600;
            }
            .stats { 
                display: grid; 
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); 
                gap: 1rem; 
                margin: 1rem 0; 
            }
            .stat-card { 
                background: rgba(255,255,255,0.2); 
                padding: 1rem; 
                border-radius: 8px; 
                backdrop-filter: blur(10px);
            }
            .stat-number { 
                font-size: 1.5rem; 
                font-weight: bold; 
                margin-bottom: 0.25rem;
            }
            .container { 
                max-width: 1200px; 
                margin: 0 auto; 
                padding: 2rem; 
            }
            .controls { 
                display: flex; 
                gap: 1rem; 
                margin-bottom: 2rem; 
                flex-wrap: wrap;
            }
            .btn { 
                background: #667eea; 
                color: white; 
                border: none; 
                padding: 0.75rem 1.5rem; 
                border-radius: 6px; 
                cursor: pointer; 
                text-decoration: none;
                display: inline-block;
                font-weight: 500;
                transition: all 0.2s;
            }
            .btn:hover { 
                background: #5a67d8; 
                transform: translateY(-1px);
            }
            .btn-danger { 
                background: #e53e3e; 
            }
            .btn-danger:hover { 
                background: #c53030; 
            }
            .message-card { 
                background: white; 
                border-radius: 12px; 
                padding: 1.5rem; 
                margin-bottom: 1rem; 
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                border-left: 4px solid #667eea;
                transition: transform 0.2s;
            }
            .message-card:hover { 
                transform: translateY(-2px); 
                box-shadow: 0 4px 16px rgba(0,0,0,0.15);
            }
            .message-header { 
                display: flex; 
                justify-content: space-between; 
                align-items: center; 
                margin-bottom: 1rem; 
                flex-wrap: wrap;
                gap: 0.5rem;
            }
            .message-id { 
                background: #667eea; 
                color: white; 
                padding: 0.25rem 0.75rem; 
                border-radius: 20px; 
                font-size: 0.8rem; 
                font-weight: 500;
            }
            .message-time { 
                color: #666; 
                font-size: 0.9rem; 
            }
            .message-content { 
                margin-bottom: 1rem; 
            }
            .message-phone { 
                font-weight: 600; 
                color: #667eea; 
                margin-bottom: 0.5rem;
            }
            .message-text { 
                background: #f8f9fa; 
                padding: 1rem; 
                border-radius: 8px; 
                border-left: 3px solid #667eea;
                font-size: 1.1rem;
                line-height: 1.5;
            }
            .raw-data { 
                background: #f1f3f4; 
                padding: 1rem; 
                border-radius: 6px; 
                font-family: 'Monaco', 'Menlo', monospace; 
                font-size: 0.8rem; 
                margin-top: 1rem;
                max-height: 200px;
                overflow-y: auto;
            }
            .toggle-raw { 
                background: #718096; 
                color: white; 
                border: none; 
                padding: 0.4rem 0.8rem; 
                border-radius: 4px; 
                cursor: pointer; 
                font-size: 0.8rem;
                transition: background 0.2s;
            }
            .toggle-raw:hover { 
                background: #4a5568; 
            }
            .empty-state { 
                text-align: center; 
                padding: 4rem 2rem; 
                color: #666;
            }
            .empty-state-icon { 
                font-size: 4rem; 
                margin-bottom: 1rem; 
            }
            .search-box { 
                width: 100%; 
                max-width: 400px; 
                padding: 0.75rem; 
                border: 2px solid #e2e8f0; 
                border-radius: 6px; 
                font-size: 1rem;
                transition: border-color 0.2s;
            }
            .search-box:focus { 
                outline: none; 
                border-color: #667eea; 
            }
            @media (max-width: 768px) {
                .container { padding: 1rem; }
                .header { padding: 1.5rem; }
                .message-header { flex-direction: column; align-items: flex-start; }
                .controls { flex-direction: column; }
            }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>📱 DHIS2 SMS Gateway Dashboard</h1>
            <div class="stats">
                <div class="stat-card">
                    <div class="stat-number">{{len(messages)}}</div>
                    <div>Total Messages</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{{len([m for m in messages if datetime.fromisoformat(m['timestamp']).date() == datetime.now().date()])}}</div>
                    <div>Today</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{{len(set([m['phone'] for m in messages]))}}</div>
                    <div>Unique Senders</div>
                </div>
            </div>
        </div>

        <div class="container">
            <div class="controls">
                <button class="btn" onclick="location.reload()">🔄 Refresh</button>
                <button class="btn btn-danger" onclick="clearMessages()">🗑️ Clear All</button>
                <a href="/api/messages" class="btn">📋 JSON API</a>
                <input type="text" class="search-box" placeholder="🔍 Search messages..." id="searchBox" onkeyup="filterMessages()">
            </div>

            <div id="messages">
                % if not messages:
                    <div class="empty-state">
                        <div class="empty-state-icon">📭</div>
                        <h3>No SMS messages received yet</h3>
                        <p>SMS messages from DHIS2 will appear here when received.</p>
                    </div>
                % else:
                    % for message in messages:
                        <div class="message-card" data-searchable="{{message['phone']}} {{message['message']}}">
                            <div class="message-header">
                                <div class="message-time">
                                    📅 {{datetime.fromisoformat(message['timestamp']).strftime('%Y-%m-%d %H:%M:%S')}}
                                </div>
                                <div class="message-id">ID: {{message.get('id', 'N/A')}}</div>
                            </div>

                            <div class="message-content">
                                <div class="message-phone">📞 From: {{message['phone']}}</div>
                                <div class="message-text">{{message['message']}}</div>
                            </div>

                            <button class="toggle-raw" onclick="toggleRaw({{message.get('id', 0)}})">
                                Show Raw Data
                            </button>
                            <div id="raw-{{message.get('id', 0)}}" class="raw-data" style="display: none;">
                                {{json.dumps(message['raw_data'], indent=2)}}
                            </div>
                        </div>
                    % end
                % end
            </div>
        </div>

        <script>
            function toggleRaw(id) {
                const element = document.getElementById('raw-' + id);
                const button = element.previousElementSibling;
                if (element.style.display === 'none') {
                    element.style.display = 'block';
                    button.textContent = 'Hide Raw Data';
                } else {
                    element.style.display = 'none';
                    button.textContent = 'Show Raw Data';
                }
            }

            function clearMessages() {
                if (confirm('Are you sure you want to clear all SMS messages? This cannot be undone.')) {
                    fetch('/api/clear', {method: 'POST'})
                        .then(response => response.json())
                        .then(data => {
                            if (data.status === 'success') {
                                location.reload();
                            } else {
                                alert('Error: ' + data.message);
                            }
                        })
                        .catch(err => alert('Error clearing messages: ' + err));
                }
            }

            function filterMessages() {
                const searchTerm = document.getElementById('searchBox').value.toLowerCase();
                const messages = document.querySelectorAll('.message-card');

                messages.forEach(message => {
                    const searchableText = message.getAttribute('data-searchable').toLowerCase();
                    if (searchableText.includes(searchTerm)) {
                        message.style.display = 'block';
                    } else {
                        message.style.display = 'none';
                    }
                });
            }

            // Auto-refresh every 30 seconds
            setInterval(() => {
                location.reload();
            }, 30000);
        </script>
    </body>
    </html>
    '''

    return template(html, messages=messages, datetime=datetime, json=json, len=len, set=set)


@app.route('/api/messages')
def api_messages():
    """API endpoint to get all messages as JSON"""
    messages = load_sms_messages()
    return {
        'status': 'success',
        'count': len(messages),
        'messages': messages
    }


@app.route('/api/clear', method='POST')
def api_clear():
    """API endpoint to clear all messages"""
    try:
        # Clear the storage file
        with open(SMS_STORAGE_FILE, 'w') as f:
            json.dump([], f)
        logger.info("All SMS messages cleared via API")
        return {'status': 'success', 'message': 'All messages cleared'}
    except Exception as e:
        logger.error(f"Error clearing messages: {e}")
        response.status = 500
        return {'status': 'error', 'message': str(e)}


@app.route('/sms/receive', method='POST')
def receive_sms():
    """Endpoint to receive SMS from the DHIS2 SMS gateway"""
    try:
        logger.info("Received SMS request")
        logger.info(f"Content-Type: {request.content_type}")
        logger.info(f"Raw body: {request.body.read()}")

        # Reset body stream
        request.body.seek(0)

        # Parse incoming request more robustly
        data = {}

        if request.content_type and 'application/json' in request.content_type:
            try:
                data = request.json or {}
            except Exception as e:
                logger.warning(f"Failed to parse JSON: {e}")
                # Try to get raw body as fallback
                raw_body = request.body.read().decode('utf-8')
                logger.info(f"Raw body content: {raw_body}")
                data = {'raw_content': raw_body}
        else:
            # Handle form data or query params
            data = dict(request.forms) or dict(request.params)

        # DHIS2 might send data in different formats, so let's be flexible
        phone_number = (data.get('originator') or
                        data.get('from') or
                        data.get('sender') or
                        data.get('msisdn') or
                        'unknown')

        message_content = (data.get('message') or
                           data.get('text') or
                           data.get('content') or
                           str(data))

        timestamp = datetime.now().isoformat()

        logger.info(f"SMS from {phone_number}: {message_content}")

        # Store SMS in a structured format
        sms_data = {
            'phone': phone_number,
            'message': message_content,
            'timestamp': timestamp,
            'raw_data': data
        }

        # Save to storage file
        save_sms_message(sms_data)

        # Log the full SMS data for debugging
        logger.info(f"Complete SMS data: {json.dumps(sms_data, indent=2)}")

        # Return success response that DHIS2 expects
        return {"status": "success", "message": "SMS received successfully"}

    except Exception as e:
        logger.error(f"Error processing SMS: {e}")
        response.status = 500
        return {"status": "error", "message": str(e)}


@app.route('/health', method='GET')
def health_check():
    """Simple health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


if __name__ == '__main__':
    logger.info(f"Starting SMS receiver with web UI on port {SMS_PORT}")
    logger.info(f"Dashboard available at: http://0.0.0.0:{SMS_PORT}/")
    logger.info(f"SMS endpoint: http://0.0.0.0:{SMS_PORT}/sms/receive")
    run(app, host='0.0.0.0', port=SMS_PORT)
