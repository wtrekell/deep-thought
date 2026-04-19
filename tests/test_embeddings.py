"""Tests for deep_thought.embeddings — shared embedding infrastructure.

All tests mock the Qdrant client so no live server is required.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from deep_thought.embeddings import (
    COLLECTION_NAME,
    EMBEDDING_MODEL_NAME,
    INGEST_VERSION,
    PAYLOAD_INDEX_FIELDS,
    chunk_text,
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


class TestChunkText:
    """Unit tests for chunk_text()."""

    def test_empty_text_returns_empty_list(self) -> None:
        """Empty input produces no chunks."""
        assert chunk_text("") == []
        assert chunk_text("   \n  \n  ") == []

    def test_short_text_returns_single_chunk(self) -> None:
        """Text under the chunk budget produces one chunk preserving content."""
        short_text = "This is a short paragraph with only a handful of words."
        result = chunk_text(short_text, max_words=100, overlap_words=10)
        assert len(result) == 1
        assert "short paragraph" in result[0]

    def test_paragraphs_kept_together_when_budget_allows(self) -> None:
        """Multiple short paragraphs combine into one chunk when total fits the budget."""
        text = "First paragraph here.\n\nSecond paragraph follows.\n\nThird and final paragraph."
        result = chunk_text(text, max_words=50, overlap_words=5)
        assert len(result) == 1
        assert "First paragraph" in result[0]
        assert "Third and final" in result[0]

    def test_long_text_splits_into_multiple_chunks(self) -> None:
        """Text exceeding the budget is split into multiple chunks."""
        # 5 paragraphs of 30 words each = 150 words; budget 50, should produce 3+ chunks.
        paragraph = " ".join(["word"] * 30)
        long_text = "\n\n".join([paragraph] * 5)
        result = chunk_text(long_text, max_words=50, overlap_words=10)
        assert len(result) >= 3

    def test_chunks_share_overlap_words(self) -> None:
        """Consecutive chunks share trailing/leading words equal to overlap_words."""
        # Build text with distinct words so we can detect overlap.
        words = [f"word{i}" for i in range(200)]
        text_with_paragraphs = "\n\n".join(" ".join(words[i : i + 40]) for i in range(0, 200, 40))
        result = chunk_text(text_with_paragraphs, max_words=80, overlap_words=10)
        assert len(result) >= 2
        # The tail of chunk N and the head of chunk N+1 should share at least
        # some words from the overlap window.
        first_chunk_tail = result[0].split()[-10:]
        second_chunk_head = result[1].split()[:20]
        shared = set(first_chunk_tail) & set(second_chunk_head)
        assert len(shared) > 0

    def test_giant_paragraph_split_on_word_boundaries(self) -> None:
        """A single paragraph longer than max_words is split mid-paragraph."""
        giant_paragraph = " ".join([f"w{i}" for i in range(500)])
        result = chunk_text(giant_paragraph, max_words=100, overlap_words=20)
        assert len(result) >= 5
        for chunk in result:
            assert len(chunk.split()) <= 100


class TestWriteEmbedding:
    """Unit tests for write_embedding() — chunked schema."""

    def test_single_chunk_doc_writes_one_point_with_provenance(self) -> None:
        """A short doc produces one chunk with all provenance fields populated."""
        mock_qdrant_client = MagicMock()
        mock_model = MagicMock()
        fake_vector = [0.1] * 384
        canonical_id = "https://example.com/article"
        source_payload = {"source_tool": "web", "title": "Test Article"}

        with patch("deep_thought.embeddings.embed_text", return_value=fake_vector):
            write_embedding(
                content="Some short article content.",
                payload=source_payload,
                canonical_id=canonical_id,
                model=mock_model,
                qdrant_client=mock_qdrant_client,
                output_path="/data/web/article.md",
                collection_name="test_collection",
            )

        mock_qdrant_client.upsert.assert_called_once()
        upsert_kwargs = mock_qdrant_client.upsert.call_args.kwargs
        assert upsert_kwargs["collection_name"] == "test_collection"
        assert len(upsert_kwargs["points"]) == 1

        upserted_point = upsert_kwargs["points"][0]
        assert upserted_point.vector == fake_vector
        assert upserted_point.payload["source_tool"] == "web"
        assert upserted_point.payload["title"] == "Test Article"
        assert upserted_point.payload["canonical_id"] == canonical_id
        assert upserted_point.payload["parent_id"] == canonical_id
        assert upserted_point.payload["chunk_index"] == 0
        assert upserted_point.payload["chunk_count"] == 1
        assert upserted_point.payload["embedding_model"] == EMBEDDING_MODEL_NAME
        assert upserted_point.payload["ingest_version"] == INGEST_VERSION
        assert upserted_point.payload["chunk_text"] == "Some short article content."
        assert upserted_point.payload["output_path"] == "/data/web/article.md"

    def test_long_doc_writes_multiple_chunks(self) -> None:
        """A doc longer than the chunk budget produces multiple points sharing parent_id."""
        mock_qdrant_client = MagicMock()
        mock_model = MagicMock()
        fake_vector = [0.2] * 384
        canonical_id = "https://example.com/long-doc"
        long_content = "\n\n".join(" ".join([f"word{i}"] * 40) for i in range(20))

        with patch("deep_thought.embeddings.embed_text", return_value=fake_vector):
            write_embedding(
                content=long_content,
                payload={"source_tool": "web"},
                canonical_id=canonical_id,
                model=mock_model,
                qdrant_client=mock_qdrant_client,
            )

        upsert_kwargs = mock_qdrant_client.upsert.call_args.kwargs
        assert len(upsert_kwargs["points"]) > 1

        chunk_count = len(upsert_kwargs["points"])
        for chunk_index, point in enumerate(upsert_kwargs["points"]):
            assert point.payload["parent_id"] == canonical_id
            assert point.payload["chunk_index"] == chunk_index
            assert point.payload["chunk_count"] == chunk_count

    def test_point_id_is_uuid5_of_canonical_id_plus_chunk_index(self) -> None:
        """Each chunk's point ID is a UUID5 of ``canonical_id#chunk-{index}``."""
        mock_qdrant_client = MagicMock()
        mock_model = MagicMock()
        fake_vector = [0.3] * 384
        canonical_id = "https://reddit.com/r/x/comments/abc"
        expected_first_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{canonical_id}#chunk-0"))

        with patch("deep_thought.embeddings.embed_text", return_value=fake_vector):
            write_embedding(
                content="Single chunk content.",
                payload={"source_tool": "reddit"},
                canonical_id=canonical_id,
                model=mock_model,
                qdrant_client=mock_qdrant_client,
            )

        upsert_kwargs = mock_qdrant_client.upsert.call_args.kwargs
        assert upsert_kwargs["points"][0].id == expected_first_id

    def test_stale_chunks_deleted_before_upsert(self) -> None:
        """Existing chunks for the same canonical_id are deleted before new chunks are upserted."""
        from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue

        mock_qdrant_client = MagicMock()
        mock_model = MagicMock()
        fake_vector = [0.4] * 384
        canonical_id = "msg-id-12345"

        with patch("deep_thought.embeddings.embed_text", return_value=fake_vector):
            write_embedding(
                content="Email body content.",
                payload={"source_tool": "gmail"},
                canonical_id=canonical_id,
                model=mock_model,
                qdrant_client=mock_qdrant_client,
            )

        mock_qdrant_client.delete.assert_called_once()
        delete_kwargs = mock_qdrant_client.delete.call_args.kwargs
        selector = delete_kwargs["points_selector"]
        assert isinstance(selector, FilterSelector)
        assert isinstance(selector.filter, Filter)
        condition = selector.filter.must[0]
        assert isinstance(condition, FieldCondition)
        assert condition.key == "parent_id"
        assert condition.match == MatchValue(value=canonical_id)

    def test_default_collection_name_used_when_not_specified(self) -> None:
        """When collection_name is omitted, write_embedding targets COLLECTION_NAME."""
        mock_qdrant_client = MagicMock()
        mock_model = MagicMock()
        fake_vector = [0.5] * 384

        with patch("deep_thought.embeddings.embed_text", return_value=fake_vector):
            write_embedding(
                content="Some content.",
                payload={"source_tool": "research"},
                canonical_id="search:test query@2026-04-19T00:00:00Z",
                model=mock_model,
                qdrant_client=mock_qdrant_client,
            )

        upsert_kwargs = mock_qdrant_client.upsert.call_args.kwargs
        assert upsert_kwargs["collection_name"] == COLLECTION_NAME

    def test_output_path_omitted_when_not_supplied(self) -> None:
        """When output_path is None, the payload does not carry an output_path key."""
        mock_qdrant_client = MagicMock()
        mock_model = MagicMock()
        fake_vector = [0.6] * 384

        with patch("deep_thought.embeddings.embed_text", return_value=fake_vector):
            write_embedding(
                content="Content without a backing file.",
                payload={"source_tool": "research"},
                canonical_id="research:test@2026-04-19",
                model=mock_model,
                qdrant_client=mock_qdrant_client,
            )

        upsert_kwargs = mock_qdrant_client.upsert.call_args.kwargs
        assert "output_path" not in upsert_kwargs["points"][0].payload

    def test_empty_content_writes_nothing(self) -> None:
        """Empty or whitespace-only content produces no upsert and no delete."""
        mock_qdrant_client = MagicMock()
        mock_model = MagicMock()
        fake_vector = [0.0] * 384

        with patch("deep_thought.embeddings.embed_text", return_value=fake_vector):
            write_embedding(
                content="   \n  \n  ",
                payload={"source_tool": "web"},
                canonical_id="https://example.com/empty",
                model=mock_model,
                qdrant_client=mock_qdrant_client,
            )

        mock_qdrant_client.upsert.assert_not_called()
        mock_qdrant_client.delete.assert_not_called()


class TestEnsureCollection:
    def test_new_collection_creates_collection_and_all_indexes(self) -> None:
        """A collection that does not exist is created and all required payload indexes are added."""
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
        already_indexed = {field: MagicMock() for field in ["source_tool", "rule_name"]}
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

    def test_all_required_index_field_names_are_submitted(self) -> None:
        """The exact set of required field names is submitted when no indexes exist."""
        mock_client = _make_qdrant_client(existing_collections=[])

        ensure_collection(mock_client, "my_collection")

        submitted_field_names = {
            index_call.kwargs["field_name"] for index_call in mock_client.create_payload_index.call_args_list
        }
        assert submitted_field_names == set(PAYLOAD_INDEX_FIELDS.keys())

    def test_output_path_is_not_indexed(self) -> None:
        """``output_path`` is intentionally absent from PAYLOAD_INDEX_FIELDS (advisory only)."""
        assert "output_path" not in PAYLOAD_INDEX_FIELDS


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
