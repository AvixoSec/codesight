import asyncio
from unittest.mock import patch

from codesight.benchmark import BUILTIN_CASES, BUILTIN_SOURCES, VulnerableFile, benchmark_model
from codesight.config import AppConfig, ProviderConfig
from codesight.providers.base import LLMResponse


class FakeProvider:
    def __init__(self, *contents: str) -> None:
        self.contents = list(contents)

    async def complete(self, messages, max_tokens=4096, temperature=0.2):
        return LLMResponse(
            content=self.contents.pop(0),
            model="fake-model",
            usage={"prompt_tokens": 1, "completion_tokens": 1},
            provider="fake",
        )


def config() -> AppConfig:
    return AppConfig(
        default_provider="fake",
        providers={"fake": ProviderConfig(provider="fake", model="fake-model")},
    )


def test_builtin_benchmark_has_clean_false_positive_traps():
    clean_cases = [case for case in BUILTIN_CASES if not case.cwe_ids]

    assert len(clean_cases) >= 2


def test_builtin_benchmark_has_semantic_and_ai_agent_cases():
    cases = {case.path: case for case in BUILTIN_CASES}

    assert cases["__builtin__/tenant_auth_bypass.py"].cwe_ids == ["CWE-862"]
    assert cases["__builtin__/ai_agent_unvalidated_tool.py"].cwe_ids == ["CWE-20"]
    assert "model_output" in BUILTIN_SOURCES["__builtin__/ai_agent_unvalidated_tool.py"]


def test_benchmark_tracks_false_positives_on_clean_cases(tmp_path):
    vuln = tmp_path / "vuln.py"
    clean = tmp_path / "clean.py"
    vuln.write_text("db.execute(user_input)\n", encoding="utf-8")
    clean.write_text("db.execute('SELECT 1')\n", encoding="utf-8")
    cases = [
        VulnerableFile(str(vuln), "python", ["CWE-89"], "vulnerable"),
        VulnerableFile(str(clean), "python", [], "clean"),
    ]

    fake = FakeProvider("CWE-89", "CWE-79")
    with patch("codesight.benchmark.create_provider", return_value=fake):
        summary = asyncio.run(benchmark_model("fake", "fake-model", config(), cases))

    assert summary.true_positives == 1
    assert summary.false_positives == 1
    assert summary.clean_files == 1
    assert summary.false_positive_cases == 1
    assert summary.false_positive_rate == 1.0
