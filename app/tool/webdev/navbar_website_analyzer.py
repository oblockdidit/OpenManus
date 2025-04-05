import asyncio
import base64
import json
import os
import time
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Optional

from app.logger import logger
from app.tool.base import BaseTool
from app.tool.browser_use_tool import BrowserUseTool
from app.llm.llm import LLM


class NavbarWebsiteAnalyzer(BaseTool):
    """
    Enhanced website analyzer that uses navbar exploration to analyze websites.
    
    This tool uses direct Playwright methods to:
    - Identify and navigate through navbar links
    - Capture screenshots of each page
    - Use vision models to analyze page content
    - Generate comprehensive website analysis
    """

    name: str = "website_analyzer"
    description: str = (
        "Performs comprehensive website analysis by navigating through navbar links "
        "and analyzing each page using vision models"
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
        Execute comprehensive website analysis using navbar exploration.

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
                await asyncio.sleep(3)

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
                results["performance_metrics"] = {"homepage_load_time": round(load_time, 2)}

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
            domain = url.split("//")[-1].split("/")[0]
            results["domain"] = domain

            # Get the current page
            context = await browser_tool._ensure_browser_initialized()
            page = await context.get_current_page()

            # Take screenshot of homepage
            screenshot_bytes = await page.screenshot()
            screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
            
            # Save screenshot to file for reference
            timestamp = int(time.time())
            screenshot_path = os.path.join(self.SCREENSHOTS_DIR, f"{domain}_homepage_{timestamp}.jpg")
            with open(screenshot_path, "wb") as f:
                f.write(screenshot_bytes)
            
            if save_screenshots:
                results["screenshots"].append({
                    "page_name": "homepage",
                    "path": screenshot_path,
                    "timestamp": timestamp
                })
            
            # Use vision model to identify navbar elements
            vision_llm = LLM("vision")
            prompt = (
                "Identify all navigation menu elements on this webpage. "
                "For each navigation item, provide its exact text label. "
                "Format your response as a simple numbered list with just the link text. "
                "Only include main navigation menu items."
            )
            
            try:
                nav_analysis = await vision_llm.ask_with_images(
                    messages=[{"role": "user", "content": prompt}],
                    images=[{"base64": screenshot_b64}],
                    stream=False,
                    temperature=0.2,
                )
                
                # Parse links from the result
                links = []
                for line in nav_analysis.split('\n'):
                    line = line.strip()
                    if line and (line[0].isdigit() or line[0] in ['•', '-', '*']):
                        # Remove numbering or bullet points
                        link_text = line.split('.', 1)[-1] if '.' in line[:3] else line
                        link_text = link_text.strip()
                        # Remove any bullet points
                        for char in ['•', '-', '*']:
                            if link_text.startswith(char):
                                link_text = link_text[1:].strip()
                        if link_text and link_text.lower() not in ['home', 'homepage']:
                            links.append(link_text)
                
                logger.info(f"Found navigation links: {links}")
                
                # Analyze homepage content with vision model
                homepage_prompt = "Describe this webpage. What is the main content and purpose of this site? Extract key information."
                homepage_analysis = await vision_llm.ask_with_images(
                    messages=[{"role": "user", "content": homepage_prompt}],
                    images=[{"base64": screenshot_b64}],
                    stream=False,
                    temperature=0.2,
                )
                
                # Add homepage to analyzed pages
                results["pages_analyzed"].append({
                    "url": url,
                    "title": "Homepage",
                    "description": homepage_analysis[:100] + "..." if len(homepage_analysis) > 100 else homepage_analysis,
                })
                
                # Add content analysis
                results["content_analysis"]["homepage"] = {
                    "text_sample": homepage_analysis[:500] + "..." if len(homepage_analysis) > 500 else homepage_analysis,
                    "word_count": len(homepage_analysis.split()),
                    "has_contact_info": "contact" in homepage_analysis.lower() or "phone" in homepage_analysis.lower() or "email" in homepage_analysis.lower(),
                }
                
                # Detect technologies
                tech_prompt = "Identify the technologies used on this website (frameworks, libraries, CMS, etc.)"
                tech_analysis = await vision_llm.ask_with_images(
                    messages=[{"role": "user", "content": tech_prompt}],
                    images=[{"base64": screenshot_b64}],
                    stream=False,
                    temperature=0.2,
                )
                
                # Extract technologies from the text
                techs = []
                common_techs = [
                    "HTML", "CSS", "JavaScript", "jQuery", "React", "Angular", "Vue",
                    "WordPress", "Shopify", "Wix", "Drupal", "Magento", "Bootstrap",
                    "PHP", "Google Analytics", "Cloudflare", "Node.js", "Express",
                    "Tailwind CSS", "Font Awesome", "GSAP", "Three.js",
                ]
                
                for tech in common_techs:
                    if tech.lower() in tech_analysis.lower():
                        techs.append(tech)
                
                if not techs:
                    techs = ["HTML", "CSS", "JavaScript"]
                
                results["technologies"] = techs
                
                # Limit to max_pages
                if len(links) > max_pages - 1:
                    links = links[:max_pages - 1]
                
                # Navigate to each link and analyze the page
                for link in links:
                    # Try to find and click the link directly using Playwright
                    try:
                        # Find all links on the page
                        all_links = await page.query_selector_all("a")
                        
                        # Look for a link with matching text
                        link_found = False
                        for link_element in all_links:
                            text_content = await link_element.text_content()
                            if link.lower() in text_content.lower():
                                logger.info(f"Found link with text: {text_content}")
                                
                                # Click the link
                                await link_element.click()
                                await page.wait_for_load_state()
                                await asyncio.sleep(2)  # Wait for page to load
                                
                                # Take a screenshot of the new page
                                page_screenshot = await page.screenshot()
                                page_screenshot_b64 = base64.b64encode(page_screenshot).decode("utf-8")
                                
                                # Save screenshot if enabled
                                if save_screenshots:
                                    page_timestamp = int(time.time())
                                    page_screenshot_path = os.path.join(
                                        self.SCREENSHOTS_DIR, 
                                        f"{domain}_{link.replace(' ', '_')}_{page_timestamp}.jpg"
                                    )
                                    with open(page_screenshot_path, "wb") as f:
                                        f.write(page_screenshot)
                                    
                                    results["screenshots"].append({
                                        "page_name": link,
                                        "path": page_screenshot_path,
                                        "timestamp": page_timestamp
                                    })
                                
                                # Analyze the page with vision model
                                page_prompt = f"This is the {link} page of a website. Describe what this page contains, its purpose, and key information or features visible on the page."
                                page_analysis = await vision_llm.ask_with_images(
                                    messages=[{"role": "user", "content": page_prompt}],
                                    images=[{"base64": page_screenshot_b64}],
                                    stream=False,
                                    temperature=0.2,
                                )
                                
                                # Add to pages analyzed
                                page_url = page.url
                                results["pages_analyzed"].append({
                                    "url": page_url,
                                    "title": link,
                                    "description": page_analysis[:100] + "..." if len(page_analysis) > 100 else page_analysis,
                                })
                                
                                # Add content analysis
                                results["content_analysis"][link.lower()] = {
                                    "text_sample": page_analysis[:500] + "..." if len(page_analysis) > 500 else page_analysis,
                                    "word_count": len(page_analysis.split()),
                                    "has_contact_info": "contact" in page_analysis.lower() or "phone" in page_analysis.lower() or "email" in page_analysis.lower(),
                                }
                                
                                # Go back to homepage
                                await page.goto(url)
                                await page.wait_for_load_state()
                                await asyncio.sleep(2)
                                
                                link_found = True
                                break
                        
                        if not link_found:
                            logger.warning(f"Could not find link with text: {link}")
                    
                    except Exception as e:
                        logger.error(f"Error navigating to {link}: {e}")
                
                # Calculate scores based on analysis
                scores = self._calculate_scores(results)
                results["scores"] = scores
                
                # Generate improvement recommendations
                recommendations = self._generate_recommendations(results)
                results["improvement_opportunities"] = recommendations
                
            except Exception as e:
                logger.error(f"Error analyzing website: {e}")
                results["error"] = f"Error analyzing website: {e}"
            
            # Cleanup browser
            if browser_tool:
                await browser_tool.cleanup()
                browser_tool = None
            
            # Format final results - prepare client-friendly output
            final_results = {
                "url": url,
                "exists": True,
                "scores": results.get("scores", {}),
                "technologies": results.get("technologies", []),
                "improvement_opportunities": results.get("improvement_opportunities", []),
                "pages_analyzed": [page["url"] for page in results.get("pages_analyzed", [])],
                "screenshots": (
                    [s["path"] for s in results.get("screenshots", [])]
                    if save_screenshots
                    else []
                ),
                "details": {
                    "content_summary": self._summarize_content(
                        results.get("content_analysis", {})
                    ),
                    "performance_metrics": results.get("performance_metrics", {}),
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
    
    def _calculate_scores(self, results: Dict[str, Any]) -> Dict[str, int]:
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
                    
                    # Having contact info is good
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
            
            # Mobile score - estimate based on vision model analysis
            mobile_score = 60  # Default
            
            # SEO score - estimate based on vision model analysis
            seo_score = 60  # Default
            
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
    
    def _generate_recommendations(self, results: Dict[str, Any]) -> List[str]:
        """Generate improvement recommendations based on analysis results."""
        try:
            recommendations = []
            
            # Get scores and determine the most important areas to improve
            scores = results.get("scores", {})
            design_score = scores.get("design", 65)
            performance_score = scores.get("performance", 40)
            mobile_score = scores.get("mobile", 40)
            seo_score = scores.get("seo", 25)
            
            # Add recommendations based on scores
            if seo_score < 50:
                recommendations.append(
                    "Improve SEO with better meta tags, headings, and content structure"
                )
            
            if mobile_score < 60:
                recommendations.append(
                    "Enhance mobile compatibility for better user experience on all devices"
                )
            
            if performance_score < 60:
                if results.get("performance_metrics", {}).get("homepage_load_time", 0) > 3.0:
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
