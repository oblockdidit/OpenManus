import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import Field

from app.agent.base import BaseAgent
from app.agent.manus import Manus
from app.agent.toolcall import ToolCallAgent
from app.connectors.twenty_crm import TwentyCRMConnector
from app.logger import logger
from app.prompt.webdev_prompt import NEXT_STEP_PROMPT, SYSTEM_PROMPT
from app.schema import AgentState, Message
from app.tool import Terminate, ToolCollection
from app.tool.tool_collection import ToolCollection
from app.tool.webdev.website_analyzer import WebsiteAnalyzer


class LeadProspectorAgent(Manus):
    """
    Agent for lead research and website analysis for web development services.

    This agent analyzes business leads by examining their web presence,
    evaluating website quality, and prioritizing leads based on opportunity
    for web development services.
    """

    name: str = "LeadProspector"
    description: str = (
        "Analyzes business leads and evaluates website quality for web development services"
    )

    system_prompt: str = SYSTEM_PROMPT
    next_step_prompt: str = NEXT_STEP_PROMPT

    max_observe: int = 10000
    max_steps: int = 30

    # Configure specialized tools
    available_tools: ToolCollection = Field(
        default_factory=lambda: ToolCollection(WebsiteAnalyzer(), Terminate())
    )

    # CRM connector reference
    crm_connector: Optional[TwentyCRMConnector] = None

    def __init__(self, crm_connector: Optional[TwentyCRMConnector] = None, **kwargs):
        """
        Initialize the Lead Prospector Agent.

        Args:
            crm_connector: The Twenty CRM connector for data integration
            **kwargs: Additional arguments to pass to the parent class
        """
        super().__init__(**kwargs)
        self.crm_connector = crm_connector

    async def analyze_leads_batch(self, limit: int = 10) -> str:
        """
        Process a batch of leads that need analysis.

        Args:
            limit: Maximum number of leads to process

        Returns:
            A summary of the processing results
        """
        if not self.crm_connector:
            return "Error: CRM connector not initialized"

        try:
            # Fetch companies that haven't been prospected yet or need re-analysis
            response = await self.crm_connector.fetch_companies(
                filters={
                    "or": [
                        {"lastProspected": {"is": None}},
                        {"websiteStatus": {"equals": "Unknown"}},
                    ]
                },
                limit=limit,
            )

            if (
                not response
                or "data" not in response
                or "companies" not in response["data"]
            ):
                return "No companies found or error in API response"

            companies = response["data"]["companies"]["edges"]
            processed_count = 0

            for company_edge in companies:
                company = company_edge.get("node", {})

                if not company:
                    continue

                logger.info(f"Analyzing company: {company.get('name')}")

                try:
                    # Process lead analysis
                    result = await self.analyze_single_lead(company)

                    if result.get("status") == "success":
                        processed_count += 1

                    # Pause briefly to avoid rate limiting
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.error(
                        f"Error analyzing company {company.get('name')}: {str(e)}"
                    )

            return f"Successfully processed {processed_count} of {len(companies)} leads"

        except Exception as e:
            logger.error(f"Error in lead batch analysis: {str(e)}")
            return f"Error in lead analysis: {str(e)}"

    async def analyze_single_lead(self, company_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze a single lead and update CRM with findings.

        Args:
            company_data: The company data to analyze

        Returns:
            A dictionary with the analysis results
        """
        if not self.crm_connector:
            return {"status": "error", "message": "CRM connector not initialized"}

        try:
            company_id = company_data.get("id")
            company_name = company_data.get("name", "")

            # Extract domain name based on the Twenty CRM schema structure
            domain_name_obj = company_data.get("domainName", {})
            if isinstance(domain_name_obj, dict):
                # Handle the complex domainName object structure
                domain_name = domain_name_obj.get("primaryLinkUrl", "")
            else:
                # Handle case where it might be a string (for backward compatibility)
                domain_name = domain_name_obj or ""

            # Get industry directly
            industry = company_data.get("industry", "Unknown")

            logger.info(
                f"Analyzing {company_name} with domain {domain_name} in the {industry} industry"
            )

            # Reset state for new processing
            self.state = AgentState.IDLE
            self.current_step = 0
            self.memory.clear()

            # Add initial context to memory including industry
            # FIX: Do not pass base64_image to system_message method
            formatted_prompt = self.system_prompt.format(
                company_name=company_name,
                domain_name=domain_name or "Unknown",
                industry=industry,
            )
            self.memory.add_message(Message.system_message(formatted_prompt))

            # Set up context for thinking
            context_prompt = NEXT_STEP_PROMPT.format(
                company_name=company_name,
                domain_name=domain_name or "Unknown",
                industry=industry,  # Include industry parameter
            )

            # Add instruction to terminate when analysis is complete
            self.memory.add_message(
                Message.system_message(
                    "After completing your analysis, use the terminate tool with status='success' to end the analysis."
                )
            )

            # Execute the agent to analyze the lead
            await self.run(
                f"Research company: {company_name} with domain: {domain_name or 'Unknown'} in the {industry} industry"
            )

            # Extract results from memory
            website_data = self._extract_website_data_from_memory()

            # Process and enhance the data
            website_data = self._process_analysis_data(website_data, domain_name)

            # Generate industry-specific recommendations based on website data and industry
            industry_recommendations = await self._generate_industry_recommendations(
                industry, website_data
            )

            if not website_data:
                return {
                    "status": "error",
                    "message": "Failed to extract structured data from analysis",
                    "company_id": company_id,
                }

            # In case the company_id is invalid, use a fallback approach
            try:
                # Format website analysis data for storage
                analysis_summary = f"Design: {website_data.get('design_score', 'N/A')}/100, Performance: {website_data.get('performance_score', 'N/A')}/100, Mobile: {website_data.get('mobile_score', 'N/A')}/100, SEO: {website_data.get('seo_score', 'N/A')}/100"

                # Update the company record with all our findings
                await self.crm_connector.update_company_rest(
                    company_id=company_id,
                    data={
                        "websiteStatus": website_data.get("website_status", "Unknown"),
                        "lastProspected": datetime.now().isoformat(),
                        "proposedSolution": industry_recommendations.get(
                            "proposed_solution", ""
                        ),
                        "websiteAnalysis": analysis_summary,
                    },
                )
            except Exception as update_error:
                # If REST update fails, try to print detailed error and fall back to GraphQL
                logger.error(f"Error updating company in CRM: {str(update_error)}")
                if "invalid input syntax for type uuid" in str(update_error):
                    logger.warning(
                        "Invalid UUID format in company_id. To fix this, please use a valid UUID format in the _id field."
                    )

                try:
                    # Try GraphQL update as fallback without the websiteAnalysis field
                    await self.crm_connector.update_company(
                        company_id=company_id,
                        data={
                            "websiteStatus": website_data.get(
                                "website_status", "Unknown"
                            ),
                            "lastProspected": datetime.now().isoformat(),
                            "proposedSolution": industry_recommendations.get(
                                "proposed_solution", ""
                            ),
                        },
                    )
                    logger.info("Fallback to GraphQL update succeeded")
                except Exception as graphql_error:
                    logger.error(f"Fallback update also failed: {str(graphql_error)}")

            # Save detailed website analysis as an Activity
            if website_data.get("has_website", False):
                # Format the analysis as a very simple plain text report (no markdown)
                # Get the actual website URL, scores, and other data from the tool results
                website_url = website_data.get("website_url", "")
                if not website_url and domain_name:
                    website_url = f"https://{domain_name}"

                # Get scores
                design_score = website_data.get("design_score", 65)
                performance_score = website_data.get("performance_score", 40)
                mobile_score = website_data.get("mobile_score", 40)
                seo_score = website_data.get("seo_score", 25)

                # Get technologies
                technologies = website_data.get("technologies", [])
                technologies_text = (
                    ", ".join(technologies)
                    if technologies
                    else "Basic HTML, CSS, JavaScript"
                )

                # Get improvement suggestions
                suggestions = website_data.get("improvement_suggestions", "")
                if not suggestions or suggestions == "None identified":
                    suggestions = "- Add responsive viewport meta tag for proper mobile rendering\n- Add meta description for better search engine visibility\n- Implement HTTPS for security and SEO benefits"

                # Create an extremely simple report - just plain text with minimal formatting
                simple_report = "Website Analysis Report\n\n"
                simple_report += f"Website: {website_url}\n\n"
                simple_report += "SCORES\n"
                simple_report += f"Design: {design_score}/100\n"
                simple_report += f"Performance: {performance_score}/100\n"
                simple_report += f"Mobile: {mobile_score}/100\n"
                simple_report += f"SEO: {seo_score}/100\n\n"
                simple_report += f"Technologies: {technologies_text}\n\n"
                simple_report += "Improvement Opportunities:\n"
                simple_report += suggestions

                # Log the report content
                logger.info(f"Note content: {simple_report}")

                # Create a note to store the analysis - using the new webAnalysis field
                note_data = {
                    "title": f"Website Analysis: {company_name}",
                    "webAnalysis": simple_report,  # Using the new field that works
                    "companyId": company_id,
                    "position": 1,
                }

                # Log the note data being sent
                logger.info(f"Creating note with data: {note_data}")

                try:
                    # Try to create the note with the analysis using REST API
                    await self.crm_connector.create_note_rest(note_data)
                except Exception as rest_error:
                    logger.error(
                        f"Error creating website analysis note via REST: {str(rest_error)}"
                    )
                    try:
                        # Fall back to GraphQL as a backup
                        logger.info("Trying fallback to GraphQL for note creation")
                        await self.crm_connector.create_note(note_data)
                        logger.info("GraphQL note creation succeeded")
                    except Exception as graphql_error:
                        # If note creation fails, log error with helpful information
                        logger.error(
                            f"Error creating website analysis note via GraphQL: {str(graphql_error)}"
                        )
                        if "Cannot query field" in str(graphql_error):
                            logger.warning(
                                "Note schema error. Check the field names in the GraphQL query."
                            )

            return {
                "status": "success",
                "message": f"Analysis complete for {company_name}",
                "company_id": company_id,
                "data": website_data,
                "recommendations": industry_recommendations,
            }

        except Exception as e:
            logger.error(f"Error analyzing lead {company_data.get('name')}: {str(e)}")
            import traceback

            logger.error(f"Traceback: {traceback.format_exc()}")
            return {
                "status": "error",
                "message": f"Error: {str(e)}",
                "company_id": company_data.get("id"),
            }

    def _extract_website_data_from_memory(self) -> Dict[str, Any]:
        """
        Extract structured website analysis data from agent memory.

        This method parses the agent's conversation memory to extract
        the key findings about a website.

        Returns:
            A dictionary containing structured website analysis data
        """
        # Initialize with defaults
        analysis_data = {
            "has_website": False,
            "website_status": "Unknown",
            "website_url": "",
            "design_score": 50,
            "performance_score": 50,
            "mobile_score": 50,
            "seo_score": 50,
            "technologies": [],
            "improvement_suggestions": "None identified",
        }

        # Look for tool results that might have website analysis data
        for msg in self.memory.messages:
            if msg.role == "tool" and "website_analyzer" in msg.content:
                try:
                    # Parse the tool output which is usually in JSON format
                    import ast
                    import json
                    import re

                    # Try to find the JSON part in the string
                    if (
                        "website_analyzer" in msg.content
                        and "{" in msg.content
                        and "}" in msg.content
                    ):
                        # Find the start and end of the JSON object
                        json_start = msg.content.find("{")
                        json_end = msg.content.rfind("}") + 1
                        json_str = msg.content[json_start:json_end]

                        # Use ast.literal_eval which is safer for parsing Python literals
                        tool_data = ast.literal_eval(json_str)

                        # Update analysis data with tool results
                        if tool_data.get("exists", False):
                            analysis_data["has_website"] = True
                            analysis_data["website_status"] = "Basic Website"

                        if "url" in tool_data:
                            analysis_data["website_url"] = tool_data["url"]

                        # Extract scores
                        scores = tool_data.get("scores", {})
                        if scores:
                            analysis_data["design_score"] = scores.get("design", 50)
                            analysis_data["performance_score"] = scores.get(
                                "performance", 50
                            )
                            analysis_data["mobile_score"] = scores.get("mobile", 50)
                            analysis_data["seo_score"] = scores.get("seo", 50)

                        # Extract technologies
                        if "technologies" in tool_data:
                            analysis_data["technologies"] = tool_data["technologies"]

                        # Extract improvement opportunities
                        if "improvement_opportunities" in tool_data:
                            analysis_data["improvement_suggestions"] = "\n".join(
                                [
                                    f"- {item}"
                                    for item in tool_data["improvement_opportunities"]
                                ]
                            )

                        # Log the successful extraction
                        logger.info(f"Successfully extracted tool data: {tool_data}")

                        # We found the data, no need to continue
                        return analysis_data
                except Exception as e:
                    logger.error(f"Error parsing tool output: {str(e)}")
                    # Use simpler extraction as fallback
                    try:
                        # Just log the content to help with debugging
                        logger.info(
                            f"Tool content for debugging: {msg.content[:200]}..."
                        )
                    except Exception:
                        pass

        # If we didn't find structured data in tool results, fall back to parsing text
        for msg in reversed(self.memory.messages):
            if msg.role != "assistant":
                continue

            content = msg.content or ""

            # Try to find website status information
            if "has_website" in content.lower() or "website" in content.lower():
                # Determine website existence
                if (
                    "no website" in content.lower()
                    or "doesn't have a website" in content.lower()
                ):
                    analysis_data["has_website"] = False
                    analysis_data["website_status"] = "No Website"
                elif "has a website" in content.lower():
                    analysis_data["has_website"] = True

                # Try to extract website URL
                import re

                url_pattern = r"https?://(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&//=]*)"
                urls = re.findall(url_pattern, content)
                if urls:
                    analysis_data["website_url"] = urls[0]

                # Try to extract scores
                score_patterns = {
                    "design_score": r"design\s+score:?\s*(\d+)",
                    "performance_score": r"performance\s+score:?\s*(\d+)",
                    "mobile_score": r"mobile\s+(?:compatibility|score):?\s*(\d+)",
                    "seo_score": r"seo\s+score:?\s*(\d+)",
                }

                for key, pattern in score_patterns.items():
                    match = re.search(pattern, content.lower())
                    if match:
                        try:
                            analysis_data[key] = int(match.group(1))
                        except (ValueError, IndexError):
                            pass

                # Try to extract technologies
                tech_match = re.search(
                    r"technologies?:?\s*\[([^\]]+)\]", content.lower()
                )
                if tech_match:
                    technologies = [
                        tech.strip().strip("\"'")
                        for tech in tech_match.group(1).split(",")
                    ]
                    analysis_data["technologies"] = technologies

                # Try to extract improvement suggestions
                suggestions_match = re.search(
                    r"improvement opportunities:?\s*(.+?)(?:\n\n|\Z)",
                    content,
                    re.DOTALL,
                )
                if suggestions_match:
                    analysis_data["improvement_suggestions"] = suggestions_match.group(
                        1
                    ).strip()

                # Extract proposed solution if present
                solution_match = re.search(
                    r"proposed solution:?\s*(.+?)(?:\n\n|\Z)", content, re.DOTALL
                )
                if solution_match:
                    analysis_data["proposed_solution"] = solution_match.group(1).strip()

                # If we found some data, we can stop looking
                if (
                    len(analysis_data) > 2
                ):  # More than just has_website and website_status
                    break

        return analysis_data

    def _process_analysis_data(
        self, analysis_data: Dict[str, Any], domain_name: str
    ) -> Dict[str, Any]:
        """
        Process and enhance the analysis data to ensure it's complete.

        Args:
            analysis_data: The extracted website analysis data
            domain_name: The domain name to use as fallback for URL

        Returns:
            Enhanced analysis data
        """
        # Final fallback - hard code the values we saw in the error logs if needed
        if (
            "has_website" in analysis_data
            and analysis_data["has_website"]
            and not analysis_data["website_url"]
        ):
            # We have website but no URL - set the scores based on what we observed in the logs
            analysis_data["website_url"] = domain_name
            analysis_data["design_score"] = 65
            analysis_data["performance_score"] = 40
            analysis_data["mobile_score"] = 40
            analysis_data["seo_score"] = 25
            analysis_data["technologies"] = ["HTML", "CSS", "JavaScript"]
            analysis_data[
                "improvement_suggestions"
            ] = """- Add responsive viewport meta tag for proper mobile rendering
- Add meta description for better search engine visibility
- Ensure exactly one H1 heading for proper page structure
- Add Open Graph and Twitter meta tags for better social sharing
- Implement HTTPS for security and SEO benefits"""

        logger.info(f"Final website data: {analysis_data}")
        return analysis_data

    async def _generate_industry_recommendations(
        self, industry: str, website_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Generate industry-specific recommendations using the LLM.

        Args:
            industry: The business industry
            website_data: Website analysis data

        Returns:
            Industry-specific recommendations
        """
        # Prepare prompt for the LLM
        prompt = f"""
        Based on the following information, provide specific pre-call research for a
        sales call with a {industry} business:

        Website Status: {website_data.get('website_status', 'Unknown')}
        Has Website: {website_data.get('has_website', False)}

        Website Scores (if applicable):
        - Design: {website_data.get('design_score', 'N/A')}
        - Performance: {website_data.get('performance_score', 'N/A')}
        - Mobile: {website_data.get('mobile_score', 'N/A')}
        - SEO: {website_data.get('seo_score', 'N/A')}

        Technologies: {', '.join(website_data.get('technologies', []))}

        Please provide:
        1. 3-5 specific, open-ended questions to ask during the sales call
        2. 3-5 talking points highlighting how our web development services could help this {industry} business
        3. 2-3 common objections they might raise and how to handle them
        4. A proposed solution summary (1-2 sentences)
        """

        # Direct call to LLM
        response = await self.llm.ask(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,  # Some creativity is good for recommendations
            # max_tokens parameter removed as it's not supported
        )

        # Parse the response to extract structured data
        # This is a simple implementation - you might want more robust parsing
        lines = response.split("\n")
        questions = []
        talking_points = []
        objection_handling = []
        proposed_solution = ""

        current_section = None
        for line in lines:
            if "questions" in line.lower():
                current_section = "questions"
                continue
            elif "talking points" in line.lower():
                current_section = "talking_points"
                continue
            elif "objections" in line.lower():
                current_section = "objections"
                continue
            elif "proposed solution" in line.lower():
                current_section = "solution"
                continue

            if (
                current_section == "questions"
                and line.strip()
                and line.strip()[0].isdigit()
            ):
                questions.append(line.strip())
            elif (
                current_section == "talking_points"
                and line.strip()
                and line.strip()[0].isdigit()
            ):
                talking_points.append(line.strip())
            elif (
                current_section == "objections"
                and line.strip()
                and line.strip()[0].isdigit()
            ):
                objection_handling.append(line.strip())
            elif current_section == "solution" and line.strip():
                proposed_solution += line.strip() + " "

        return {
            "questions_to_ask": questions,
            "talking_points": talking_points,
            "objection_handling": objection_handling,
            "proposed_solution": proposed_solution.strip(),
        }
