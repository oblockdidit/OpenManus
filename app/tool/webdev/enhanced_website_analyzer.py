import asyncio
import base64
import json
import os
import random
import re
import time
from typing import Any, ClassVar, Dict, List, Optional, Set, Union
from urllib.parse import urljoin, urlparse

from app.logger import logger
from app.tool.base import BaseTool
from app.tool.browser_use_tool import BrowserUseTool


class EnhancedWebsiteAnalyzer(BaseTool):
    """
    Enhanced tool for analyzing websites to determine quality and improvement opportunities.

    This tool uses browser automation to:
    - Crawl multiple pages of a website
    - Capture screenshots of key pages
    - Extract and analyze page content
    - Check SEO factors (meta tags, headings, etc.)
    - Test mobile compatibility
    - Analyze performance
    - Detect technologies used
    - Generate improvement recommendations
    """

    name: str = "website_analyzer"
    description: str = (
        "Performs comprehensive website analysis including crawling, screenshots, content analysis, "
        "SEO analysis, mobile testing, and performance measurements"
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Website URL to analyze",
            },
            "company_name": {
                "type": "string",
                "description": "Company name for context",
                "default": "",
            },
            "depth": {
                "type": "integer",
                "description": "Analysis depth (1-5, with 5 being most thorough)",
                "default": 3,
            },
            "max_pages": {
                "type": "integer",
                "description": "Maximum number of pages to analyze",
                "default": 5,
            },
            "save_screenshots": {
                "type": "boolean",
                "description": "Whether to save screenshots of analyzed pages",
                "default": True,
            },
        },
        "required": ["url"],
    }

    # Define data storage directories with proper annotation
    SCREENSHOTS_DIR: ClassVar[str] = "website_analysis_screenshots"

    # Ensure directories exist
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Create screenshots directory if it doesn't exist
        os.makedirs(self.SCREENSHOTS_DIR, exist_ok=True)

    async def execute(
        self,
        url: str,
        company_name: str = "",
        depth: int = 3,
        max_pages: int = 5,
        save_screenshots: bool = True,
    ) -> Dict[str, Any]:
        """
        Execute comprehensive website analysis.

        Args:
            url: The website URL to analyze
            company_name: Optional company name for context
            depth: Analysis depth level (1-5)
            max_pages: Maximum number of pages to analyze
            save_screenshots: Whether to save screenshots of analyzed pages

        Returns:
            Dictionary containing analysis results
        """
        browser_tool = None
        try:
            # Validate URL format
            if not url.startswith(("http://", "https://")):
                url = "https://" + url

            # Create browser tool for navigation
            browser_tool = BrowserUseTool()

            # Results object
            results = {
                "url": url,
                "company_name": company_name,
                "exists": False,
                "pages_analyzed": [],
                "technologies": [],
                "scores": {},
                "improvement_opportunities": [],
                "screenshots": [],
                "content_analysis": {},
                "seo_analysis": {},
                "mobile_compatibility": {},
                "performance_metrics": {},
            }

            # Navigate to website
            logger.info(f"Navigating to {url}")
            try:
                # Navigate to the website and wait for it to load completely
                start_time = time.time()

                navigation_result = await browser_tool.execute(
                    action="go_to_url", url=url
                )

                # Wait for the page to load fully
                await browser_tool.execute(action="wait", seconds=5)

                load_time = time.time() - start_time

                # Check if website exists
                if hasattr(navigation_result, "error") and navigation_result.error:
                    logger.info(f"Website not accessible: {navigation_result.error}")
                    # Clean up
                    if browser_tool:
                        await browser_tool.cleanup()
                    return {
                        "url": url,
                        "exists": False,
                        "error": f"Website not accessible: {navigation_result.error}",
                    }

                results["exists"] = True
                results["performance_metrics"]["homepage_load_time"] = round(
                    load_time, 2
                )

            except Exception as e:
                logger.info(f"Error accessing website: {str(e)}")
                # Clean up
                if browser_tool:
                    await browser_tool.cleanup()
                return {
                    "url": url,
                    "exists": False,
                    "error": f"Error accessing website: {str(e)}",
                }

            # If we get here, the website exists and was loaded successfully

            # Get site information (domain, homepage title, etc.)
            domain = urlparse(url).netloc
            results["domain"] = domain

            # Take screenshot of homepage
            if save_screenshots:
                try:
                    homepage_screenshot = await self._take_screenshot(
                        browser_tool, "homepage", domain
                    )
                    if homepage_screenshot:
                        results["screenshots"].append(homepage_screenshot)
                except Exception as e:
                    logger.error(f"Error taking homepage screenshot: {str(e)}")

            # Collect links from homepage for further crawling
            links = await self._extract_internal_links(browser_tool, domain)

            # Detect technologies
            technologies = await self._detect_technologies(browser_tool)
            results["technologies"] = technologies

            # Analyze homepage content
            content_analysis = await self._analyze_page_content(browser_tool)
            results["content_analysis"]["homepage"] = content_analysis

            # SEO analysis
            seo_analysis = await self._analyze_seo(browser_tool)
            results["seo_analysis"]["homepage"] = seo_analysis

            # Test mobile compatibility
            mobile_results = await self._test_mobile_compatibility(browser_tool)
            results["mobile_compatibility"] = mobile_results

            # Add homepage to analyzed pages
            results["pages_analyzed"].append(
                {
                    "url": url,
                    "title": content_analysis.get("title", ""),
                    "description": content_analysis.get("description", ""),
                }
            )

            # Crawl additional pages if depth > 1
            if depth > 1 and links and max_pages > 1:
                # Prioritize key pages
                key_pages = self._prioritize_pages(links, domain)

                # Limit to max_pages
                pages_to_visit = key_pages[: min(max_pages - 1, len(key_pages))]

                # Visit and analyze each page
                for page_url in pages_to_visit:
                    page_results = await self._analyze_single_page(
                        browser_tool, page_url, domain, save_screenshots
                    )

                    if page_results:
                        # Add to pages analyzed
                        results["pages_analyzed"].append(
                            {
                                "url": page_url,
                                "title": page_results.get("title", ""),
                                "description": page_results.get("description", ""),
                            }
                        )

                        # Add content analysis
                        page_name = self._get_page_name(page_url)
                        results["content_analysis"][page_name] = page_results.get(
                            "content", {}
                        )

                        # Add SEO analysis
                        results["seo_analysis"][page_name] = page_results.get("seo", {})

                        # Add screenshot if available
                        if "screenshot" in page_results and page_results["screenshot"]:
                            results["screenshots"].append(page_results["screenshot"])

            # Calculate scores based on comprehensive analysis
            scores = await self._calculate_scores(results)
            results["scores"] = scores

            # Generate improvement recommendations
            recommendations = await self._generate_recommendations(results)
            results["improvement_opportunities"] = recommendations

            # Cleanup browser
            if browser_tool:
                await browser_tool.cleanup()
                browser_tool = None

            # Format final results - prepare client-friendly output
            final_results = {
                "url": url,
                "exists": True,
                "scores": results["scores"],
                "technologies": results["technologies"],
                "improvement_opportunities": results["improvement_opportunities"],
                "pages_analyzed": [page["url"] for page in results["pages_analyzed"]],
                "screenshots": (
                    [s["path"] for s in results["screenshots"]]
                    if save_screenshots
                    else []
                ),
                "details": {
                    "content_summary": self._summarize_content(
                        results["content_analysis"]
                    ),
                    "seo_issues": self._summarize_seo_issues(results["seo_analysis"]),
                    "mobile_compatibility": results["mobile_compatibility"],
                    "performance_metrics": results["performance_metrics"],
                },
            }

            return final_results

        except Exception as e:
            logger.error(f"Error analyzing website {url}: {str(e)}")
            # Make sure to clean up
            if browser_tool:
                try:
                    await browser_tool.cleanup()
                except Exception:
                    pass
            return {"url": url, "exists": False, "error": f"Analysis error: {str(e)}"}

    async def _analyze_single_page(
        self,
        browser_tool: BrowserUseTool,
        page_url: str,
        domain: str,
        save_screenshots: bool = True,
    ) -> Dict[str, Any]:
        """Analyze a single page of the website."""
        try:
            # Navigate to page
            start_time = time.time()
            await browser_tool.execute(action="go_to_url", url=page_url)

            # Wait for the page to load fully
            await browser_tool.execute(action="wait", seconds=3)

            load_time = time.time() - start_time

            # Analyze content
            content_analysis = await self._analyze_page_content(browser_tool)

            # SEO analysis
            seo_analysis = await self._analyze_seo(browser_tool)

            # Take screenshot if enabled
            screenshot_info = None
            if save_screenshots:
                page_name = self._get_page_name(page_url)
                screenshot_info = await self._take_screenshot(
                    browser_tool, page_name, domain
                )

            return {
                "url": page_url,
                "title": content_analysis.get("title", ""),
                "description": content_analysis.get("description", ""),
                "load_time": round(load_time, 2),
                "content": content_analysis,
                "seo": seo_analysis,
                "screenshot": screenshot_info,
            }

        except Exception as e:
            logger.error(f"Error analyzing page {page_url}: {str(e)}")
            return None

    async def _take_screenshot(self, browser_tool: BrowserUseTool, page_name: str, domain: str) -> Dict[str, Any]:
        """Take a screenshot of the current page."""
        try:
            # Get the current state which includes a screenshot
            try:
                state = await browser_tool.get_current_state()
            except Exception as e:
                logger.error(f"Error getting current state for screenshot: {str(e)}")
                return None

            if not state:
                logger.warning("Browser state is None, cannot take screenshot")
                return None

            if not hasattr(state, 'base64_image') or not state.base64_image:
                logger.warning("No base64_image in browser state, cannot take screenshot")
                return None

            # Generate filename based on domain and page name
            filename = f"{domain}_{page_name}_{int(time.time())}.jpg"
            filepath = os.path.join(self.SCREENSHOTS_DIR, filename)

            # Save screenshot to disk
            image_data = base64.b64decode(state.base64_image)
            with open(filepath, "wb") as f:
                f.write(image_data)

            return {"page_name": page_name, "path": filepath, "timestamp": time.time()}

        except Exception as e:
            logger.error(f"Error taking screenshot of {page_name}: {str(e)}")
            return None

    async def _extract_internal_links(self, browser_tool: BrowserUseTool, domain: str) -> List[str]:
        """Extract internal links from the current page."""
        try:
            # Extract all links using JavaScript
            page_info = await browser_tool.execute(
                action="extract_content",
                goal="Extract all links (a href) from the page",
            )

            if not page_info:
                logger.warning("Browser tool returned None for extract_content")
                return []

            if not hasattr(page_info, "output") or not page_info.output:
                logger.warning("Browser tool output is None or missing")
                return []

            # Parse the JSON output
            try:
                output_json = json.loads(
                    page_info.output.replace("Extracted from page:", "").strip()
                )
                content_text = output_json.get("extracted_content", {}).get("text", "")
            except Exception:
                content_text = page_info.output

            # Use regex to extract URLs
            url_pattern = r"https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+"
            urls = re.findall(url_pattern, content_text)

            # Filter for internal links only
            internal_links = [url for url in urls if domain in url]

            # Remove duplicates
            unique_links = list(set(internal_links))

            return unique_links

        except Exception as e:
            logger.error(f"Error extracting links: {str(e)}")
            return []

    async def _detect_technologies(self, browser_tool: BrowserUseTool) -> List[str]:
        """Detect technologies used by the website."""
        try:
            result = await browser_tool.execute(
                action="extract_content",
                goal="Detect technologies used by this website including frameworks, libraries, CMS, etc.",
            )

            if not result or not hasattr(result, "output"):
                return ["HTML", "CSS", "JavaScript"]

            # Parse the result
            try:
                output_json = json.loads(
                    result.output.replace("Extracted from page:", "").strip()
                )
                tech_text = output_json.get("extracted_content", {}).get("text", "")

                # Extract technologies from the text
                techs = []
                common_techs = [
                    "HTML",
                    "CSS",
                    "JavaScript",
                    "jQuery",
                    "React",
                    "Angular",
                    "Vue",
                    "WordPress",
                    "Shopify",
                    "Wix",
                    "Drupal",
                    "Magento",
                    "Bootstrap",
                    "PHP",
                    "Google Analytics",
                    "Cloudflare",
                    "Node.js",
                    "Express",
                    "Tailwind CSS",
                    "Font Awesome",
                    "GSAP",
                    "Three.js",
                ]

                for tech in common_techs:
                    if tech.lower() in tech_text.lower():
                        techs.append(tech)

                if not techs:
                    techs = ["HTML", "CSS", "JavaScript"]

                return techs

            except Exception:
                # Fallback to basics
                return ["HTML", "CSS", "JavaScript"]

        except Exception as e:
            logger.error(f"Error detecting technologies: {str(e)}")
            return ["HTML", "CSS", "JavaScript"]

    async def _analyze_page_content(self, browser_tool: BrowserUseTool) -> Dict[str, Any]:
        """Analyze the content of the current page."""
        try:
            # Extract content using the browser tool
            content_result = await browser_tool.execute(
                action="extract_content",
                goal="Extract the main content of the page including title, headings, paragraphs, and meta description",
            )

            if not content_result:
                logger.warning("Browser tool returned None for content extraction")
                return {}

            if not hasattr(content_result, "output") or not content_result.output:
                logger.warning("Browser tool output is None or missing for content extraction")
                return {}

            # Parse the result
            try:
                output_json = json.loads(
                    content_result.output.replace("Extracted from page:", "").strip()
                )
                content_text = output_json.get("extracted_content", {}).get("text", "")
            except Exception:
                content_text = content_result.output

            # Execute script to get content metrics
            state = await browser_tool.get_current_state()

            # Combine the information
            content_analysis = {
                "text_sample": (
                    content_text[:500] + "..."
                    if len(content_text) > 500
                    else content_text
                ),
                "title": None,
                "description": None,
                "word_count": 0,
                "has_contact_info": False,
            }

            # Extract additional info from the state
            if state and hasattr(state, "output"):
                try:
                    state_data = json.loads(state.output)
                    content_analysis["title"] = state_data.get("title", "")
                    content_analysis["url"] = state_data.get("url", "")
                except Exception:
                    pass

            # Extract structured data from content text
            if "title:" in content_text.lower():
                title_match = re.search(
                    r"title:\s*([^\n]+)", content_text, re.IGNORECASE
                )
                if title_match:
                    content_analysis["title"] = title_match.group(1).strip()

            if "description:" in content_text.lower():
                desc_match = re.search(
                    r"description:\s*([^\n]+)", content_text, re.IGNORECASE
                )
                if desc_match:
                    content_analysis["description"] = desc_match.group(1).strip()

            # Estimate word count
            content_analysis["word_count"] = len(content_text.split())

            # Check for contact information
            phone_pattern = r"[(]?[0-9]{3}[)]?[-. ]?[0-9]{3}[-. ]?[0-9]{4}"
            email_pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"

            has_phone = bool(re.search(phone_pattern, content_text))
            has_email = bool(re.search(email_pattern, content_text))

            content_analysis["has_contact_info"] = has_phone or has_email

            return content_analysis

        except Exception as e:
            logger.error(f"Error analyzing page content: {str(e)}")
            return {}

    async def _analyze_seo(self, browser_tool: BrowserUseTool) -> Dict[str, Any]:
        """Analyze SEO factors of the current page."""
        try:
            # Extract SEO data
            seo_result = await browser_tool.execute(
                action="extract_content",
                goal="Analyze SEO factors including meta tags, headings, links, and more",
            )

            if not seo_result:
                logger.warning("Browser tool returned None for SEO analysis")
                return {}

            if not hasattr(seo_result, "output") or not seo_result.output:
                logger.warning("Browser tool output is None or missing for SEO analysis")
                return {}

            # Parse the result
            try:
                output_json = json.loads(
                    seo_result.output.replace("Extracted from page:", "").strip()
                )
                seo_text = output_json.get("extracted_content", {}).get("text", "")
            except Exception:
                seo_text = seo_result.output

            # State for additional info
            state = await browser_tool.get_current_state()

            # Build SEO analysis
            seo_analysis = {
                "has_title": False,
                "title_length": 0,
                "has_meta_description": False,
                "meta_description_length": 0,
                "has_h1": False,
                "has_exactly_one_h1": False,
                "images_with_alt_text_percent": 0,
                "has_mobile_viewport": False,
                "is_https": False,
                "has_social_tags": False,
                "issues": [],
            }

            # Get page URL from state
            if state and hasattr(state, "output"):
                try:
                    state_data = json.loads(state.output)
                    url = state_data.get("url", "")
                    seo_analysis["is_https"] = url.startswith("https://")
                except Exception:
                    pass

            # Extract data from SEO text
            if "title:" in seo_text.lower():
                title_match = re.search(r"title:\s*([^\n]+)", seo_text, re.IGNORECASE)
                if title_match:
                    title = title_match.group(1).strip()
                    seo_analysis["has_title"] = bool(title)
                    seo_analysis["title_length"] = len(title)

            if "description:" in seo_text.lower():
                desc_match = re.search(
                    r"description:\s*([^\n]+)", seo_text, re.IGNORECASE
                )
                if desc_match:
                    desc = desc_match.group(1).strip()
                    seo_analysis["has_meta_description"] = bool(desc)
                    seo_analysis["meta_description_length"] = len(desc)

            if "h1" in seo_text.lower():
                seo_analysis["has_h1"] = (
                    "h1" in seo_text.lower() and not "no h1" in seo_text.lower()
                )
                seo_analysis["has_exactly_one_h1"] = (
                    "exactly one h1" in seo_text.lower()
                    or "single h1" in seo_text.lower()
                )

            if "viewport" in seo_text.lower():
                seo_analysis["has_mobile_viewport"] = (
                    "viewport" in seo_text.lower()
                    and not "no viewport" in seo_text.lower()
                )

            if "og:" in seo_text.lower() or "open graph" in seo_text.lower():
                seo_analysis["has_social_tags"] = True

            # Generate SEO issues
            issues = []

            if not seo_analysis["has_title"] or seo_analysis["title_length"] < 10:
                issues.append("Missing or too short page title")
            elif seo_analysis["title_length"] > 70:
                issues.append("Page title too long (over 70 characters)")

            if not seo_analysis["has_meta_description"]:
                issues.append("Missing meta description")
            elif seo_analysis["meta_description_length"] < 50:
                issues.append("Meta description too short (under 50 characters)")
            elif seo_analysis["meta_description_length"] > 160:
                issues.append("Meta description too long (over 160 characters)")

            if not seo_analysis["has_h1"]:
                issues.append("Missing H1 heading")
            elif not seo_analysis["has_exactly_one_h1"]:
                issues.append("Multiple H1 headings (should have exactly one)")

            if not seo_analysis["has_mobile_viewport"]:
                issues.append("Missing mobile viewport meta tag")

            if not seo_analysis["is_https"]:
                issues.append("Not using HTTPS")

            if not seo_analysis["has_social_tags"]:
                issues.append("Missing social media meta tags (Open Graph/Twitter)")

            seo_analysis["issues"] = issues

            return seo_analysis

        except Exception as e:
            logger.error(f"Error analyzing SEO: {str(e)}")
            return {}

    async def _test_mobile_compatibility(self, browser_tool: BrowserUseTool) -> Dict[str, Any]:
        """Test mobile compatibility of the current page."""
        try:
            # Check for mobile-specific meta tags and responsive elements
            mobile_result = await browser_tool.execute(
                action="extract_content",
                goal="Analyze mobile compatibility including viewport meta tag, responsive design elements, and touch targets",
            )

            if not mobile_result:
                logger.warning("Browser tool returned None for mobile compatibility test")
                return {"mobile_score": 40, "issues": ["Could not analyze mobile compatibility"]}

            if not hasattr(mobile_result, "output") or not mobile_result.output:
                logger.warning("Browser tool output is None or missing for mobile compatibility test")
                return {"mobile_score": 40, "issues": ["Could not analyze mobile compatibility"]}

            # Parse the result
            try:
                output_json = json.loads(
                    mobile_result.output.replace("Extracted from page:", "").strip()
                )
                mobile_text = output_json.get("extracted_content", {}).get("text", "")
            except Exception:
                mobile_text = mobile_result.output

            # Build mobile compatibility analysis
            mobile_analysis = {
                "has_viewport_meta": False,
                "has_responsive_design": False,
                "uses_media_queries": False,
                "has_touch_friendly_elements": False,
                "mobile_score": 0,
                "issues": [],
            }

            # Extract mobile compatibility data from text
            if "viewport" in mobile_text.lower():
                mobile_analysis["has_viewport_meta"] = (
                    "viewport" in mobile_text.lower()
                    and not "no viewport" in mobile_text.lower()
                )

            if "responsive" in mobile_text.lower():
                mobile_analysis["has_responsive_design"] = (
                    "responsive" in mobile_text.lower()
                    and not "not responsive" in mobile_text.lower()
                )

            if "media queries" in mobile_text.lower() or "@media" in mobile_text:
                mobile_analysis["uses_media_queries"] = True

            # Generate mobile issues
            issues = []

            if not mobile_analysis["has_viewport_meta"]:
                issues.append("Missing viewport meta tag")

            if not mobile_analysis["has_responsive_design"]:
                issues.append("No responsive design elements detected")

            if not mobile_analysis["uses_media_queries"]:
                issues.append("No CSS media queries detected for responsive layouts")

            # Calculate mobile score (0-100)
            score = 0
            if mobile_analysis["has_viewport_meta"]:
                score += 40
            if mobile_analysis["has_responsive_design"]:
                score += 40
            if mobile_analysis["uses_media_queries"]:
                score += 20

            mobile_analysis["mobile_score"] = score
            mobile_analysis["issues"] = issues

            return mobile_analysis

        except Exception as e:
            logger.error(f"Error testing mobile compatibility: {str(e)}")
            return {
                "mobile_score": 40,
                "issues": ["Could not fully analyze mobile compatibility"],
            }

    async def _calculate_scores(self, results: Dict[str, Any]) -> Dict[str, int]:
        """Calculate scores for different aspects of the website."""
        try:
            # Design score based on content analysis
            design_score = 65  # Default starting point

            # Adjust for content quality
            content_analysis = results.get("content_analysis", {})
            if content_analysis:
                # Check homepage content
                homepage = content_analysis.get("homepage", {})
                if homepage:
                    # More content is usually better
                    if homepage.get("word_count", 0) > 300:
                        design_score += 5

                    # Having a clear title is good
                    if homepage.get("title") and len(homepage.get("title", "")) > 10:
                        design_score += 5

                    # Having a description is good
                    if (
                        homepage.get("description")
                        and len(homepage.get("description", "")) > 50
                    ):
                        design_score += 5

                    # Contact info is important
                    if homepage.get("has_contact_info"):
                        design_score += 5

            # Performance score based on load times
            performance_score = 50  # Default
            load_time = results.get("performance_metrics", {}).get(
                "homepage_load_time", 0
            )

            if load_time > 0:
                # Adjust score based on load time
                if load_time < 1.0:
                    performance_score = 90
                elif load_time < 2.0:
                    performance_score = 80
                elif load_time < 3.0:
                    performance_score = 70
                elif load_time < 4.0:
                    performance_score = 60
                else:
                    performance_score = 50

            # Mobile score from mobile analysis
            mobile_score = results.get("mobile_compatibility", {}).get(
                "mobile_score", 40
            )

            # SEO score based on SEO analysis
            seo_score = 50  # Default

            # Get all SEO issues
            all_seo_issues = []
            seo_analysis = results.get("seo_analysis", {})
            for page, analysis in seo_analysis.items():
                issues = analysis.get("issues", [])
                all_seo_issues.extend(issues)

            # Count unique issues
            unique_issues = set(all_seo_issues)

            # Adjust SEO score based on issue count
            if len(unique_issues) == 0:
                seo_score = 90
            elif len(unique_issues) <= 2:
                seo_score = 80
            elif len(unique_issues) <= 4:
                seo_score = 70
            elif len(unique_issues) <= 6:
                seo_score = 60
            elif len(unique_issues) <= 8:
                seo_score = 50
            elif len(unique_issues) <= 10:
                seo_score = 40
            else:
                seo_score = 30

            # Cap all scores to valid range
            design_score = max(0, min(100, design_score))
            performance_score = max(0, min(100, performance_score))
            mobile_score = max(0, min(100, mobile_score))
            seo_score = max(0, min(100, seo_score))

            return {
                "design": design_score,
                "performance": performance_score,
                "mobile": mobile_score,
                "seo": seo_score,
            }

        except Exception as e:
            logger.error(f"Error calculating scores: {str(e)}")
            return {"design": 65, "performance": 40, "mobile": 40, "seo": 25}

    async def _generate_recommendations(self, results: Dict[str, Any]) -> List[str]:
        """Generate improvement recommendations based on analysis results."""
        try:
            recommendations = []

            # Get scores and determine the most important areas to improve
            scores = results.get("scores", {})
            design_score = scores.get("design", 65)
            performance_score = scores.get("performance", 40)
            mobile_score = scores.get("mobile", 40)
            seo_score = scores.get("seo", 25)

            # Get issues from SEO analysis
            seo_issues = set()
            seo_analysis = results.get("seo_analysis", {})
            for page, analysis in seo_analysis.items():
                issues = analysis.get("issues", [])
                seo_issues.update(issues)

            # Get mobile issues
            mobile_issues = results.get("mobile_compatibility", {}).get("issues", [])

            # Add recommendations based on scores and issues

            # SEO recommendations
            if "Missing meta description" in seo_issues:
                recommendations.append(
                    "Add meta description for better search engine visibility"
                )

            if (
                "Missing H1 heading" in seo_issues
                or "Multiple H1 headings (should have exactly one)" in seo_issues
            ):
                recommendations.append(
                    "Ensure each page has exactly one H1 heading for proper page structure"
                )

            if "Missing social media meta tags (Open Graph/Twitter)" in seo_issues:
                recommendations.append(
                    "Add Open Graph and Twitter meta tags for better social sharing"
                )

            if "Not using HTTPS" in seo_issues:
                recommendations.append("Implement HTTPS for security and SEO benefits")

            # Mobile recommendations
            if "Missing viewport meta tag" in mobile_issues:
                recommendations.append(
                    "Add responsive viewport meta tag for proper mobile rendering"
                )

            if "No responsive design elements detected" in mobile_issues:
                recommendations.append(
                    "Implement responsive design for better mobile user experience"
                )

            if "No CSS media queries detected for responsive layouts" in mobile_issues:
                recommendations.append(
                    "Use CSS media queries to create a mobile-friendly layout"
                )

            # Performance recommendations
            if performance_score < 60:
                if (
                    results.get("performance_metrics", {}).get("homepage_load_time", 0)
                    > 3.0
                ):
                    recommendations.append(
                        "Optimize page load speed (current load time exceeds 3 seconds)"
                    )
                else:
                    recommendations.append(
                        "Improve website performance for better user experience"
                    )

            # Design and content recommendations
            homepage_content = results.get("content_analysis", {}).get("homepage", {})
            if homepage_content:
                if homepage_content.get("word_count", 0) < 200:
                    recommendations.append(
                        "Add more content to the homepage for better engagement and SEO"
                    )
                if not homepage_content.get("has_contact_info", False):
                    recommendations.append(
                        "Add contact information for better user accessibility"
                    )

            # Add technology-specific recommendations
            technologies = results.get("technologies", [])
            if "WordPress" in technologies:
                recommendations.append(
                    "Consider optimizing WordPress with caching and image optimization plugins"
                )
            if (
                "jQuery" in technologies
                and "React" not in technologies
                and "Angular" not in technologies
                and "Vue" not in technologies
            ):
                recommendations.append(
                    "Consider modernizing frontend with a current JavaScript framework"
                )

            # If few recommendations, add generic ones based on scores
            if len(recommendations) < 3:
                lowest_score_category = min(
                    [
                        ("design", design_score),
                        ("seo", seo_score),
                        ("mobile", mobile_score),
                        ("performance", performance_score),
                    ],
                    key=lambda x: x[1],
                )[0]

                if lowest_score_category == "design":
                    recommendations.append(
                        "Improve overall website design and user experience"
                    )
                elif lowest_score_category == "seo":
                    recommendations.append(
                        "Implement SEO best practices to improve search visibility"
                    )
                elif lowest_score_category == "mobile":
                    recommendations.append(
                        "Enhance mobile compatibility for better user experience on all devices"
                    )
                elif lowest_score_category == "performance":
                    recommendations.append(
                        "Optimize website performance for faster loading and better user experience"
                    )

            # Limit to top 5 recommendations
            return recommendations[:5]

        except Exception as e:
            logger.error(f"Error generating recommendations: {str(e)}")
            return [
                "Improve website design for better user experience",
                "Optimize for better search engine visibility",
                "Enhance mobile compatibility",
            ]

    def _prioritize_pages(self, links: List[str], domain: str) -> List[str]:
        """Prioritize which pages to analyze based on importance."""
        try:
            # Key page indicators in URL paths
            key_pages = {
                "contact": 10,
                "about": 9,
                "services": 8,
                "products": 8,
                "portfolio": 7,
                "gallery": 6,
                "blog": 5,
                "faq": 4,
                "pricing": 8,
                "testimonials": 6,
            }

            # Score each link
            scored_links = []
            for link in links:
                # Skip non-http links and external links
                if not link.startswith(("http://", "https://")) or domain not in link:
                    continue

                # Skip links with fragments (#) or query parameters (?)
                if "#" in link or "?" in link:
                    continue

                # Get path
                path = urlparse(link).path.lower()

                # Calculate score
                score = 0
                for key, value in key_pages.items():
                    if key in path:
                        score = value
                        break

                # Penalize deep paths (many slashes)
                depth = path.count("/")
                if depth > 2:
                    score -= depth - 2

                # Prioritize root pages
                if path == "/" or path == "":
                    score = 1  # Already analyzed homepage

                scored_links.append((link, score))

            # Sort by score (descending)
            sorted_links = [
                link
                for link, score in sorted(
                    scored_links, key=lambda x: x[1], reverse=True
                )
            ]

            # Remove duplicate paths with different protocols or trailing slashes
            normalized_links = []
            normalized_paths = set()

            for link in sorted_links:
                path = urlparse(link).path
                if path.endswith("/"):
                    path = path[:-1]

                if path not in normalized_paths:
                    normalized_paths.add(path)
                    normalized_links.append(link)

            return normalized_links

        except Exception as e:
            logger.error(f"Error prioritizing pages: {str(e)}")
            return links

    def _get_page_name(self, url: str) -> str:
        """Extract a readable name from a page URL."""
        try:
            # Parse URL
            parsed = urlparse(url)
            path = parsed.path

            # Remove trailing slash
            if path.endswith("/"):
                path = path[:-1]

            # If it's the homepage
            if path == "" or path == "/":
                return "homepage"

            # Split by slashes and get the last part
            parts = path.split("/")
            last_part = parts[-1]

            # If the last part is empty, use the one before it
            if not last_part and len(parts) > 1:
                last_part = parts[-2]

            # Remove file extension if any
            if "." in last_part:
                last_part = last_part.split(".")[0]

            # Return the name or a default if empty
            return last_part if last_part else "page"

        except Exception:
            return "page"

    def _summarize_content(self, content_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Summarize content analysis into a client-friendly format."""
        try:
            total_word_count = 0
            pages_with_content = 0
            pages_with_contact_info = 0

            for page, analysis in content_analysis.items():
                word_count = analysis.get("word_count", 0)
                total_word_count += word_count

                if word_count > 100:
                    pages_with_content += 1

                if analysis.get("has_contact_info", False):
                    pages_with_contact_info += 1

            return {
                "total_pages_analyzed": len(content_analysis),
                "total_word_count": total_word_count,
                "pages_with_substantial_content": pages_with_content,
                "pages_with_contact_info": pages_with_contact_info,
            }

        except Exception as e:
            logger.error(f"Error summarizing content: {str(e)}")
            return {"total_pages_analyzed": len(content_analysis)}

    def _summarize_seo_issues(self, seo_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Summarize SEO issues into a client-friendly format."""
        try:
            all_issues = []
            issues_by_page = {}

            for page, analysis in seo_analysis.items():
                page_issues = analysis.get("issues", [])
                all_issues.extend(page_issues)
                issues_by_page[page] = len(page_issues)

            # Count unique issues
            unique_issues = list(set(all_issues))

            # Find most common issues
            issue_counts = {}
            for issue in all_issues:
                issue_counts[issue] = issue_counts.get(issue, 0) + 1

            sorted_issues = sorted(
                issue_counts.items(), key=lambda x: x[1], reverse=True
            )
            top_issues = [issue for issue, count in sorted_issues[:3]]

            return {
                "total_issues_found": len(all_issues),
                "unique_issues_found": len(unique_issues),
                "top_issues": top_issues,
                "issues_by_page": issues_by_page,
            }

        except Exception as e:
            logger.error(f"Error summarizing SEO issues: {str(e)}")
            return {"total_issues_found": 0}
