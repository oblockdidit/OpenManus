#!/usr/bin/env python
"""
Setup script for Twenty CRM metadata configuration.

This script:
1. Creates the WebsiteAnalysis custom object
2. Adds fields to the WebsiteAnalysis object
3. Extends the Company object with web development fields
4. Creates relationships between objects
"""

import argparse
import asyncio
import os
import sys
from typing import Any, Dict, List

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.connectors.graphql.metadata_queries import (
    COMPANY_EXTENSION_FIELDS,
    WEBSITE_ANALYSIS_FIELDS,
    WEBSITE_ANALYSIS_OBJECT,
)
from app.connectors.twenty_crm import TwentyCRMConnector


async def setup_website_analysis_object(connector: TwentyCRMConnector) -> str:
    """
    Create the WebsiteAnalysis object in Twenty CRM.

    Args:
        connector: Initialized Twenty CRM connector

    Returns:
        The ID of the created object
    """
    print("Creating WebsiteAnalysis object...")

    # Create the object
    result = await connector.create_object_metadata(WEBSITE_ANALYSIS_OBJECT)

    if not result or "data" not in result or "createObject" not in result["data"]:
        raise Exception("Failed to create WebsiteAnalysis object")

    object_id = result["data"]["createObject"]["id"]
    print(f"Successfully created WebsiteAnalysis object with ID: {object_id}")

    return object_id


async def add_fields_to_object(
    connector: TwentyCRMConnector, object_id: str, fields: List[Dict[str, Any]]
) -> None:
    """
    Add fields to an object in Twenty CRM.

    Args:
        connector: Initialized Twenty CRM connector
        object_id: The ID of the object to add fields to
        fields: List of field definitions
    """
    print(f"Adding {len(fields)} fields to object {object_id}...")

    for field in fields:
        try:
            result = await connector.add_field_to_object(object_id, field)

            if (
                not result
                or "data" not in result
                or "createField" not in result["data"]
            ):
                print(f"Failed to create field {field['name']}")
                continue

            field_id = result["data"]["createField"]["id"]
            print(f"- Created field {field['name']} with ID: {field_id}")

        except Exception as e:
            print(f"Error creating field {field['name']}: {str(e)}")


async def extend_company_object(connector: TwentyCRMConnector) -> None:
    """
    Extend the Company object with web development fields.

    Args:
        connector: Initialized Twenty CRM connector
    """
    print("Finding Company object...")

    # Find Company object
    query = """
    query GetObjectByName($nameSingular: String!) {
      findObjectMetadataByName(nameSingular: $nameSingular) {
        id
        nameSingular
        namePlural
      }
    }
    """

    result = await connector.execute_query(query, {"nameSingular": "company"})

    if (
        not result
        or "data" not in result
        or not result["data"]["findObjectMetadataByName"]
    ):
        raise Exception("Failed to find Company object")

    company_object_id = result["data"]["findObjectMetadataByName"]["id"]
    print(f"Found Company object with ID: {company_object_id}")

    # Add web development fields
    await add_fields_to_object(connector, company_object_id, COMPANY_EXTENSION_FIELDS)


async def create_relationships(
    connector: TwentyCRMConnector, website_analysis_object_id: str
) -> None:
    """
    Create relationships between objects.

    Args:
        connector: Initialized Twenty CRM connector
        website_analysis_object_id: The ID of the WebsiteAnalysis object
    """
    print("Creating relationships between objects...")

    # Find Company object
    query = """
    query GetObjectByName($nameSingular: String!) {
      findObjectMetadataByName(nameSingular: $nameSingular) {
        id
        nameSingular
        namePlural
      }
    }
    """

    result = await connector.execute_query(query, {"nameSingular": "company"})

    if (
        not result
        or "data" not in result
        or not result["data"]["findObjectMetadataByName"]
    ):
        raise Exception("Failed to find Company object")

    company_object_id = result["data"]["findObjectMetadataByName"]["id"]

    # Create relationship: WebsiteAnalysis -> Company (many-to-one)
    relation_query = """
    mutation CreateRelation($input: CreateRelationInput!) {
      createRelation(input: $input) {
        id
        relationType
        fromObjectMetadataId
        toObjectMetadataId
      }
    }
    """

    relation_input = {
        "input": {
            "relationType": "ONE_TO_MANY",
            "fromObjectMetadataId": company_object_id,
            "toObjectMetadataId": website_analysis_object_id,
            "fromFieldMetadataName": "websiteAnalyses",
            "toFieldMetadataName": "company",
        }
    }

    result = await connector.execute_query(relation_query, relation_input)

    if not result or "data" not in result or "createRelation" not in result["data"]:
        print("Failed to create relationship between WebsiteAnalysis and Company")
    else:
        print("Successfully created relationship between WebsiteAnalysis and Company")


async def setup_twenty_metadata(api_url: str, api_key: str) -> None:
    """
    Setup all required metadata in Twenty CRM.

    Args:
        api_url: Twenty CRM API URL
        api_key: Twenty CRM API key
    """
    connector = TwentyCRMConnector(api_url, api_key)

    try:
        # Create WebsiteAnalysis object
        website_analysis_object_id = await setup_website_analysis_object(connector)

        # Add fields to WebsiteAnalysis object
        await add_fields_to_object(
            connector, website_analysis_object_id, WEBSITE_ANALYSIS_FIELDS
        )

        # Extend Company object
        await extend_company_object(connector)

        # Create relationships
        await create_relationships(connector, website_analysis_object_id)

        print("\nMetadata setup completed successfully!")

    except Exception as e:
        print(f"Error during metadata setup: {str(e)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Setup Twenty CRM metadata")
    parser.add_argument("--api-url", required=True, help="Twenty CRM API URL")
    parser.add_argument("--api-key", required=True, help="Twenty CRM API key")

    args = parser.parse_args()

    asyncio.run(setup_twenty_metadata(args.api_url, args.api_key))
