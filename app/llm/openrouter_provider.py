import asyncio
import time
import os
import tomllib
import json
import httpx
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union

import openai
import tenacity
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.logger import logger
from app.exceptions import TokenLimitExceeded
from app.config import config

# Import the OpenRouter configuration
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'config'))
from openrouter_config import (
    OPENROUTER_MODELS,
    MODEL_CAPABILITIES,
    get_model_settings,
    get_fallback_models,
    get_prompt_enhancement,
    DEFAULT_PROVIDER_SORTING
)


# Enhanced rate limiting for OpenRouter
class AdaptiveRateLimiter:
    """Adaptive rate limiter for API calls."""
    
    def __init__(self, initial_rate=10, window_size=60):
        self.current_rate = initial_rate
        self.window_size = window_size  # seconds
        self.calls = []
        self.failures = 0
        self.max_failures = 3
        self.backoff_factor = 0.5
        
    async def wait_if_needed(self):
        """Wait if we're exceeding our rate limit."""
        now = time.time()
        # Remove old calls
        self.calls = [call for call in self.calls if now - call < self.window_size]
        
        if len(self.calls) >= self.current_rate:
            wait_time = self.window_size - (now - self.calls[0])
            if wait_time > 0:
                logger.info(f"Rate limiting: waiting {wait_time:.2f}s before next request")
                await asyncio.sleep(wait_time)
        
        self.calls.append(time.time())
        
    def adjust_rate(self, success: bool):
        """Adjust rate based on successful or failed calls."""
        if not success:
            self.failures += 1
            if self.failures >= self.max_failures:
                self.current_rate = max(1, int(self.current_rate * self.backoff_factor))
                logger.warning(f"Reducing rate limit to {self.current_rate} requests per {self.window_size}s")
                self.failures = 0
        else:
            self.failures = max(0, self.failures - 1)
            # If we're consistently hitting the limit without errors, try increasing slightly
            if len(self.calls) >= self.current_rate * 0.9:
                old_rate = self.current_rate
                self.current_rate += 1
                logger.info(f"Increasing rate limit from {old_rate} to {self.current_rate} requests per {self.window_size}s")


