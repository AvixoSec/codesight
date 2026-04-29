import pytest

from codesight.context import SourceContext
from codesight.profiles import get_profile, profile_for_context, profile_names


def context(path: str, snippet: str) -> SourceContext:
    return SourceContext(
        file_path=None,
        display_path=path,
        start_line=1,
        end_line=1,
        snippet=snippet,
    )


def test_profile_names_include_auto_and_core_profiles():
    names = profile_names()

    assert "auto" in names
    assert "flask" in names
    assert "fastapi" in names
    assert "express" in names
    assert "ai-agent" in names


def test_auto_profile_detects_flask():
    profile = profile_for_context(
        context("app.py", 'from flask import request\nterm = request.args["q"]')
    )

    assert profile.name == "flask"


def test_auto_profile_detects_express():
    profile = profile_for_context(
        context("server.js", "app.post('/x', (req, res) => db.query(req.body.q))")
    )

    assert profile.name == "express"


def test_auto_profile_detects_github_actions():
    profile = profile_for_context(
        context(".github/workflows/ci.yml", "on: pull_request_target\nruns-on: ubuntu-latest")
    )

    assert profile.name == "github-actions"


def test_requested_profile_overrides_detection():
    profile = profile_for_context(
        context("app.py", "from flask import request"),
        requested="fastapi",
    )

    assert profile.name == "fastapi"


def test_get_profile_rejects_unknown_profile():
    with pytest.raises(ValueError):
        get_profile("rails")
