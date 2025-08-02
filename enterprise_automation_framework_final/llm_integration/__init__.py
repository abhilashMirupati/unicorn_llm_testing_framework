"""
LLM Integration Package
-----------------------

This package exposes the :class:`LLMAgent` class which abstracts away
differences between local and cloud large language model providers.  It
also defines simple data structures for representing API requests.
"""

from .llm_agent import LLMAgent, APIRequest

__all__ = ["LLMAgent", "APIRequest"]