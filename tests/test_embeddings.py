"""Tests for deep_thought.embeddings — shared embedding infrastructure.

All tests mock the Qdrant client so no live server is required.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from deep_thought.embeddings import (
    COLLECTION_NAME,
    PAYLOAD_INDEX_FIELDS,
    ensure_collection,
    search_embeddings,
    strip_frontmatter,
    write_embedding,
)


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


class TestStripFrontmatter:
    """Unit tests for strip_frontmatter()."""

    def test_removes_yaml_frontmatter_from_content(self) -> None:
        """Frontmatter delimited by --- is removed; body content is returned."""
        markdown_with_frontmatter = "---\ntitle: Test\ndate: 2026-04-09\n---\n\n# Heading\n\nBody text."
        result = strip_frontmatter(markdown_with_frontmatter)
        assert result == "# Heading\n\nBody text."

    def test_content_without_frontmatter_returned_unchanged(self) -> None:
        """A string that does not start with --- is returned exactly as given."""
        plain_markdown = "# Heading\n\nNo frontmatter here."
        result = strip_frontmatter(plain_markdown)
        assert result == plain_markdown

    def test_triple_dash_inside_yaml_value_not_treated_as_closing_delimiter(self) -> None:
        """A --- that appears mid-value (not on its own line after a newline) is not a closing delimiter."""
        # The closing delimiter is found via "\n---" so a value of "foo---bar" is safe.
        markdown_text = "---\ntitle: foo---bar\n---\n\nBody after real closing delimiter."
        result = strip_frontmatter(markdown_text)
        assert result == "Body after real closing delimiter."

    def test_empty_string_returned_unchanged(self) -> None:
        """An empty string input produces an empty string output."""
        result = strip_frontmatter("")
        assert result == ""

    def test_frontmatter_only_with_no_body_returns_empty_string(self) -> None:
        """Frontmatter with no following body content produces an empty string."""
        frontmatter_only = "---\ntitle: Only\n---\n"
        result = strip_frontmatter(frontmatter_only)
        assert result == ""

    def test_leading_newlines_after_closing_delimiter_stripped(self) -> None:
        """Newlines immediately after the closing --- are stripped from the body."""
        markdown_text = "---\ntitle: Test\n---\n\n\nFirst paragraph."
        result = strip_frontmatter(markdown_text)
        assert result == "First paragraph."


class TestWriteEmbedding:
    """Unit tests for write_embedding()."""

    def test_upsert_called_with_correct_collection_and_merged_payload(self) -> None:
        """write_embedding upserts to the specified collection with the correct payload."""
        mock_qdrant_client = MagicMock()
        mock_model = MagicMock()
        fake_vector = [0.1] * 384
        source_output_path = "/data/web/article.md"
        source_payload = {"source_tool": "web", "title": "Test Article"}

        with patch("deep_thought.embeddings.embed_text", return_value=fake_vector):
            write_embedding(
                content="Some article content",
                payload=source_payload,
                output_path=source_output_path,
                model=mock_model,
                qdrant_client=mock_qdrant_client,
                collection_name="test_collection",
            )

        mock_qdrant_client.upsert.assert_called_once()
        upsert_kwargs = mock_qdrant_client.upsert.call_args.kwargs
        assert upsert_kwargs["collection_name"] == "test_collection"

        upserted_point = upsert_kwargs["points"][0]
        assert upserted_point.vector == fake_vector
        assert upserted_point.payload["output_path"] == source_output_path
        assert upserted_point.payload["source_tool"] == "web"
        assert upserted_point.payload["title"] == "Test Article"

    def test_point_id_is_uuid5_derived_from_output_path(self) -> None:
        """The Qdrant point ID must be a UUID5 generated from the output_path."""
        mock_qdrant_client = MagicMock()
        mock_model = MagicMock()
        fake_vector = [0.2] * 384
        source_output_path = "/data/reddit/post-123.md"
        expected_point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, source_output_path))

        with patch("deep_thought.embeddings.embed_text", return_value=fake_vector):
            write_embedding(
                content="Reddit post content",
                payload={"source_tool": "reddit"},
                output_path=source_output_path,
                model=mock_model,
                qdrant_client=mock_qdrant_client,
            )

        upsert_kwargs = mock_qdrant_client.upsert.call_args.kwargs
        upserted_point = upsert_kwargs["points"][0]
        assert upserted_point.id == expected_point_id

    def test_default_collection_name_used_when_not_specified(self) -> None:
        """When collection_name is omitted, write_embedding targets COLLECTION_NAME."""
        mock_qdrant_client = MagicMock()
        mock_model = MagicMock()
        fake_vector = [0.3] * 384

        with patch("deep_thought.embeddings.embed_text", return_value=fake_vector):
            write_embedding(
                content="Some content",
                payload={"source_tool": "research"},
                output_path="/data/research/query.md",
                model=mock_model,
                qdrant_client=mock_qdrant_client,
            )

        upsert_kwargs = mock_qdrant_client.upsert.call_args.kwargs
        assert upsert_kwargs["collection_name"] == COLLECTION_NAME


class TestEnsureCollection:
    def test_new_collection_creates_collection_and_all_indexes(self) -> None:
        """A collection that does not exist is created and all 6 payload indexes are added."""
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

    def test_all_six_index_field_names_are_submitted(self) -> None:
        """The exact set of 6 required field names is submitted when no indexes exist."""
        mock_client = _make_qdrant_client(existing_collections=[])

        ensure_collection(mock_client, "my_collection")

        submitted_field_names = {
            index_call.kwargs["field_name"] for index_call in mock_client.create_payload_index.call_args_list
        }
        assert submitted_field_names == set(PAYLOAD_INDEX_FIELDS.keys())


class TestSearchEmbeddings:
    """Tests for search_embeddings() — the shared Qdrant retrieval interface."""

    def _make_mock_client(self) -> MagicMock:
        """Return a mock Qdrant client whose query_points() returns an empty result by default."""
        mock_client = MagicMock()
        mock_client.query_points.return_value.points = []
        return mock_client

    def test_unfiltered_search_passes_no_query_filter(self) -> None:
        """When no source_tool or source_type is given, query_filter must be None."""
        mock_client = self._make_mock_client()
        mock_model = MagicMock()
        fake_vector = [0.1] * 384

        with patch("deep_thought.embeddings.embed_text", return_value=fake_vector):
            search_embeddings(query="async Rust patterns", model=mock_model, qdrant_client=mock_client)

        call_kwargs = mock_client.query_points.call_args.kwargs
        assert call_kwargs["query_filter"] is None

    def test_source_tool_filter_produces_correct_field_condition(self) -> None:
        """Passing source_tool='reddit' must build a Filter with one FieldCondition on source_tool."""
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        mock_client = self._make_mock_client()
        mock_model = MagicMock()
        fake_vector = [0.1] * 384

        with patch("deep_thought.embeddings.embed_text", return_value=fake_vector):
            search_embeddings(
                query="Rust memory safety",
                model=mock_model,
                qdrant_client=mock_client,
                source_tool="reddit",
            )

        call_kwargs = mock_client.query_points.call_args.kwargs
        query_filter = call_kwargs["query_filter"]
        assert isinstance(query_filter, Filter)
        assert len(query_filter.must) == 1
        condition = query_filter.must[0]
        assert isinstance(condition, FieldCondition)
        assert condition.key == "source_tool"
        assert condition.match == MatchValue(value="reddit")

    def test_source_type_filter_produces_correct_field_condition(self) -> None:
        """Passing source_type='research_deep' must build a Filter with one FieldCondition on source_type."""
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        mock_client = self._make_mock_client()
        mock_model = MagicMock()
        fake_vector = [0.1] * 384

        with patch("deep_thought.embeddings.embed_text", return_value=fake_vector):
            search_embeddings(
                query="error handling patterns",
                model=mock_model,
                qdrant_client=mock_client,
                source_type="research_deep",
            )

        call_kwargs = mock_client.query_points.call_args.kwargs
        query_filter = call_kwargs["query_filter"]
        assert isinstance(query_filter, Filter)
        assert len(query_filter.must) == 1
        condition = query_filter.must[0]
        assert isinstance(condition, FieldCondition)
        assert condition.key == "source_type"
        assert condition.match == MatchValue(value="research_deep")

    def test_both_filters_produce_two_must_conditions(self) -> None:
        """Passing both source_tool and source_type must produce a Filter with two must conditions."""
        from qdrant_client.models import Filter

        mock_client = self._make_mock_client()
        mock_model = MagicMock()
        fake_vector = [0.1] * 384

        with patch("deep_thought.embeddings.embed_text", return_value=fake_vector):
            search_embeddings(
                query="documentation quality",
                model=mock_model,
                qdrant_client=mock_client,
                source_tool="web",
                source_type="documentation",
            )

        call_kwargs = mock_client.query_points.call_args.kwargs
        query_filter = call_kwargs["query_filter"]
        assert isinstance(query_filter, Filter)
        assert len(query_filter.must) == 2
        condition_keys = {cond.key for cond in query_filter.must}
        assert condition_keys == {"source_tool", "source_type"}

    def test_limit_parameter_forwarded_to_client_search(self) -> None:
        """The limit argument must be passed through to the Qdrant client search call."""
        mock_client = self._make_mock_client()
        mock_model = MagicMock()
        fake_vector = [0.1] * 384

        with patch("deep_thought.embeddings.embed_text", return_value=fake_vector):
            search_embeddings(
                query="test query",
                model=mock_model,
                qdrant_client=mock_client,
                limit=25,
            )

        call_kwargs = mock_client.query_points.call_args.kwargs
        assert call_kwargs["limit"] == 25

    def test_default_collection_name_used_when_not_specified(self) -> None:
        """When collection_name is omitted, the call must target COLLECTION_NAME."""
        mock_client = self._make_mock_client()
        mock_model = MagicMock()
        fake_vector = [0.1] * 384

        with patch("deep_thought.embeddings.embed_text", return_value=fake_vector):
            search_embeddings(query="test query", model=mock_model, qdrant_client=mock_client)

        call_kwargs = mock_client.query_points.call_args.kwargs
        assert call_kwargs["collection_name"] == COLLECTION_NAME

    def test_query_vector_passed_to_client_search(self) -> None:
        """The embedded query vector must be forwarded to the Qdrant search call."""
        mock_client = self._make_mock_client()
        mock_model = MagicMock()
        distinctive_vector = [0.42] * 384

        with patch("deep_thought.embeddings.embed_text", return_value=distinctive_vector):
            search_embeddings(query="vector passthrough test", model=mock_model, qdrant_client=mock_client)

        call_kwargs = mock_client.query_points.call_args.kwargs
        assert call_kwargs["query"] == distinctive_vector

    def test_results_returned_from_client_search(self) -> None:
        """The list returned by the Qdrant client search call must be returned to the caller."""
        mock_client = self._make_mock_client()
        mock_model = MagicMock()
        fake_vector = [0.1] * 384
        expected_results = [MagicMock(), MagicMock()]
        mock_client.query_points.return_value.points = expected_results

        with patch("deep_thought.embeddings.embed_text", return_value=fake_vector):
            results = search_embeddings(query="return value test", model=mock_model, qdrant_client=mock_client)

        assert results is expected_results
