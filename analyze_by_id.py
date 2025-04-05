#!/usr/bin/env python
"""Script to analyze a company directly by ID through direct website analysis using navbar exploration."""

import asyncio
import base64
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Add the current directory to the path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.agent.lead_prospector import LeadProspectorAgent
from app.connectors.twenty_crm import TwentyCRMConnector
from app.llm.llm import LLM
from app.logger import logger
from app.tool.browser_use_tool import BrowserUseTool


async def analyze_company_by_id(company_id):
    """Get a company by ID and analyze its website directly."""
    try:
        # Initialize the CRM connector
        api_url = os.environ.get("TWENTY_API_URL", "http://localhost:3000")
        api_key = os.environ.get(
            "TWENTY_API_KEY",
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiOTViNTEyNS0xY2Y0LTRjODUtYTUzYi05YmVlODdlZDVmNjIiLCJ0eXBlIjoiQVBJX0tFWSIsIndvcmtzcGFjZUlkIjoiYjk1YjUxMjUtMWNmNC00Yzg1LWE1M2ItOWJlZTg3ZWQ1ZjYyIiwiaWF0IjoxNzQzMzAyNDAzLCJleHAiOjQ4OTY5MDI0MDIsImp0aSI6IjliODIwNDY2LTRiNzAtNGYzYS05YjViLWIyZGNlMjk5ZTRjZCJ9.7B6lEME5e1TG8jkKcYYIzR14HrIxjI8sRzNeSphGdIc",
        )

        # Ensure we're using HTTP for localhost, not HTTPS
        if api_url.startswith("https://localhost"):
            api_url = api_url.replace("https://", "http://")
            print(f"Converting to HTTP for localhost: {api_url}")

        crm_connector = TwentyCRMConnector(api_url, api_key)

        # For now, let's use hardcoded data since we know it from the screenshot
        print(f"Using known data for company ID: {company_id}")
        domain_name = "occasionhirenottingham.co.uk"
        company_data = {
            "id": company_id,
            "name": "Occasion Hire Nottingham",
            "domainName": {"primaryLinkUrl": domain_name},
            "industry": "Event Services",
        }
        print(f"Analyzing website: {domain_name}")

        try:
            # Initialize the Lead Prospector agent
            lead_prospector = LeadProspectorAgent(crm_connector=crm_connector)

            # Process the company using the agent
            start_time = datetime.now()
            result = await lead_prospector.analyze_single_lead(company_data)
            end_time = datetime.now()

            processing_time = (end_time - start_time).total_seconds()

            # Format results
            full_result = {
                "result": result,
                "company_name": company_data["name"],
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "processing_time_seconds": processing_time,
            }

            print(f"Analysis complete: {result['status']}")
            print(f"Processing time: {processing_time:.2f} seconds")

            # Return full detailed results if requested
            if "--verbose" in sys.argv:
                print(json.dumps(full_result, indent=2, default=str))

        except Exception as e:
            print(f"Error: {str(e)}")
            import traceback

            print(traceback.format_exc())
    except Exception as outer_e:
        print(f"Outer error: {str(outer_e)}")
        import traceback

        print(traceback.format_exc())


if __name__ == "__main__":
    # Set up graceful termination
    def handle_sigint(sig, frame):
        print("\nReceived interrupt signal. Shutting down...")
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sigint)

    if len(sys.argv) < 2:
        print("Usage: python analyze_by_id.py COMPANY_ID [--verbose]")
        sys.exit(1)

    company_id = sys.argv[1]
    asyncio.run(analyze_company_by_id(company_id))
