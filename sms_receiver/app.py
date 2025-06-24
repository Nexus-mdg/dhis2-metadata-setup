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

        # Store the complete SMS data
        redis_client.hset(f"sms:{sms_id}", mapping={
            'id': sms_id,
            'phone': phone_number,
            'message': sms_data['message'],
            'timestamp': timestamp,
            'raw_data': json.dumps(sms_data['raw_data']),
            'processed': 'false'
        })

        # Add to time-ordered list for chronological access
        redis_client.zadd("sms:timeline", {sms_id: timestamp})

        # Add to phone number index for lookup by sender
        redis_client.sadd(f"sms:phone:{phone_number}", sms_id)

        # Add to daily index for reporting
        date_key = datetime.fromisoformat(timestamp.replace('Z', '+00:00')).strftime('%Y-%m-%d')
        redis_client.sadd(f"sms:date:{date_key}", sms_id)

        # Add to unprocessed queue
        redis_client.lpush("sms:unprocessed", sms_id)

        # Set expiration for SMS data (30 days)
        redis_client.expire(f"sms:{sms_id}", 30 * 24 * 60 * 60)

        logger.info(f"SMS {sms_id} stored in Redis")
        return sms_id

    except Exception as e:
        logger.error(f"Error storing SMS in Redis: {e}")
        return None


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

        # Store in Redis
        sms_id = store_sms_in_redis(sms_data)

        # Log the full SMS data for debugging
        logger.info(f"Complete SMS data: {json.dumps(sms_data, indent=2)}")

        # Return success response that DHIS2 expects
        response_data = {"status": "success", "message": "SMS received successfully"}
        if sms_id:
            response_data["sms_id"] = sms_id

        return response_data

    except Exception as e:
        logger.error(f"Error processing SMS: {e}")
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

        sms_ids = []

        if phone:
            # Get SMS from specific phone number
            sms_ids = list(redis_client.smembers(f"sms:phone:{phone}"))
        elif date:
            # Get SMS from specific date
            sms_ids = list(redis_client.smembers(f"sms:date:{date}"))
        else:
            # Get SMS from timeline (most recent first)
            sms_ids = redis_client.zrevrange("sms:timeline", offset, offset + limit - 1)

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

        return {
            "status": "success",
            "count": len(sms_list),
            "sms": sms_list
        }

    except Exception as e:
        logger.error(f"Error listing SMS: {e}")
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
