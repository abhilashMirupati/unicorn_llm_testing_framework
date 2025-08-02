"""
Enhanced LLM Agent
-----------------

This module defines an abstraction layer over different large language
model (LLM) providers with support for LangChain/LangGraph frameworks.
The agent is responsible for classifying plain English test steps,
translating natural language API commands into structured requests,
suggesting UI selectors, generating SQL statements, and creating
entire test cases from BRDs and Swagger documents.

The agent implements a conservative fallback strategy: if the
configured provider is unavailable or returns invalid output, it
reverts to deterministic heuristics. Calls into the LLM are also
cached in memory to minimise repeated prompts.

Supported LLM Providers:
- OpenAI (GPT-3.5, GPT-4)
- Google Gemini
- Local Ollama models
- LangChain/LangGraph integration
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, List, Optional, Union
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

# Optional imports for different LLM providers
try:
    import openai
    _openai_available = True
except ImportError:
    _openai_available = False

try:
    import google.generativeai as genai
    _gemini_available = True
except ImportError:
    _gemini_available = False

try:
    import ollama
    _ollama_available = True
except ImportError:
    _ollama_available = False

try:
    from langchain.llms.base import LLM
    from langchain.chains import LLMChain, SimpleSequentialChain
    from langchain.prompts import PromptTemplate
    from langchain.memory import ConversationBufferMemory
    from langgraph.graph import StateGraph, END
    _langchain_available = True
except ImportError:
    _langchain_available = False

# RAGAS Framework Integration
try:
    from ragas import evaluate, generate
    from ragas.metrics import faithfulness, answer_relevancy
    _ragas_available = True
except ImportError:
    _ragas_available = False


@dataclass
class APIRequest:
    """Structured representation of an API request."""
    method: str
    url: str
    headers: Optional[Dict[str, str]]
    body: Optional[Any]
    expected_status: int


@dataclass
class TestCase:
    """Structured representation of a generated test case."""
    user_story: str
    test_set: str
    steps: List[Dict[str, Any]]
    category: str  # positive, negative, boundary
    priority: str  # high, medium, low
    tags: List[str]


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    @abstractmethod
    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.0) -> Optional[str]:
        """Send messages to the LLM and return the response."""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if the provider is available and configured."""
        pass
    
    @abstractmethod
    def get_priority(self) -> int:
        """Get provider priority for selection."""
        pass


class OpenAIProvider(LLMProvider):
    """OpenAI API provider implementation."""
    
    def __init__(self, config: Dict[str, Any]):
        self.api_key = config.get("api_key") or os.getenv("OPENAI_API_KEY")
        self.model = config.get("model", "gpt-3.5-turbo")
        self.timeout = config.get("timeout", 30)
        self.max_tokens = config.get("max_tokens", 2048)
        self.priority = config.get("priority", 1)
        if _openai_available and self.api_key:
            openai.api_key = self.api_key
    
    def is_available(self) -> bool:
        return _openai_available and bool(self.api_key)
    
    def get_priority(self) -> int:
        return self.priority
    
    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.0) -> Optional[str]:
        if not self.is_available():
            return None
        
        try:
            response = openai.ChatCompletion.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                timeout=self.timeout,
                max_tokens=self.max_tokens,
            )
            return response.choices[0].message["content"]
        except Exception as exc:
            logger.error(f"OpenAI API call failed: {exc}")
            return None


class GeminiProvider(LLMProvider):
    """Google Gemini API provider implementation."""
    
    def __init__(self, config: Dict[str, Any]):
        self.api_key = config.get("api_key") or os.getenv("GEMINI_API_KEY")
        self.model = config.get("model", "gemini-pro")
        self.timeout = config.get("timeout", 30)
        self.max_tokens = config.get("max_tokens", 2048)
        self.priority = config.get("priority", 2)
        if _gemini_available and self.api_key:
            genai.configure(api_key=self.api_key)
    
    def is_available(self) -> bool:
        return _gemini_available and bool(self.api_key)
    
    def get_priority(self) -> int:
        return self.priority
    
    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.0) -> Optional[str]:
        if not self.is_available():
            return None
        
        try:
            # Convert messages to Gemini format
            prompt = "\n".join([msg["content"] for msg in messages])
            model = genai.GenerativeModel(self.model)
            response = model.generate_content(prompt)
            return response.text
        except Exception as exc:
            logger.error(f"Gemini API call failed: {exc}")
            return None


