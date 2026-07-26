import os
import json

from tools.registry import get_all_tools
from llm.loop_protector import check_for_infinite_loop
from engine.handle_permissions import determine_and_execute_tool
from managers.conversation_manager import (
    compile_llm_context,
    save_user_message,
    save_assistant_message,
    log_api_usage,
)
from managers.summary_manager import trigger_background_summary
from llm.provider_factory import LLMFactory
import utils.config_manager as config_manager
from engine.stream_processor import process_llm_stream, calculate_fallback_tokens


class AgentEngine:
    def __init__(
        self,
        provider_name: str = "gemini",
        model_name: str = "gemini-3.1-flash-lite",
        api_key: str | None = None,
        autonomous: bool = False,
    ):
        # Dynamically map the correct environment variable key name
        env_var_map = {"gemini": "GEMINI_API_KEY", "groq": "GROQ_API_KEY"}
        env_var_name = env_var_map.get(provider_name.lower(), "GEMINI_API_KEY")
        resolved_key = api_key or os.environ.get(env_var_name)

        if not resolved_key:
            raise ValueError(
                f"API Key missing. Must pass api_key or set environment variable {env_var_name} for {provider_name}."
            )

        # Instantiate the provider through the factory
        self.provider = LLMFactory.get_provider(provider_name, resolved_key, model_name)
        self.autonomous = autonomous

    def _trigger_summary_safely(self, conversation_id: int) -> None:
        try:
            trigger_background_summary(
                self.provider.__class__.__name__.replace("Provider", "").lower(),
                self.provider.api_key,
                self.provider.model_name,
                conversation_id,
            )
        except Exception:
            pass

    def send_message(
        self,
        conversation_id: int,
        user_text: str,
        source: str = "cli",
        send_message_callback=None,
        status_callback=None,
        approval_callback=None,
    ) -> str:
        """Executes the ReAct loop using the abstract LLM provider."""
        save_user_message(conversation_id, user_text)

        db_messages = compile_llm_context(conversation_id)
        tool_call_history = []
        turn_count = 0

        MAX_TURNS = config_manager.get_max_turns()

        while True:
            if turn_count >= MAX_TURNS:
                error_msg = (
                    f"Error: Maximum tool execution limit ({MAX_TURNS} turns) reached."
                )
                save_assistant_message(conversation_id, error_msg)
                return error_msg

            turn_count += 1

            if status_callback:
                status_callback(f"Generating thoughts... [Turn #{turn_count}]")

            try:
                # 1. Get the stream from the provider
                stream = self.provider.generate_content(
                    messages=db_messages,
                    tools=get_all_tools(),
                    status_callback=status_callback,
                )

                # 2. Pass to our middle piece to handle buffering and UI callbacks
                full_text, parsed_tool_calls, prompt_tokens, comp_tokens = (
                    process_llm_stream(stream, send_message_callback)
                )

            except Exception as e:
                raise RuntimeError(f"LLM API execution failed: {e}") from e

            if prompt_tokens == 0 or comp_tokens == 0:
                fallback_prompt, fallback_comp = calculate_fallback_tokens(
                    db_messages, full_text, parsed_tool_calls
                )
                # Only overwrite if the API actually failed to provide them
                prompt_tokens = prompt_tokens or fallback_prompt
                comp_tokens = comp_tokens or fallback_comp

            # 4. Log API usage to SQLite
            log_api_usage(
                conversation_id,
                self.provider.model_name,
                prompt_tokens,
                comp_tokens,
            )

            # 4. Execute Tools if requested
            if parsed_tool_calls:
                db_messages.append(
                    {
                        "role": "assistant",
                        "content": full_text,
                        "tool_calls": parsed_tool_calls,
                    }
                )

                for tool_call in parsed_tool_calls:
                    tool_name = tool_call.name
                    tool_args = tool_call.args
                    serialized_args = json.dumps(tool_args, sort_keys=True)

                    is_looping, loop_error, _ = check_for_infinite_loop(
                        tool_call_history, tool_name, tool_args
                    )

                    if is_looping:
                        save_assistant_message(conversation_id, loop_error)
                        return loop_error

                    if status_callback:
                        status_callback(
                            f"Executing tool '{tool_name}' with arguments:\n{tool_args}"
                        )

                    tool_output, status = determine_and_execute_tool(
                        tool_name,
                        tool_args,
                        conversation_id,
                        self.autonomous,
                        approval_callback=approval_callback,
                    )

                    if status_callback:
                        status_callback(
                            f"Tool '{tool_name}' returned status: '{status}'"
                        )

                    tool_call_history.append(
                        {
                            "name": tool_name,
                            "args_json": serialized_args,
                            "status": status,
                        }
                    )

                    if status == "success":
                        formatted_output = f"SYSTEM: Action SUCCESS. DO NOT repeat this action. Review output and move to next step.\n\nOUTPUT:\n{tool_output}"
                    else:
                        formatted_output = f"SYSTEM: Action FAILED. Analyze the error below and change your approach.\n\nERROR:\n{tool_output}"

                    db_messages.append(
                        {
                            "role": "tool",
                            "tool_name": tool_name,
                            "content": formatted_output,
                        }
                    )

                continue

            else:
                # 5. Final text response received
                save_assistant_message(conversation_id, full_text)
                self._trigger_summary_safely(conversation_id)
                return full_text
