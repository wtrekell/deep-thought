"""Tests for the audio CLI entry point in deep_thought.audio.cli."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from deep_thought.audio.cli import (
    _COMMAND_HANDLERS,
    _build_argument_parser,
    _build_config_with_overrides,
    _build_root_parser_with_transcribe_defaults,
    _get_version,
    _load_config_from_args,
    _resolve_output_root,
    _setup_logging,
    cmd_config,
    cmd_init,
    cmd_transcribe,
    main,
)
from deep_thought.audio.config import (
    AudioConfig,
    DiarizationConfig,
    EngineConfig,
    FillerConfig,
    HallucinationConfig,
    LimitsConfig,
    OutputConfig,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(
    engine: str = "mlx",
    model: str = "small",
    language: str | None = "en",
    output_mode: str = "paragraph",
    pause_threshold: float = 1.5,
    output_dir: str = "data/audio/export/",
    generate_llms_files: bool = True,
    diarize: bool = False,
    remove_fillers: bool = False,
) -> AudioConfig:
    """Return an AudioConfig with sensible test defaults."""
    return AudioConfig(
        engine=EngineConfig(engine=engine, model=model, language=language),
        output=OutputConfig(
            output_mode=output_mode,
            pause_threshold=pause_threshold,
            output_dir=output_dir,
            generate_llms_files=generate_llms_files,
        ),
        diarization=DiarizationConfig(diarize=diarize, hf_token_env="HF_TOKEN"),
        filler=FillerConfig(remove_fillers=remove_fillers),
        limits=LimitsConfig(max_file_size_mb=100, chunk_duration_minutes=5),
        hallucination=HallucinationConfig(
            repetition_threshold=3,
            compression_ratio_threshold=2.4,
            confidence_floor=-1.0,
            no_speech_prob_threshold=0.6,
            duration_chars_per_sec_max=25,
            duration_chars_per_sec_min=2,
            blocklist_enabled=True,
            score_threshold=2,
            action="remove",
        ),
    )


def _make_transcribe_args(**kwargs: object) -> MagicMock:
    """Return a mock Namespace with sensible transcribe defaults and any overrides applied."""
    args = MagicMock()
    args.config = None
    args.input = "input/"
    args.output = None
    args.engine = None
    args.model = None
    args.language = None
    args.output_mode = None
    args.diarize = None
    args.pause_threshold = None
    args.remove_fillers = None
    args.nuke = False
    args.dry_run = False
    args.force = False
    args.subcommand = "transcribe"
    for key, value in kwargs.items():
        setattr(args, key, value)
    return args


# ---------------------------------------------------------------------------
# TestArgumentParser
# ---------------------------------------------------------------------------


class TestArgumentParser:
    def test_help_flag_exists(self) -> None:
        """The argument parser must recognise the --help flag without erroring."""
        parser = _build_argument_parser()
        # ArgumentParser always registers --help; confirm it is present in the option strings
        option_strings = {action.option_strings[0] for action in parser._actions if action.option_strings}
        assert "--help" in option_strings or "-h" in option_strings

    def test_version_flag_exists(self) -> None:
        """The argument parser must recognise the --version flag."""
        parser = _build_argument_parser()
        option_strings = {string for action in parser._actions for string in action.option_strings}
        assert "--version" in option_strings

    def test_verbose_defaults_to_false(self) -> None:
        """The --verbose flag must default to False when not provided."""
        parser = _build_argument_parser()
        args = parser.parse_args([])
        assert args.verbose is False

    def test_subcommands_exist(self) -> None:
        """The parser must expose transcribe, config, and init subcommands."""
        parser = _build_argument_parser()
        # Locate the subparsers action and check its choices
        subparser_action = next(action for action in parser._actions if hasattr(action, "_name_parser_map"))
        assert "transcribe" in subparser_action._name_parser_map
        assert "config" in subparser_action._name_parser_map
        assert "init" in subparser_action._name_parser_map

    def test_transcribe_flags_are_parsed_correctly(self) -> None:
        """The transcribe subcommand must parse all its flags without error."""
        parser = _build_argument_parser()
        args = parser.parse_args(
            [
                "transcribe",
                "--input",
                "recordings/",
                "--output",
                "out/",
                "--engine",
                "whisper",
                "--model",
                "small",
                "--language",
                "en",
                "--output-mode",
                "segment",
                "--diarize",
                "--pause-threshold",
                "2.0",
                "--remove-fillers",
                "--nuke",
                "--dry-run",
                "--force",
            ]
        )
        assert args.input == "recordings/"
        assert args.output == "out/"
        assert args.engine == "whisper"
        assert args.model == "small"
        assert args.language == "en"
        assert args.output_mode == "segment"
        assert args.diarize is True
        assert args.pause_threshold == 2.0
        assert args.remove_fillers is True
        assert args.nuke is True
        assert args.dry_run is True
        assert args.force is True

    def test_no_subcommand_falls_back_to_transcribe_mode(self) -> None:
        """When no subcommand is given, the fallback parser must expose transcription flags."""
        fallback_parser = _build_root_parser_with_transcribe_defaults()
        args = fallback_parser.parse_args(["--input", "audio/", "--engine", "mlx"])
        assert args.input == "audio/"
        assert args.engine == "mlx"

    def test_input_defaults_to_input_slash(self) -> None:
        """The --input flag must default to 'input/' when not specified."""
        parser = _build_argument_parser()
        args = parser.parse_args(["transcribe"])
        assert args.input == "input/"

    def test_diarize_defaults_to_none(self) -> None:
        """The --diarize flag must default to None when not specified."""
        parser = _build_argument_parser()
        args = parser.parse_args(["transcribe"])
        assert args.diarize is None

    def test_no_diarize_flag_parses_as_false(self) -> None:
        """Passing --no-diarize must set args.diarize to False."""
        parser = _build_argument_parser()
        args = parser.parse_args(["transcribe", "--no-diarize"])
        assert args.diarize is False

    def test_remove_fillers_defaults_to_none(self) -> None:
        """The --remove-fillers flag must default to None when not specified."""
        parser = _build_argument_parser()
        args = parser.parse_args(["transcribe"])
        assert args.remove_fillers is None

    def test_no_remove_fillers_flag_parses_as_false(self) -> None:
        """Passing --no-remove-fillers must set args.remove_fillers to False."""
        parser = _build_argument_parser()
        args = parser.parse_args(["transcribe", "--no-remove-fillers"])
        assert args.remove_fillers is False


# ---------------------------------------------------------------------------
# TestCommandHandlers
# ---------------------------------------------------------------------------


class TestCommandHandlers:
    def test_cmd_config_loads_and_prints_config(self, capsys: pytest.CaptureFixture[str]) -> None:
        """cmd_config must load the config and print the engine and output settings."""
        args = MagicMock()
        args.config = None

        with patch("deep_thought.audio.cli.load_config", return_value=_make_config()) as mock_load:
            cmd_config(args)

        mock_load.assert_called_once()
        captured = capsys.readouterr()
        assert "mlx" in captured.out
        assert "small" in captured.out
        assert "paragraph" in captured.out

    def test_cmd_config_prints_valid_message_when_no_issues(self, capsys: pytest.CaptureFixture[str]) -> None:
        """cmd_config must print 'Configuration is valid.' when validate_config returns no issues."""
        args = MagicMock()
        args.config = None

        with (
            patch("deep_thought.audio.cli.load_config", return_value=_make_config()),
            patch("deep_thought.audio.cli.validate_config", return_value=[]),
        ):
            cmd_config(args)

        captured = capsys.readouterr()
        assert "Configuration is valid." in captured.out

    def test_cmd_config_prints_warnings_when_issues_found(self, capsys: pytest.CaptureFixture[str]) -> None:
        """cmd_config must list validation issues when validate_config returns warnings."""
        args = MagicMock()
        args.config = None

        with (
            patch("deep_thought.audio.cli.load_config", return_value=_make_config()),
            patch("deep_thought.audio.cli.validate_config", return_value=["engine 'bad' is not valid"]),
        ):
            cmd_config(args)

        captured = capsys.readouterr()
        assert "WARNING" in captured.out
        assert "engine 'bad' is not valid" in captured.out

    def test_cmd_init_creates_config_output_dir_and_database(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """cmd_init must copy the bundled config, create the output dir, and initialise the DB."""
        monkeypatch.chdir(tmp_path)
        bundled_config = tmp_path / "bundled.yaml"
        bundled_config.write_text("engine: mlx\n", encoding="utf-8")
        args = MagicMock()
        args.save_config = None

        mock_db_conn = MagicMock()

        with (
            patch("deep_thought.audio.cli.get_bundled_config_path", return_value=bundled_config),
            patch("deep_thought.audio.db.schema.initialize_database", return_value=mock_db_conn) as mock_init_db,
            patch("deep_thought.audio.db.schema.get_data_dir", return_value=tmp_path),
        ):
            cmd_init(args)

        mock_init_db.assert_called_once()
        mock_db_conn.close.assert_called_once()

        captured = capsys.readouterr()
        assert "Audio Tool initialised" in captured.out

    def test_cmd_init_copies_config_when_missing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """cmd_init must copy the bundled config to the project-level path when it does not exist."""
        monkeypatch.chdir(tmp_path)
        bundled_config = tmp_path / "bundled.yaml"
        bundled_config.write_text("engine: mlx\n", encoding="utf-8")
        args = MagicMock()
        args.save_config = None

        with (
            patch("deep_thought.audio.cli.get_bundled_config_path", return_value=bundled_config),
            patch("deep_thought.audio.db.schema.initialize_database", return_value=MagicMock()),
            patch("deep_thought.audio.db.schema.get_data_dir", return_value=tmp_path),
        ):
            cmd_init(args)

        expected_project_config = tmp_path / "src" / "config" / "audio-configuration.yaml"
        assert expected_project_config.exists()
        assert expected_project_config.read_text(encoding="utf-8") == "engine: mlx\n"

    def test_cmd_init_skips_config_copy_when_already_exists(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """cmd_init must print an 'already exists' message and skip copying when config is present."""
        monkeypatch.chdir(tmp_path)
        bundled_config = tmp_path / "bundled.yaml"
        bundled_config.write_text("engine: mlx\n", encoding="utf-8")

        project_config = tmp_path / "src" / "config" / "audio-configuration.yaml"
        project_config.parent.mkdir(parents=True)
        project_config.write_text("engine: whisper\n", encoding="utf-8")

        args = MagicMock()
        args.save_config = None

        with (
            patch("deep_thought.audio.cli.get_bundled_config_path", return_value=bundled_config),
            patch("deep_thought.audio.db.schema.initialize_database", return_value=MagicMock()),
            patch("deep_thought.audio.db.schema.get_data_dir", return_value=tmp_path),
        ):
            cmd_init(args)

        captured = capsys.readouterr()
        assert "already exists" in captured.out
        # Original content must be preserved — not overwritten
        assert project_config.read_text(encoding="utf-8") == "engine: whisper\n"

    def test_cmd_transcribe_calls_process_batch_with_correct_args(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """cmd_transcribe must call process_batch with the resolved engine and config."""
        from deep_thought.audio.processor import ProcessResult

        args = _make_transcribe_args(input=str(tmp_path / "audio"), output=str(tmp_path / "out"))
        mock_config = _make_config(generate_llms_files=False)
        success_result = ProcessResult(source_path=tmp_path / "audio" / "a.wav", status="success")

        with (
            patch("deep_thought.audio.cli.load_config", return_value=mock_config),
            patch("deep_thought.audio.cli.validate_config", return_value=[]),
            patch("deep_thought.audio.db.schema.initialize_database", return_value=MagicMock()),
            patch("deep_thought.audio.engines.create_engine", return_value=MagicMock()) as mock_create_engine,
            patch("deep_thought.audio.processor.process_batch", return_value=[success_result]) as mock_batch,
        ):
            cmd_transcribe(args)

        mock_create_engine.assert_called_once_with(
            mock_config.engine.engine,
            mock_config.engine.model,
            mock_config.limits.chunk_duration_minutes,
        )
        mock_batch.assert_called_once()


# ---------------------------------------------------------------------------
# TestConfigOverrides
# ---------------------------------------------------------------------------


class TestConfigOverrides:
    def test_engine_override_is_applied(self) -> None:
        """_build_config_with_overrides must replace the engine when --engine is set."""
        base_config = _make_config(engine="mlx")
        args = _make_transcribe_args(engine="whisper")

        updated_config = _build_config_with_overrides(args, base_config)

        assert updated_config.engine.engine == "whisper"

    def test_model_override_is_applied(self) -> None:
        """_build_config_with_overrides must replace the model when --model is set."""
        base_config = _make_config(model="small")
        args = _make_transcribe_args(model="large-v3")

        updated_config = _build_config_with_overrides(args, base_config)

        assert updated_config.engine.model == "large-v3"

    def test_language_override_is_applied(self) -> None:
        """_build_config_with_overrides must replace the language when --language is set."""
        base_config = _make_config(language="en")
        args = _make_transcribe_args(language="fr")

        updated_config = _build_config_with_overrides(args, base_config)

        assert updated_config.engine.language == "fr"

    def test_output_mode_override_is_applied(self) -> None:
        """_build_config_with_overrides must replace output_mode when --output-mode is set."""
        base_config = _make_config(output_mode="paragraph")
        args = _make_transcribe_args(output_mode="timestamp")

        updated_config = _build_config_with_overrides(args, base_config)

        assert updated_config.output.output_mode == "timestamp"

    def test_pause_threshold_override_is_applied(self) -> None:
        """_build_config_with_overrides must replace pause_threshold when --pause-threshold is set."""
        base_config = _make_config(pause_threshold=1.5)
        args = _make_transcribe_args(pause_threshold=3.0)

        updated_config = _build_config_with_overrides(args, base_config)

        assert updated_config.output.pause_threshold == 3.0

    def test_config_values_preserved_when_flags_are_not_set(self) -> None:
        """Unset CLI flags must not overwrite the loaded config values."""
        base_config = _make_config(engine="mlx", model="large-v3", language="de")
        args = _make_transcribe_args(engine=None, model=None, language=None)

        updated_config = _build_config_with_overrides(args, base_config)

        assert updated_config.engine.engine == "mlx"
        assert updated_config.engine.model == "large-v3"
        assert updated_config.engine.language == "de"

    def test_diarize_flag_is_applied(self) -> None:
        """_build_config_with_overrides must enable diarization when --diarize is set."""
        base_config = _make_config(diarize=False)
        args = _make_transcribe_args(diarize=True)

        updated_config = _build_config_with_overrides(args, base_config)

        assert updated_config.diarization.diarize is True

    def test_remove_fillers_flag_is_applied(self) -> None:
        """_build_config_with_overrides must enable filler removal when --remove-fillers is set."""
        base_config = _make_config(remove_fillers=False)
        args = _make_transcribe_args(remove_fillers=True)

        updated_config = _build_config_with_overrides(args, base_config)

        assert updated_config.filler.remove_fillers is True

    def test_no_diarize_flag_disables_config_enabled_diarization(self) -> None:
        """--no-diarize must disable diarization even when the config has diarize: true."""
        base_config = _make_config(diarize=True)
        args = _make_transcribe_args(diarize=False)

        updated_config = _build_config_with_overrides(args, base_config)

        assert updated_config.diarization.diarize is False

    def test_no_remove_fillers_flag_disables_config_enabled_filler_removal(self) -> None:
        """--no-remove-fillers must disable filler removal even when the config has remove_fillers: true."""
        base_config = _make_config(remove_fillers=True)
        args = _make_transcribe_args(remove_fillers=False)

        updated_config = _build_config_with_overrides(args, base_config)

        assert updated_config.filler.remove_fillers is False

    def test_unset_diarize_leaves_config_value_intact(self) -> None:
        """When --diarize is not passed (None), the config value must be preserved."""
        base_config = _make_config(diarize=True)
        args = _make_transcribe_args(diarize=None)

        updated_config = _build_config_with_overrides(args, base_config)

        assert updated_config.diarization.diarize is True

    def test_unset_remove_fillers_leaves_config_value_intact(self) -> None:
        """When --remove-fillers is not passed (None), the config value must be preserved."""
        base_config = _make_config(remove_fillers=True)
        args = _make_transcribe_args(remove_fillers=None)

        updated_config = _build_config_with_overrides(args, base_config)

        assert updated_config.filler.remove_fillers is True


# ---------------------------------------------------------------------------
# TestExitCodes
# ---------------------------------------------------------------------------


class TestExitCodes:
    def test_exit_code_0_when_all_files_succeed(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """cmd_transcribe must exit with code 0 when all files succeed."""
        from deep_thought.audio.processor import ProcessResult

        success_result = ProcessResult(source_path=tmp_path / "a.wav", status="success")
        args = _make_transcribe_args()
        mock_config = _make_config(generate_llms_files=False)

        with (
            patch("deep_thought.audio.cli.load_config", return_value=mock_config),
            patch("deep_thought.audio.cli.validate_config", return_value=[]),
            patch("deep_thought.audio.db.schema.initialize_database", return_value=MagicMock()),
            patch("deep_thought.audio.engines.create_engine", return_value=MagicMock()),
            patch("deep_thought.audio.processor.process_batch", return_value=[success_result]),
        ):
            # No sys.exit should be raised for all-success
            cmd_transcribe(args)

    def test_exit_code_1_when_all_files_error(self, tmp_path: Path) -> None:
        """cmd_transcribe must exit with code 1 when all files produce errors."""
        from deep_thought.audio.processor import ProcessResult

        error_result = ProcessResult(source_path=tmp_path / "a.wav", status="error")
        args = _make_transcribe_args()
        mock_config = _make_config(generate_llms_files=False)

        with (
            patch("deep_thought.audio.cli.load_config", return_value=mock_config),
            patch("deep_thought.audio.cli.validate_config", return_value=[]),
            patch("deep_thought.audio.db.schema.initialize_database", return_value=MagicMock()),
            patch("deep_thought.audio.engines.create_engine", return_value=MagicMock()),
            patch("deep_thought.audio.processor.process_batch", return_value=[error_result]),
            pytest.raises(SystemExit) as exc_info,
        ):
            cmd_transcribe(args)

        assert exc_info.value.code == 1

    def test_exit_code_2_when_partial_failure(self, tmp_path: Path) -> None:
        """cmd_transcribe must exit with code 2 when some files succeed and some error."""
        from deep_thought.audio.processor import ProcessResult

        success_result = ProcessResult(source_path=tmp_path / "a.wav", status="success")
        error_result = ProcessResult(source_path=tmp_path / "b.wav", status="error")
        args = _make_transcribe_args()
        mock_config = _make_config(generate_llms_files=False)

        with (
            patch("deep_thought.audio.cli.load_config", return_value=mock_config),
            patch("deep_thought.audio.cli.validate_config", return_value=[]),
            patch("deep_thought.audio.db.schema.initialize_database", return_value=MagicMock()),
            patch("deep_thought.audio.engines.create_engine", return_value=MagicMock()),
            patch("deep_thought.audio.processor.process_batch", return_value=[success_result, error_result]),
            pytest.raises(SystemExit) as exc_info,
        ):
            cmd_transcribe(args)

        assert exc_info.value.code == 2

    def test_exit_code_0_when_no_files_found(self, tmp_path: Path) -> None:
        """cmd_transcribe must exit with code 0 (via sys.exit(0)) when no files are found."""
        args = _make_transcribe_args()
        mock_config = _make_config(generate_llms_files=False)

        with (
            patch("deep_thought.audio.cli.load_config", return_value=mock_config),
            patch("deep_thought.audio.cli.validate_config", return_value=[]),
            patch("deep_thought.audio.db.schema.initialize_database", return_value=MagicMock()),
            patch("deep_thought.audio.engines.create_engine", return_value=MagicMock()),
            patch("deep_thought.audio.processor.process_batch", return_value=[]),
            pytest.raises(SystemExit) as exc_info,
        ):
            cmd_transcribe(args)

        assert exc_info.value.code == 0


# ---------------------------------------------------------------------------
# TestCommandHandlersDispatch
# ---------------------------------------------------------------------------


class TestCommandHandlersDispatch:
    def test_command_handlers_dict_contains_all_subcommands(self) -> None:
        """The _COMMAND_HANDLERS dict must map all three subcommand names to callables."""
        assert "transcribe" in _COMMAND_HANDLERS
        assert "config" in _COMMAND_HANDLERS
        assert "init" in _COMMAND_HANDLERS

    def test_command_handlers_map_to_correct_functions(self) -> None:
        """Each entry in _COMMAND_HANDLERS must be the corresponding cmd_* function."""
        assert _COMMAND_HANDLERS["transcribe"] is cmd_transcribe
        assert _COMMAND_HANDLERS["config"] is cmd_config
        assert _COMMAND_HANDLERS["init"] is cmd_init


# ---------------------------------------------------------------------------
# TestCLIHelpers (T-04)
# ---------------------------------------------------------------------------


class TestSetupLogging:
    def test_sets_debug_level_when_verbose_true(self) -> None:
        """When verbose=True, the root logger level must be DEBUG."""
        _setup_logging(verbose=True)
        assert logging.getLogger().level == logging.DEBUG

    def test_sets_info_level_when_verbose_false(self) -> None:
        """When verbose=False, the root logger level must be INFO."""
        _setup_logging(verbose=False)
        assert logging.getLogger().level == logging.INFO


class TestLoadConfigFromArgs:
    def test_loads_config_from_explicit_path(self, tmp_path: Path) -> None:
        """When args.config is set, load_config must receive that path."""
        # Write a minimal valid config file
        config_file = tmp_path / "audio-configuration.yaml"
        config_file.write_text(
            "engine: mlx\nmodel: small\nlanguage: en\n"
            "output_mode: paragraph\npause_threshold: 1.5\n"
            "diarize: false\nhf_token_env: HF_TOKEN\n"
            "remove_fillers: false\noutput_dir: data/\n"
            "generate_llms_files: false\nmax_file_size_mb: 100\n"
            "chunk_duration_minutes: 5\n",
            encoding="utf-8",
        )
        args = MagicMock()
        args.config = str(config_file)

        config = _load_config_from_args(args)

        assert config.engine.engine == "mlx"
        assert config.engine.model == "small"

    def test_passes_none_path_when_config_not_set(self) -> None:
        """When args.config is None, load_config must be called with no path."""
        args = MagicMock()
        args.config = None

        with patch("deep_thought.audio.cli.load_config", return_value=_make_config()) as mock_load:
            _load_config_from_args(args)

        called_path = mock_load.call_args[0][0]
        assert called_path is None


class TestResolveOutputRoot:
    def test_cli_output_overrides_config(self) -> None:
        """When args.output is set, the result must be that path."""
        args = MagicMock()
        args.output = "/override/output"
        config = _make_config(output_dir="data/audio/export/")

        result = _resolve_output_root(args, config)

        assert result == Path("/override/output")

    def test_falls_back_to_config_output_dir(self) -> None:
        """When args.output is None, the result must be config.output.output_dir."""
        args = MagicMock()
        args.output = None
        config = _make_config(output_dir="data/audio/export/")

        result = _resolve_output_root(args, config)

        assert result == Path("data/audio/export/")


# ---------------------------------------------------------------------------
# TestMainEntryPoint (T-03)
# ---------------------------------------------------------------------------


class TestMainEntryPoint:
    def test_main_dispatches_to_config_subcommand(self, capsys: pytest.CaptureFixture[str]) -> None:
        """main() with the 'config' subcommand must invoke cmd_config."""
        mock_cmd_config = MagicMock()
        with (
            patch("sys.argv", ["audio", "config"]),
            patch.dict("deep_thought.audio.cli._COMMAND_HANDLERS", {"config": mock_cmd_config}),
        ):
            main()

        mock_cmd_config.assert_called_once()

    def test_main_dispatches_to_init_subcommand(self) -> None:
        """main() with the 'init' subcommand must invoke cmd_init."""
        mock_cmd_init = MagicMock()
        with (
            patch("sys.argv", ["audio", "init"]),
            patch.dict("deep_thought.audio.cli._COMMAND_HANDLERS", {"init": mock_cmd_init}),
        ):
            main()

        mock_cmd_init.assert_called_once()

    def test_main_exits_1_on_file_not_found(self) -> None:
        """main() must exit with code 1 when FileNotFoundError is raised by the handler."""
        failing_handler = MagicMock(side_effect=FileNotFoundError("no config"))
        with (
            patch("sys.argv", ["audio", "config"]),
            patch.dict("deep_thought.audio.cli._COMMAND_HANDLERS", {"config": failing_handler}),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 1

    def test_main_exits_1_on_os_error(self) -> None:
        """main() must exit with code 1 when OSError is raised by the handler."""
        failing_handler = MagicMock(side_effect=OSError("disk full"))
        with (
            patch("sys.argv", ["audio", "config"]),
            patch.dict("deep_thought.audio.cli._COMMAND_HANDLERS", {"config": failing_handler}),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 1

    def test_main_exits_1_on_value_error(self) -> None:
        """main() must exit with code 1 when ValueError is raised by the handler."""
        failing_handler = MagicMock(side_effect=ValueError("bad value"))
        with (
            patch("sys.argv", ["audio", "config"]),
            patch.dict("deep_thought.audio.cli._COMMAND_HANDLERS", {"config": failing_handler}),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 1

    def test_main_exits_1_on_unexpected_error(self) -> None:
        """main() must exit with code 1 when an unexpected Exception is raised."""
        failing_handler = MagicMock(side_effect=RuntimeError("unexpected"))
        with (
            patch("sys.argv", ["audio", "config"]),
            patch.dict("deep_thought.audio.cli._COMMAND_HANDLERS", {"config": failing_handler}),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 1

    def test_main_defaults_to_transcribe_when_no_subcommand(self) -> None:
        """main() with no subcommand must fall back to cmd_transcribe."""
        mock_transcribe = MagicMock()
        with (
            patch("sys.argv", ["audio"]),
            patch.dict("deep_thought.audio.cli._COMMAND_HANDLERS", {"transcribe": mock_transcribe}),
        ):
            main()

        mock_transcribe.assert_called_once()


# ---------------------------------------------------------------------------
# TestGetVersion
# ---------------------------------------------------------------------------


class TestGetVersion:
    def test_returns_string(self) -> None:
        """_get_version() must always return a string."""
        result = _get_version()
        assert isinstance(result, str)

    def test_fallback_when_package_not_found(self) -> None:
        """When the package is not installed, _get_version() must return the fallback string."""
        from importlib.metadata import PackageNotFoundError

        with patch("deep_thought.audio.cli.version", side_effect=PackageNotFoundError()):
            result = _get_version()

        assert result == "0.0.0+unknown"


# ---------------------------------------------------------------------------
# TestLlmFlag (T-06)
# ---------------------------------------------------------------------------


class TestLlmFlag:
    def test_llm_flag_triggers_llm_file_generation(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """When --llm is set, cmd_transcribe must generate llms.txt and llms-full.txt."""
        from deep_thought.audio.processor import ProcessResult

        output_dir = tmp_path / "output"
        output_dir.mkdir()
        md_dir = output_dir / "interview"
        md_dir.mkdir()
        md_file = md_dir / "interview.md"
        md_file.write_text("---\ntool: audio\n---\nTranscript body.", encoding="utf-8")

        success_result = ProcessResult(
            source_path=tmp_path / "interview.wav",
            output_path=md_dir,
            status="success",
            duration_seconds=90.0,
        )

        args = _make_transcribe_args(
            input=str(tmp_path / "audio"),
            output=str(output_dir),
            llm=True,
        )
        # generate_llms_files=False in config, but --llm overrides it
        mock_config = _make_config(generate_llms_files=False)

        with (
            patch("deep_thought.audio.cli.load_config", return_value=mock_config),
            patch("deep_thought.audio.cli.validate_config", return_value=[]),
            patch("deep_thought.audio.db.schema.initialize_database", return_value=MagicMock()),
            patch("deep_thought.audio.engines.create_engine", return_value=MagicMock()),
            patch("deep_thought.audio.processor.process_batch", return_value=[success_result]),
        ):
            cmd_transcribe(args)

        captured = capsys.readouterr()
        assert "llms" in captured.out.lower() or (output_dir / "llms.txt").exists()

    def test_llm_flag_none_uses_config_value(self, tmp_path: Path) -> None:
        """When args.llm is None, the config's generate_llms_files value is used."""
        from deep_thought.audio.processor import ProcessResult

        success_result = ProcessResult(source_path=tmp_path / "a.wav", status="success")
        args = _make_transcribe_args(llm=None)
        # config has generate_llms_files=False and no output_path on result
        mock_config = _make_config(generate_llms_files=False)

        with (
            patch("deep_thought.audio.cli.load_config", return_value=mock_config),
            patch("deep_thought.audio.cli.validate_config", return_value=[]),
            patch("deep_thought.audio.db.schema.initialize_database", return_value=MagicMock()),
            patch("deep_thought.audio.engines.create_engine", return_value=MagicMock()),
            patch("deep_thought.audio.processor.process_batch", return_value=[success_result]),
            patch("deep_thought.audio.llms.write_llms_index") as mock_write_index,
        ):
            cmd_transcribe(args)

        # With generate_llms_files=False and llm=None, LLM files must not be written
        mock_write_index.assert_not_called()
