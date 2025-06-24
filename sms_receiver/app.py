#!/usr/bin/env python3
"""
DHIS2 SMS Gateway Receiver
A simple Bottle application that receives SMS messages from the DHIS2 SMS Gateway
and stores them in Redis for further processing.
"""

import os
import json
import logging
import redis
import uuid
from datetime import datetime
from bottle import Bottle, request, response, run

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

# Redis configuration
REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))
REDIS_DB = int(os.environ.get('REDIS_DB', 0))

# Initialize Redis connection
try:
    redis_client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5
    )
    # Test connection
    redis_client.ping()
    logger.info(f"Connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
except Exception as e:
    logger.error(f"Failed to connect to Redis: {e}")
    redis_client = None

# Initialize Bottle app
app = Bottle()


def store_sms_in_redis(sms_data):
    """Store SMS data in Redis with multiple access patterns"""
    if not redis_client:
        logger.warning("Redis not available, SMS data not stored")
        return None

    try:
        # Generate unique ID for this SMS
        sms_id = str(uuid.uuid4())
        timestamp = sms_data['timestamp']
        phone_number = sms_data['phone']
        sms_type = sms_data.get('type', 'unknown')

        logger.info(f"Storing SMS {sms_id} with timestamp {timestamp}")

        # Store the complete SMS data
        redis_client.hset(f"sms:{sms_id}", mapping={
            'id': sms_id,
            'type': sms_type,
            'phone': phone_number,
            'message': sms_data['message'],
            'timestamp': timestamp,
            'raw_data': json.dumps(sms_data['raw_data']),
            'processed': 'false',
            'status': sms_data.get('status', 'pending')
        })

        # Add to time-ordered list for chronological access
        try:
            # Parse timestamp to get numeric value for sorting
            if 'T' in timestamp:
                # ISO format: 2025-06-24T11:58:08.924491
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            else:
                # Fallback parsing
                dt = datetime.now()

            timestamp_score = dt.timestamp()
            logger.info(f"Adding to timeline with score {timestamp_score}")
            redis_client.zadd("sms:timeline", {sms_id: timestamp_score})

            # Verify it was added
            timeline_count = redis_client.zcard("sms:timeline")
            logger.info(f"Timeline now has {timeline_count} items")

        except Exception as timeline_error:
            logger.error(f"Error adding to timeline: {timeline_error}")
            # Use current time as fallback
            timestamp_score = datetime.now().timestamp()
            redis_client.zadd("sms:timeline", {sms_id: timestamp_score})

        # Add to phone number index for lookup by sender/recipient
        redis_client.sadd(f"sms:phone:{phone_number}", sms_id)

        # Add to type index (inbound/outbound)
        redis_client.sadd(f"sms:type:{sms_type}", sms_id)

        # Add to daily index for reporting
        try:
            date_key = datetime.fromisoformat(timestamp.replace('Z', '+00:00')).strftime('%Y-%m-%d')
        except:
            date_key = datetime.now().strftime('%Y-%m-%d')
        redis_client.sadd(f"sms:date:{date_key}", sms_id)

        # Add to unprocessed queue
        redis_client.lpush("sms:unprocessed", sms_id)

        # Set expiration for SMS data (30 days)
        redis_client.expire(f"sms:{sms_id}", 30 * 24 * 60 * 60)

        logger.info(f"SMS {sms_id} ({sms_type}) stored in Redis successfully")
        return sms_id

    except Exception as e:
        logger.error(f"Error storing SMS in Redis: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return None


@app.route('/sms/send', method='POST')
def send_sms():
    """Endpoint for DHIS2 to send outbound SMS through this gateway"""
    try:
        logger.info("=== OUTBOUND SMS REQUEST RECEIVED ===")
        logger.info(f"Method: {request.method}")
        logger.info(f"Content-Type: {request.content_type}")
        logger.info(f"Headers: {dict(request.headers)}")
        logger.info(f"Query params: {dict(request.params)}")
        logger.info(f"Form data: {dict(request.forms)}")

        # Log raw request for debugging
        request.body.seek(0)
        raw_body = request.body.read()
        logger.info(f"Raw body: {raw_body}")
        logger.info(f"Raw body decoded: {raw_body.decode('utf-8', errors='ignore')}")
        request.body.seek(0)

        # Parse incoming request
        data = {}
        if request.content_type and 'application/json' in request.content_type:
            try:
                data = request.json or {}
                logger.info(f"Parsed JSON data: {data}")
            except Exception as e:
                logger.warning(f"Failed to parse JSON: {e}")
                # Handle URL-encoded or query params
                data = dict(request.forms) or dict(request.params)
                logger.info(f"Fallback to form/params: {data}")
        else:
            # Handle form data, query params, or URL template variables
            data = dict(request.forms) or dict(request.params)
            logger.info(f"Form/query data: {data}")
            if not data:
                # Try to parse as simple key=value pairs from query string
                query_string = request.environ.get('QUERY_STRING', '')
                logger.info(f"Query string: {query_string}")
                if query_string:
                    from urllib.parse import parse_qs, unquote_plus
                    parsed = parse_qs(query_string)
                    data = {k: unquote_plus(v[0]) if v else '' for k, v in parsed.items()}
                    logger.info(f"Parsed query string: {data}")

        # If still no data, try parsing raw body as form data
        if not data and raw_body:
            try:
                from urllib.parse import parse_qs, unquote_plus
                body_str = raw_body.decode('utf-8')
                if '=' in body_str:
                    parsed = parse_qs(body_str)
                    data = {k: unquote_plus(v[0]) if v else '' for k, v in parsed.items()}
                    logger.info(f"Parsed raw body as form data: {data}")
            except Exception as e:
                logger.warning(f"Failed to parse raw body: {e}")

        # Extract SMS details - DHIS2 might use different field names
        recipients = data.get('recipients', [])
        if isinstance(recipients, str):
            recipients = [recipients]

        # Handle different possible field names for phone numbers
        phone_number = (data.get('recipient') or
                        data.get('to') or
                        data.get('msisdn') or
                        data.get('originator') or  # Sometimes DHIS2 uses this
                        (recipients[0] if recipients else 'unknown'))

        # Handle different possible field names for message content and URL decode
        message_content = (data.get('message') or
                           data.get('text') or
                           data.get('content') or
                           'No message content')

        # URL decode the message content to handle + symbols and other encoded characters
        if message_content and message_content != 'No message content':
            from urllib.parse import unquote_plus
            message_content = unquote_plus(message_content)

        timestamp = datetime.now().isoformat()

        logger.info(f"=== EXTRACTED SMS DATA ===")
        logger.info(f"Phone: {phone_number}")
        logger.info(f"Message: {message_content}")
        logger.info(f"Timestamp: {timestamp}")

        # Store outbound SMS in Redis for monitoring
        sms_data = {
            'type': 'outbound',
            'phone': phone_number,
            'message': message_content,
            'timestamp': timestamp,
            'raw_data': data,
            'status': 'sent'
        }

        # Store in Redis
        sms_id = store_sms_in_redis(sms_data)
        logger.info(f"SMS stored with ID: {sms_id}")

        # Debug: Verify storage immediately
        if sms_id and redis_client:
            try:
                stored_data = redis_client.hgetall(f"sms:{sms_id}")
                logger.info(f"Verification - SMS {sms_id} stored data: {stored_data}")
                timeline_count = redis_client.zcard("sms:timeline")
                logger.info(f"Timeline now has {timeline_count} SMS messages")
            except Exception as verify_error:
                logger.error(f"Failed to verify storage: {verify_error}")
        else:
            logger.error("SMS was not stored - sms_id is None or Redis unavailable")

        # Log the full SMS data for debugging
        logger.info(f"Complete outbound SMS data: {json.dumps(sms_data, indent=2)}")

        # Here you would integrate with your actual SMS provider
        # For now, we'll just log and return success

        # Return success response that DHIS2 expects
        response_data = {"status": "success", "message": "SMS sent successfully"}
        if sms_id:
            response_data["sms_id"] = sms_id

        logger.info(f"=== SENDING RESPONSE ===")
        logger.info(f"Response: {response_data}")
        return response_data

    except Exception as e:
        logger.error(f"=== ERROR PROCESSING OUTBOUND SMS ===")
        logger.error(f"Error: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        response.status = 500
        return {"status": "error", "message": str(e)}


@app.route('/sms/receive', method='POST')
def receive_sms():
    """Endpoint to receive inbound SMS (from external sources to DHIS2)"""
    try:
        logger.info("Received inbound SMS")
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

        # Extract SMS details
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

        logger.info(f"Inbound SMS from {phone_number}: {message_content}")

        # Store SMS in a structured format
        sms_data = {
            'type': 'inbound',
            'phone': phone_number,
            'message': message_content,
            'timestamp': timestamp,
            'raw_data': data
        }

        # Store in Redis
        sms_id = store_sms_in_redis(sms_data)

        # Log the full SMS data for debugging
        logger.info(f"Complete inbound SMS data: {json.dumps(sms_data, indent=2)}")

        # Return success response
        response_data = {"status": "success", "message": "SMS received successfully"}
        if sms_id:
            response_data["sms_id"] = sms_id

        return response_data

    except Exception as e:
        logger.error(f"Error processing inbound SMS: {e}")
        response.status = 500
        return {"status": "error", "message": str(e)}


@app.route('/sms/list', method='GET')
def list_sms():
    """List SMS messages from Redis"""
    if not redis_client:
        response.status = 503
        return {"error": "Redis not available"}

    try:
        # Get query parameters
        limit = int(request.params.get('limit', 50))
        offset = int(request.params.get('offset', 0))
        phone = request.params.get('phone')
        date = request.params.get('date')

        logger.info(f"SMS list request - limit: {limit}, offset: {offset}, phone: {phone}, date: {date}")

        sms_ids = []

        if phone:
            # Get SMS from specific phone number
            sms_ids = list(redis_client.smembers(f"sms:phone:{phone}"))
            logger.info(f"Found {len(sms_ids)} SMS for phone {phone}")
        elif date:
            # Get SMS from specific date
            sms_ids = list(redis_client.smembers(f"sms:date:{date}"))
            logger.info(f"Found {len(sms_ids)} SMS for date {date}")
        else:
            # Get SMS from timeline (most recent first)
            sms_ids = redis_client.zrevrange("sms:timeline", offset, offset + limit - 1)
            logger.info(f"Found {len(sms_ids)} SMS from timeline (offset: {offset}, limit: {limit})")

        # Retrieve SMS data
        sms_list = []
        for sms_id in sms_ids:
            sms_hash = redis_client.hgetall(f"sms:{sms_id}")
            if sms_hash:
                try:
                    sms_hash['raw_data'] = json.loads(sms_hash.get('raw_data', '{}'))
                except:
                    pass
                sms_list.append(sms_hash)
                logger.info(f"Retrieved SMS {sms_id}: {sms_hash.get('message', 'No message')[:50]}...")
            else:
                logger.warning(f"SMS {sms_id} not found in Redis")

        logger.info(f"Returning {len(sms_list)} SMS messages")

        return {
            "status": "success",
            "count": len(sms_list),
            "sms": sms_list
        }

    except Exception as e:
        logger.error(f"Error listing SMS: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        response.status = 500
        return {"error": str(e)}


@app.route('/sms/stats', method='GET')
def sms_stats():
    """Get SMS statistics from Redis"""
    if not redis_client:
        response.status = 503
        return {"error": "Redis not available"}

    try:
        total_sms = redis_client.zcard("sms:timeline")
        unprocessed_count = redis_client.llen("sms:unprocessed")

        # Get today's SMS count
        today = datetime.now().strftime('%Y-%m-%d')
        today_count = redis_client.scard(f"sms:date:{today}")

        return {
            "status": "success",
            "stats": {
                "total_sms": total_sms,
                "unprocessed": unprocessed_count,
                "today": today_count
            }
        }

    except Exception as e:
        logger.error(f"Error getting SMS stats: {e}")
        response.status = 500
        return {"error": str(e)}


@app.route('/sms/<sms_id>', method='GET')
def get_sms(sms_id):
    """Get specific SMS by ID"""
    if not redis_client:
        response.status = 503
        return {"error": "Redis not available"}

    try:
        sms_hash = redis_client.hgetall(f"sms:{sms_id}")
        if not sms_hash:
            response.status = 404
            return {"error": "SMS not found"}

        try:
            sms_hash['raw_data'] = json.loads(sms_hash.get('raw_data', '{}'))
        except:
            pass

        return {
            "status": "success",
            "sms": sms_hash
        }

    except Exception as e:
        logger.error(f"Error getting SMS {sms_id}: {e}")
        response.status = 500
        return {"error": str(e)}


@app.route('/', method='GET')
def dashboard():
    """Main dashboard UI"""
    html = '''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>DHIS2 SMS Gateway Dashboard</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f5f5f5; color: #333; }
            .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
            .header { background: #2c3e50; color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
            .header h1 { margin-bottom: 10px; }
            .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }
            .stat-card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); text-align: center; }
            .stat-number { font-size: 2em; font-weight: bold; color: #3498db; }
            .stat-label { color: #666; margin-top: 5px; }
            .controls { background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            .controls h3 { margin-bottom: 15px; }
            .control-group { display: flex; gap: 10px; align-items: center; margin-bottom: 15px; flex-wrap: wrap; }
            .control-group label { min-width: 100px; }
            .control-group input, .control-group select, .control-group button { padding: 8px 12px; border: 1px solid #ddd; border-radius: 4px; }
            .control-group button { background: #3498db; color: white; border: none; cursor: pointer; }
            .control-group button:hover { background: #2980b9; }
            .sms-list { background: white; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            .sms-item { padding: 15px; border-bottom: 1px solid #eee; }
            .sms-item:last-child { border-bottom: none; }
            .sms-header { display: flex; justify-content: between; align-items: center; margin-bottom: 8px; }
            .sms-phone { font-weight: bold; color: #2c3e50; }
            .sms-time { color: #666; font-size: 0.9em; }
            .sms-message { background: #f8f9fa; padding: 10px; border-radius: 4px; margin-top: 8px; }
            .sms-id { font-size: 0.8em; color: #999; }
            .loading { text-align: center; padding: 40px; color: #666; }
            .error { background: #e74c3c; color: white; padding: 10px; border-radius: 4px; margin: 10px 0; }
            .refresh-btn { float: right; }
            @media (max-width: 768px) {
                .control-group { flex-direction: column; align-items: stretch; }
                .sms-header { flex-direction: column; align-items: flex-start; }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>DHIS2 SMS Gateway Dashboard</h1>
                <p>Monitor and manage incoming SMS messages</p>
            </div>

            <div class="stats-grid" id="stats">
                <div class="stat-card">
                    <div class="stat-number" id="total-sms">-</div>
                    <div class="stat-label">Total SMS</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" id="today-sms">-</div>
                    <div class="stat-label">Today</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" id="unprocessed-sms">-</div>
                    <div class="stat-label">Unprocessed</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" id="redis-status">-</div>
                    <div class="stat-label">Redis Status</div>
                </div>
            </div>

            <div class="controls">
                <h3>Filters & Controls <button class="refresh-btn" onclick="loadSMS()">Refresh</button></h3>
                <div class="control-group">
                    <label>Phone:</label>
                    <input type="text" id="phone-filter" placeholder="Enter phone number">
                    <label>Date:</label>
                    <input type="date" id="date-filter">
                    <label>Limit:</label>
                    <select id="limit-filter">
                        <option value="10">10</option>
                        <option value="25" selected>25</option>
                        <option value="50">50</option>
                        <option value="100">100</option>
                    </select>
                    <button onclick="loadSMS()">Filter</button>
                    <button onclick="clearFilters()">Clear</button>
                </div>
                <div class="control-group">
                    <button onclick="sendTestSMS()">Send Test SMS</button>
                    <button onclick="exportSMS()">Export CSV</button>
                </div>
            </div>

            <div class="sms-list">
                <div class="loading" id="loading">Loading SMS messages...</div>
                <div id="sms-container"></div>
            </div>
        </div>

        <script>
            let currentSMS = [];

            async function loadStats() {
                try {
                    const response = await fetch('/sms/stats');
                    const data = await response.json();

                    if (data.status === 'success') {
                        document.getElementById('total-sms').textContent = data.stats.total_sms;
                        document.getElementById('today-sms').textContent = data.stats.today;
                        document.getElementById('unprocessed-sms').textContent = data.stats.unprocessed;
                    }
                } catch (error) {
                    console.error('Error loading stats:', error);
                }

                try {
                    const response = await fetch('/health');
                    const data = await response.json();
                    const redisStatus = document.getElementById('redis-status');
                    redisStatus.textContent = data.redis;
                    redisStatus.style.color = data.redis === 'healthy' ? '#27ae60' : '#e74c3c';
                } catch (error) {
                    console.error('Error loading health:', error);
                }
            }

            async function loadSMS() {
                const loading = document.getElementById('loading');
                const container = document.getElementById('sms-container');

                loading.style.display = 'block';
                container.innerHTML = '';

                try {
                    const params = new URLSearchParams();

                    const phone = document.getElementById('phone-filter').value;
                    const date = document.getElementById('date-filter').value;
                    const limit = document.getElementById('limit-filter').value;

                    if (phone) params.append('phone', phone);
                    if (date) params.append('date', date);
                    if (limit) params.append('limit', limit);

                    const response = await fetch(`/sms/list?${params}`);
                    const data = await response.json();

                    loading.style.display = 'none';

                    if (data.status === 'success') {
                        currentSMS = data.sms;
                        displaySMS(data.sms);
                    } else {
                        container.innerHTML = `<div class="error">Error: ${data.error || 'Unknown error'}</div>`;
                    }
                } catch (error) {
                    loading.style.display = 'none';
                    container.innerHTML = `<div class="error">Error loading SMS: ${error.message}</div>`;
                }
            }

            function displaySMS(smsArray) {
                const container = document.getElementById('sms-container');

                if (smsArray.length === 0) {
                    container.innerHTML = '<div class="loading">No SMS messages found</div>';
                    return;
                }

                container.innerHTML = smsArray.map(sms => `
                    <div class="sms-item">
                        <div class="sms-header">
                            <span class="sms-phone">${sms.phone}</span>
                            <span class="sms-time">${formatTime(sms.timestamp)}</span>
                        </div>
                        <div class="sms-message">${escapeHtml(sms.message)}</div>
                        <div class="sms-id">
                            ID: ${sms.id} | 
                            Type: <span style="color: ${sms.type === 'outbound' ? '#e74c3c' : '#27ae60'}">${sms.type || 'unknown'}</span> | 
                            Status: ${sms.status || 'pending'} | 
                            Processed: ${sms.processed === 'true' ? 'Yes' : 'No'}
                        </div>
                    </div>
                `).join('');
            }

            function formatTime(timestamp) {
                try {
                    return new Date(timestamp).toLocaleString();
                } catch {
                    return timestamp;
                }
            }

            function escapeHtml(text) {
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            }

            function clearFilters() {
                document.getElementById('phone-filter').value = '';
                document.getElementById('date-filter').value = '';
                document.getElementById('limit-filter').value = '25';
                loadSMS();
            }

            async function sendTestSMS() {
                try {
                    const response = await fetch('/sms/receive', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            originator: '+1234567890',
                            message: `Test SMS sent at ${new Date().toLocaleString()}`
                        })
                    });

                    const result = await response.json();
                    alert(result.status === 'success' ? 'Test SMS sent successfully!' : 'Error sending test SMS');

                    if (result.status === 'success') {
                        loadStats();
                        loadSMS();
                    }
                } catch (error) {
                    alert('Error sending test SMS: ' + error.message);
                }
            }

            function exportSMS() {
                if (currentSMS.length === 0) {
                    alert('No SMS data to export');
                    return;
                }

                const csv = [
                    'ID,Phone,Message,Timestamp,Type,Status,Processed',
                    ...currentSMS.map(sms => `"${sms.id}","${sms.phone}","${sms.message.replace(/"/g, '""')}","${sms.timestamp}","${sms.type || 'unknown'}","${sms.status || 'pending'}","${sms.processed}"`)
                ].join('\\n');

                const blob = new Blob([csv], { type: 'text/csv' });
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `sms-export-${new Date().toISOString().split('T')[0]}.csv`;
                a.click();
                window.URL.revokeObjectURL(url);
            }

            // Auto-refresh every 30 seconds
            setInterval(() => {
                loadStats();
                if (!document.getElementById('phone-filter').value && !document.getElementById('date-filter').value) {
                    loadSMS();
                }
            }, 30000);

            // Initial load
            loadStats();
            loadSMS();
        </script>
    </body>
    </html>
    '''
    response.content_type = 'text/html'
    return html


@app.route('/debug/redis', method='GET')
def debug_redis():
    """Debug Redis connection and data"""
    try:
        if not redis_client:
            return {"error": "Redis client not initialized"}

        # Test Redis connection
        redis_client.ping()

        # Get Redis info
        info = {
            "redis_connected": True,
            "total_keys": len(redis_client.keys("*")),
            "sms_keys": len(redis_client.keys("sms:*")),
            "timeline_count": redis_client.zcard("sms:timeline"),
            "unprocessed_count": redis_client.llen("sms:unprocessed"),
            "all_keys": redis_client.keys("*"),
            "timeline_data": redis_client.zrange("sms:timeline", 0, -1, withscores=True)
        }

        # Get sample SMS data
        sms_ids = redis_client.zrange("sms:timeline", 0, 4)  # Get first 5
        sample_sms = []
        for sms_id in sms_ids:
            sms_data = redis_client.hgetall(f"sms:{sms_id}")
            if sms_data:
                sample_sms.append(sms_data)

        info["sample_sms"] = sample_sms

        return {"status": "success", "debug_info": info}

    except Exception as e:
        return {"error": f"Redis debug failed: {e}"}


@app.route('/debug/fix-timeline', method='POST')
def fix_timeline():
    """Fix timeline for existing SMS that weren't added properly"""
    try:
        if not redis_client:
            return {"error": "Redis not available"}

        # Get all SMS keys
        sms_keys = redis_client.keys("sms:*")
        sms_keys = [key for key in sms_keys if key.startswith("sms:") and len(key.split(":")) == 2]

        fixed_count = 0

        for sms_key in sms_keys:
            sms_id = sms_key.split(":")[-1]
            sms_data = redis_client.hgetall(sms_key)

            if sms_data and 'timestamp' in sms_data:
                try:
                    timestamp = sms_data['timestamp']
                    # Parse timestamp
                    if 'T' in timestamp:
                        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    else:
                        dt = datetime.now()

                    timestamp_score = dt.timestamp()

                    # Add to timeline
                    redis_client.zadd("sms:timeline", {sms_id: timestamp_score})

                    # Ensure type field exists
                    if 'type' not in sms_data:
                        redis_client.hset(sms_key, 'type', 'inbound')

                    fixed_count += 1

                except Exception as e:
                    logger.error(f"Error fixing SMS {sms_id}: {e}")

        timeline_count = redis_client.zcard("sms:timeline")

        return {
            "status": "success",
            "fixed_count": fixed_count,
            "timeline_count": timeline_count,
            "message": f"Fixed {fixed_count} SMS messages, timeline now has {timeline_count} entries"
        }

    except Exception as e:
        return {"error": f"Fix timeline failed: {e}"}


@app.route('/debug/test-storage', method='POST')
def test_storage():
    """Test storing SMS data manually"""
    try:
        test_sms = {
            'type': 'test',
            'phone': '+123456789',
            'message': 'Test storage message',
            'timestamp': datetime.now().isoformat(),
            'raw_data': {'test': True}
        }

        sms_id = store_sms_in_redis(test_sms)

        return {
            "status": "success",
            "sms_id": sms_id,
            "stored_data": test_sms
        }

    except Exception as e:
        return {"error": f"Storage test failed: {e}"}
    """Main dashboard UI"""
    html = '''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>DHIS2 SMS Gateway Dashboard</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f5f5f5; color: #333; }
            .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
            .header { background: #2c3e50; color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
            .header h1 { margin-bottom: 10px; }
            .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }
            .stat-card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); text-align: center; }
            .stat-number { font-size: 2em; font-weight: bold; color: #3498db; }
            .stat-label { color: #666; margin-top: 5px; }
            .controls { background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            .controls h3 { margin-bottom: 15px; }
            .control-group { display: flex; gap: 10px; align-items: center; margin-bottom: 15px; flex-wrap: wrap; }
            .control-group label { min-width: 100px; }
            .control-group input, .control-group select, .control-group button { padding: 8px 12px; border: 1px solid #ddd; border-radius: 4px; }
            .control-group button { background: #3498db; color: white; border: none; cursor: pointer; }
            .control-group button:hover { background: #2980b9; }
            .sms-list { background: white; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            .sms-item { padding: 15px; border-bottom: 1px solid #eee; }
            .sms-item:last-child { border-bottom: none; }
            .sms-header { display: flex; justify-content: between; align-items: center; margin-bottom: 8px; }
            .sms-phone { font-weight: bold; color: #2c3e50; }
            .sms-time { color: #666; font-size: 0.9em; }
            .sms-message { background: #f8f9fa; padding: 10px; border-radius: 4px; margin-top: 8px; }
            .sms-id { font-size: 0.8em; color: #999; }
            .loading { text-align: center; padding: 40px; color: #666; }
            .error { background: #e74c3c; color: white; padding: 10px; border-radius: 4px; margin: 10px 0; }
            .refresh-btn { float: right; }
            @media (max-width: 768px) {
                .control-group { flex-direction: column; align-items: stretch; }
                .sms-header { flex-direction: column; align-items: flex-start; }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>DHIS2 SMS Gateway Dashboard</h1>
                <p>Monitor and manage incoming SMS messages</p>
            </div>

            <div class="stats-grid" id="stats">
                <div class="stat-card">
                    <div class="stat-number" id="total-sms">-</div>
                    <div class="stat-label">Total SMS</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" id="today-sms">-</div>
                    <div class="stat-label">Today</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" id="unprocessed-sms">-</div>
                    <div class="stat-label">Unprocessed</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" id="redis-status">-</div>
                    <div class="stat-label">Redis Status</div>
                </div>
            </div>

            <div class="controls">
                <h3>Filters & Controls <button class="refresh-btn" onclick="loadSMS()">Refresh</button></h3>
                <div class="control-group">
                    <label>Phone:</label>
                    <input type="text" id="phone-filter" placeholder="Enter phone number">
                    <label>Date:</label>
                    <input type="date" id="date-filter">
                    <label>Limit:</label>
                    <select id="limit-filter">
                        <option value="10">10</option>
                        <option value="25" selected>25</option>
                        <option value="50">50</option>
                        <option value="100">100</option>
                    </select>
                    <button onclick="loadSMS()">Filter</button>
                    <button onclick="clearFilters()">Clear</button>
                </div>
                <div class="control-group">
                    <button onclick="sendTestSMS()">Send Test SMS</button>
                    <button onclick="exportSMS()">Export CSV</button>
                </div>
            </div>

            <div class="sms-list">
                <div class="loading" id="loading">Loading SMS messages...</div>
                <div id="sms-container"></div>
            </div>
        </div>

        <script>
            let currentSMS = [];

            async function loadStats() {
                try {
                    const response = await fetch('/sms/stats');
                    const data = await response.json();

                    if (data.status === 'success') {
                        document.getElementById('total-sms').textContent = data.stats.total_sms;
                        document.getElementById('today-sms').textContent = data.stats.today;
                        document.getElementById('unprocessed-sms').textContent = data.stats.unprocessed;
                    }
                } catch (error) {
                    console.error('Error loading stats:', error);
                }

                try {
                    const response = await fetch('/health');
                    const data = await response.json();
                    const redisStatus = document.getElementById('redis-status');
                    redisStatus.textContent = data.redis;
                    redisStatus.style.color = data.redis === 'healthy' ? '#27ae60' : '#e74c3c';
                } catch (error) {
                    console.error('Error loading health:', error);
                }
            }

            async function loadSMS() {
                const loading = document.getElementById('loading');
                const container = document.getElementById('sms-container');

                loading.style.display = 'block';
                container.innerHTML = '';

                try {
                    const params = new URLSearchParams();

                    const phone = document.getElementById('phone-filter').value;
                    const date = document.getElementById('date-filter').value;
                    const limit = document.getElementById('limit-filter').value;

                    if (phone) params.append('phone', phone);
                    if (date) params.append('date', date);
                    if (limit) params.append('limit', limit);

                    const response = await fetch(`/sms/list?${params}`);
                    const data = await response.json();

                    loading.style.display = 'none';

                    if (data.status === 'success') {
                        currentSMS = data.sms;
                        displaySMS(data.sms);
                    } else {
                        container.innerHTML = `<div class="error">Error: ${data.error || 'Unknown error'}</div>`;
                    }
                } catch (error) {
                    loading.style.display = 'none';
                    container.innerHTML = `<div class="error">Error loading SMS: ${error.message}</div>`;
                }
            }

            function displaySMS(smsArray) {
                const container = document.getElementById('sms-container');

                if (smsArray.length === 0) {
                    container.innerHTML = '<div class="loading">No SMS messages found</div>';
                    return;
                }

                container.innerHTML = smsArray.map(sms => `
                    <div class="sms-item">
                        <div class="sms-header">
                            <span class="sms-phone">${sms.phone}</span>
                            <span class="sms-time">${formatTime(sms.timestamp)}</span>
                        </div>
                        <div class="sms-message">${escapeHtml(sms.message)}</div>
                        <div class="sms-id">
                            ID: ${sms.id} | 
                            Type: <span style="color: ${sms.type === 'outbound' ? '#e74c3c' : '#27ae60'}">${sms.type || 'unknown'}</span> | 
                            Status: ${sms.status || 'pending'} | 
                            Processed: ${sms.processed === 'true' ? 'Yes' : 'No'}
                        </div>
                    </div>
                `).join('');
            }

            function formatTime(timestamp) {
                try {
                    return new Date(timestamp).toLocaleString();
                } catch {
                    return timestamp;
                }
            }

            function escapeHtml(text) {
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            }

            function clearFilters() {
                document.getElementById('phone-filter').value = '';
                document.getElementById('date-filter').value = '';
                document.getElementById('limit-filter').value = '25';
                loadSMS();
            }

            async function sendTestSMS() {
                try {
                    const response = await fetch('/sms/receive', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            originator: '+1234567890',
                            message: `Test SMS sent at ${new Date().toLocaleString()}`
                        })
                    });

                    const result = await response.json();
                    alert(result.status === 'success' ? 'Test SMS sent successfully!' : 'Error sending test SMS');

                    if (result.status === 'success') {
                        loadStats();
                        loadSMS();
                    }
                } catch (error) {
                    alert('Error sending test SMS: ' + error.message);
                }
            }

            function exportSMS() {
                if (currentSMS.length === 0) {
                    alert('No SMS data to export');
                    return;
                }

                const csv = [
                    'ID,Phone,Message,Timestamp,Processed',
                    ...currentSMS.map(sms => `"${sms.id}","${sms.phone}","${sms.message.replace(/"/g, '""')}","${sms.timestamp}","${sms.processed}"`)
                ].join('\\n');

                const blob = new Blob([csv], { type: 'text/csv' });
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `sms-export-${new Date().toISOString().split('T')[0]}.csv`;
                a.click();
                window.URL.revokeObjectURL(url);
            }

            // Auto-refresh every 30 seconds
            setInterval(() => {
                loadStats();
                if (!document.getElementById('phone-filter').value && !document.getElementById('date-filter').value) {
                    loadSMS();
                }
            }, 30000);

            // Initial load
            loadStats();
            loadSMS();
        </script>
    </body>
    </html>
    '''
    response.content_type = 'text/html'
    return html


@app.route('/health', method='GET')
def health_check():
    """Enhanced health check endpoint"""
    redis_status = "healthy"
    if redis_client:
        try:
            redis_client.ping()
        except:
            redis_status = "unhealthy"
    else:
        redis_status = "unavailable"

    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "redis": redis_status
    }


if __name__ == '__main__':
    logger.info(f"Starting SMS receiver on port {SMS_PORT}")
    logger.info(f"Redis configuration: {REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}")
    run(app, host='0.0.0.0', port=SMS_PORT)
