from dataclasses import dataclass

from .config import AppConfig, ProviderConfig, get_provider_config
from .providers import create_provider
from .providers.base import Message


@dataclass
class PipelineConfig:
    triage_provider: str  # e.g. "ollama"
    triage_model: str     # e.g. "llama3"
    verify_provider: str  # e.g. "openai"
    verify_model: str     # e.g. "gpt-4o"


TRIAGE_PROMPT = (
    "You are a fast security pre-screener. Read the code and list ONLY the lines "
    "that look like they might have security vulnerabilities. Be aggressive - "
    "flag anything suspicious. For each flag, give: line number, one-line reason. "
    "If the code looks clean, respond with exactly: NO_FINDINGS"
)

VERIFY_PROMPT = (
    "You are a senior security auditor. A fast pre-screening model flagged "
    "potential vulnerabilities in this code. Review each flag and determine "
    "if it is a real vulnerability or a false positive.\n\n"
    "For REAL vulnerabilities, provide:\n"
    "- Severity: CRITICAL / HIGH / MEDIUM / LOW\n"
    "- CWE ID\n"
    "- OWASP category\n"
    "- Description and proof of concept\n"
    "- Recommended fix\n\n"
    "For false positives, briefly explain why.\n\n"
    "Pre-screening flags:\n{triage_output}\n\n"
    "Output format:\n"
    "## Security Findings\n"
    "### [SEVERITY] Title — CWE-XXX\n"
    "**OWASP:** Category\n"
    "**Location:** file:line\n"
    "**Description:** ...\n"
    "**Fix:** ...\n\n"
    "## False Positives\n"
    "List dismissed flags.\n\n"
    "## Summary\n"
    "Totals and risk assessment."
)


async def run_pipeline(
    source: str,
    file_path: str,
    config: AppConfig,
    pipeline_config: PipelineConfig,
) -> tuple[str, dict]:

    triage_pconfig = ProviderConfig(
        provider=pipeline_config.triage_provider,
        model=pipeline_config.triage_model,
        base_url=get_provider_config(config, pipeline_config.triage_provider).base_url,
        api_key=get_provider_config(config, pipeline_config.triage_provider).api_key,
    )
    triage_provider = create_provider(triage_pconfig)

    triage_messages = [
        Message(role="system", content=TRIAGE_PROMPT),
        Message(role="user", content=f"File: `{file_path}`\n\n```\n{source}\n```"),
    ]

    triage_response = await triage_provider.complete(
        triage_messages, max_tokens=2048, temperature=0.1,
    )

    triage_output = triage_response.content.strip()
    triage_usage = triage_response.usage

    if "NO_FINDINGS" in triage_output.upper():
        clean_msg = (
            "## Security Findings\n\nNo vulnerabilities found."
            "\n\n## Summary\n\nCode passed triage screening."
            " No issues detected."
        )
        t_in = triage_usage.get("prompt_tokens", 0)
        t_out = triage_usage.get("completion_tokens", 0)
        return clean_msg, {
            "prompt_tokens": t_in,
            "completion_tokens": t_out,
            "triage_tokens": t_in + t_out,
            "verify_tokens": 0,
        }

    verify_pconfig = ProviderConfig(
        provider=pipeline_config.verify_provider,
        model=pipeline_config.verify_model,
        base_url=get_provider_config(config, pipeline_config.verify_provider).base_url,
        api_key=get_provider_config(config, pipeline_config.verify_provider).api_key,
    )
    verify_provider = create_provider(verify_pconfig)

    verify_system = VERIFY_PROMPT.format(triage_output=triage_output)
    verify_messages = [
        Message(role="system", content=verify_system),
        Message(role="user", content=f"File: `{file_path}`\n\n```\n{source}\n```"),
    ]

    verify_response = await verify_provider.complete(
        verify_messages, max_tokens=4096, temperature=0.2,
    )

    verify_usage = verify_response.usage
    t_in = triage_usage.get("prompt_tokens", 0)
    t_out = triage_usage.get("completion_tokens", 0)
    v_in = verify_usage.get("prompt_tokens", 0)
    v_out = verify_usage.get("completion_tokens", 0)
    combined_usage = {
        "prompt_tokens": t_in + v_in,
        "completion_tokens": t_out + v_out,
        "triage_tokens": t_in + t_out,
        "verify_tokens": v_in + v_out,
    }

    return verify_response.content, combined_usage
