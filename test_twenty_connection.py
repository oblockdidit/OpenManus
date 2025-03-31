#!/usr/bin/env python
"""
Test script to verify connection to Twenty CRM and fetch company data.
"""

import asyncio
import sys
import os
import json
import requests

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.connectors.twenty_crm import TwentyCRMConnector
from app.logger import logger

async def test_connection():
    """Test the connection to Twenty CRM"""

    # Get API credentials from environment or use defaults from config
    api_url = os.environ.get("TWENTY_API_URL", "http://localhost:3000/")
    api_key = os.environ.get("TWENTY_API_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiOTViNTEyNS0xY2Y0LTRjODUtYTUzYi05YmVlODdlZDVmNjIiLCJ0eXBlIjoiQVBJX0tFWSIsIndvcmtzcGFjZUlkIjoiYjk1YjUxMjUtMWNmNC00Yzg1LWE1M2ItOWJlZTg3ZWQ1ZjYyIiwiaWF0IjoxNzQzMzAyNDAzLCJleHAiOjQ4OTY5MDI0MDIsImp0aSI6IjliODIwNDY2LTRiNzAtNGYzYS05YjViLWIyZGNlMjk5ZTRjZCJ9.7B6lEME5e1TG8jkKcYYIzR14HrIxjI8sRzNeSphGdIc")

    # Make sure we're using HTTP, not HTTPS
    if api_url.startswith("https://"):
        api_url = api_url.replace("https://", "http://")

    logger.info(f"Connecting to Twenty CRM at {api_url}")
    
    # Initialize CRM connector
    crm_connector = TwentyCRMConnector(api_url, api_key)
    
    try:
        # Attempt to fetch companies with correct schema
        logger.info("Fetching companies...")
        
        # Use a query that matches the exact schema
        query = """
        query GetCompanies($first: Int!) {
          companies(first: $first) {
            edges {
              node {
                id
                name
                domainName {
                  primaryLinkUrl
                  primaryLinkLabel
                }
                industry
                address {
                  addressStreet1
                  addressCity
                  addressCountry
                }
                phoneNumber {
                  primaryPhoneNumber
                }
              }
              cursor
            }
            pageInfo {
              hasNextPage
              endCursor
            }
            totalCount
          }
        }
        """
        
        variables = {"first": 5}
        
        response = await crm_connector.execute_query(query, variables)
        
        # Check if the response contains data
        if response and "data" in response and "companies" in response["data"]:
            companies = response["data"]["companies"]["edges"]
            total_count = response["data"]["companies"].get("totalCount", "unknown")
            
            logger.info(f"Successfully connected! Found {total_count} total companies.")
            logger.info(f"Fetched {len(companies)} companies for preview:")
            
            # Display company information
            for i, company_edge in enumerate(companies, 1):
                company = company_edge.get("node", {})
                domain = company.get("domainName", {})
                domain_url = domain.get("primaryLinkUrl", "No domain") if domain else "No domain"
                industry = company.get("industry", "Unknown industry")
                logger.info(f"{i}. {company.get('name', 'Unnamed')} | {domain_url} | {industry}")
                
            # Also test the REST API
            logger.info("\nTesting REST API access...")
            if len(companies) > 0:
                first_company_id = companies[0]["node"]["id"]
                rest_url = f"{api_url.rstrip('/')}/rest/companies/{first_company_id}"
                
                try:
                    headers = {"Authorization": f"Bearer {api_key}"}
                    rest_response = requests.get(rest_url, headers=headers)
                    
                    if rest_response.status_code == 200:
                        logger.info(f"✅ REST API access successful for company ID: {first_company_id}")
                    else:
                        logger.warning(f"⚠️ REST API returned status {rest_response.status_code}")
                        logger.debug(f"Response: {rest_response.text}")
                except Exception as e:
                    logger.warning(f"⚠️ Error testing REST API: {str(e)}")
            
            return True, response
        else:
            error_msg = "Error: Response did not contain expected data structure"
            logger.error(error_msg)
            logger.debug(f"Response: {json.dumps(response, indent=2)}")
            return False, {"error": error_msg, "response": response}
            
    except Exception as e:
        error_msg = f"Error connecting to Twenty CRM: {str(e)}"
        logger.error(error_msg)
        return False, {"error": error_msg}

if __name__ == "__main__":
    result, data = asyncio.run(test_connection())
    
    if result:
        print("\n✅ Connection successful!")
        print(f"Found companies in the CRM. Ready to proceed with lead analysis.")
    else:
        print("\n❌ Connection failed!")
        print("Please check your Twenty CRM configuration and make sure the service is running.")
        
        # Print detailed error information
        if "error" in data:
            print(f"\nError details: {data['error']}")
        
        # If we got a response, try to print it for debugging
        if "response" in data:
            try:
                print("\nResponse data:")
                print(json.dumps(data["response"], indent=2))
            except:
                print("Could not print response data (may not be JSON serializable)")
                print(f"Raw response: {data['response']}")