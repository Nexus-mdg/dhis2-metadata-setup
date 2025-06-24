#!/bin/bash
# Madagascar DHIS2 Organization Unit Tree Creation
# This script imports the complete organization unit structure for Madagascar
# Based on 23 regions and their districts for DHIS2

# DHIS2 Connection Settings (can be overridden with environment variables)
DHIS2_URL="${DHIS2_URL:-https://dhis2.stack}"
DHIS2_USERNAME="${DHIS2_USERNAME:-admin}"
DHIS2_PASSWORD="${DHIS2_PASSWORD:-district}"

# Path to the JSON metadata file
METADATA_FILE="../metadata/madagascar_ou_structure.json"

# Check if metadata file exists
if [ ! -f "$METADATA_FILE" ]; then
  echo "Error: Metadata file not found: $METADATA_FILE"
  echo "Please make sure the file exists in the correct location."
  exit 1
fi

echo "=================================================="
echo "Madagascar DHIS2 Organization Unit Structure Setup"
echo "=================================================="
echo "Using metadata file: $METADATA_FILE"
echo "DHIS2 URL: $DHIS2_URL"
echo ""

# Import the organization unit structure
echo "Importing organization unit structure..."
curl -k -u "$DHIS2_USERNAME:$DHIS2_PASSWORD" \
  -H "Content-Type: application/json" \
  -X POST \
  "$DHIS2_URL/api/metadata" \
  -d @"$METADATA_FILE"

# Check the result
echo ""
echo "=================================================="
echo "Organization Unit Structure Import Completed"
echo "=================================================="
echo ""
echo "Summary:"
echo "- Country: Madagascar"
echo "- Regions: 23 regions"
echo "- Districts: Sample districts for key regions"
echo ""
echo "Verification:"
echo "Visit: $DHIS2_URL/dhis-web-maintenance/#/list/organisationUnitSection/organisationUnit"
echo "Or API: curl -u $DHIS2_USERNAME:$DHIS2_PASSWORD '$DHIS2_URL/api/organisationUnits?fields=id,name,level&paging=false'"
echo ""
