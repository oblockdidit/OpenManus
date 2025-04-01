import asyncio
import time
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

def get_openrouter_client(api_key: Optional[str] = None) -> OpenRouterClient:
    """Get or create the OpenRouter client instance."""
    global _client_instance
    if _client_instance is None:
        if api_key is None:
            from app.config import config
            api_key = config.llm.get("openrouter", {}).get("api_key", None)
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
        return await client.generate_completion(
            messages=messages,
            model_id=full_model_id,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream,
            top_p=top_p
        )
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
                return await client.generate_completion(
                    messages=messages,
                    model_id=fallback_id,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=stream,
                    top_p=top_p
                )
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
