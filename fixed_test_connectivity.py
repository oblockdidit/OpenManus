#!/usr/bin/env python
"""
Test script to verify OpenManus connectivity to required services.
"""

import asyncio
import json
import os
import sys
from typing import Optional, Tuple

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.connectors.twenty_crm import TwentyCRMConnector
from app.llm import LLM
from app.logger import logger


async def test_twenty_crm(api_url: str, api_key: str) -> bool:
    """Test connection to Twenty CRM"""
    print(f"Testing connection to Twenty CRM at {api_url}...")
    
    # Use HTTP explicitly here
    if not api_url.startswith("http"):
        api_url = "http://" + api_url.replace("https://", "")
    
    # Initialize CRM connector with HTTP URL
    connector = TwentyCRMConnector(api_url, api_key)
    
    try:
        # Try to fetch a few companies to verify connection
        response = await connector.fetch_companies(limit=3)
        
        if response and "data" in response and "companies" in response["data"]:
            companies = response["data"]["companies"]["edges"]
            print(f"✅ Connection to Twenty CRM successful! Found {len(companies)} companies.")
            return True
        else:
            print(f"❌ Response did not contain expected data: {response}")
            return False
            
    except Exception as e:
        print(f"❌ Error connecting to Twenty CRM: {str(e)}")
        return False


async def test_llm(api_key: str, model: str = "google/gemini-2.0-flash-exp:free") -> bool:
    """Test connection to LLM API"""
    print(f"Testing connection to LLM API...")
    
    # Initialize LLM with reduced max_tokens
    llm = LLM(
        model=model,
        base_url="https://openrouter.ai/api/v1/",
        api_key=api_key,
        max_tokens=2000,  # Reduced max tokens to stay within free tier limits
        api_type="openai"
    )
    
    try:
        # Send a simple test prompt
        response = await llm.ask(
            messages=[{"role": "user", "content": "Say hello and confirm you're working!"}],
            temperature=0.7,
        )
        
        print(f"✅ LLM API test successful! Response: {response[:100]}...")
        return True
        
    except Exception as e:
        print(f"❌ Error testing LLM API: {str(e)}")
        return False


def test_db_record() -> Tuple[bool, Optional[dict]]:
    """Test loading of database record"""
    print("Testing loading of database record from test_db_record.json...")
    
    try:
        with open("test_db_record.json", "r") as f:
            data = json.load(f)
            
        if not data or not isinstance(data, dict):
            print("❌ Database record is empty or invalid format")
            return False, None
            
        print(f"✅ Successfully loaded database record!")
        print(f"Company: {data.get('name', 'Unknown')}")
        print(f"Industry: {data.get('industry', 'Unknown')}")
        print(f"Website: {data.get('website', 'Unknown')}")
        
        return True, data
    except FileNotFoundError:
        print("❌ test_db_record.json file not found")
        return False, None
    except json.JSONDecodeError:
        print("❌ Invalid JSON format in test_db_record.json")
        return False, None
    except Exception as e:
        print(f"❌ Error loading database record: {str(e)}")
        return False, None


def check_config_file() -> bool:
    """Check if config.toml exists"""
    if os.path.exists("config/config.toml"):
        print("✅ config.toml file exists")
        return True
    else:
        print("❌ config.toml file not found")
        return False


async def main():
    """Main entry point"""
    print("=== OpenManus Connectivity Test ===\n")
    
    # Check for config.toml
    check_config_file()
    
    # Test Twenty CRM connection
    twenty_api_url = os.environ.get("TWENTY_API_URL", "http://localhost:3000/")
    twenty_api_key = os.environ.get("TWENTY_API_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiOTViNTEyNS0xY2Y0LTRjODUtYTUzYi05YmVlODdlZDVmNjIiLCJ0eXBlIjoiQVBJX0tFWSIsIndvcmtzcGFjZUlkIjoiYjk1YjUxMjUtMWNmNC00Yzg1LWE1M2ItOWJlZTg3ZWQ1ZjYyIiwiaWF0IjoxNzQzMzAyNDAzLCJleHAiOjQ4OTY5MDI0MDIsImp0aSI6IjliODIwNDY2LTRiNzAtNGYzYS05YjViLWIyZGNlMjk5ZTRjZCJ9.7B6lEME5e1TG8jkKcYYIzR14HrIxjI8sRzNeSphGdIc")
    
    await test_twenty_crm(twenty_api_url, twenty_api_key)
    
    # Test LLM API connection
    openai_api_key = "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"
    try:
        await test_llm(openai_api_key, "google/gemini-2.0-flash-exp:free")
    except Exception as e:
        print(f"❌ Error during LLM testing: {str(e)}")
    
    # Test database record
    test_db_record()


if __name__ == "__main__":
    asyncio.run(main())