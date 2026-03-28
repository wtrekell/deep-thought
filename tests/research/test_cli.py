"""Tests for the Research Tool CLI argument parsing, helpers, and dispatch."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from deep_thought.research.cli import (
    _build_research_parser,
    _build_search_parser,
    _handle_save_config,
    _parse_domains,
    _run_command,
    _setup_logging,
    cmd_config,
    cmd_init,
    cmd_research,
    cmd_search,
    research_main,
    search_main,
)

# ---------------------------------------------------------------------------
# TestBuildSearchParser
# ---------------------------------------------------------------------------


class TestBuildSearchParser:
    """Tests for _build_search_parser."""

    def test_returns_parser(self) -> None:
        """Should return an ArgumentParser instance."""
        parser = _build_search_parser()
        assert isinstance(parser, argparse.ArgumentParser)

    def test_query_positional(self) -> None:
        """Should accept a positional query argument and store it as args.query."""
        parser = _build_search_parser()
        args = parser.parse_args(["test query"])
        assert args.query == "test query"

    def test_quick_flag(self) -> None:
        """Should parse --quick as True when present."""
        parser = _build_search_parser()
        args = parser.parse_args(["some query", "--quick"])
        assert args.quick is True

    def test_quick_flag_default(self) -> None:
        """Should default --quick to False when not provided."""
        parser = _build_search_parser()
        args = parser.parse_args(["some query"])
        assert args.quick is False

    def test_context_repeatable(self) -> None:
        """Should accumulate --context values into a list when specified multiple times."""
        parser = _build_search_parser()
        args = parser.parse_args(["my query", "--context", "a.md", "--context", "b.md"])
        assert len(args.context) == 2
        assert "a.md" in args.context
        assert "b.md" in args.context

    def test_domains_flag(self) -> None:
        """Should parse --domains as a raw string value."""
        parser = _build_search_parser()
        args = parser.parse_args(["my query", "--domains", "example.com,test.com"])
        assert args.domains == "example.com,test.com"

    def test_recency_choices(self) -> None:
        """Should parse --recency with a valid choice like 'week'."""
        parser = _build_search_parser()
        args = parser.parse_args(["my query", "--recency", "week"])
        assert args.recency == "week"

    def test_dry_run_flag(self) -> None:
        """Should parse --dry-run as True when present."""
        parser = _build_search_parser()
        args = parser.parse_args(["my query", "--dry-run"])
        assert args.dry_run is True

    def test_verbose_flag(self) -> None:
        """Should parse --verbose as True when present."""
        parser = _build_search_parser()
        args = parser.parse_args(["my query", "--verbose"])
        assert args.verbose is True


# ---------------------------------------------------------------------------
# TestBuildResearchParser
# ---------------------------------------------------------------------------


class TestBuildResearchParser:
    """Tests for _build_research_parser."""

    def test_returns_parser(self) -> None:
        """Should return an ArgumentParser instance."""
        parser = _build_research_parser()
        assert isinstance(parser, argparse.ArgumentParser)

    def test_subcommand_without_query_accepted(self) -> None:
        """Should parse 'init' subcommand without requiring a query argument."""
        parser = _build_research_parser()
        # query is not declared in the parser; subcommand works without a free-text arg
        args = parser.parse_args(["init"])
        assert args.subcommand == "init"

    def test_no_quick_flag(self) -> None:
        """Should not expose a --quick flag on the research parser."""
        parser = _build_research_parser()
        args = parser.parse_args([])
        assert not hasattr(args, "quick")

    def test_init_subcommand(self) -> None:
        """Should parse 'init' and store it as args.subcommand."""
        parser = _build_research_parser()
        args = parser.parse_args(["init"])
        assert args.subcommand == "init"

    def test_config_subcommand(self) -> None:
        """Should parse 'config' and store it as args.subcommand."""
        parser = _build_research_parser()
        args = parser.parse_args(["config"])
        assert args.subcommand == "config"


# ---------------------------------------------------------------------------
# TestParseDomains
# ---------------------------------------------------------------------------


class TestParseDomains:
    """Tests for _parse_domains."""

    def test_basic_parsing(self) -> None:
        """Should split a comma-separated string into a list of domain strings."""
        result = _parse_domains("a.com,b.com")
        assert result == ["a.com", "b.com"]

    def test_strips_whitespace(self) -> None:
        """Should strip leading and trailing whitespace from each domain."""
        result = _parse_domains("a.com, b.com")
        assert result == ["a.com", "b.com"]

    def test_filters_empty(self) -> None:
        """Should discard empty strings that result from consecutive commas."""
        result = _parse_domains("a.com,,b.com")
        assert result == ["a.com", "b.com"]

    @pytest.mark.error_handling
    def test_max_domains_exceeded(self) -> None:
        """Should raise ValueError when more than 20 domains are supplied."""
        twenty_one_domains = ",".join(f"domain{index}.com" for index in range(21))
        with pytest.raises(ValueError, match="20"):
            _parse_domains(twenty_one_domains)

    @pytest.mark.error_handling
    def test_mixed_allow_deny_raises(self) -> None:
        """Should raise ValueError when allowlist and denylist domains are mixed."""
        with pytest.raises(ValueError):
            _parse_domains("a.com,-b.com")

    def test_all_denylist(self) -> None:
        """Should accept a list where all domains are prefixed with '-'."""
        result = _parse_domains("-a.com,-b.com")
        assert result == ["-a.com", "-b.com"]


# ---------------------------------------------------------------------------
# TestSetupLogging
# ---------------------------------------------------------------------------


class TestSetupLogging:
    """Tests for _setup_logging."""

    def test_verbose_sets_debug(self) -> None:
        """Should set the root logger to DEBUG level when verbose is True."""
        _setup_logging(verbose=True)
        assert logging.getLogger().level == logging.DEBUG

    def test_non_verbose_sets_info(self) -> None:
        """Should set the root logger to INFO level when verbose is False."""
        _setup_logging(verbose=False)
        assert logging.getLogger().level == logging.INFO


# ---------------------------------------------------------------------------
# TestRunCommand
# ---------------------------------------------------------------------------


class TestRunCommand:
    """Tests for _run_command error wrapper."""

    def test_calls_handler(self) -> None:
        """Should invoke the provided handler callable and return 0 on success."""
        handler = MagicMock(return_value=None)
        args = argparse.Namespace()
        return_code = _run_command(handler, args)
        handler.assert_called_once_with(args)
        assert return_code == 0

    def test_catches_file_not_found(self) -> None:
        """Should return 1 when the handler raises FileNotFoundError."""
        handler = MagicMock(side_effect=FileNotFoundError("missing.yaml"))
        return_code = _run_command(handler, argparse.Namespace())
        assert return_code == 1

    def test_catches_value_error(self) -> None:
        """Should return 1 when the handler raises ValueError."""
        handler = MagicMock(side_effect=ValueError("bad value"))
        return_code = _run_command(handler, argparse.Namespace())
        assert return_code == 1

    def test_catches_os_error(self) -> None:
        """Should return 1 when the handler raises OSError."""
        handler = MagicMock(side_effect=OSError("disk full"))
        return_code = _run_command(handler, argparse.Namespace())
        assert return_code == 1

    @pytest.mark.error_handling
    def test_catches_generic_exception(self) -> None:
        """Should return 1 when the handler raises an unexpected Exception."""
        handler = MagicMock(side_effect=Exception("something went wrong"))
        return_code = _run_command(handler, argparse.Namespace())
        assert return_code == 1


# ---------------------------------------------------------------------------
# TestSearchMain
# ---------------------------------------------------------------------------


class TestSearchMain:
    """Tests for search_main."""

    def test_no_args_shows_help(self) -> None:
        """Should exit with code 2 when required positional query is missing."""
        with patch("sys.argv", ["search"]), pytest.raises(SystemExit) as exit_info:
            search_main()
        assert exit_info.value.code == 2

    def test_dry_run(self) -> None:
        """Should not call the Perplexity API when --dry-run is passed."""
        # PerplexityClient is lazy-imported inside cmd_search; patch at its source module.
        mock_client_class = MagicMock()
        with (
            patch("sys.argv", ["search", "test query", "--dry-run"]),
            patch("deep_thought.research.cli.load_config", return_value=MagicMock()),
            patch("deep_thought.research.cli.get_api_key", return_value="test-api-key"),
            patch("deep_thought.research.researcher.PerplexityClient", mock_client_class),
            pytest.raises(SystemExit),
        ):
            search_main()

        # cmd_search exits early in dry-run mode before constructing the client
        mock_client_class.assert_not_called()


# ---------------------------------------------------------------------------
# TestResearchMain
# ---------------------------------------------------------------------------


class TestResearchMain:
    """Tests for research_main."""

    def test_no_args_shows_help(self) -> None:
        """Should exit with code 0 when called with no arguments (prints help)."""
        with patch("sys.argv", ["research"]), pytest.raises(SystemExit) as exit_info:
            research_main()
        assert exit_info.value.code == 0

    def test_init_subcommand(self) -> None:
        """Should call cmd_init when the 'init' subcommand is provided."""
        with (
            patch("sys.argv", ["research", "init"]),
            patch("deep_thought.research.cli.cmd_init") as mock_cmd_init,
            pytest.raises(SystemExit),
        ):
            research_main()

        mock_cmd_init.assert_called_once()

    def test_config_subcommand(self) -> None:
        """Should call cmd_config when the 'config' subcommand is provided."""
        with (
            patch("sys.argv", ["research", "config"]),
            patch("deep_thought.research.cli.cmd_config") as mock_cmd_config,
            pytest.raises(SystemExit),
        ):
            research_main()

        mock_cmd_config.assert_called_once()

    def test_query_dispatches_to_cmd_research(self) -> None:
        """Should dispatch to cmd_research when a query is provided without a subcommand."""
        with (
            patch("sys.argv", ["research", "Compare MLX vs PyTorch"]),
            patch("deep_thought.research.cli._run_command", return_value=0) as mock_run,
            pytest.raises(SystemExit) as exit_info,
        ):
            research_main()
        mock_run.assert_called_once()
        handler_arg = mock_run.call_args[0][0]
        assert handler_arg is cmd_research
        assert exit_info.value.code == 0

    def test_flags_without_query_or_subcommand_prints_help_and_exits_zero(self) -> None:
        """Should print help and exit 0 when flags are given but no query or subcommand."""
        with (
            patch("sys.argv", ["research", "--verbose"]),
            pytest.raises(SystemExit) as exit_info,
        ):
            research_main()
        assert exit_info.value.code == 0


# ---------------------------------------------------------------------------
# _handle_save_config
# ---------------------------------------------------------------------------


class TestHandleSaveConfig:
    """Tests for _handle_save_config."""

    def test_writes_config_to_destination(self, tmp_path: Path) -> None:
        """Should copy the default config to the specified destination path."""
        destination = tmp_path / "my-config.yaml"

        with patch("deep_thought.research.cli.get_bundled_config_path") as mock_config_path:
            source = tmp_path / "source-config.yaml"
            source.write_text("# example research config\n", encoding="utf-8")
            mock_config_path.return_value = source

            _handle_save_config(str(destination))

        assert destination.exists()
        assert destination.read_text() == "# example research config\n"

    def test_exits_if_source_missing(self, tmp_path: Path) -> None:
        """Should exit with code 1 if the default config template is missing."""
        with patch("deep_thought.research.cli.get_bundled_config_path") as mock_config_path:
            mock_config_path.return_value = tmp_path / "nonexistent.yaml"

            with pytest.raises(SystemExit) as exit_info:
                _handle_save_config(str(tmp_path / "output.yaml"))

        assert exit_info.value.code == 1

    def test_exits_if_destination_exists(self, tmp_path: Path) -> None:
        """Should exit with code 1 if the destination file already exists."""
        destination = tmp_path / "existing.yaml"
        destination.write_text("existing content", encoding="utf-8")

        with patch("deep_thought.research.cli.get_bundled_config_path") as mock_config_path:
            source = tmp_path / "source.yaml"
            source.write_text("# config", encoding="utf-8")
            mock_config_path.return_value = source

            with pytest.raises(SystemExit) as exit_info:
                _handle_save_config(str(destination))

        assert exit_info.value.code == 1

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """Should create missing parent directories before writing the config file."""
        destination = tmp_path / "nested" / "dirs" / "my-config.yaml"

        with patch("deep_thought.research.cli.get_bundled_config_path") as mock_config_path:
            source = tmp_path / "source.yaml"
            source.write_text("# config", encoding="utf-8")
            mock_config_path.return_value = source

            _handle_save_config(str(destination))

        assert destination.exists()


# ---------------------------------------------------------------------------
# cmd_init
# ---------------------------------------------------------------------------


class TestCmdInit:
    """Tests for cmd_init."""

    def test_prints_confirmation(self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
        """Should print a confirmation message to stdout."""
        monkeypatch.chdir(tmp_path)
        bundled = tmp_path / "bundled.yaml"
        bundled.write_text("api_key_env: TEST_KEY\n", encoding="utf-8")

        with patch("deep_thought.research.cli.get_bundled_config_path", return_value=bundled):
            args = argparse.Namespace(output=None)
            cmd_init(args)

        captured = capsys.readouterr()
        assert "Research Tool initialised" in captured.out

    def test_uses_output_override(self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
        """Should use the --output override path instead of the default output dir."""
        monkeypatch.chdir(tmp_path)
        bundled = tmp_path / "bundled.yaml"
        bundled.write_text("api_key_env: TEST_KEY\n", encoding="utf-8")
        override_output_dir = tmp_path / "custom_output"

        with patch("deep_thought.research.cli.get_bundled_config_path", return_value=bundled):
            args = argparse.Namespace(output=str(override_output_dir))
            cmd_init(args)

        captured = capsys.readouterr()
        assert str(override_output_dir) in captured.out
        assert override_output_dir.exists()

    def test_creates_output_directory(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should create the default output directory on disk."""
        monkeypatch.chdir(tmp_path)
        bundled = tmp_path / "bundled.yaml"
        bundled.write_text("api_key_env: TEST_KEY\n", encoding="utf-8")

        with patch("deep_thought.research.cli.get_bundled_config_path", return_value=bundled):
            args = argparse.Namespace(output=None)
            cmd_init(args)

        assert (tmp_path / "data" / "research" / "export").exists()

    def test_copies_config_to_project(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should copy the bundled config template to src/config/ in the calling repo."""
        monkeypatch.chdir(tmp_path)
        bundled = tmp_path / "bundled.yaml"
        bundled.write_text("# bundled default\napi_key_env: TEST_KEY\n", encoding="utf-8")

        with patch("deep_thought.research.cli.get_bundled_config_path", return_value=bundled):
            args = argparse.Namespace(output=None)
            cmd_init(args)

        project_config = tmp_path / "src" / "config" / "research-configuration.yaml"
        assert project_config.exists()
        assert project_config.read_text() == "# bundled default\napi_key_env: TEST_KEY\n"

    def test_skips_config_copy_if_exists(self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
        """Should not overwrite an existing project-level config file."""
        monkeypatch.chdir(tmp_path)
        bundled = tmp_path / "bundled.yaml"
        bundled.write_text("# new content\n", encoding="utf-8")
        project_config = tmp_path / "src" / "config" / "research-configuration.yaml"
        project_config.parent.mkdir(parents=True)
        project_config.write_text("# existing content\n", encoding="utf-8")

        with patch("deep_thought.research.cli.get_bundled_config_path", return_value=bundled):
            args = argparse.Namespace(output=None)
            cmd_init(args)

        assert project_config.read_text() == "# existing content\n"
        captured = capsys.readouterr()
        assert "already exists" in captured.out


# ---------------------------------------------------------------------------
# cmd_config
# ---------------------------------------------------------------------------


class TestCmdConfig:
    """Tests for cmd_config."""

    def test_prints_valid_config_fields(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Should print all configuration fields when config is valid."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            "api_key_env: MY_PERPLEXITY_KEY\nsearch_model: sonar\nresearch_model: sonar-deep-research\n",
            encoding="utf-8",
        )
        args = argparse.Namespace(config=str(config_file))
        cmd_config(args)
        captured = capsys.readouterr()
        assert "Configuration is valid" in captured.out
        assert "MY_PERPLEXITY_KEY" in captured.out

    def test_exits_one_with_validation_issues(self, tmp_path: Path) -> None:
        """Should exit with code 1 when the config has validation issues."""
        config_file = tmp_path / "config.yaml"
        # api_key_env is empty, which triggers a validation issue.
        config_file.write_text('api_key_env: ""\n', encoding="utf-8")
        args = argparse.Namespace(config=str(config_file))
        with pytest.raises(SystemExit) as exit_info:
            cmd_config(args)
        assert exit_info.value.code == 1

    def test_prints_issues_to_stderr(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Should print validation issues to stderr when config is invalid."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text('api_key_env: ""\n', encoding="utf-8")
        args = argparse.Namespace(config=str(config_file))
        with pytest.raises(SystemExit):
            cmd_config(args)
        captured = capsys.readouterr()
        assert "WARNING" in captured.err


# ---------------------------------------------------------------------------
# cmd_search
# ---------------------------------------------------------------------------


class TestCmdSearch:
    """Tests for cmd_search."""

    def _make_search_args(self, tmp_path: Path, **overrides: object) -> argparse.Namespace:
        """Return a Namespace with defaults suitable for cmd_search tests."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            f"api_key_env: TEST_KEY\noutput_dir: {tmp_path}/output\n",
            encoding="utf-8",
        )
        defaults: dict[str, object] = {
            "query": "What is MLX?",
            "quick": False,
            "dry_run": False,
            "recency": None,
            "domains": None,
            "context": None,
            "output": None,
            "config": str(config_file),
        }
        defaults.update(overrides)
        return argparse.Namespace(**defaults)

    def test_dry_run_prints_preview_without_api_call(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Should print a dry-run preview and return without making any API calls."""
        args = self._make_search_args(tmp_path, dry_run=True)
        cmd_search(args)
        captured = capsys.readouterr()
        assert "dry-run" in captured.out
        assert "What is MLX?" in captured.out

    def test_quick_prints_answer_to_stdout(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """With --quick, should print the answer to stdout without writing a file."""
        args = self._make_search_args(tmp_path, quick=True)

        mock_result = MagicMock()
        mock_result.answer = "MLX is an array framework for Apple Silicon."
        mock_client = MagicMock()
        mock_client.search.return_value = mock_result

        with (
            patch.dict(
                "sys.modules",
                {
                    "deep_thought.research.researcher": MagicMock(PerplexityClient=MagicMock(return_value=mock_client)),
                    "deep_thought.research.output": MagicMock(
                        generate_research_markdown=MagicMock(return_value="# content"),
                        write_research_file=MagicMock(return_value=Path("/out/file.md")),
                    ),
                },
            ),
            patch("deep_thought.research.cli.get_api_key", return_value="fake_key"),
        ):
            cmd_search(args)

        captured = capsys.readouterr()
        assert "MLX is an array framework" in captured.out

    def test_writes_file_and_prints_summary(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Should write markdown to a file and print a summary when not --quick."""
        args = self._make_search_args(tmp_path)

        mock_result = MagicMock()
        mock_result.answer = "The answer."
        mock_result.search_results = [MagicMock(), MagicMock()]
        mock_result.cost_usd = 0.0042
        mock_client = MagicMock()
        mock_client.search.return_value = mock_result
        written_output_path = tmp_path / "output" / "2026-03-23_what-is-mlx.md"

        with (
            patch.dict(
                "sys.modules",
                {
                    "deep_thought.research.researcher": MagicMock(PerplexityClient=MagicMock(return_value=mock_client)),
                    "deep_thought.research.output": MagicMock(
                        generate_research_markdown=MagicMock(return_value="# content"),
                        write_research_file=MagicMock(return_value=written_output_path),
                    ),
                },
            ),
            patch("deep_thought.research.cli.get_api_key", return_value="fake_key"),
        ):
            cmd_search(args)

        captured = capsys.readouterr()
        assert "Search complete" in captured.out
        assert "Sources: 2" in captured.out

    def test_parses_domains_before_api_call(
        self,
        tmp_path: Path,
    ) -> None:
        """Should pass parsed domain list to the client.search() call."""
        args = self._make_search_args(tmp_path, domains="example.com,other.org")

        mock_result = MagicMock()
        mock_result.search_results = []
        mock_result.cost_usd = 0.001
        mock_client = MagicMock()
        mock_client.search.return_value = mock_result
        written_output_path = tmp_path / "output" / "result.md"

        with (
            patch.dict(
                "sys.modules",
                {
                    "deep_thought.research.researcher": MagicMock(PerplexityClient=MagicMock(return_value=mock_client)),
                    "deep_thought.research.output": MagicMock(
                        generate_research_markdown=MagicMock(return_value="# content"),
                        write_research_file=MagicMock(return_value=written_output_path),
                    ),
                },
            ),
            patch("deep_thought.research.cli.get_api_key", return_value="fake_key"),
        ):
            cmd_search(args)

        call_kwargs = mock_client.search.call_args.kwargs
        assert call_kwargs["domains"] == ["example.com", "other.org"]


# ---------------------------------------------------------------------------
# cmd_research
# ---------------------------------------------------------------------------


class TestCmdResearch:
    """Tests for cmd_research."""

    def _make_research_args(self, tmp_path: Path, **overrides: object) -> argparse.Namespace:
        """Return a Namespace with defaults suitable for cmd_research tests."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            f"api_key_env: TEST_KEY\noutput_dir: {tmp_path}/output\n",
            encoding="utf-8",
        )
        defaults: dict[str, object] = {
            "query": "Compare MLX vs PyTorch",
            "dry_run": False,
            "recency": None,
            "domains": None,
            "context": None,
            "output": None,
            "config": str(config_file),
        }
        defaults.update(overrides)
        return argparse.Namespace(**defaults)

    @pytest.mark.error_handling
    def test_raises_value_error_when_no_query(self, tmp_path: Path) -> None:
        """Should raise ValueError when query is None."""
        args = self._make_research_args(tmp_path, query=None)
        with pytest.raises(ValueError, match="query is required"):
            cmd_research(args)

    def test_dry_run_prints_preview_without_api_call(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Should print a dry-run preview and return without making any API calls."""
        args = self._make_research_args(tmp_path, dry_run=True)
        cmd_research(args)
        captured = capsys.readouterr()
        assert "dry-run" in captured.out
        assert "Compare MLX vs PyTorch" in captured.out

    def test_prints_submitting_message_before_api_call(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Should print 'Submitting deep research query...' before making the API call."""
        args = self._make_research_args(tmp_path)

        mock_result = MagicMock()
        mock_result.search_results = []
        mock_result.cost_usd = 0.24
        mock_client = MagicMock()
        mock_client.research.return_value = mock_result
        written_output_path = tmp_path / "output" / "result.md"

        with (
            patch.dict(
                "sys.modules",
                {
                    "deep_thought.research.researcher": MagicMock(PerplexityClient=MagicMock(return_value=mock_client)),
                    "deep_thought.research.output": MagicMock(
                        generate_research_markdown=MagicMock(return_value="# content"),
                        write_research_file=MagicMock(return_value=written_output_path),
                    ),
                },
            ),
            patch("deep_thought.research.cli.get_api_key", return_value="fake_key"),
        ):
            cmd_research(args)

        captured = capsys.readouterr()
        assert "Submitting deep research query" in captured.out

    def test_writes_file_and_prints_summary(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Should write markdown to a file and print a summary upon completion."""
        args = self._make_research_args(tmp_path)

        mock_result = MagicMock()
        mock_result.search_results = [MagicMock(), MagicMock(), MagicMock()]
        mock_result.cost_usd = 0.24
        mock_client = MagicMock()
        mock_client.research.return_value = mock_result
        written_output_path = tmp_path / "output" / "2026-03-23_compare-mlx.md"

        with (
            patch.dict(
                "sys.modules",
                {
                    "deep_thought.research.researcher": MagicMock(PerplexityClient=MagicMock(return_value=mock_client)),
                    "deep_thought.research.output": MagicMock(
                        generate_research_markdown=MagicMock(return_value="# content"),
                        write_research_file=MagicMock(return_value=written_output_path),
                    ),
                },
            ),
            patch("deep_thought.research.cli.get_api_key", return_value="fake_key"),
        ):
            cmd_research(args)

        captured = capsys.readouterr()
        assert "Research complete" in captured.out
        assert "Sources: 3" in captured.out
