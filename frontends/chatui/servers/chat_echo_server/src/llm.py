"""LLM client with multi-provider support via LangGraph."""

import os
from collections.abc import AsyncIterator

from langchain_core.messages import AIMessageChunk, BaseMessage, HumanMessage


def get_llm():
    """Create LLM instance based on LLM_MODEL environment variable.
    
    Format: provider:model (e.g., "ollama:llama3.2", "anthropic:claude-sonnet-4-5")
    """
    llm_model = os.getenv("LLM_MODEL", "ollama:llama3.2")
    
    if ":" not in llm_model:
        raise ValueError(f"LLM_MODEL must be in format 'provider:model', got: {llm_model}")
    
    provider, model = llm_model.split(":", 1)
    
    if provider == "ollama":
        from langchain_ollama import ChatOllama
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        return ChatOllama(
            model=model,
            base_url=base_url,
        )
    
    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        return ChatAnthropic(
            model=model,
            api_key=api_key,
        )
    
    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set")
        return ChatOpenAI(
            model=model,
            api_key=api_key,
        )
    
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")


async def stream_chat(messages: list[dict]) -> AsyncIterator[str]:
    """Stream chat response from LLM.
    
    Args:
        messages: List of message dicts with 'role' and 'content' keys
        
    Yields:
        Content chunks as strings
    """
    llm = get_llm()
    
    # Convert to LangChain message format
    lc_messages: list[BaseMessage] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        
        if role == "user":
            lc_messages.append(HumanMessage(content=content))
        elif role == "assistant":
            from langchain_core.messages import AIMessage
            lc_messages.append(AIMessage(content=content))
        elif role == "system":
            from langchain_core.messages import SystemMessage
            lc_messages.append(SystemMessage(content=content))
    
    # Stream the response
    async for chunk in llm.astream(lc_messages):
        if isinstance(chunk, AIMessageChunk) and chunk.content:
            yield chunk.content