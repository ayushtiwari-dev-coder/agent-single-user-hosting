import json
import math
from utils import config_manager
from llm.provider_factory import LLMFactory
from queries.memory_queries import (
    create_memory_with_embedding,
    get_memories_by_category,
    create_category_with_embedding,
    get_all_categories,
)
import utils.config_manager as config_manager


def _get_active_provider():
    """Dynamically resolves the active LLM provider for embeddings."""
    # CHANGED: Now fetches the dedicated embedding provider!
    provider_name = config_manager.get_default_embedding_provider()
    model_name = config_manager.get_embedding_model(provider_name)
    api_key = config_manager.get_provider_api_key(provider_name)

    if not api_key:
        raise ValueError(
            f"API key missing for provider '{provider_name}'. Cannot generate embeddings."
        )

    return LLMFactory.get_provider(provider_name, api_key, model_name)


def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Calculates semantic similarity between two vectors."""
    dot_product = sum(x * y for x, y in zip(v1, v2))
    mag1 = math.sqrt(sum(x * x for x in v1))
    mag2 = math.sqrt(sum(x * x for x in v2))
    return dot_product / (mag1 * mag2) if mag1 and mag2 else 0.0


def save_semantic_memory(content: str, suggested_category: str) -> None:
    """Embeds memory, compares categories, and saves to the best block."""
    provider = _get_active_provider()

    # Batch request both embeddings to save network round-trips
    embeddings = provider.embed_text([content, suggested_category])
    memory_vector = embeddings[0]
    category_vector = embeddings[1]

    existing_blocks = get_all_categories()

    best_match_category = None
    best_score = -1.0

    for block in existing_blocks:
        block_vector = json.loads(block["embedding"])
        score = _cosine_similarity(category_vector, block_vector)
        if score > best_score:
            best_score = score
            best_match_category = block["category"]

        similarity_threshold = config_manager.get_memory_similarity_threshold()

    if best_match_category and best_score >= similarity_threshold:
        target_category = best_match_category
    else:
        # Topic drift: Create a brand new block in the database
        target_category = suggested_category
        create_category_with_embedding(target_category, json.dumps(category_vector))

    # Save the raw memory linked to the resolved category
    create_memory_with_embedding(content, target_category, json.dumps(memory_vector))


def retrieve_semantic_memory(
    query_text: str, category: str, limit: int = 3
) -> list[str]:
    """Finds the correct block first, then calculates similarities inside that block."""
    provider = _get_active_provider()

    # 1. Resolve the target block via category vector match
    search_cat_vector = provider.embed_text([category])[0]

    existing_blocks = get_all_categories()
    best_category = None
    best_score = -1.0

    for block in existing_blocks:
        block_vector = json.loads(block["embedding"])
        score = _cosine_similarity(search_cat_vector, block_vector)
        if score > best_score:
            best_score = score
            best_category = block["category"]

    if not best_category:
        return []  # No blocks exist yet

    # 2. Embed the actual user search query
    query_vector = provider.embed_text([query_text])[0]

    # 3. Pull ONLY memories inside this specific block
    stored_memories = get_memories_by_category(best_category)

    results = []
    for mem in stored_memories:
        if mem["embedding"]:
            stored_vector = json.loads(mem["embedding"])
            score = _cosine_similarity(query_vector, stored_vector)
            results.append((score, mem["content"]))

    # Sort and return the highest matches
    results.sort(key=lambda x: x[0], reverse=True)
    return [content for score, content in results[:limit]]
