import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import httpx


class TwentyCRMConnector:
    """Connector for Twenty CRM API integration"""

    def __init__(self, api_url: str, api_key: str):
        """
        Initialize the Twenty CRM connector.

        Args:
            api_url: The base URL for the Twenty CRM API
            api_key: The API key for authentication
        """
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self.retry_attempts = 3
        self.retry_delay = 1  # seconds

    async def execute_query(
        self, query: str, variables: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute a GraphQL query against Twenty CRM.

        Args:
            query: The GraphQL query string
            variables: Optional variables for the query

        Returns:
            The JSON response from the API

        Raises:
            Exception: If the API request fails
        """
        for attempt in range(self.retry_attempts):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{self.api_url}/graphql",
                        headers=self.headers,
                        json={"query": query, "variables": variables or {}},
                        timeout=30.0,
                    )

                    if response.status_code == 429:  # Rate limiting
                        retry_after = int(response.headers.get("Retry-After", 5))
                        await asyncio.sleep(retry_after)
                        continue

                    if response.status_code != 200:
                        error_message = f"API request failed with status {response.status_code}: {response.text}"
                        print(f"Error: {error_message}")
                        if attempt == self.retry_attempts - 1:
                            raise Exception(error_message)
                        # Exponential backoff
                        await asyncio.sleep(self.retry_delay * (2**attempt))
                        continue

                    result = response.json()
                    if "errors" in result:
                        error_message = f"GraphQL error: {json.dumps(result['errors'])}"
                        print(f"Error: {error_message}")
                        if attempt == self.retry_attempts - 1:
                            raise Exception(error_message)
                        await asyncio.sleep(self.retry_delay * (2**attempt))
                        continue

                    return result
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
                if attempt == self.retry_attempts - 1:
                    raise Exception(f"Connection error: {str(e)}")
                await asyncio.sleep(self.retry_delay * (2**attempt))

        raise Exception(f"Failed after {self.retry_attempts} attempts")

    async def fetch_companies(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 50,
        cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Fetch companies matching the specified criteria.

        Args:
            filters: Optional filters to apply
            limit: Maximum number of results to return
            cursor: Pagination cursor

        Returns:
            The list of companies and pagination info
        """
        query = """
        query GetCompanies($first: Int, $after: String, $filter: CompanyFilterInput, $orderBy: [CompanyOrderByInput!]) {
          companies(first: $first, after: $after, filter: $filter, orderBy: $orderBy) {
            edges {
              node {
                id
                name
                domainName {
                  primaryLinkUrl
                  primaryLinkLabel
                }
                address {
                  addressStreet1
                  addressStreet2
                  addressCity
                  addressState
                  addressPostcode
                  addressCountry
                }
                industry
                websiteStatus
                lastProspected
                proposedSolution
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

        variables = {
            "first": limit,
            "after": cursor,
            "filter": filters or {},
            "orderBy": [{"createdAt": "Desc"}],  # Changed to proper case - Desc not DESC
        }

        return await self.execute_query(query, variables)

    async def get_company(self, company_id: str) -> Dict[str, Any]:
        """
        Get a specific company by ID.

        Args:
            company_id: The ID of the company to fetch

        Returns:
            The company data
        """
        query = """
        query GetCompany($id: ID!) {
          company(id: $id) {
            id
            name
            domainName {
              primaryLinkUrl
              primaryLinkLabel
            }
            address {
              addressStreet1
              addressStreet2
              addressCity
              addressState
              addressPostcode
              addressCountry
            }
            industry
            websiteStatus
            lastProspected
            proposedSolution
          }
        }
        """

        variables = {"id": company_id}

        return await self.execute_query(query, variables)

    async def create_company(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new company in Twenty CRM.

        Args:
            data: The company data to create

        Returns:
            The created company data
        """
        query = """
        mutation CreateCompany($data: CompanyCreateInput!) {
          createCompany(data: $data) {
            id
            name
            domainName {
              primaryLinkUrl
              primaryLinkLabel
            }
            address {
              addressStreet1
              addressCity
              addressState
              addressPostcode
              addressCountry
            }
            industry
            websiteStatus
            lastProspected
            proposedSolution
          }
        }
        """

        variables = {"data": data}

        return await self.execute_query(query, variables)

    async def update_company(
        self, company_id: str, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update a company in Twenty CRM.

        Args:
            company_id: The ID of the company to update
            data: The data to update

        Returns:
            The updated company data
        """
        query = """
        mutation UpdateCompany($id: ID!, $data: CompanyUpdateInput!) {
          updateCompany(id: $id, data: $data) {
            id
            name
            domainName {
              primaryLinkUrl
              primaryLinkLabel
            }
            address {
              addressStreet1
              addressCity
              addressState
              addressPostcode
              addressCountry
            }
            industry
            websiteStatus
            lastProspected
            proposedSolution
          }
        }
        """

        variables = {"id": company_id, "data": data}

        return await self.execute_query(query, variables)
        
    async def update_company_rest(
        self, company_id: str, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update a company in Twenty CRM using the REST API.

        Args:
            company_id: The ID of the company to update
            data: The data to update

        Returns:
            The updated company data
        """
        try:
            url = f"{self.api_url}/rest/companies/{company_id}"
            
            # Ensure proper fields are present
            update_data = {}
            
            # Only include fields that are being updated
            for key, value in data.items():
                if key in ["websiteStatus", "lastProspected", "proposedSolution", "websiteAnalysis"]:
                    update_data[key] = value
            
            if not update_data:
                return {"message": "No fields to update"}
            
            async with httpx.AsyncClient() as client:
                response = await client.patch(
                    url,
                    headers=self.headers,
                    json=update_data,
                    timeout=30.0,
                )
                
                if response.status_code not in [200, 201, 202]:
                    error_message = f"REST API request failed with status {response.status_code}: {response.text}"
                    print(f"Error: {error_message}")
                    raise Exception(error_message)
                
                result = response.json()
                return result
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
            raise Exception(f"Connection error: {str(e)}")
        except Exception as e:
            raise Exception(f"Error updating company via REST: {str(e)}")
    
    async def create_note(
        self, note_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create a note in Twenty CRM using GraphQL and link it to a company.

        Args:
            note_data: The note data to create

        Returns:
            The created note data
        """
        # Extract company ID but don't include it in note creation
        company_id = note_data.pop("companyId", None) if "companyId" in note_data else None
        
        # Step 1: Create the note
        create_note_query = """
        mutation CreateNote($data: NoteCreateInput!) {
          createNote(data: $data) {
            id
            title
            bodyV2 {
              blocknote
              markdown
            }
            webAnalysis
          }
        }
        """

        # Print note data for debugging
        print(f"GraphQL note data: {note_data}")
        
        variables = {
            "data": {
                "position": note_data.get("position", 1),
                "title": note_data.get("title", ""),
                "bodyV2": {
                    "blocknote": "",
                    "markdown": ""
                },
                "webAnalysis": note_data.get("webAnalysis", "")
            }
        }
        
        # Print variables for debugging
        print(f"GraphQL variables: {variables}")

        result = await self.execute_query(create_note_query, variables)
        
        # Extract note ID from response
        note_id = result.get("data", {}).get("createNote", {}).get("id")
        
        if not note_id:
            raise Exception("Failed to get note ID from GraphQL response")
        
        # Step 2: Create note target relationship if company ID was provided
        if company_id:
            create_target_query = """
            mutation CreateNoteTarget($data: NoteTargetCreateInput!) {
              createNoteTarget(data: $data) {
                id
                note {
                  id
                }
                company {
                  id
                }
              }
            }
            """
            
            target_variables = {
                "data": {
                    "noteId": note_id,
                    "companyId": company_id
                }
            }
            
            await self.execute_query(create_target_query, target_variables)
        
        return result
    
    async def create_note_rest(
        self, note_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create a note in Twenty CRM using the REST API and link it to a company.

        Args:
            note_data: The note data to create

        Returns:
            The created note data
        """
        try:
            # Step 1: Create the note first
            url = f"{self.api_url}/rest/notes"
            
            # Extract company ID but don't include it in the note creation payload
            company_id = note_data.pop("companyId", None) if "companyId" in note_data else None
            
            # Debug print to log the note_data and see what's arriving
            print(f"Creating note with data: {note_data}")
            
            # Prepare the note data following the API schema
            rest_note_data = {
                "position": note_data.get("position", 1),
                "title": note_data.get("title", ""),
                "bodyV2": {
                    "blocknote": "",
                    "markdown": ""
                },
                "webAnalysis": note_data.get("webAnalysis", ""),  # Use the new field
                "createdBy": {
                    "source": "EMAIL"
                }
            }
            
            # Debug the composed data
            print(f"Sending to API: {rest_note_data}")
            
            async with httpx.AsyncClient() as client:
                # Create the note
                response = await client.post(
                    url,
                    headers=self.headers,
                    json=rest_note_data,
                    timeout=30.0,
                )
                
                if response.status_code not in [200, 201, 202]:
                    error_message = f"REST API request failed with status {response.status_code}: {response.text}"
                    print(f"Error: {error_message}")
                    raise Exception(error_message)
                
                # Extract the created note ID
                note_result = response.json()
                # Debug the response
                print(f"Note creation response: {note_result}")
                
                # The response format might be different than expected, try different paths
                note_id = None
                if "data" in note_result and "createNote" in note_result["data"]:
                    note_id = note_result["data"]["createNote"].get("id")
                elif "id" in note_result:
                    note_id = note_result["id"]
                
                if not note_id:
                    print(f"Warning: Could not extract note ID from response. Response: {note_result}")
                    # If we can't get the ID, still return the result but don't try to create the noteTarget
                    return note_result
                
                # Step 2: If we have a company ID, create the note-company relationship
                if company_id:
                    target_url = f"{self.api_url}/rest/noteTargets"
                    
                    # Create payload for noteTarget following the API schema
                    note_target_data = {
                        "noteId": note_id,
                        "companyId": company_id
                    }
                    
                    # Create the relationship
                    target_response = await client.post(
                        target_url,
                        headers=self.headers,
                        json=note_target_data,
                        timeout=30.0,
                    )
                    
                    if target_response.status_code not in [200, 201, 202]:
                        print(f"Warning: Created note but failed to link to company: {target_response.text}")
                
                return note_result
                
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
            raise Exception(f"Connection error: {str(e)}")
        except Exception as e:
            raise Exception(f"Error creating note via REST: {str(e)}")

    async def get_notes(
        self,
        company_id: Optional[str] = None,
        limit: int = 10,
        cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get notes, optionally filtered by company.

        Args:
            company_id: Optional company ID to filter by
            limit: Maximum number of results to return
            cursor: Pagination cursor

        Returns:
            The list of notes
        """
        query = """
        query GetNotes($filter: NoteFilterInput, $first: Int, $after: String) {
          notes(filter: $filter, first: $first, after: $after) {
            edges {
              node {
                id
                title
                bodyV2 {
                  blocknote
                  markdown
                }
                webAnalysis
                createdAt
                updatedAt
                position
              }
              cursor
            }
            pageInfo {
              hasNextPage
              endCursor
            }
          }
        }
        """

        variables = {
            "first": limit,
            "after": cursor,
            "filter": {"companyId": {"equals": company_id}} if company_id else {},
        }

        return await self.execute_query(query, variables)

    async def register_webhook(
        self,
        target_url: str,
        operations: Optional[List[str]] = None,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Register a webhook for event notifications.

        Args:
            target_url: The URL to send webhook events to
            operations: List of operations to trigger the webhook (default: all operations)
            description: Optional description for the webhook

        Returns:
            The created webhook data
        """
        query = """
        mutation CreateWebhook($data: WebhookCreateInput!) {
          createWebhook(data: $data) {
            id
            targetUrl
            operations
            description
          }
        }
        """

        variables = {
            "data": {
                "targetUrl": target_url,
                "operations": operations or ["*.*"],  # Default to all operations
                "description": description or "OpenManus integration webhook",
            }
        }

        return await self.execute_query(query, variables)

    async def list_webhooks(self) -> Dict[str, Any]:
        """
        List all registered webhooks.

        Returns:
            The list of webhooks
        """
        query = """
        query ListWebhooks {
          webhooks {
            edges {
              node {
                id
                targetUrl
                operations
                description
              }
            }
          }
        }
        """

        return await self.execute_query(query)

    async def delete_webhook(self, webhook_id: str) -> Dict[str, Any]:
        """
        Delete a webhook.

        Args:
            webhook_id: The ID of the webhook to delete

        Returns:
            The result of the deletion operation
        """
        query = """
        mutation DeleteWebhook($id: ID!) {
          deleteWebhook(id: $id) {
            id
          }
        }
        """

        variables = {"id": webhook_id}

        return await self.execute_query(query, variables)

    async def create_object_metadata(
        self, object_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create custom object metadata in Twenty CRM.

        Args:
            object_metadata: The object metadata to create

        Returns:
            The created object metadata
        """
        query = """
        mutation CreateObjectMetadata($input: CreateObjectInput!) {
          createObject(input: $input) {
            id
            nameSingular
            namePlural
            labelSingular
            labelPlural
            description
            icon
          }
        }
        """

        variables = {"input": object_metadata}

        return await self.execute_query(query, variables)

    async def add_field_to_object(
        self, object_id: str, field_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Add a field to an object in Twenty CRM.

        Args:
            object_id: The ID of the object to add the field to
            field_metadata: The field metadata to create

        Returns:
            The created field metadata
        """
        query = """
        mutation AddFieldToObject($input: CreateFieldInput!) {
          createField(input: $input) {
            id
            name
            label
            type
            description
            icon
          }
        }
        """

        variables = {"input": {"objectId": object_id, **field_metadata}}

        return await self.execute_query(query, variables)

    async def get_workflow_stats(self) -> Dict[str, Any]:
        """
        Get workflow statistics for web development leads.

        Returns:
            Statistics about lead processing
        """
        query = """
        query GetWorkflowStats {
          companies(filter: { lastProspected: { is: null } }) {
            totalCount
            aggregates {
              groupBy {
                webDevPriority
              }
              count
            }
          }
        }
        """

        result = await self.execute_query(query)

        # Process the results into a more usable format
        stats = {
            "totalProspectedLeads": 0,
            "priorityDistribution": {},
            "timestamp": datetime.now().isoformat(),
        }

        if result and "data" in result and "companies" in result["data"]:
            data = result["data"]["companies"]
            stats["totalProspectedLeads"] = data.get("totalCount", 0)

            if "aggregates" in data:
                for item in data["aggregates"]:
                    priority = item["groupBy"]["webDevPriority"] or "Unknown"
                    stats["priorityDistribution"][priority] = item["count"]

        return stats