class OllamaProvider(LLMProvider):
    """Local Ollama provider implementation."""
    
    def __init__(self, config: Dict[str, Any]):
        self.host = config.get("host", "http://localhost:11434")
        self.model = config.get("model", "llama2")
        self.timeout = config.get("timeout", 60)
        self.max_tokens = config.get("max_tokens", 4096)
        self.priority = config.get("priority", 3)
    
    def is_available(self) -> bool:
        if not _ollama_available:
            return False
        try:
            import requests
            response = requests.get(f"{self.host}/api/tags", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def get_priority(self) -> int:
        return self.priority
    
    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.0) -> Optional[str]:
        if not self.is_available():
            return None
        
        try:
            # Convert messages to Ollama format
            prompt = "\n".join([msg["content"] for msg in messages])
            response = ollama.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": temperature}
            )
            return response["message"]["content"]
        except Exception as exc:
            logger.error(f"Ollama API call failed: {exc}")
            return None


class LangChainManager:
    """Manages LangChain/LangGraph integration."""
    
    def __init__(self, config: Dict[str, Any], llm_provider: LLMProvider):
        self.config = config
        self.llm_provider = llm_provider
        self.memory = None
        if config.get("memory_enabled", True):
            self.memory = ConversationBufferMemory()
    
    def create_chain(self, chain_type: str = "simple") -> Optional[Any]:
        """Create a LangChain chain based on configuration."""
        if not _langchain_available:
            return None
        
        try:
            llm = self._create_langchain_llm()
            if not llm:
                return None
            
            if chain_type == "simple":
                return LLMChain(llm=llm, memory=self.memory)
            elif chain_type == "sequential":
                # Create a simple sequential chain
                return SimpleSequentialChain(chains=[LLMChain(llm=llm)])
            elif chain_type == "router":
                # Create a router chain (simplified)
                return LLMChain(llm=llm, memory=self.memory)
            else:
                return LLMChain(llm=llm, memory=self.memory)
        except Exception as exc:
            logger.error(f"Failed to create LangChain: {exc}")
            return None
    
    def _create_langchain_llm(self) -> Any:
        """Create a LangChain LLM wrapper around our provider."""
        if not _langchain_available:
            return None
        
        class CustomLLM(LLM):
            def __init__(self, provider: LLMProvider):
                super().__init__()
                self.provider = provider
            
            def _call(self, prompt: str, stop: Optional[List[str]] = None) -> str:
                response = self.provider.chat([{"role": "user", "content": prompt}])
                return response or ""
            
            @property
            def _llm_type(self) -> str:
                return "custom"
        
        return CustomLLM(self.llm_provider)


