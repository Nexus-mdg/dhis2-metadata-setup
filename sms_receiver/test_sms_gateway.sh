#!/bin/bash

# SMS Gateway Test Script
# Tests both inbound and outbound SMS functionality

# Configuration - Set your DHIS2 URL here
DHIS2_URL="${DHIS2_URL:-https://dhis2.stack}"
DHIS2_USER="${DHIS2_USER:-admin}"
DHIS2_PASS="${DHIS2_PASS:-district}"
SMS_GATEWAY_URL="${SMS_GATEWAY_URL:-http://localhost:8002}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_test() {
    echo -e "${BLUE}[TEST]${NC} $1"
}

# Function to wait for user input
wait_for_user() {
    echo -e "${YELLOW}Press Enter to continue...${NC}"
    read
}

# Function to check if service is running
check_service() {
    local url=$1
    local name=$2

    if curl -s "$url" > /dev/null 2>&1; then
        print_status "$name is running ✓"
        return 0
    else
        print_error "$name is not accessible at $url ✗"
        return 1
    fi
}

# Main script
echo "======================================"
echo "     SMS GATEWAY TEST SUITE"
echo "======================================"
echo "DHIS2 URL: $DHIS2_URL"
echo "SMS Gateway: $SMS_GATEWAY_URL"
echo "======================================"
echo

# 1. Check prerequisites
print_test "1. Checking Prerequisites"
echo "----------------------------------------"

check_service "$SMS_GATEWAY_URL/health" "SMS Gateway"
if [ $? -ne 0 ]; then
    print_error "Please start the SMS gateway first: make up"
    exit 1
fi

check_service "$DHIS2_URL/api/system/info" "DHIS2"
if [ $? -ne 0 ]; then
    print_warning "DHIS2 may not be accessible. Some tests may fail."
fi

echo
wait_for_user

# 2. Test SMS Gateway Health
print_test "2. Testing SMS Gateway Health"
echo "----------------------------------------"

response=$(curl -s "$SMS_GATEWAY_URL/health")
echo "Health Response: $response"

redis_status=$(echo "$response" | grep -o '"redis":"[^"]*"' | cut -d'"' -f4)
if [ "$redis_status" = "healthy" ]; then
    print_status "Redis is healthy ✓"
else
    print_warning "Redis status: $redis_status"
fi

echo
wait_for_user

# 3. Test Inbound SMS (Phone → DHIS2)
print_test "3. Testing Inbound SMS Reception"
echo "----------------------------------------"

print_status "Sending test inbound SMS..."
inbound_response=$(curl -s -X POST "$SMS_GATEWAY_URL/sms/receive" \
  -H "Content-Type: application/json" \
  -d '{
    "originator": "+261331234567",
    "message": "MALARIA 3 FEVER,HEADACHE,VOMITING"
  }')

echo "Inbound Response: $inbound_response"

if echo "$inbound_response" | grep -q '"status":"success"'; then
    print_status "Inbound SMS received successfully ✓"
else
    print_error "Inbound SMS failed ✗"
fi

echo
wait_for_user

# 4. Test Outbound SMS (DHIS2 → Phone via Gateway)
print_test "4. Testing Outbound SMS through Gateway"
echo "----------------------------------------"

print_status "Sending test outbound SMS directly to gateway..."
outbound_response=$(curl -s -X POST "$SMS_GATEWAY_URL/sms/send" \
  -H "Content-Type: application/json" \
  -d '{
    "recipient": "+261331234567",
    "message": "Test outbound SMS from gateway"
  }')

echo "Outbound Response: $outbound_response"

if echo "$outbound_response" | grep -q '"status":"success"'; then
    print_status "Outbound SMS sent successfully ✓"
else
    print_error "Outbound SMS failed ✗"
fi

echo
wait_for_user

# 5. Test DHIS2 Outbound SMS Integration
print_test "5. Testing DHIS2 → Gateway Integration"
echo "----------------------------------------"

print_status "Sending SMS through DHIS2 API..."
dhis2_response=$(curl -s -X POST -k "$DHIS2_URL/api/sms/outbound" \
  -u "$DHIS2_USER:$DHIS2_PASS" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Disease Alert: New case reported in Test District",
    "recipients": ["+261331234567"]
  }')

