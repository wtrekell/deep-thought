"""Tests for deep_thought.embeddings — shared embedding infrastructure.

All tests mock the Qdrant client so no live server is required.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from deep_thought.embeddings import PAYLOAD_INDEX_FIELDS, ensure_collection


def _make_qdrant_client(
    existing_collections: list[str],
    existing_indexed_fields: dict[str, object] | None = None,
) -> MagicMock:
    """Return a mock Qdrant client with configurable collection and index state.

    Args:
        existing_collections: Names of collections the mock server already knows about.
        existing_indexed_fields: Mapping of field names already indexed on the collection.
            Pass an empty dict or None to simulate a collection with no payload indexes.
    """
    mock_client = MagicMock()

    collection_mocks = []
    for name in existing_collections:
        collection_mock = MagicMock()
        collection_mock.name = name
        collection_mocks.append(collection_mock)
    mock_client.get_collections.return_value.collections = collection_mocks

    collection_info = MagicMock()
    collection_info.payload_schema = existing_indexed_fields or {}
    mock_client.get_collection.return_value = collection_info

    return mock_client


class TestEnsureCollection:
    def test_new_collection_creates_collection_and_all_indexes(self) -> None:
        """A collection that does not exist is created and all 7 payload indexes are added."""
        mock_client = _make_qdrant_client(existing_collections=[])

        ensure_collection(mock_client, "my_collection")

        mock_client.create_collection.assert_called_once()
        assert mock_client.create_payload_index.call_count == len(PAYLOAD_INDEX_FIELDS)

    def test_existing_collection_is_not_recreated(self) -> None:
        """An already-existing collection is not recreated, but missing indexes are still added."""
        mock_client = _make_qdrant_client(existing_collections=["my_collection"])

        ensure_collection(mock_client, "my_collection")

        mock_client.create_collection.assert_not_called()
        assert mock_client.create_payload_index.call_count == len(PAYLOAD_INDEX_FIELDS)

    def test_partial_indexes_only_missing_ones_are_created(self) -> None:
        """When a collection already has some indexes, only the missing ones are created."""
        already_indexed = {field: MagicMock() for field in ["output_path", "source_tool", "rule_name"]}
        mock_client = _make_qdrant_client(
            existing_collections=["my_collection"],
            existing_indexed_fields=already_indexed,
        )

        ensure_collection(mock_client, "my_collection")

        expected_missing_count = len(PAYLOAD_INDEX_FIELDS) - len(already_indexed)
        assert mock_client.create_payload_index.call_count == expected_missing_count

        created_field_names = {
            index_call.kwargs["field_name"] for index_call in mock_client.create_payload_index.call_args_list
        }
        assert created_field_names == set(PAYLOAD_INDEX_FIELDS.keys()) - set(already_indexed.keys())

    def test_fully_indexed_collection_makes_no_index_calls(self) -> None:
        """A collection with all required indexes already present triggers no Qdrant writes."""
        all_indexed = {field: MagicMock() for field in PAYLOAD_INDEX_FIELDS}
        mock_client = _make_qdrant_client(
            existing_collections=["my_collection"],
            existing_indexed_fields=all_indexed,
        )

        ensure_collection(mock_client, "my_collection")

        mock_client.create_collection.assert_not_called()
        mock_client.create_payload_index.assert_not_called()

    def test_create_payload_index_receives_correct_collection_name(self) -> None:
        """Each create_payload_index call targets the correct collection."""
        mock_client = _make_qdrant_client(existing_collections=[])

        ensure_collection(mock_client, "target_collection")

        for index_call in mock_client.create_payload_index.call_args_list:
            assert index_call.kwargs["collection_name"] == "target_collection"

    def test_all_seven_index_field_names_are_submitted(self) -> None:
        """The exact set of 7 required field names is submitted when no indexes exist."""
        mock_client = _make_qdrant_client(existing_collections=[])

        ensure_collection(mock_client, "my_collection")

        submitted_field_names = {
            index_call.kwargs["field_name"] for index_call in mock_client.create_payload_index.call_args_list
        }
        assert submitted_field_names == set(PAYLOAD_INDEX_FIELDS.keys())
