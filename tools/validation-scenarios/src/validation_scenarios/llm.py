"""LLM client with multi-provider support via LangChain."""

import os

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage


def get_llm() -> BaseChatModel:
    """Create LLM instance based on LLM_MODEL environment variable.
    
    Format: provider:model (e.g., "ollama:llama3.2", "anthropic:claude-sonnet-4-20250514")
    """
    llm_model = os.getenv("LLM_MODEL", "ollama:llama3.2")
    
    if ":" not in llm_model:
        raise ValueError(f"LLM_MODEL must be in format 'provider:model', got: {llm_model}")
    
    provider, model = llm_model.split(":", 1)
    
    if provider == "ollama":
        from langchain_ollama import ChatOllama
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        return ChatOllama(model=model, base_url=base_url)
    
    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        return ChatAnthropic(model=model, api_key=api_key)
    
    else:
        raise ValueError(f"Unknown LLM provider: {provider}. Supported: ollama, anthropic")


async def analyze(content: str, prompt: str, system_prompt: str | None = None) -> str:
    """Run single analysis prompt against content.
    
    Args:
        content: The document content to analyze
        prompt: The analysis prompt template (should include {content} placeholder)
        system_prompt: Optional system prompt for context
    
    Returns:
        The LLM's analysis response as a string
    """
    llm = get_llm()
    
    messages = []
    if system_prompt:
        messages.append(SystemMessage(content=system_prompt))
    
    # Format prompt with content
    formatted_prompt = prompt.format(content=content)
    messages.append(HumanMessage(content=formatted_prompt))
    
    response = await llm.ainvoke(messages)
    return response.content


def get_model_info() -> dict:
    """Get information about the configured LLM."""
    llm_model = os.getenv("LLM_MODEL", "ollama:llama3.2")
    provider, model = llm_model.split(":", 1) if ":" in llm_model else ("unknown", llm_model)
    
    return {
        "provider": provider,
        "model": model,
        "env_var": llm_model,
    }