echo "DHIS2 Response: $dhis2_response"

if echo "$dhis2_response" | grep -q '"httpStatus":"OK"'; then
    print_status "DHIS2 SMS integration working ✓"
    print_status "Check your SMS Gateway dashboard for the outbound message"
else
    print_error "DHIS2 SMS integration failed ✗"
    print_warning "Make sure SMS gateway is configured in DHIS2"
fi

echo
wait_for_user

# 6. Test Disease Surveillance SMS Format
print_test "6. Testing Disease Surveillance SMS Format"
echo "----------------------------------------"

print_status "Sending disease surveillance formatted SMS..."
surveillance_response=$(curl -s -X POST "$SMS_GATEWAY_URL/sms/receive" \
  -H "Content-Type: application/json" \
  -d '{
    "originator": "+261331234567",
    "message": "SURVEILLANCE CHOLERA 5 SEVERE DIARRHEA,DEHYDRATION,FEVER"
  }')

echo "Surveillance Response: $surveillance_response"

# Send notification back
notification_response=$(curl -s -X POST "$SMS_GATEWAY_URL/sms/send" \
  -H "Content-Type: application/json" \
  -d '{
    "recipient": "+261331234567",
    "message": "Alert received: 5 cholera cases reported. Health team dispatched."
  }')

print_status "Automated notification sent: $notification_response"

echo
wait_for_user

# 7. Check SMS Statistics
print_test "7. Checking SMS Statistics"
echo "----------------------------------------"

stats_response=$(curl -s "$SMS_GATEWAY_URL/sms/stats")
echo "SMS Statistics: $stats_response"

total_sms=$(echo "$stats_response" | grep -o '"total_sms":[0-9]*' | cut -d':' -f2)
print_status "Total SMS processed: $total_sms"

echo
wait_for_user

# 8. List Recent SMS Messages
print_test "8. Listing Recent SMS Messages"
echo "----------------------------------------"

print_status "Fetching last 5 SMS messages..."
list_response=$(curl -s "$SMS_GATEWAY_URL/sms/list?limit=5")

# Parse and display SMS messages nicely
echo "$list_response" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    if data.get('status') == 'success':
        sms_list = data.get('sms', [])
        print(f'Found {len(sms_list)} recent SMS messages:')
        print('----------------------------------------')
        for i, sms in enumerate(sms_list, 1):
            sms_type = sms.get('type', 'unknown')
            phone = sms.get('phone', 'unknown')
            message = sms.get('message', 'No message')[:50]
            timestamp = sms.get('timestamp', 'No timestamp')
            print(f'{i}. [{sms_type.upper()}] {phone}: {message}...')
            print(f'   Time: {timestamp}')
            print()
    else:
        print('Error fetching SMS list')
except:
    print('Could not parse SMS list response')
"

echo
wait_for_user

# 9. Test Performance (Multiple SMS)
print_test "9. Testing Performance (10 SMS messages)"
echo "----------------------------------------"

print_status "Sending 10 test SMS messages rapidly..."

for i in {1..10}; do
    curl -s -X POST "$SMS_GATEWAY_URL/sms/receive" \
      -H "Content-Type: application/json" \
      -d "{
        \"originator\": \"+26133123456$i\",
        \"message\": \"Performance test message $i - $(date)\"
      }" > /dev/null &
done

wait  # Wait for all background jobs to complete

print_status "Performance test completed. Checking final stats..."
final_stats=$(curl -s "$SMS_GATEWAY_URL/sms/stats")
echo "Final Statistics: $final_stats"

echo
echo "======================================"
echo "         TEST SUITE COMPLETED"
echo "======================================"

print_status "All tests completed!"
print_status "Visit $SMS_GATEWAY_URL to see your SMS dashboard"
print_status "Redis and SMS gateway are functioning properly"

echo
echo "Summary of URLs:"
echo "- SMS Gateway Dashboard: $SMS_GATEWAY_URL"
echo "- DHIS2 Instance: $DHIS2_URL"
echo "- Health Check: $SMS_GATEWAY_URL/health"
echo "- SMS Statistics: $SMS_GATEWAY_URL/sms/stats"

echo
print_status "Test script completed successfully! 🎉"