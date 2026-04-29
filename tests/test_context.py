from pathlib import Path

from codesight.context import extract_context, resolve_artifact_path


def test_resolve_artifact_path_accepts_relative_uri(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    app = root / "app.py"
    app.write_text("print('ok')\n", encoding="utf-8")

    assert resolve_artifact_path(root, "app.py") == app.resolve()


def test_resolve_artifact_path_blocks_escape(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "secret.py"
    outside.write_text("secret = True\n", encoding="utf-8")

    assert resolve_artifact_path(root, "../secret.py") is None


def test_resolve_artifact_path_accepts_file_uri(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    app = root / "app.py"
    app.write_text("print('ok')\n", encoding="utf-8")

    assert resolve_artifact_path(root, Path(app).as_uri()) == app.resolve()


def test_extract_context_returns_stable_line_window(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    app = root / "app.py"
    app.write_text("one\ntwo\nthree\nfour\nfive\n", encoding="utf-8")

    context = extract_context(root, "app.py", start_line=3, before=1, after=1)

    assert context.display_path == "app.py"
    assert context.start_line == 3
    assert "   2: two" in context.snippet
    assert "   3: three" in context.snippet
    assert "   4: four" in context.snippet


def test_extract_context_reports_missing_file(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()

    context = extract_context(root, "missing.py", start_line=10)

    assert context.missing is True
    assert "not found" in context.reason
