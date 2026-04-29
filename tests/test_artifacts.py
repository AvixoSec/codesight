import json

from codesight.artifacts import verification_payload, write_verification_artifacts
from codesight.verify import verify_sarif_file

from .test_verify import FIXTURES


def test_verification_payload_includes_run_metadata():
    result = verify_sarif_file(
        FIXTURES / "semgrep_sample.sarif",
        source_root=FIXTURES / "sample_project",
    )

    payload = verification_payload(
        result,
        fail_on="exploitable",
        judge_enabled=False,
        skeptic_enabled=False,
        profile="flask",
    )

    assert payload["scanner_alert_count"] == 1
    assert payload["profile"] == "flask"
    assert payload["summary"]["uncertain"] == 1


def test_write_verification_artifacts_writes_report_bundle(tmp_path):
    result = verify_sarif_file(
        FIXTURES / "semgrep_sample.sarif",
        source_root=FIXTURES / "sample_project",
    )

    artifacts = write_verification_artifacts(
        result,
        tmp_path,
        fail_on="exploitable",
        judge_enabled=False,
        skeptic_enabled=False,
        profile="flask",
        preview={"scanner_alert_count": 1, "contexts": []},
    )

    assert (tmp_path / "report.md").is_file()
    assert (tmp_path / "report.json").is_file()
    assert (tmp_path / "results.sarif").is_file()
    assert (tmp_path / "preview-context.json").is_file()
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["finding_count"] == 1
    assert manifest["artifacts"]["sarif"] == artifacts["sarif"]
