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

        # Parse incoming request
        if request.content_type and request.content_type.startswith('application/json'):
            data = request.json
        else:
            data = request.params

        # Extract SMS data
        phone_number = data.get('originator', '')
        message_content = data.get('message', '')
        timestamp = datetime.now().isoformat()

        logger.info(f"SMS from {phone_number}: {message_content}")

        # Store SMS in a structured format for later processing
        sms_data = {
            'phone': phone_number,
            'message': message_content,
            'timestamp': timestamp
        }

        # Log the full SMS data for debugging
        logger.debug(f"Complete SMS data: {json.dumps(sms_data)}")

        # Here you could save to a database, forward to another service, etc.

        # Return success response
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
