# tests/test_memory_manager.py
import pytest
from unittest.mock import patch, MagicMock
from managers.memory_manager import _cosine_similarity, save_semantic_memory


def test_cosine_similarity_math():
    """Verifies the raw math for vector similarity."""
    v1 = [1.0, 0.0, 0.0]
    v2 = [1.0, 0.0, 0.0]
    v3 = [0.0, 1.0, 0.0]

    # Identical vectors should be 1.0
    assert _cosine_similarity(v1, v2) == 1.0
    # Orthogonal (unrelated) vectors should be 0.0
    assert _cosine_similarity(v1, v3) == 0.0


@patch("managers.memory_manager.create_memory_with_embedding")
@patch("managers.memory_manager.create_category_with_embedding")
@patch("managers.memory_manager.get_all_categories")
@patch("managers.memory_manager._get_active_provider")
def test_save_semantic_memory_new_category(
    mock_provider, mock_get_cats, mock_create_cat, mock_create_mem
):
    """If no existing categories match, it should create a new category block."""
    # Mock provider returning dummy embeddings
    mock_llm = MagicMock()
    mock_llm.embed_text.return_value = [
        [0.1, 0.1],
        [0.1, 0.1],
    ]  # content_emb, category_emb
    mock_provider.return_value = mock_llm

    # Mock DB returning NO existing categories
    mock_get_cats.return_value = []

    save_semantic_memory("User likes Python", "Programming")

    # Assert it created a new category AND saved the memory
    mock_create_cat.assert_called_once()
    mock_create_mem.assert_called_once()


@patch(
    "managers.memory_manager.config_manager.get_memory_similarity_threshold",
    return_value=0.8,
)
@patch("managers.memory_manager.create_memory_with_embedding")
@patch("managers.memory_manager.create_category_with_embedding")
@patch("managers.memory_manager.get_all_categories")
@patch("managers.memory_manager._get_active_provider")
def test_save_semantic_memory_existing_category(
    mock_provider, mock_get_cats, mock_create_cat, mock_create_mem, mock_thresh
):
    """If an existing category is highly similar, it should append to it, NOT create a new one."""
    mock_llm = MagicMock()
    # Return vectors that are identical to trigger a 1.0 similarity score
    mock_llm.embed_text.return_value = [[1.0, 0.0], [1.0, 0.0]]
    mock_provider.return_value = mock_llm

    # Mock DB returning an existing category with the exact same vector
    mock_get_cats.return_value = [
        {"category": "Existing Coding Block", "embedding": "[1.0, 0.0]"}
    ]

    save_semantic_memory("User likes Python", "Programming")

    # Assert it DID NOT create a new category, but DID save the memory to the existing one
    mock_create_cat.assert_not_called()
    mock_create_mem.assert_called_once()
    # Verify it used the existing category name
    args, _ = mock_create_mem.call_args
    assert args[1] == "Existing Coding Block"
