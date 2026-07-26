import threading
from database.helper import execute_read
from queries.summary_queries import (
    create_or_update_summary,
    get_summary_by_conversation,
)
from llm.provider_factory import LLMFactory
import utils.config_manager as config_manager
import logging

logger = logging.getLogger("managers.summary_manager")
logger.setLevel(logging.DEBUG)


def trigger_background_summary(
    provider_name: str, api_key: str, model_name: str, conversation_id: int
) -> None:
    thread = threading.Thread(
        target=_run_summary_workflow,
        args=(provider_name, api_key, model_name, conversation_id),
    )
    thread.daemon = True
    thread.start()


def _run_summary_workflow(
    provider_name: str, api_key: str, model_name: str, conversation_id: int
) -> None:

    # 1. Fetch old summary and determine the last message ID we summarized
    summary_record = get_summary_by_conversation(conversation_id)
    last_msg_id = summary_record["last_summarized_message_id"] if summary_record else 0

    # 2. Query the messages table for all un-summarized messages
    query = """
    SELECT id, role, content
    FROM messages
    WHERE conversation_id = ? AND id > ?
    ORDER BY id ASC;
    """
    try:
        raw_messages = execute_read(query, (conversation_id, last_msg_id))
    except Exception:
        return  # Safely ignore DB read errors in the background

    trigger_threshold = config_manager.get_summary_trigger_count()
    if len(raw_messages) < trigger_threshold:
        return

    # 3. Compile the text block to feed to the LLM
    old_summary = (
        summary_record["summary_text"] if summary_record else "No previous summary."
    )
    new_text_to_summarize = ""
    for msg in raw_messages:
        new_text_to_summarize += f"{msg['role']}: {msg['content']}\n"

    prompt = f"""
    You are a background text compressor.
    Incorporate the following new messages into the old running summary of this conversation.
    Keep the summary concise, factual, and strictly under 300 words. Preserve key facts and user preferences.

    [Old Summary]
    {old_summary}

    [New Messages]
    {new_text_to_summarize}
    """

    try:
        # Use our decoupled factory instead of raw direct SDK calls
        provider = LLMFactory.get_provider(provider_name, api_key, model_name)

        # Format the prompt as a standard unified message structure
        messages = [{"role": "user", "content": prompt}]

        # Execute content generation using the unified provider interface
        response = provider.generate_content(messages=messages, tools=[])

        if response.text:
            latest_msg_id = raw_messages[-1]["id"]
            # Save the new compressed summary to the database
            create_or_update_summary(
                conversation_id, response.text.strip(), latest_msg_id
            )
    except Exception as e:
        logger.exception(
            f"Background summary generation failed for conversation {conversation_id}: {e}"
        )
        pass