class LLMAgent:
    """Enhanced abstraction over local and cloud LLMs with LangChain support."""

    def __init__(self, config: Any) -> None:
        # Extract LLM configuration
        self.config = config
        self.mode = str(config.get("llm_mode", "local")).lower()
        self.model = str(config.get("model", "gpt-3.5-turbo")).strip()
        
        # Initialize LLM providers with dynamic configuration
        self.providers = self._initialize_providers()
        self.active_provider = self._select_active_provider()
        
        # LangChain integration
        self.langchain_manager = None
        if config.get("llm_framework", {}).get("use_langchain", False):
            self.langchain_manager = LangChainManager(config, self.active_provider)
        
        # Configuration parameters
        self.retries = int(config.get("llm_retries", 1))
        self.timeout = int(config.get("llm_timeout", 30))
        self.temperature = float(config.get("llm_framework", {}).get("temperature", 0.1))
        self.max_tokens = int(config.get("llm_framework", {}).get("max_tokens", 2048))
        
        # NLP Configuration
        self.nlp_config = config.get("nlp", {})
        self.enable_advanced_parsing = self.nlp_config.get("enable_advanced_parsing", True)
        self.fallback_to_keywords = self.nlp_config.get("fallback_to_keywords", True)
        self.context_awareness = self.nlp_config.get("context_awareness", True)

    def _initialize_providers(self) -> Dict[str, LLMProvider]:
        """Initialize all available LLM providers from configuration."""
        providers = {}
        
        # Get provider configurations
        provider_configs = self.config.get("llm_providers", [])
        
        for provider_config in provider_configs:
            name = provider_config.get("name")
            enabled = provider_config.get("enabled", True)
            
            if not enabled:
                continue
                
            if name == "openai":
                providers["openai"] = OpenAIProvider(provider_config.get("config", {}))
            elif name == "gemini":
                providers["gemini"] = GeminiProvider(provider_config.get("config", {}))
            elif name == "ollama":
                providers["ollama"] = OllamaProvider(provider_config.get("config", {}))
        
        return providers

    def _select_active_provider(self) -> Optional[LLMProvider]:
        """Select the active LLM provider based on configuration and availability."""
        if self.mode == "auto":
            # Select based on priority and availability
            available_providers = [
                provider for provider in self.providers.values() 
                if provider.is_available()
            ]
            if available_providers:
                return min(available_providers, key=lambda p: p.get_priority())
        
        elif self.mode == "cloud":
            # Prefer cloud providers
            for provider_name in ["openai", "gemini"]:
                if provider_name in self.providers and self.providers[provider_name].is_available():
                    return self.providers[provider_name]
        
        # Fall back to local provider
        if "ollama" in self.providers and self.providers["ollama"].is_available():
            return self.providers["ollama"]
        
        # Fall back to any available provider
        for provider in self.providers.values():
            if provider.is_available():
                return provider
        
        return None

    def _call_llm(self, messages: List[Dict[str, str]], temperature: float = None) -> Optional[str]:
        """Call the active LLM provider with retry logic."""
        if not self.active_provider:
            return None
        
        temp = temperature if temperature is not None else self.temperature
        
        for attempt in range(1, self.retries + 1):
            try:
                result = self.active_provider.chat(messages, temp)
                if result:
                    return result
            except Exception as exc:
                logger.warning(f"LLM call attempt {attempt}/{self.retries} failed: {exc}")
                if attempt >= self.retries:
                    break
                time.sleep(1)  # Brief delay before retry
        
        return None

    # Enhanced Natural Language Processing
    @lru_cache(maxsize=128)
    def parse_natural_language_step(self, step_text: str) -> Dict[str, Any]:
        """Parse natural language step using advanced LLM processing."""
        if not self.enable_advanced_parsing:
            return self._parse_with_keywords(step_text)
        
        messages = [
            {
                "role": "system", 
                "content": """Parse this test step into structured format. Return JSON with:
                {
                    "action": "click|fill|navigate|assert|api_request|sql_query",
                    "target": "selector or element description",
                    "data": {"value": "input data if any"},
                    "expected": "expected result",
                    "timeout": 30,
                    "retry_count": 3
                }"""
            },
            {"role": "user", "content": step_text}
        ]
        
        response = self._call_llm(messages)
        if response:
            try:
                return json.loads(response)
            except json.JSONDecodeError:
                logger.warning("Failed to parse LLM response as JSON")
        
        # Fallback to keyword parsing
        if self.fallback_to_keywords:
            return self._parse_with_keywords(step_text)
        
        return {"action": "unknown", "target": step_text}

    def _parse_with_keywords(self, text: str) -> Dict[str, Any]:
        """Parse step using keyword-based heuristics."""
        text_lower = text.lower()
        
        # UI Actions
        if any(word in text_lower for word in ["click", "tap", "press"]):
            return {"action": "click", "target": self._extract_target(text)}
        elif any(word in text_lower for word in ["fill", "enter", "type", "input"]):
            return {"action": "fill", "target": self._extract_target(text), "data": {"value": self._extract_value(text)}}
        elif any(word in text_lower for word in ["navigate", "go to", "visit"]):
            return {"action": "navigate", "target": self._extract_url(text)}
        elif any(word in text_lower for word in ["assert", "verify", "check"]):
            return {"action": "assert", "target": self._extract_target(text), "expected": self._extract_expected(text)}
        
        # API Actions
        elif any(word in text_lower for word in ["get", "post", "put", "delete"]):
            return {"action": "api_request", "target": self._extract_api_endpoint(text)}
        
        # SQL Actions
        elif any(word in text_lower for word in ["select", "insert", "update", "delete", "query"]):
            return {"action": "sql_query", "target": self._extract_sql_query(text)}
        
        # Mobile Actions
        elif any(word in text_lower for word in ["swipe", "scroll", "pinch"]):
            return {"action": "swipe", "target": self._extract_target(text)}
        
        return {"action": "unknown", "target": text}

    def _extract_target(self, text: str) -> str:
        """Extract target element from text."""
        # Simple extraction - can be enhanced with NLP
        words = text.split()
        for i, word in enumerate(words):
            if word.lower() in ["click", "fill", "enter", "type", "input", "assert", "verify"]:
                if i + 1 < len(words):
                    return " ".join(words[i+1:])
        return text

    def _extract_value(self, text: str) -> str:
        """Extract input value from text."""
        # Simple extraction - can be enhanced
        if "with" in text.lower():
            parts = text.lower().split("with")
            if len(parts) > 1:
                return parts[1].strip()
        return ""

    def _extract_url(self, text: str) -> str:
        """Extract URL from text."""
        import re
        url_pattern = r'https?://[^\s]+'
        match = re.search(url_pattern, text)
        return match.group() if match else text

    def _extract_expected(self, text: str) -> str:
        """Extract expected result from text."""
        if "should" in text.lower():
            parts = text.lower().split("should")
            if len(parts) > 1:
                return parts[1].strip()
        return ""

    def _extract_api_endpoint(self, text: str) -> str:
        """Extract API endpoint from text."""
        import re
        endpoint_pattern = r'/[^\s]+'
        match = re.search(endpoint_pattern, text)
        return match.group() if match else text

    def _extract_sql_query(self, text: str) -> str:
        """Extract SQL query from text."""
        # Simple extraction - can be enhanced
        return text

    # Classification of test steps
    @lru_cache(maxsize=128)
    def classify(self, text: str) -> str:
        """Classify a block of text into one of: ui, api, mobile or sql."""
        if not self.active_provider:
            return self._heuristic_classify(text)
        
        messages = [
            {
                "role": "system",
                "content": "Classify this test step into one category: ui, api, mobile, or sql. Respond with only the category name."
            },
            {"role": "user", "content": text}
        ]
        
        response = self._call_llm(messages)
        if response:
            category = response.strip().lower()
            if category in ["ui", "api", "mobile", "sql"]:
                return category
        
        return self._heuristic_classify(text)

    def _heuristic_classify(self, text: str) -> str:
        """Heuristic classification based on keywords."""
        text_lower = text.lower()
        
        # UI keywords
        ui_keywords = self.config.get("router", {}).get("ui_keywords", [])
        if any(keyword in text_lower for keyword in ui_keywords):
            return "ui"
        
        # API keywords
        api_keywords = self.config.get("router", {}).get("api_keywords", [])
        if any(keyword in text_lower for keyword in api_keywords):
            return "api"
        
        # Mobile keywords
        mobile_keywords = self.config.get("router", {}).get("mobile_keywords", [])
        if any(keyword in text_lower for keyword in mobile_keywords):
            return "mobile"
        
        # SQL keywords
        sql_keywords = self.config.get("router", {}).get("sql_keywords", [])
        if any(keyword in text_lower for keyword in sql_keywords):
            return "sql"
        
        return "ui"  # Default to UI

    # API Translation
    @lru_cache(maxsize=128)
    def translate_api(self, command: str, base_url: str = "") -> APIRequest:
        """Translate natural language API command to structured request."""
        if not self.active_provider:
            return self._heuristic_api_translation(command, base_url)
        
        messages = [
            {
                "role": "system",
                "content": f"""Translate this API command to structured format. Base URL: {base_url}
                Return JSON with:
                {{
                    "method": "GET|POST|PUT|DELETE",
                    "url": "full URL",
                    "headers": {{"Content-Type": "application/json"}},
                    "body": "request body if any",
                    "expected_status": 200
                }}"""
            },
            {"role": "user", "content": command}
        ]
        
        response = self._call_llm(messages)
        if response:
            try:
                data = json.loads(response)
                return APIRequest(
                    method=data.get("method", "GET"),
                    url=data.get("url", ""),
                    headers=data.get("headers", {}),
                    body=data.get("body"),
                    expected_status=data.get("expected_status", 200)
                )
            except json.JSONDecodeError:
                logger.warning("Failed to parse API translation as JSON")
        
        return self._heuristic_api_translation(command, base_url)

    def _heuristic_api_translation(self, command: str, base_url: str) -> APIRequest:
        """Heuristic API translation using keyword matching."""
        command_lower = command.lower()
        
        # Determine method
        method = "GET"
        if "post" in command_lower:
            method = "POST"
        elif "put" in command_lower:
            method = "PUT"
        elif "delete" in command_lower:
            method = "DELETE"
        
        # Extract URL
        import re
        url_pattern = r'https?://[^\s]+'
        url_match = re.search(url_pattern, command)
        url = url_match.group() if url_match else f"{base_url}/api"
        
        return APIRequest(
            method=method,
            url=url,
            headers={"Content-Type": "application/json"},
            body=None,
            expected_status=200
        )

    # SQL Translation
    @lru_cache(maxsize=64)
    def translate_sql(self, command: str) -> Dict[str, str]:
        """Translate natural language to SQL query."""
        if not self.active_provider:
            return self._heuristic_sql_translation(command)
        
        messages = [
            {
                "role": "system",
                "content": "Translate this natural language command to SQL. Return JSON with 'sql' and 'assertion' fields."
            },
            {"role": "user", "content": command}
        ]
        
        response = self._call_llm(messages)
        if response:
            try:
                return json.loads(response)
            except json.JSONDecodeError:
                logger.warning("Failed to parse SQL translation as JSON")
        
        return self._heuristic_sql_translation(command)

    def _heuristic_sql_translation(self, command: str) -> Dict[str, str]:
        """Heuristic SQL translation."""
        command_lower = command.lower()
        
        if "select" in command_lower:
            return {"sql": f"SELECT * FROM {self._extract_table_name(command)}", "assertion": "verify results"}
        elif "insert" in command_lower:
            return {"sql": f"INSERT INTO {self._extract_table_name(command)} VALUES (...)", "assertion": "verify insert"}
        elif "update" in command_lower:
            return {"sql": f"UPDATE {self._extract_table_name(command)} SET ...", "assertion": "verify update"}
        elif "delete" in command_lower:
            return {"sql": f"DELETE FROM {self._extract_table_name(command)}", "assertion": "verify delete"}
        
        return {"sql": command, "assertion": "verify execution"}

    def _extract_table_name(self, command: str) -> str:
        """Extract table name from command."""
        # Simple extraction - can be enhanced
        words = command.split()
        for i, word in enumerate(words):
            if word.lower() in ["from", "into", "table"]:
                if i + 1 < len(words):
                    return words[i + 1]
        return "table"

    # UI Locator Suggestions
    @lru_cache(maxsize=64)
    def suggest_ui_locator(self, description: str) -> Optional[str]:
        """Suggest UI locator based on description."""
        if not self.active_provider:
            return None
        
        messages = [
            {
                "role": "system",
                "content": "Suggest a CSS selector or XPath for this UI element. Return only the selector."
            },
            {"role": "user", "content": description}
        ]
        
        response = self._call_llm(messages)
        return response.strip() if response else None

    # RAGAS Integration for Test Case Generation
    def generate_test_cases_with_ragas(self, brd_content: str, max_cases: int = 10) -> List[TestCase]:
        """Generate test cases using actual RAGAS framework."""
        if not _ragas_available:
            logger.warning("RAGAS framework not available, using fallback generation")
            return self.generate_test_cases_from_brd_fallback(brd_content, max_cases)
        
        try:
            # Use actual RAGAS framework
            dataset = self._create_dataset_from_brd(brd_content)
            generated_cases = generate(dataset, metrics=[faithfulness, answer_relevancy])
            return self._convert_ragas_output_to_test_cases(generated_cases, max_cases)
        except Exception as exc:
            logger.error(f"RAGAS generation failed: {exc}")
            return self.generate_test_cases_from_brd_fallback(brd_content, max_cases)

    def _create_dataset_from_brd(self, brd_content: str) -> Any:
        """Create RAGAS dataset from BRD content."""
        # This is a simplified implementation
        # In a real implementation, you would create proper RAGAS datasets
        return {"content": brd_content}

    def _convert_ragas_output_to_test_cases(self, ragas_output: Any, max_cases: int) -> List[TestCase]:
        """Convert RAGAS output to test cases."""
        # Simplified conversion
        test_cases = []
        # Implementation would parse RAGAS output and create structured test cases
        return test_cases

    def generate_test_cases_from_brd_fallback(self, brd_content: str, max_cases: int = 10) -> List[TestCase]:
        """Fallback test case generation without RAGAS."""
        # Extract user stories from BRD content
        user_stories = self._extract_user_stories_from_brd(brd_content)
        
        test_cases = []
        for story in user_stories[:max_cases]:
            # Generate positive test case
            positive_steps = self._generate_positive_test_steps(story)
            test_case = TestCase(
                user_story=story,
                test_set="BRD Generated",
                steps=positive_steps,
                category="positive",
                priority="medium",
                tags=["brd", "positive"]
            )
            test_cases.append(test_case)
            
            # Generate negative test case
            negative_steps = self._generate_negative_test_steps(story)
            test_case = TestCase(
                user_story=story,
                test_set="BRD Generated - Negative",
                steps=negative_steps,
                category="negative",
                priority="medium",
                tags=["brd", "negative"]
            )
            test_cases.append(test_case)
        
        return test_cases

    def _extract_user_stories_from_brd(self, brd_content: str) -> List[str]:
        """Extract user stories from BRD content."""
        import re
        stories = []
        
        # Pattern-based extraction
        patterns = [
            r"As a (\w+), I want to (.+?) so that (.+?)(?=\n|$)",
            r"User Story: (.+?)(?=\n|$)",
            r"Story: (.+?)(?=\n|$)",
            r"Requirement: (.+?)(?=\n|$)",
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, brd_content, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                if isinstance(match, tuple):
                    stories.append(" ".join(match))
                else:
                    stories.append(match)
        
        return stories

    def _generate_positive_test_steps(self, user_story: str) -> List[Dict[str, Any]]:
        """Generate positive test steps from user story."""
        if not self.active_provider:
            return [{"action": "click", "target": "element", "expected": "success"}]
        
        messages = [
            {
                "role": "system",
                "content": "Generate positive test steps for this user story. Return JSON array of steps."
            },
            {"role": "user", "content": user_story}
        ]
        
        response = self._call_llm(messages)
        if response:
            try:
                return json.loads(response)
            except json.JSONDecodeError:
                pass
        
        return [{"action": "click", "target": "element", "expected": "success"}]

    def _generate_negative_test_steps(self, user_story: str) -> List[Dict[str, Any]]:
        """Generate negative test steps from user story."""
        if not self.active_provider:
            return [{"action": "click", "target": "invalid_element", "expected": "error"}]
        
        messages = [
            {
                "role": "system",
                "content": "Generate negative test steps for this user story. Return JSON array of steps."
            },
            {"role": "user", "content": user_story}
        ]
        
        response = self._call_llm(messages)
        if response:
            try:
                return json.loads(response)
            except json.JSONDecodeError:
                pass
        
        return [{"action": "click", "target": "invalid_element", "expected": "error"}]

    def generate_test_cases_from_swagger(self, swagger_content: str, max_cases: int = 10) -> List[TestCase]:
        """Generate API test cases from Swagger/OpenAPI specification."""
        # Extract endpoints from Swagger
        endpoints = self._extract_endpoints_from_swagger(swagger_content)
        
        test_cases = []
        for endpoint in endpoints[:max_cases]:
            # Generate positive test case
            positive_steps = self._generate_api_test_steps(endpoint, "positive")
            test_case = TestCase(
                user_story=f"Test {endpoint['method']} {endpoint['path']}",
                test_set="API Generated",
                steps=positive_steps,
                category="positive",
                priority="medium",
                tags=["api", "swagger", "positive"]
            )
            test_cases.append(test_case)
            
            # Generate negative test case
            negative_steps = self._generate_api_test_steps(endpoint, "negative")
            test_case = TestCase(
                user_story=f"Test {endpoint['method']} {endpoint['path']} - Negative",
                test_set="API Generated - Negative",
                steps=negative_steps,
                category="negative",
                priority="medium",
                tags=["api", "swagger", "negative"]
            )
            test_cases.append(test_case)
        
        return test_cases

    def _extract_endpoints_from_swagger(self, swagger_content: str) -> List[Dict[str, Any]]:
        """Extract endpoints from Swagger/OpenAPI content."""
        import re
        endpoints = []
        
        # Simple pattern matching - can be enhanced with proper JSON parsing
        path_pattern = r'"([^"]+)"\s*:\s*{'
        method_pattern = r'"(get|post|put|delete|patch)"\s*:\s*{'
        
        paths = re.findall(path_pattern, swagger_content, re.IGNORECASE)
        methods = re.findall(method_pattern, swagger_content, re.IGNORECASE)
        
        for path in paths:
            for method in methods:
                endpoints.append({
                    "path": path,
                    "method": method.upper(),
                    "summary": f"{method.upper()} {path}"
                })
        
        return endpoints

    def _generate_api_test_steps(self, endpoint: Dict[str, Any], test_type: str) -> List[Dict[str, Any]]:
        """Generate API test steps for endpoint."""
        if test_type == "positive":
            return [{
                "action": "api_request",
                "target": f"{endpoint['method']} {endpoint['path']}",
                "data": {
                    "method": endpoint['method'],
                    "url": f"{{base_url}}{endpoint['path']}",
                    "headers": {"Content-Type": "application/json"}
                },
                "expected": f"Response with status 200/201 for {endpoint['method']} {endpoint['path']}"
            }]
        else:
            return [{
                "action": "api_request",
                "target": f"{endpoint['method']} {endpoint['path']}",
                "data": {
                    "method": endpoint['method'],
                    "url": f"{{base_url}}{endpoint['path']}",
                    "headers": {"Content-Type": "application/json"},
                    "body": "invalid_data"
                },
                "expected": f"Response with status 400/500 for {endpoint['method']} {endpoint['path']}"
            }]