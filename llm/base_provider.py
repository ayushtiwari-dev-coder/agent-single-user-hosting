from abc import ABC, abstractmethod
from typing import List, Dict, Any, Callable
from .schemas import LLMResponse


class BaseLLMProvider(ABC):

    def __init__(self, api_key: str, model_name: str):
        self.api_key = api_key
        self.model_name = model_name

    @abstractmethod
    def format_messages(self, db_messages: List[Dict[str, Any]]) -> Any:
        """
        Converts standard database messages (e.g., [{"role": "user", "content": "hi"}])
        into the specific format required by the LLM SDK.
        """
        pass

    @abstractmethod
    def generate_content(
        self,
        messages: Any,
        tools: List[Callable],
        system_instruction: str = "",
        **kwargs
    ) -> LLMResponse:
        """
        Executes the LLM generation.

        Args:
            messages: The formatted messages from format_messages().
            tools: A dynamic list of Python functions (e.g., from get_all_tools()).
                   The provider is responsible for parsing these dynamically.
            system_instruction: The base system prompt.

        Returns:
            LLMResponse: Our standardized schema containing text, tool_calls, and token counts.
        """
        pass

    @abstractmethod
    def embed_text(self, texts: List[str]) -> List[List[float]]:
        """
        Generates coordinate vector lists for a list of strings.
        Args:
            texts: A list of strings to embed.
        Returns:
            A list of float arrays representing the embeddings.
        """
        pass
