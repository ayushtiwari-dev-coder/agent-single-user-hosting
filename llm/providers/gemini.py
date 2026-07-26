# llm/providers/gemini.py
from typing import List, Dict, Any, Callable, Generator
from google import genai
from google.genai import types
import json
from ..base_provider import BaseLLMProvider
from ..schemas import LLMResponse, ToolCall, StreamChunk
from utils.native_types_helpers import _to_native_types
from llm.context_formatter import format_context
from llm.generate_with_retry import generate_with_retry, is_quota_error
from engine.thinking_configure import get_thinking_config
from utils.config_manager import get_thinking_level
import utils.config_manager as config_manager


class GeminiProvider(BaseLLMProvider):
    def __init__(self, api_key: str, model_name: str):
        super().__init__(api_key, model_name)
        self.client = genai.Client(api_key=self.api_key)

    def format_messages(
        self, standard_messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Maps universal standard messages to Gemini's specific SDK format."""
        gemini_messages = []
        current_function_parts = []  # Buffer to group parallel tool calls

        for msg in standard_messages:
            role = msg["role"]
            content = msg.get("content", "")

            if role == "tool":
                # Buffer the tool responses instead of appending immediately
                current_function_parts.append(
                    {
                        "function_response": {
                            "name": msg.get("tool_name"),
                            "response": {"result": content},
                        }
                    }
                )
            else:
                # If we have buffered tool calls, flush them into a SINGLE message with role 'user'
                if current_function_parts:
                    gemini_messages.append(
                        {"role": "user", "parts": current_function_parts}  # CHANGED: 'function' -> 'user'
                    )
                    current_function_parts = []

                # Handle user/model roles
                gemini_role = "model" if role == "assistant" else "user"
                parts = [{"text": content}] if content else []

                if msg.get("tool_calls"):
                    for tc in msg["tool_calls"]:
                        # SAFELY handle both dicts (from DB) and ToolCall objects
                        if isinstance(tc, dict):
                            tc_name = tc.get("name")
                            tc_args = tc.get("args")
                            metadata = tc.get("metadata", {})
                        else:
                            tc_name = getattr(tc, "name", None)
                            tc_args = getattr(tc, "args", None)
                            metadata = getattr(tc, "metadata", {}) or {}

                        fc_dict = {"name": tc_name, "args": tc_args}
                        if "id" in metadata:
                            fc_dict["id"] = metadata["id"]

                        part_dict = {"function_call": fc_dict}
                        if "thought_signature" in metadata:
                            part_dict["thought_signature"] = metadata[
                                "thought_signature"
                            ]

                        parts.append(part_dict)

                if parts:
                    gemini_messages.append({"role": gemini_role, "parts": parts})

        # Flush any remaining tool calls at the very end of the loop
        if current_function_parts:
            gemini_messages.append(
                {"role": "user", "parts": current_function_parts}  
            )

        return gemini_messages

    def embed_text(self, texts: List[str]) -> List[List[float]]:
        """Generates embeddings using Gemini's native client."""
        try:
            embedding_model = config_manager.get_embedding_model("gemini")
            response = self.client.models.embed_content(
                model=embedding_model, contents=texts
            )
            if not isinstance(response.embeddings, list):
                return [response.embeddings.values]
            return [emb.values for emb in response.embeddings]
        except Exception as e:
            raise RuntimeError(f"Gemini Embedding API failed: {str(e)}")

    def generate_content(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Callable],
        system_instruction: str = "",
        **kwargs,
    ) -> Generator[StreamChunk, None, None]:
        # 1. Extract app-wide logic
        db_sys_inst, standard_msgs = format_context(messages)
        final_system_instruction = f"{system_instruction}\n{db_sys_inst}".strip()

        # 2. Translate to Gemini format
        gemini_messages = self.format_messages(standard_msgs)

        # 3. Build Gemini configuration
        config_params = {
            "automatic_function_calling": types.AutomaticFunctionCallingConfig(
                disable=True
            )
        }

        if final_system_instruction:
            config_params["system_instruction"] = final_system_instruction

        if tools:
            config_params["tools"] = tools

        # Dynamically retrieve and apply active thinking level
        active_thinking_level = config_manager.get_thinking_level()
        thinking_cfg = get_thinking_config(
            self.model_name, level=active_thinking_level
        )
        if thinking_cfg:
            config_params["thinking_config"] = thinking_cfg

        config = types.GenerateContentConfig(**config_params)

        def make_gemini_request():
            return self.client.models.generate_content_stream(
                model=self.model_name, contents=gemini_messages, config=config
            )

        # 4. Use generic retry template
        stream = generate_with_retry(
            request_fn=make_gemini_request,
            is_quota_error_fn=is_quota_error,
            status_callback=kwargs.get("status_callback"),
            max_attempts=3,
        )

        # 5. Parse and yield chunks
        for chunk in stream:
            text_chunk = ""
            tool_deltas = []

            if chunk.candidates and chunk.candidates[0].content:
                for part in chunk.candidates[0].content.parts:
                    if part.text:
                        text_chunk += part.text

                    if part.function_call:
                        metadata = {}
                        if (
                            hasattr(part, "thought_signature")
                            and part.thought_signature
                        ):
                            metadata["thought_signature"] = part.thought_signature

                        tool_deltas.append(
                            {
                                "index": 0,
                                "id": getattr(
                                    part.function_call,
                                    "id",
                                    f"call_{part.function_call.name}",
                                ),
                                "name": part.function_call.name,
                                "arguments": json.dumps(
                                    _to_native_types(part.function_call.args)
                                ),
                                "metadata": metadata,
                            }
                        )

            # Extract usage if final chunk
            prompt_tokens = (
                chunk.usage_metadata.prompt_token_count
                if chunk.usage_metadata
                else 0
            )
            comp_tokens = (
                chunk.usage_metadata.candidates_token_count
                if chunk.usage_metadata
                else 0
            )
            is_finished = True if chunk.usage_metadata else False

            yield StreamChunk(
                text=text_chunk,
                tool_call_deltas=tool_deltas,
                is_finished=is_finished,
                prompt_tokens=prompt_tokens,
                completion_tokens=comp_tokens,
            )