#!/usr/bin/env python
"""
Simple script to test connectivity to the Twenty CRM API and OpenAI API.
"""

import asyncio
import json
import os
import sys

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.connectors.twenty_crm import TwentyCRMConnector
from app.llm import LLM


async def test_twenty_crm(api_url, api_key):
    """Test the connection to Twenty CRM"""
    try:
        # Convert HTTPS to HTTP for localhost connections
        if api_url.startswith("https://localhost"):
            api_url = api_url.replace("https://", "http://")
            print(f"Converting to HTTP for localhost: {api_url}")
            
        print(f"Testing connection to Twenty CRM at {api_url}...")
        
        connector = TwentyCRMConnector(api_url, api_key)
        
        # Fixed query with proper selection of subfields for domainName
        query = """
        query TestQuery {
          companies(first: 3) {
            edges {
              node {
                id
                name
                # Query domainName with subfields based on the Links type
                domainName {
                  url
                  label
                }
              }
            }
          }
        }
        """
        
        result = await connector.execute_query(query)
        
        if result and "data" in result:
            print("✅ Successfully connected to Twenty CRM!")
            if "companies" in result.get("data", {}):
                companies = result["data"]["companies"]["edges"]
                print(f"Found {len(companies)} companies:")
                for i, company in enumerate(companies, 1):
                    node = company.get("node", {})
                    domain = node.get("domainName", {})
                    domain_url = domain.get("url", "No domain") if domain else "No domain"
                    print(f"  {i}. {node.get('name', 'Unnamed')} - {domain_url}")
            return True
        else:
            print("❌ Connection to Twenty CRM failed. Response did not contain expected data.")
            print(f"Response: {json.dumps(result, indent=2)}")
            return False
    
    except Exception as e:
        print(f"❌ Error connecting to Twenty CRM: {str(e)}")
        return False


async def test_llm(api_key, model=None):
    """Test the connection to LLM API"""
    try:
        print(f"Testing connection to LLM API...")
        
        # Create standard LLM instance without max_tokens parameter
        llm = LLM()
        
        if model:
            llm.model = model
        
        llm.api_key = api_key
        # Set max_tokens after initialization
        llm.max_tokens = 2000
        
        response = await llm.ask(
            messages=[{"role": "user", "content": "Say hello in one short sentence."}],
            temperature=0.7,
            max_tokens=1000  # Limit max_tokens in the request
        )
        
        if response:
            print("✅ Successfully connected to LLM API!")
            print(f"Response: {response}")
            return True
        else:
            print("❌ Connection to LLM API failed. No response received.")
            return False
    
    except Exception as e:
        print(f"❌ Error connecting to LLM API: {str(e)}")
        # Print more detailed error information
        import traceback
        print(f"Error details: {traceback.format_exc()}")
        return False


async def test_db_record(db_record_path="test_db_record.json"):
    """Test loading a database record"""
    try:
        print(f"Testing loading of database record from {db_record_path}...")
        
        with open(db_record_path, 'r') as f:
            db_record = json.load(f)
        
        print("✅ Successfully loaded database record!")
        print(f"Company: {db_record.get('name')}")
        print(f"Industry: {db_record.get('industry')}")
        print(f"Website: {db_record.get('website')}")
        return True
    
    except Exception as e:
        print(f"❌ Error loading database record: {str(e)}")
        return False


async def main():
    """Run all tests"""
    print("=== OpenManus Connectivity Test ===\n")
    
    # Get API credentials from environment or use defaults from our config
    twenty_api_url = os.environ.get("TWENTY_API_URL", "http://localhost:3000/")
    twenty_api_key = os.environ.get("TWENTY_API_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiOTViNTEyNS0xY2Y0LTRjODUtYTUzYi05YmVlODdlZDVmNjIiLCJ0eXBlIjoiQVBJX0tFWSIsIndvcmtzcGFjZUlkIjoiYjk1YjUxMjUtMWNmNC00Yzg1LWE1M2ItOWJlZTg3ZWQ1ZjYyIiwiaWF0IjoxNzQzMzAyNDAzLCJleHAiOjQ4OTY5MDI0MDIsImp0aSI6IjliODIwNDY2LTRiNzAtNGYzYS05YjViLWIyZGNlMjk5ZTRjZCJ9.7B6lEME5e1TG8jkKcYYIzR14HrIxjI8sRzNeSphGdIc")
    openai_api_key = os.environ.get("OPENAI_API_KEY", "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")
    
    # Check if using OpenRouter API key
    if openai_api_key and openai_api_key.startswith("sk-or-"):
        print("Using OpenRouter API key - limiting max tokens to 2000")
        openai_api_key = openai_api_key  # Keep as is
        llm_model = "google/gemini-2.0-flash-exp:free"  # Use Gemini for OpenRouter
    else:
        llm_model = "gpt-4o"  # Default model
    
    # Check if config.toml exists
    if os.path.exists("config/config.toml"):
        print("✅ config.toml file exists")
    else:
        print("❌ config.toml file not found")
    
    # Test CRM connection
    await test_twenty_crm(twenty_api_url, twenty_api_key)
    
    # Test LLM connection if API key is available
    if openai_api_key:
        print("Testing connection to LLM API...")
        await test_llm(openai_api_key, llm_model)
    
    # Test database record loading
    await test_db_record()


if __name__ == "__main__":
    asyncio.run(main())