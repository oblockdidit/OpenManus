#!/bin/bash

# Set environment variables
export TWENTY_API_URL="http://localhost:3000/"
export TWENTY_API_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiOTViNTEyNS0xY2Y0LTRjODUtYTUzYi05YmVlODdlZDVmNjIiLCJ0eXBlIjoiQVBJX0tFWSIsIndvcmtzcGFjZUlkIjoiYjk1YjUxMjUtMWNmNC00Yzg1LWE1M2ItOWJlZTg3ZWQ1ZjYyIiwiaWF0IjoxNzQzMzAyNDAzLCJleHAiOjQ4OTY5MDI0MDIsImp0aSI6IjliODIwNDY2LTRiNzAtNGYzYS05YjViLWIyZGNlMjk5ZTRjZCJ9.7B6lEME5e1TG8jkKcYYIzR14HrIxjI8sRzNeSphGdIc"

# Run the test script
/opt/anaconda3/envs/open_manus/bin/python /Users/teez/Development/Claude/OpenManus/test_connectivity.py

echo ""
echo "If you still see connection issues, try running our specific test script:"
echo "/opt/anaconda3/envs/open_manus/bin/python /Users/teez/Development/Claude/openmanus/test_twenty_connection.py"