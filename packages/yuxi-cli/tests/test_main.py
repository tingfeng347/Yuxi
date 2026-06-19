from typer.testing import CliRunner

from yuxi_cli import __version__
from yuxi_cli.main import app


def test_version_option_without_command():
    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert __version__ in result.output


def test_agent_eval_help_is_registered():
    result = CliRunner().invoke(app, ["agent", "eval", "--help"])

    assert result.exit_code == 0
    assert "--dataset-name" in result.output
    assert "--create-smoke-item" not in result.output
    assert "--auth-token" not in result.output
