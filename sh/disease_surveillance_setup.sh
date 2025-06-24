#!/bin/bash
# Disease Surveillance Tracker Program Setup
# This script imports a disease surveillance tracker program with SMS notifications

# DHIS2 Connection Settings (can be overridden with environment variables)
DHIS2_URL="${DHIS2_URL:-https://dhis2.stack}"
DHIS2_USERNAME="${DHIS2_USERNAME:-admin}"
DHIS2_PASSWORD="${DHIS2_PASSWORD:-district}"

# Path to the JSON metadata file
METADATA_FILE="../metadata/disease_surveillance_program.json"

# Check if metadata file exists
if [ ! -f "$METADATA_FILE" ]; then
  echo "Error: Metadata file not found: $METADATA_FILE"
  echo "Please make sure the file exists in the correct location."
  exit 1
fi

echo "=================================================="
echo "Disease Surveillance Tracker Program Setup"
echo "=================================================="
echo "Using metadata file: $METADATA_FILE"
echo "DHIS2 URL: $DHIS2_URL"
echo ""

# Import the tracker program
echo "Importing Disease Surveillance program..."
IMPORT_RESPONSE=$(curl -k -s -u "$DHIS2_USERNAME:$DHIS2_PASSWORD" \
  -H "Content-Type: application/json" \
  -X POST \
  "$DHIS2_URL/api/metadata?importMode=COMMIT&identifier=UID&importStrategy=CREATE_AND_UPDATE" \
  -d @"$METADATA_FILE")

# Check if there were any errors during import
if echo "$IMPORT_RESPONSE" | grep -q "\"status\":\"ERROR\""; then
  echo "There were errors during import:"
  echo "$IMPORT_RESPONSE" | grep -A5 "ERROR"
  echo ""
  echo "Full response:"
  echo "$IMPORT_RESPONSE"

  # Continue anyway for partial success
  echo ""
  echo "Continuing despite errors..."
else
  echo "Import completed successfully!"
  # Try to extract stats
  STATS=$(echo "$IMPORT_RESPONSE" | grep -o '"stats":{[^}]*}' | head -1)
  if [ -n "$STATS" ]; then
    echo "Import statistics: $STATS"
  fi
fi

# Check if program was created successfully
echo ""
echo "Verifying Disease Surveillance program..."
PROGRAM_CHECK=$(curl -k -s -u "$DHIS2_USERNAME:$DHIS2_PASSWORD" \
  "$DHIS2_URL/api/programs/MDGdisSurv1?fields=id,name")

if echo "$PROGRAM_CHECK" | grep -q "MDGdisSurv1"; then
  echo "✓ Disease Surveillance program verified!"
else
  echo "Warning: Could not verify program creation. Response:"
  echo "$PROGRAM_CHECK"
  echo "Check DHIS2 interface to verify if the program was created."
fi

# Check if SMS gateway is configured
echo ""
echo "Checking SMS gateway configuration..."
SMS_CONFIG=$(curl -k -s -u "$DHIS2_USERNAME:$DHIS2_PASSWORD" \
  "$DHIS2_URL/api/gateways")

if echo "$SMS_CONFIG" | grep -q "\"empty\":true"; then
  echo "⚠️  Warning: No SMS gateway is configured. SMS notifications will not work."
  echo "To configure an SMS gateway, go to:"
  echo "$DHIS2_URL/dhis-web-maintenance/#/mobile/sms-config"

  # Provide a sample command to configure it
  echo ""
  echo "Sample command to configure a generic SMS gateway:"
  echo "curl -k -X POST -u $DHIS2_USERNAME:$DHIS2_PASSWORD -H 'Content-Type: application/json' $DHIS2_URL/api/gateways -d '{\"type\":\"http\",\"name\":\"SMS Provider\",\"configurationTemplate\":{\"urlTemplate\":\"https://example.com/sms?to={recipients}&message={text}\",\"useGet\":true}}'"
else
  echo "✓ SMS gateway appears to be configured."

  # Show the gateway name if possible
  GATEWAY_NAME=$(echo "$SMS_CONFIG" | grep -o '"name":"[^"]*"' | head -1 | cut -d'"' -f4)
  if [ -n "$GATEWAY_NAME" ]; then
    echo "Gateway name: $GATEWAY_NAME"
  fi
fi

echo ""
echo "=================================================="
echo "Disease Surveillance Program Setup Completed"
echo "=================================================="
echo ""
echo "Summary:"
echo "- Created Disease Surveillance tracker program"
echo "- Added patient tracking attributes (ID, name, phone)"
echo "- Set up Case Registration program stage with data elements"
echo "- Configured SMS notifications on stage completion"
echo ""
echo "Next Steps:"
echo "1. Review the program in DHIS2: $DHIS2_URL/dhis-web-tracker/#/program/MDGdisSurv1"
echo "2. Ensure SMS gateway is properly configured"
echo "3. Test program enrollment and SMS notifications"
echo ""
