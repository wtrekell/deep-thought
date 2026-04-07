"""Tests for config.py: load_config and validate_config."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003

import pytest

from deep_thought.web.config import (
    CrawlConfig,
    WebConfig,
    _merge_configs,
    _parse_crawl_config,
    load_config,
    validate_config,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_crawl_config(
    mode: str = "blog",
    output_dir: str = "output/web/",
    max_depth: int = 3,
    max_pages: int = 100,
    js_wait: float = 1.0,
    retry_attempts: int = 2,
    retry_delay: float = 5.0,
    index_depth: int = 1,
    min_article_words: int = 200,
    llms_lookback_days: int = 30,
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    strip_boilerplate: list[str] | None = None,
    unwrap_tags: list[str] | None = None,
    pagination: str = "none",
    pagination_selector: str | None = None,
    pagination_wait: float = 2.0,
    max_paginations: int = 10,
) -> WebConfig:
    """Build a minimal WebConfig for testing validate_config."""
    crawl = CrawlConfig(
        mode=mode,
        input_url=None,
        max_depth=max_depth,
        max_pages=max_pages,
        js_wait=js_wait,
        browser_channel=None,
        stealth=False,
        headless=True,
        include_patterns=include_patterns or [],
        exclude_patterns=exclude_patterns or [],
        retry_attempts=retry_attempts,
        retry_delay=retry_delay,
        output_dir=output_dir,
        extract_images=False,
        generate_llms_files=True,
        index_depth=index_depth,
        min_article_words=min_article_words,
        changelog_url=None,
        strip_path_prefix=None,
        strip_domain=False,
        llms_lookback_days=llms_lookback_days,
        strip_boilerplate=strip_boilerplate or [],
        unwrap_tags=unwrap_tags or [],
        pagination=pagination,
        pagination_selector=pagination_selector,
        pagination_wait=pagination_wait,
        max_paginations=max_paginations,
        qdrant_collection="deep_thought_db",
    )
    return WebConfig(crawl=crawl)


# ---------------------------------------------------------------------------
# TestLoadConfig
# ---------------------------------------------------------------------------


class TestLoadConfig:
    """Tests for load_config."""

    def test_raises_file_not_found_for_missing_path(self, tmp_path: Path) -> None:
        """load_config must raise FileNotFoundError when the path does not exist."""
        missing_path = tmp_path / "nonexistent.yaml"
        with pytest.raises(FileNotFoundError):
            load_config(missing_path)

    def test_raises_value_error_for_non_mapping_yaml(self, tmp_path: Path) -> None:
        """load_config must raise ValueError when the YAML file contains a list, not a mapping."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text("- item_one\n- item_two\n", encoding="utf-8")
        with pytest.raises(ValueError, match="YAML mapping"):
            load_config(yaml_file)

    def test_loads_mode_from_yaml(self, tmp_path: Path) -> None:
        """load_config must parse the 'mode' key from the YAML file."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text("mode: documentation\noutput_dir: output/web/\n", encoding="utf-8")
        config = load_config(yaml_file)
        assert config.crawl.mode == "documentation"

    def test_defaults_mode_to_blog_when_absent(self, tmp_path: Path) -> None:
        """When 'mode' is absent from YAML, load_config must default to 'blog'."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text("output_dir: output/web/\n", encoding="utf-8")
        config = load_config(yaml_file)
        assert config.crawl.mode == "blog"

    def test_loads_max_pages_from_yaml(self, tmp_path: Path) -> None:
        """load_config must parse 'max_pages' correctly from YAML."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text("max_pages: 50\noutput_dir: output/web/\n", encoding="utf-8")
        config = load_config(yaml_file)
        assert config.crawl.max_pages == 50

    def test_loads_include_patterns_as_list(self, tmp_path: Path) -> None:
        """load_config must parse 'include_patterns' as a list of strings."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(
            "output_dir: output/web/\ninclude_patterns:\n  - /blog/\n  - /news/\n",
            encoding="utf-8",
        )
        config = load_config(yaml_file)
        assert config.crawl.include_patterns == ["/blog/", "/news/"]

    def test_returns_web_config_instance(self, tmp_path: Path) -> None:
        """load_config must always return a WebConfig instance."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text("output_dir: output/web/\n", encoding="utf-8")
        config = load_config(yaml_file)
        assert isinstance(config, WebConfig)


# ---------------------------------------------------------------------------
# TestValidateConfig
# ---------------------------------------------------------------------------


class TestValidateConfig:
    """Tests for validate_config — one test per validation check."""

    def test_returns_empty_list_for_valid_config(self) -> None:
        """A fully valid config must return an empty issues list."""
        config = _make_crawl_config()
        issues = validate_config(config)
        assert issues == []

    def test_invalid_mode_produces_issue(self) -> None:
        """An unrecognised mode value must appear as a validation issue."""
        config = _make_crawl_config(mode="magic")
        issues = validate_config(config)
        assert any("mode" in issue for issue in issues)

    def test_empty_output_dir_produces_issue(self) -> None:
        """An empty output_dir string must appear as a validation issue."""
        config = _make_crawl_config(output_dir="")
        issues = validate_config(config)
        assert any("output_dir" in issue for issue in issues)

    def test_whitespace_only_output_dir_produces_issue(self) -> None:
        """A whitespace-only output_dir must appear as a validation issue."""
        config = _make_crawl_config(output_dir="   ")
        issues = validate_config(config)
        assert any("output_dir" in issue for issue in issues)

    def test_negative_max_depth_produces_issue(self) -> None:
        """A negative max_depth must appear as a validation issue."""
        config = _make_crawl_config(max_depth=-1)
        issues = validate_config(config)
        assert any("max_depth" in issue for issue in issues)

    def test_negative_max_pages_produces_issue(self) -> None:
        """A negative max_pages must appear as a validation issue."""
        config = _make_crawl_config(max_pages=-1)
        issues = validate_config(config)
        assert any("max_pages" in issue for issue in issues)

    def test_negative_js_wait_produces_issue(self) -> None:
        """A negative js_wait must appear as a validation issue."""
        config = _make_crawl_config(js_wait=-0.5)
        issues = validate_config(config)
        assert any("js_wait" in issue for issue in issues)

    def test_negative_retry_attempts_produces_issue(self) -> None:
        """A negative retry_attempts must appear as a validation issue."""
        config = _make_crawl_config(retry_attempts=-1)
        issues = validate_config(config)
        assert any("retry_attempts" in issue for issue in issues)

    def test_negative_retry_delay_produces_issue(self) -> None:
        """A negative retry_delay must appear as a validation issue."""
        config = _make_crawl_config(retry_delay=-1.0)
        issues = validate_config(config)
        assert any("retry_delay" in issue for issue in issues)

    def test_index_depth_zero_produces_issue(self) -> None:
        """An index_depth of 0 must appear as a validation issue (must be >= 1)."""
        config = _make_crawl_config(index_depth=0)
        issues = validate_config(config)
        assert any("index_depth" in issue for issue in issues)

    def test_zero_min_article_words_produces_issue(self) -> None:
        """A min_article_words of 0 must appear as a validation issue (must be > 0)."""
        config = _make_crawl_config(min_article_words=0)
        issues = validate_config(config)
        assert any("min_article_words" in issue for issue in issues)

    def test_negative_llms_lookback_days_produces_issue(self) -> None:
        """A negative llms_lookback_days must appear as a validation issue."""
        config = _make_crawl_config(llms_lookback_days=-1)
        issues = validate_config(config)
        assert any("llms_lookback_days" in issue for issue in issues)

    def test_invalid_include_pattern_produces_issue(self) -> None:
        """An invalid regex in include_patterns must appear as a validation issue."""
        config = _make_crawl_config(include_patterns=["[invalid regex"])
        issues = validate_config(config)
        assert any("include_patterns" in issue for issue in issues)

    def test_invalid_exclude_pattern_produces_issue(self) -> None:
        """An invalid regex in exclude_patterns must appear as a validation issue."""
        config = _make_crawl_config(exclude_patterns=["[invalid regex"])
        issues = validate_config(config)
        assert any("exclude_patterns" in issue for issue in issues)

    def test_invalid_strip_boilerplate_pattern_produces_issue(self) -> None:
        """An invalid regex in strip_boilerplate must appear as a validation issue."""
        config = _make_crawl_config(strip_boilerplate=["[invalid regex"])
        issues = validate_config(config)
        assert any("strip_boilerplate" in issue for issue in issues)

    def test_invalid_pagination_value_produces_issue(self) -> None:
        """An unrecognised pagination value must appear as a validation issue."""
        config = _make_crawl_config(pagination="infinite")
        issues = validate_config(config)
        assert any("pagination" in issue for issue in issues)

    def test_click_pagination_without_selector_produces_issue(self) -> None:
        """click pagination without a pagination_selector must produce a validation issue."""
        config = _make_crawl_config(pagination="click", pagination_selector=None)
        issues = validate_config(config)
        assert any("pagination_selector" in issue for issue in issues)

    def test_click_pagination_with_selector_is_valid(self) -> None:
        """click pagination with a non-empty pagination_selector must not produce an issue."""
        config = _make_crawl_config(pagination="click", pagination_selector="button.load-more")
        issues = validate_config(config)
        assert not any("pagination_selector" in issue for issue in issues)

    def test_multiple_issues_reported_together(self) -> None:
        """Multiple invalid settings must all be reported as separate issues."""
        config = _make_crawl_config(mode="bad-mode", max_depth=-1, min_article_words=0)
        issues = validate_config(config)
        assert len(issues) >= 3


# ---------------------------------------------------------------------------
# TestParseRawConfig
# ---------------------------------------------------------------------------


class TestParseRawConfig:
    """Tests for _parse_crawl_config (internal parsing function)."""

    def _minimal_raw(self) -> dict[str, object]:
        """Return a minimal raw config dict."""
        return {"mode": "blog", "output_dir": "output/web/"}

    def test_parses_input_url(self) -> None:
        """input_url must be parsed as a string when present."""
        raw = self._minimal_raw()
        raw["input_url"] = "https://example.com/blog/"
        config = _parse_crawl_config(raw)
        assert config.input_url == "https://example.com/blog/"

    def test_input_url_defaults_to_none(self) -> None:
        """input_url must default to None when absent from the raw config."""
        config = _parse_crawl_config(self._minimal_raw())
        assert config.input_url is None

    def test_parses_stealth_flag(self) -> None:
        """stealth must be parsed as a boolean."""
        raw = self._minimal_raw()
        raw["stealth"] = True
        config = _parse_crawl_config(raw)
        assert config.stealth is True

    def test_strip_boilerplate_defaults_to_empty_list(self) -> None:
        """strip_boilerplate must default to an empty list when absent."""
        config = _parse_crawl_config(self._minimal_raw())
        assert config.strip_boilerplate == []

    def test_parses_strip_boilerplate_list(self) -> None:
        """strip_boilerplate must be parsed as a list of strings."""
        raw = self._minimal_raw()
        raw["strip_boilerplate"] = [r"Footer.*", r"Nav.*"]
        config = _parse_crawl_config(raw)
        assert config.strip_boilerplate == [r"Footer.*", r"Nav.*"]

    def test_browser_channel_defaults_to_none(self) -> None:
        """browser_channel must default to None when absent."""
        config = _parse_crawl_config(self._minimal_raw())
        assert config.browser_channel is None

    def test_parses_pagination_strategy(self) -> None:
        """pagination must be parsed as a string."""
        raw = self._minimal_raw()
        raw["pagination"] = "scroll"
        config = _parse_crawl_config(raw)
        assert config.pagination == "scroll"


# ---------------------------------------------------------------------------
# TestLoadConfigInheritance
# ---------------------------------------------------------------------------


class TestLoadConfigInheritance:
    """Tests for the 'inherits' base-config feature in load_config."""

    def test_inherits_scalar_child_overrides_parent(self, tmp_path: Path) -> None:
        """A scalar field in the child must override the same field from the parent."""
        base = tmp_path / "_base.yaml"
        base.write_text("mode: blog\nmax_pages: 50\noutput_dir: output/web/\n", encoding="utf-8")
        child = tmp_path / "child.yaml"
        child.write_text("inherits: _base.yaml\nmode: documentation\noutput_dir: output/web/\n", encoding="utf-8")
        config = load_config(child)
        assert config.crawl.mode == "documentation"
        assert config.crawl.max_pages == 50

    def test_inherits_list_concatenation_parent_first(self, tmp_path: Path) -> None:
        """List fields must be concatenated parent-first."""
        base = tmp_path / "_base.yaml"
        base.write_text("include_patterns:\n  - /docs/\noutput_dir: output/web/\n", encoding="utf-8")
        child = tmp_path / "child.yaml"
        child_content = "inherits: _base.yaml\ninclude_patterns:\n  - /api/\noutput_dir: output/web/\n"
        child.write_text(child_content, encoding="utf-8")
        config = load_config(child)
        assert config.crawl.include_patterns == ["/docs/", "/api/"]

    def test_inherits_child_list_extends_empty_parent(self, tmp_path: Path) -> None:
        """When the parent has no list field, the child list is used as-is."""
        base = tmp_path / "_base.yaml"
        base.write_text("output_dir: output/web/\n", encoding="utf-8")
        child = tmp_path / "child.yaml"
        child_content = "inherits: _base.yaml\ninclude_patterns:\n  - /api/\noutput_dir: output/web/\n"
        child.write_text(child_content, encoding="utf-8")
        config = load_config(child)
        assert config.crawl.include_patterns == ["/api/"]

    def test_inherits_parent_list_used_when_child_omits(self, tmp_path: Path) -> None:
        """When the child omits a list field, the parent list is preserved."""
        base = tmp_path / "_base.yaml"
        base.write_text("exclude_patterns:\n  - /login/\noutput_dir: output/web/\n", encoding="utf-8")
        child = tmp_path / "child.yaml"
        child.write_text("inherits: _base.yaml\noutput_dir: output/web/\n", encoding="utf-8")
        config = load_config(child)
        assert config.crawl.exclude_patterns == ["/login/"]

    def test_inherits_all_four_list_fields_concatenated(self, tmp_path: Path) -> None:
        """All four list fields must be concatenated parent-first when both define them."""
        base = tmp_path / "_base.yaml"
        base.write_text(
            "include_patterns:\n  - /a/\nexclude_patterns:\n  - /b/\n"
            "strip_boilerplate:\n  - 'nav'\nunwrap_tags:\n  - span\noutput_dir: output/web/\n",
            encoding="utf-8",
        )
        child = tmp_path / "child.yaml"
        child.write_text(
            "inherits: _base.yaml\ninclude_patterns:\n  - /c/\nexclude_patterns:\n  - /d/\n"
            "strip_boilerplate:\n  - 'footer'\nunwrap_tags:\n  - div\noutput_dir: output/web/\n",
            encoding="utf-8",
        )
        config = load_config(child)
        assert config.crawl.include_patterns == ["/a/", "/c/"]
        assert config.crawl.exclude_patterns == ["/b/", "/d/"]
        assert config.crawl.strip_boilerplate == ["nav", "footer"]
        assert config.crawl.unwrap_tags == ["span", "div"]

    def test_inherits_missing_key_falls_through_to_parse_default(self, tmp_path: Path) -> None:
        """A key absent from both parent and child must resolve to _parse_crawl_config's default."""
        base = tmp_path / "_base.yaml"
        base.write_text("output_dir: output/web/\n", encoding="utf-8")
        child = tmp_path / "child.yaml"
        child.write_text("inherits: _base.yaml\noutput_dir: output/web/\n", encoding="utf-8")
        config = load_config(child)
        assert config.crawl.max_pages == 100  # _parse_crawl_config default

    def test_inherits_missing_base_file_raises_file_not_found(self, tmp_path: Path) -> None:
        """A missing base file must raise FileNotFoundError with the base filename in the message."""
        child = tmp_path / "child.yaml"
        child.write_text("inherits: _nonexistent.yaml\noutput_dir: output/web/\n", encoding="utf-8")
        with pytest.raises(FileNotFoundError, match="_nonexistent.yaml"):
            load_config(child)

    def test_inherits_self_reference_raises_value_error(self, tmp_path: Path) -> None:
        """A config that declares inherits pointing at itself must raise ValueError."""
        child = tmp_path / "child.yaml"
        child.write_text("inherits: child.yaml\noutput_dir: output/web/\n", encoding="utf-8")
        with pytest.raises(ValueError, match="itself"):
            load_config(child)

    def test_inherits_chained_base_file_raises_value_error(self, tmp_path: Path) -> None:
        """A base file that itself declares inherits must raise ValueError."""
        base = tmp_path / "_base.yaml"
        base.write_text("inherits: _other.yaml\noutput_dir: output/web/\n", encoding="utf-8")
        child = tmp_path / "child.yaml"
        child.write_text("inherits: _base.yaml\noutput_dir: output/web/\n", encoding="utf-8")
        with pytest.raises(ValueError, match="cannot themselves inherit"):
            load_config(child)

    def test_inherits_base_file_non_mapping_raises_value_error(self, tmp_path: Path) -> None:
        """A base file containing a YAML list instead of a mapping must raise ValueError."""
        base = tmp_path / "_base.yaml"
        base.write_text("- item_one\n- item_two\n", encoding="utf-8")
        child = tmp_path / "child.yaml"
        child.write_text("inherits: _base.yaml\noutput_dir: output/web/\n", encoding="utf-8")
        with pytest.raises(ValueError, match="YAML mapping"):
            load_config(child)

    def test_no_inherits_field_is_unchanged(self, tmp_path: Path) -> None:
        """A config with no 'inherits' field must load identically to before this feature."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("mode: documentation\noutput_dir: output/web/\n", encoding="utf-8")
        config = load_config(config_file)
        assert config.crawl.mode == "documentation"
        assert config.crawl.max_pages == 100

    def test_inherits_base_file_with_null_inherits_is_allowed(self, tmp_path: Path) -> None:
        """A base file that contains 'inherits: null' must not be rejected."""
        base = tmp_path / "_base.yaml"
        base.write_text("inherits: null\nmax_pages: 75\noutput_dir: output/web/\n", encoding="utf-8")
        child = tmp_path / "child.yaml"
        child.write_text("inherits: _base.yaml\noutput_dir: output/web/\n", encoding="utf-8")
        config = load_config(child)
        assert config.crawl.max_pages == 75

    def test_inherits_child_null_list_field_preserves_parent(self, tmp_path: Path) -> None:
        """A child that sets a list field to null preserves the parent list rather than clearing it."""
        base = tmp_path / "_base.yaml"
        base.write_text("exclude_patterns:\n  - /login/\noutput_dir: output/web/\n", encoding="utf-8")
        child = tmp_path / "child.yaml"
        child.write_text("inherits: _base.yaml\nexclude_patterns: null\noutput_dir: output/web/\n", encoding="utf-8")
        config = load_config(child)
        assert config.crawl.exclude_patterns == ["/login/"]


# ---------------------------------------------------------------------------
# TestMergeConfigs
# ---------------------------------------------------------------------------


class TestMergeConfigs:
    """Unit tests for _merge_configs."""

    def test_scalar_child_wins(self) -> None:
        """A scalar key present in both parent and child must use the child value."""
        parent = {"mode": "blog", "max_pages": 50}
        child = {"mode": "documentation"}
        result = _merge_configs(parent, child)
        assert result["mode"] == "documentation"
        assert result["max_pages"] == 50

    def test_scalar_parent_used_when_child_absent(self) -> None:
        """A scalar key present only in the parent must appear in the merged result."""
        parent = {"max_pages": 50, "output_dir": "output/web/"}
        child = {"output_dir": "output/web/"}
        result = _merge_configs(parent, child)
        assert result["max_pages"] == 50

    def test_list_concatenates_parent_first(self) -> None:
        """List fields must be concatenated with parent entries before child entries."""
        parent = {"include_patterns": ["/a/"]}
        child = {"include_patterns": ["/b/"]}
        result = _merge_configs(parent, child)
        assert result["include_patterns"] == ["/a/", "/b/"]

    def test_null_parent_list_treated_as_empty(self) -> None:
        """A null parent list field must be treated as an empty list during merge."""
        parent = {"include_patterns": None}
        child = {"include_patterns": ["/b/"]}
        result = _merge_configs(parent, child)
        assert result["include_patterns"] == ["/b/"]

    def test_does_not_mutate_inputs(self) -> None:
        """_merge_configs must not mutate either the parent or child dict."""
        parent = {"include_patterns": ["/a/"]}
        child = {"include_patterns": ["/b/"]}
        original_parent_list_id = id(parent["include_patterns"])
        _merge_configs(parent, child)
        assert id(parent["include_patterns"]) == original_parent_list_id
        assert parent["include_patterns"] == ["/a/"]
