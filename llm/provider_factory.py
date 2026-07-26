from .base_provider import BaseLLMProvider
from .providers.gemini import GeminiProvider
from .providers.groq import GroqProvider  # Import the new provider


class LLMFactory:
    """Factory class to instantiate the correct LLM provider dynamically."""

    @staticmethod
    def get_provider(
        provider_name: str, api_key: str, model_name: str
    ) -> BaseLLMProvider:
        provider_name = provider_name.strip().lower()
        if provider_name == "gemini":
            return GeminiProvider(api_key=api_key, model_name=model_name)
        elif provider_name == "groq":
            return GroqProvider(api_key=api_key, model_name=model_name)
        else:
            raise ValueError(f"Unsupported LLM provider: '{provider_name}'.")