class OpenRouterClient:
    """Client for OpenRouter API with rate limiting and error handling."""
    
    def __init__(self, api_key: str, base_url: str = "https://openrouter.ai/api/v1", 
                 org_name: str = "OpenManus", app_name: str = "OpenManus"):
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            default_headers={
                "HTTP-Referer": "https://github.com/open-manus/OpenManus",  # Optional, for attribution
                "X-Title": app_name,  # Optional, shows in rankings
            },
        )
        self.rate_limiter = AdaptiveRateLimiter()
        self.failed_models = set()  # Track models that have failed with endpoint errors
        self.model_usage_counts = {}  # Track usage of each model
        self.model_success_rates = {}  # Track success rates of each model
        
    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type((openai.APIError, openai.RateLimitError)),
    )
    async def generate_completion(
        self, 
        messages: List[Dict], 
        model_id: str, 
        temperature: float = 0, 
        max_tokens: int = 2048,
        stream: bool = True,
        top_p: Optional[float] = None,
        provider_order: Optional[str] = None,
    ) -> Any:
        """Generate a completion from OpenRouter with retries and rate limiting."""
        # Check if model is in failed models list
        if model_id in self.failed_models:
            logger.warning(f"Skipping known failing model: {model_id}")
            raise ValueError(f"Model {model_id} previously failed with endpoint error")
            
        # Update model usage count
        self.model_usage_counts[model_id] = self.model_usage_counts.get(model_id, 0) + 1
        
        # Wait if we need to rate limit
        await self.rate_limiter.wait_if_needed()
        
        # Get model-specific settings
        model_settings = get_model_settings(model_id)
        
        # Override with passed settings if provided
        if temperature is not None:
            model_settings["temperature"] = temperature
        if max_tokens is not None:
            model_settings["max_tokens"] = max_tokens
        if top_p is not None:
            model_settings["top_p"] = top_p
        
        try:
            # Make the API call
            # Create API parameters without the provider parameter
            api_params = {
                "model": model_id,
                "messages": messages,
                "stream": stream,
                "temperature": model_settings.get("temperature", 0),
                "max_tokens": model_settings.get("max_tokens", 2048),
            }
            
            # Add optional parameters if provided
            if top_p is not None:
                api_params["top_p"] = top_p
                
            # Provider sorting can be handled through custom HTTP headers if needed
            # For now, we'll skip this as the OpenAI client doesn't support adding
            # custom headers for individual requests
                
            # Make the API call
            response = await self.client.chat.completions.create(**api_params)
            
            # Successful call
            self.rate_limiter.adjust_rate(success=True)
            
            # Update success rate
            if model_id not in self.model_success_rates:
                self.model_success_rates[model_id] = [0, 0]  # [successes, attempts]
            self.model_success_rates[model_id][0] += 1  # increment successes
            self.model_success_rates[model_id][1] += 1  # increment attempts
            
            return response
            
        except openai.BadRequestError as e:
            error_msg = str(e).lower()
            if "no endpoints found that support tool use" in error_msg or "404" in error_msg:
                # Add to failed models list
                self.failed_models.add(model_id)
                logger.error(f"Model {model_id} does not support tool use or endpoint not found")
                raise ValueError(f"Model {model_id} does not support the requested operation")
            else:
                # Other bad request errors
                logger.error(f"Bad request error with {model_id}: {e}")
                self.rate_limiter.adjust_rate(success=False)
                
                # Update failure rate
                if model_id not in self.model_success_rates:
                    self.model_success_rates[model_id] = [0, 0]  # [successes, attempts]
                self.model_success_rates[model_id][1] += 1  # increment attempts
                
                raise
                
        except openai.RateLimitError as e:
            # Rate limit error
            logger.warning(f"Rate limit error with {model_id}: {e}")
            self.rate_limiter.adjust_rate(success=False)
            
            # Update failure rate
            if model_id not in self.model_success_rates:
                self.model_success_rates[model_id] = [0, 0]  # [successes, attempts]
            self.model_success_rates[model_id][1] += 1  # increment attempts
            
            # Let tenacity retry
            raise
            
        except Exception as e:
            # Other errors
            logger.error(f"Error generating completion with {model_id}: {e}")
            self.rate_limiter.adjust_rate(success=False)
            
            # Update failure rate
            if model_id not in self.model_success_rates:
                self.model_success_rates[model_id] = [0, 0]  # [successes, attempts]
            self.model_success_rates[model_id][1] += 1  # increment attempts
            
            raise
            
    def get_model_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics about model usage and success rates."""
        stats = {}
        for model_id in set(list(self.model_usage_counts.keys()) + list(self.model_success_rates.keys())):
            success_rate = 0
            if model_id in self.model_success_rates:
                successes, attempts = self.model_success_rates[model_id]
                success_rate = (successes / attempts) * 100 if attempts > 0 else 0
                
            stats[model_id] = {
                "usage_count": self.model_usage_counts.get(model_id, 0),
                "success_rate": success_rate,
                "is_blocked": model_id in self.failed_models
            }
        return stats


# Create a global client instance
_client_instance = None

def get_openrouter_api_key():
    """Read the OpenRouter API key directly from the TOML file."""
    try:
        project_root = Path(__file__).resolve().parent.parent.parent
        config_file = project_root / "config" / "openrouter.toml"
        
        if not config_file.exists():
            raise FileNotFoundError(f"OpenRouter config file not found at {config_file}")
        
        with open(config_file, "rb") as f:
            config = tomllib.load(f)
        
        api_key = config.get("api_key")
        if not api_key:
            raise ValueError("API key not found in OpenRouter configuration")
        return api_key
    except Exception as e:
        raise ValueError(f"Error getting OpenRouter API key: {str(e)}")

def get_openrouter_client(api_key: Optional[str] = None) -> OpenRouterClient:
    """Get or create the OpenRouter client instance."""
    global _client_instance
    if _client_instance is None:
        if api_key is None:
            try:
                # First try to get from app config
                from app.config import config
                api_key = config.llm.get("openrouter", {}).get("api_key", None)
                
                # If not found in config, read directly from TOML file
                if not api_key:
                    api_key = get_openrouter_api_key()
                    logger.info("Using API key from openrouter.toml file")
            except Exception as e:
                raise ValueError(f"OpenRouter API key not found: {str(e)}")
            
            if not api_key:
                raise ValueError("OpenRouter API key not found in configuration")
        _client_instance = OpenRouterClient(api_key=api_key)
    return _client_instance


async def generate_openrouter_response(
    messages: List[Dict], 
    model_id: str, 
    temperature: float = 0, 
    max_tokens: int = 2048, 
    stream: bool = True,
    top_p: Optional[float] = None,
    fallback_enabled: bool = True
) -> Any:
    """Generate a response from OpenRouter without using native tool calling."""
    
    # Check if model_id is in our short format and convert to full OpenRouter format
    if model_id in OPENROUTER_MODELS:
        full_model_id = OPENROUTER_MODELS[model_id]
    else:
        # Assume it's already in full format
        full_model_id = model_id
    
    # Add XML instructions to the system message based on model family
    if messages and messages[0]['role'] == 'system':
        model_family = full_model_id.split('/')[0]
        messages[0]['content'] += get_prompt_enhancement(full_model_id)
    
    # Get the client
    client = get_openrouter_client()
    
    # Try primary model
    try:
        # Configure the actual stream parameter based on recent OpenRouter API behavior
        # Even if stream=True was requested, sometimes it's better to use non-streaming
        # for some models due to API changes
        actual_stream = stream
        
        response = await client.generate_completion(
            messages=messages,
            model_id=full_model_id,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=actual_stream,
            top_p=top_p
        )
        
        logger.info(f"OpenRouter returned response type: {type(response).__name__}")
        return response
        
    except ValueError as e:
        # If fallbacks are disabled or it's not an endpoint error, just raise
        if not fallback_enabled or not str(e).startswith("Model") or "support" not in str(e).lower():
            raise
            
        # Otherwise, try fallbacks
        fallbacks = get_fallback_models(full_model_id)
        logger.warning(f"Primary model {full_model_id} failed, trying fallbacks: {fallbacks}")
        
        # Try each fallback in order
        last_error = e
        for fallback_id in fallbacks:
            try:
                logger.info(f"Trying fallback model: {fallback_id}")
                response = await client.generate_completion(
                    messages=messages,
                    model_id=fallback_id,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=stream,
                    top_p=top_p
                )
                logger.info(f"Fallback model {fallback_id} returned response type: {type(response).__name__}")
                return response
            except Exception as fallback_error:
                logger.warning(f"Fallback model {fallback_id} failed: {fallback_error}")
                last_error = fallback_error
                continue
        
        # If we get here, all fallbacks failed
        logger.error(f"All fallback models failed, raising last error: {last_error}")
        raise last_error


async def get_openrouter_model_list() -> List[Dict[str, Any]]:
    """Get a list of available models from OpenRouter."""
    client = get_openrouter_client()
    
    try:
        # OpenRouter doesn't have a models endpoint through the SDK yet
        # so we need to construct a custom request
        response = await client.client.with_raw_response.models.list()
        models_data = response.json()
        return models_data.get("data", [])
    except Exception as e:
        logger.error(f"Error fetching models from OpenRouter: {e}")
        # Return a basic set of models we know about
        return [
            {"id": model_id, "name": name} 
            for name, model_id in OPENROUTER_MODELS.items()
        ]


# Simple function without all the client complexity
async def generate_openrouter_quick_response(messages, model_id=None, temperature=0.7, max_tokens=4096, stream=False):
    """
    Generate a response from OpenRouter API with timeouts and fallbacks for browser navigation.
    """
    try:
        # Get API key and base URL from config
        api_key = config.llm.get("openrouter", {}).get("api_key", None) or os.environ.get("OPENROUTER_API_KEY")
        base_url = config.llm.get("openrouter", {}).get("base_url", "https://openrouter.ai/api/v1")
        
        if not api_key:
            raise ValueError("OpenRouter API key not found in config or environment variables")
        
        # Use model_id if provided, otherwise use default from config
        if not model_id:
            model_id = config.llm.get("openrouter", {}).get("default_model", "google/gemini-pro")
            
        # Create OpenAI client with OpenRouter base URL
        client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        
        # Add a timeout for the OpenRouter call
        timeout = httpx.Timeout(30.0, connect=10.0)  # 30 seconds total, 10 seconds connect
        client.timeout = timeout
        
        # Set up the parameters dict
        params = {
            "model": model_id,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream
        }
        
        # Log the request without the full message content
        log_params = params.copy()
        log_params["messages"] = f"[{len(messages)} messages]"
        logger.info(f"Quick OpenRouter completion with: {json.dumps(log_params)}")
        
        # Make the request with a timeout
        try:
            response = await asyncio.wait_for(
                client.chat.completions.create(**params),
                timeout=20  # 20 second timeout for the API call
            )
            return response
        except asyncio.TimeoutError:
            logger.error(f"OpenRouter request to {model_id} timed out after 20 seconds")
            # Create a simple dict response instead of using the types
            return {
                "id": "error-timeout",
                "choices": [{
                    "finish_reason": "timeout",
                    "index": 0,
                    "message": {
                        "content": "I'm experiencing connectivity issues with the language model service. Let me help you directly if you'd like to browse a website or run a command.",
                        "role": "assistant"
                    }
                }],
                "created": int(time.time()),
                "model": model_id,
                "object": "chat.completion",
                "usage": {"completion_tokens": 0, "prompt_tokens": 0, "total_tokens": 0}
            }
    except Exception as e:
        logger.error(f"Error generating OpenRouter response: {str(e)}")
        # Create a simple dict response instead of using the types
        return {
            "id": "error",
            "choices": [{
                "finish_reason": "error",
                "index": 0,
                "message": {
                    "content": f"I encountered an error trying to process your request. If you're looking to visit a website, please provide the URL and I'll navigate there directly.",
                    "role": "assistant"
                }
            }],
            "created": int(time.time()),
            "model": model_id,
            "object": "chat.completion",
            "usage": {"completion_tokens": 0, "prompt_tokens": 0, "total_tokens": 0}
        }
