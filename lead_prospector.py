#!/usr/bin/env python
"""
Main script for running the Pre-Call Research workflow.

This script:
1. Initializes the Twenty CRM connector
2. Creates the Research Agent 
3. Analyzes leads before sales calls
4. Provides detailed insights to help sales representatives prepare for calls
"""

import argparse
import asyncio
import os
import sys
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agent.webdev.lead_prospector import LeadProspectorAgent
from app.connectors.twenty_crm import TwentyCRMConnector
from app.logger import logger


async def process_single_company(
    crm_connector: TwentyCRMConnector,
    lead_prospector: LeadProspectorAgent,
    company_id: str,
) -> Dict[str, Any]:
    """
    Process a single company by ID for pre-call research.

    Args:
        crm_connector: Initialized Twenty CRM connector
        lead_prospector: Initialized Lead Prospector agent
        company_id: ID of the company to process

    Returns:
        Research results
    """
    start_time = datetime.now()

    # Get company data
    response = await crm_connector.get_company(company_id)

    if not response or "data" not in response or "company" not in response["data"]:
        return {
            "error": f"Company with ID {company_id} not found",
            "start_time": start_time.isoformat(),
            "end_time": datetime.now().isoformat(),
        }

    company_data = response["data"]["company"]

    # Process company using the agent
    result = await lead_prospector.analyze_single_lead(company_data)

    end_time = datetime.now()
    processing_time = (end_time - start_time).total_seconds()

    return {
        "result": result,
        "company_name": company_data.get("name", "Unknown"),
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "processing_time_seconds": processing_time,
    }


async def process_from_db(
    crm_connector: TwentyCRMConnector,
    lead_prospector: LeadProspectorAgent,
    db_record: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Process a company directly from your database record.

    Args:
        crm_connector: Initialized Twenty CRM connector
        lead_prospector: Initialized Lead Prospector agent
        db_record: Database record with company information

    Returns:
        Research results
    """
    start_time = datetime.now()

    # Format the database record for the agent, matching Twenty CRM schema
    company_data = {
        "id": str(db_record.get("_id", "")),
        "name": db_record.get("name", ""),
        "domainName": {
            "primaryLinkUrl": db_record.get("website", ""),
            "primaryLinkLabel": ""
        },
        "industry": db_record.get("industry", "Unknown"),
        "address": {
            "addressStreet1": db_record.get("address", ""),
            "addressCity": "",
            "addressPostcode": "",
            "addressState": "",
            "addressCountry": ""
        },
        "phoneNumber": {
            "primaryPhoneNumber": db_record.get("phoneNumber", ""),
            "primaryPhoneCountryCode": "",
            "primaryPhoneCallingCode": "+1"
        }
    }

    # Process company using the agent
    result = await lead_prospector.analyze_single_lead(company_data)

    end_time = datetime.now()
    processing_time = (end_time - start_time).total_seconds()

    return {
        "result": result,
        "company_name": company_data.get("name", "Unknown"),
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "processing_time_seconds": processing_time,
    }


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Pre-Call Research Tool")

    # API connection arguments
    parser.add_argument("--api-url", help="Twenty CRM API URL")
    parser.add_argument("--api-key", help="Twenty CRM API key")

    # Operation mode arguments
    parser.add_argument(
        "--mode",
        choices=["crm", "db-record"],
        default="crm",
        help="Operation mode: 'crm' to get data from Twenty CRM, 'db-record' to provide a JSON file with DB record",
    )

    # ID for CRM mode
    parser.add_argument("--company-id", help="Company ID to process in CRM mode")

    # Input file for DB record mode
    parser.add_argument("--db-record", help="Path to JSON file with database record in DB record mode")

    args = parser.parse_args()

    # Get API credentials from environment if not provided
    api_url = args.api_url or os.environ.get("TWENTY_API_URL", "http://localhost:3000/")
    api_key = args.api_key or os.environ.get("TWENTY_API_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiOTViNTEyNS0xY2Y0LTRjODUtYTUzYi05YmVlODdlZDVmNjIiLCJ0eXBlIjoiQVBJX0tFWSIsIndvcmtzcGFjZUlkIjoiYjk1YjUxMjUtMWNmNC00Yzg1LWE1M2ItOWJlZTg3ZWQ1ZjYyIiwiaWF0IjoxNzQzMzAyNDAzLCJleHAiOjQ4OTY5MDI0MDIsImp0aSI6IjliODIwNDY2LTRiNzAtNGYzYS05YjViLWIyZGNlMjk5ZTRjZCJ9.7B6lEME5e1TG8jkKcYYIzR14HrIxjI8sRzNeSphGdIc")

    # Ensure we're using HTTP for localhost, not HTTPS
    if api_url.startswith("https://localhost"):
        api_url = api_url.replace("https://", "http://")
        logger.info(f"Converting to HTTP for localhost: {api_url}")

    if not api_url or not api_key:
        parser.error(
            "API URL and key required. Provide via arguments or environment variables "
            "(TWENTY_API_URL, TWENTY_API_KEY)"
        )

    # Initialize CRM connector
    crm_connector = TwentyCRMConnector(api_url, api_key)

    # Initialize Lead Prospector agent
    lead_prospector = LeadProspectorAgent(crm_connector=crm_connector)

    # Run in selected mode
    if args.mode == "crm":
        if not args.company_id:
            parser.error("Company ID required for CRM mode")

        logger.info(f"Processing company {args.company_id}")
        result = await process_single_company(
            crm_connector, lead_prospector, args.company_id
        )
        logger.info(f"Research complete: {result}")

    elif args.mode == "db-record":
        if not args.db_record:
            parser.error("DB record file path required for DB record mode")

        if not os.path.exists(args.db_record):
            parser.error(f"DB record file not found: {args.db_record}")

        try:
            with open(args.db_record, 'r') as f:
                db_record = json.load(f)

            logger.info(f"Processing company from DB record: {db_record.get('name', 'Unknown')}")
            result = await process_from_db(
                crm_connector, lead_prospector, db_record
            )
            logger.info(f"Research complete: {result}")
        except Exception as e:
            logger.error(f"Error processing DB record: {str(e)}")
            # Print detailed error information for debugging
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")


if __name__ == "__main__":
    asyncio.run(main())