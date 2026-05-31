"""LLM configuration and upstream errors surfaced to API clients."""


class LlmConfigurationError(RuntimeError):
    """DeepSeek (or other LLM) is not configured for live calls."""


class LlmUpstreamError(RuntimeError):
    """LLM provider returned an error or the request failed."""
