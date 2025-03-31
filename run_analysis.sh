#!/bin/bash

# Set environment variables
export TWENTY_API_URL="http://localhost:3000/"
export TWENTY_API_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiOTViNTEyNS0xY2Y0LTRjODUtYTUzYi05YmVlODdlZDVmNjIiLCJ0eXBlIjoiQVBJX0tFWSIsIndvcmtzcGFjZUlkIjoiYjk1YjUxMjUtMWNmNC00Yzg1LWE1M2ItOWJlZTg3ZWQ1ZjYyIiwiaWF0IjoxNzQzMzAyNDAzLCJleHAiOjQ4OTY5MDI0MDIsImp0aSI6IjliODIwNDY2LTRiNzAtNGYzYS05YjViLWIyZGNlMjk5ZTRjZCJ9.7B6lEME5e1TG8jkKcYYIzR14HrIxjI8sRzNeSphGdIc"

echo "=== OpenManus Lead Prospector ==="
echo ""
echo "First testing Twenty CRM connection..."
/opt/anaconda3/envs/open_manus/bin/python /Users/teez/Development/Claude/openmanus/test_twenty_connection.py

echo ""
echo "Now running lead analysis on test_db_record.json..."
/opt/anaconda3/envs/open_manus/bin/python /Users/teez/Development/Claude/openmanus/lead_prospector.py --mode db-record --db-record test_db_record.json
