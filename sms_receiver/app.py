#!/usr/bin/env python3
"""
DHIS2 SMS Gateway Receiver
A simple Bottle application that receives SMS messages from the DHIS2 SMS Gateway
and logs them for further processing.
"""

import os
import json
import logging
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

# Initialize Bottle app
app = Bottle()


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
    logger.info(f"Starting SMS receiver on port {SMS_PORT}")
    run(app, host='0.0.0.0', port=SMS_PORT)
