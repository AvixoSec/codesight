import argparse
import asyncio
import contextlib
import json
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, OSError):
            _stream.reconfigure(encoding="utf-8", errors="replace")

import questionary
from questionary import Choice
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn
from rich.text import Text

from . import __version__
from .analyzer import (
    SCAN_EXTENSIONS,
    AnalysisError,
    AnalysisResult,
    Analyzer,
    TaskType,
    collect_files,
)
from .benchmark import benchmark_model, export_benchmark_json, format_benchmark
from .config import (
    CONFIG_FILE,
    DEFAULT_ANTHROPIC_MODEL,
    DEFAULT_GOOGLE_MODEL,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_OPENAI_MODEL,
    AppConfig,
    ProviderConfig,
    load_config,
    save_config,
)
from .cost import estimate_call_cost, estimate_cost, format_cost
from .i18n import resolve_language, set_language, t
from .pipeline import PipelineConfig, run_pipeline
from .providers.anthropic_provider import is_azure_url, normalize_azure_base_url
from .providers.base import Message
from .sarif import parse_findings, to_sarif_json
from .templates import delete_template, get_template, list_templates, save_template

console = Console(stderr=True)
out = Console()


def _read_source_file(file_path: str, max_file_size_kb: int) -> tuple[Path, str]:
    resolved = Path(file_path).resolve()
    if not resolved.is_file():
        raise AnalysisError(f"File not found: {file_path}")

    size_kb = resolved.stat().st_size / 1024
    if size_kb > max_file_size_kb:
        raise AnalysisError(
            f"File too large: {size_kb:.0f}KB (limit: {max_file_size_kb}KB). "
            "Adjust max_file_size_kb in config to override."
        )

    return resolved, resolved.read_text(encoding="utf-8", errors="replace")


def _safe_relative_path(file_path: str, root: Path) -> str:
    resolved = Path(file_path).resolve()
    try:
        return str(resolved.relative_to(root))
    except ValueError:
        return resolved.name


def _mask_identifier(value: str | None, keep: int = 4) -> str:
    if not value:
        return "(not set)"
    if len(value) <= keep * 2:
        return "*" * len(value)
    return f"{value[:keep]}...{value[-keep:]}"


def _mask_url_display(url: str | None) -> str:
    if not url:
        return "(not set)"
    normalized = url.rstrip("/")
    match = re.match(r"^(https?://)([^/]+)(.*)$", normalized)
    if not match:
        return _mask_identifier(normalized)
    scheme, host, suffix = match.groups()
    parts = host.split(".")
    if len(parts) >= 3:
        parts[0] = _mask_identifier(parts[0], keep=3)
        masked_host = ".".join(parts)
    else:
        masked_host = _mask_identifier(host)
    return f"{scheme}{masked_host}{suffix}"


def _is_valid_template_name(name: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9_-]*", name))


def _parse_pipeline_arg(pipeline_arg: str) -> tuple[str, str, str, str]:
    if ":" not in pipeline_arg:
        raise ValueError("Pipeline format must contain ':' separator")

    triage_str, verify_str = pipeline_arg.rsplit(":", 1)
    if "/" not in triage_str or "/" not in verify_str:
        raise ValueError("Pipeline format must be provider/model:provider/model")

    t_provider, t_model = triage_str.split("/", 1)
    v_provider, v_model = verify_str.split("/", 1)
    if not all(part.strip() for part in (t_provider, t_model, v_provider, v_model)):
        raise ValueError("Pipeline provider/model values cannot be empty")
    return t_provider, t_model, v_provider, v_model


def _severity_exit_code(severities: set[str]) -> int:
    normalized = {severity.upper() for severity in severities}
    if normalized & {"CRITICAL", "CRIT"}:
        return 2
    if normalized & {"HIGH", "MEDIUM", "WARN", "WARNING"}:
        return 1
    return 0


def _result_exit_code(content: str, file_path: str) -> int:
    findings = parse_findings(content, file_path)
    if not findings:
        severities: set[str] = set()
        normalized = content.upper()
        if re.search(r"\[(?:CRIT|CRITICAL)\]", normalized):
            severities.add("CRITICAL")
        if re.search(r"\[(?:HIGH|WARN|WARNING)\]", normalized):
            severities.add("HIGH")
        if re.search(r"\[MEDIUM\]", normalized):
            severities.add("MEDIUM")
        return _severity_exit_code(severities)

    return _severity_exit_code({finding.severity for finding in findings})


def _results_exit_code(results: list[AnalysisResult]) -> int:
    exit_code = 0
    for result in results:
        exit_code = max(exit_code, _result_exit_code(result.content, result.file_path))
        if exit_code == 2:
            break
    return exit_code


def _batch_exit_code(results: list[AnalysisResult], errors: list[tuple[str, str]]) -> int:
    exit_code = _results_exit_code(results)
    if errors:
        exit_code = max(exit_code, 1)
    return exit_code


async def _analyze_batch(
    analyzer: Analyzer,
    files: list[tuple[str, str]],
    task: TaskType,
    progress,
    progress_task: int,
) -> tuple[list[AnalysisResult], list[tuple[str, str]], int]:
    results: list[AnalysisResult] = []
    errors: list[tuple[str, str]] = []
    total_tokens = 0

    for display_path, file_path in files:
        progress.update(progress_task, description=f"[green]{display_path}[/]")
        try:
            result = await analyzer.analyze_file(file_path, task)
            results.append(result)
            total_tokens += result.tokens_used
        except AnalysisError as exc:
            errors.append((display_path, str(exc)))
        progress.advance(progress_task)

    return results, errors, total_tokens


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codesight",
        description="Code analysis and review tool using LLMs",
    )
    parser.add_argument("-v", "--version", action="version", version=f"codesight {__version__}")
    parser.add_argument(
        "-p", "--provider",
        help=(
            "LLM provider to use (overrides config default): openai, anthropic, "
            "google, ollama, or any custom label"
        ),
    )
    parser.add_argument(
        "-o", "--output",
        choices=["markdown", "json", "plain", "sarif"],
        default=None,
        help="Output format",
    )
    parser.add_argument(
        "--lang",
        choices=["en", "ru"],
        default=None,
        help="Language for CLI messages (also: CODESIGHT_LANG env var)",
    )

    sub = parser.add_subparsers(dest="command")

    for cmd in ("review", "bugs", "security", "docs", "explain", "refactor"):
        p = sub.add_parser(cmd, help=f"Run {cmd} analysis on a file")
        p.add_argument("file", help="Path to the source file")
        p.add_argument("-c", "--context", help="Extra context for the analysis")
        if cmd == "security":
            p.add_argument(
                "--pipeline",
                metavar="TRIAGE:VERIFY",
                help="Multi-model pipeline, e.g. ollama/llama3:openai/gpt-5.4",
            )

    scan = sub.add_parser("scan", help="Scan a directory")
    scan.add_argument("dir", nargs="?", default=".", help="Directory to scan (default: .)")
    scan.add_argument(
        "-t", "--task",
        choices=["review", "bugs", "security"],
        default="review",
        help="Analysis type (default: review)",
    )
    scan.add_argument("--ext", nargs="*", help="File extensions to include (e.g. .py .js)")
    scan.add_argument(
        "--estimate",
        action="store_true",
        help="Show token and cost estimate without calling the API",
    )

    diff = sub.add_parser("diff", help="Review only git-changed files")
    diff.add_argument(
        "-t", "--task",
        choices=["review", "bugs", "security"],
        default="security",
        help="Analysis type (default: security)",
    )
    diff.add_argument("--staged", action="store_true", help="Only staged changes")

    bench = sub.add_parser("benchmark", help="Benchmark LLMs on vulnerable code")
    bench.add_argument("--models", nargs="+", help="Models to test (e.g. gpt-5.4 llama3)")
    bench.add_argument("--json", action="store_true", help="Output as JSON")

    sub.add_parser("config", help="Configure CodeSight interactively")
    sub.add_parser("health", help="Check provider connectivity")

    tmpl = sub.add_parser("templates", help="Manage custom prompt templates")
    tmpl_sub = tmpl.add_subparsers(dest="tmpl_action")
    tmpl_sub.add_parser("list", help="List all templates")
    tmpl_use = tmpl_sub.add_parser("run", help="Run analysis with a template")
    tmpl_use.add_argument("template", help="Template name")
    tmpl_use.add_argument("file", help="File to analyze")
    tmpl_add = tmpl_sub.add_parser("add", help="Create a new template")
    tmpl_add.add_argument("name", help="Template slug (e.g. my-review)")
    tmpl_del = tmpl_sub.add_parser("delete", help="Delete a custom template")
    tmpl_del.add_argument("name", help="Template name to delete")

    return parser


def _format_output(result, output_format: str) -> None:
    header = Text()
    header.append(" CodeSight ", style="bold white on dark_green")
    header.append(f" {result.task.value.upper()} ", style="bold")
    header.append(f" {result.provider} ", style="dim")
    header.append(f"({result.model})", style="dim")

    prompt_tokens = result.usage.get("prompt_tokens", 0) if result.usage else 0
    completion_tokens = result.usage.get("completion_tokens", 0) if result.usage else 0
    cost = estimate_cost(result.model, prompt_tokens, completion_tokens)

    token_text = Text()
    token_text.append(f"{result.tokens_used:,}", style="bold cyan")
    token_text.append(" tokens", style="dim")
    token_text.append(f" | {format_cost(cost)}", style="bold yellow")

    if output_format not in {"json", "sarif"}:
        out.print()
        out.print(Panel(header, subtitle=str(token_text), border_style="green"))

    if output_format == "sarif":
        findings = parse_findings(result.content, result.file_path)
        sys.stdout.write(f"{to_sarif_json(findings)}\n")
    elif output_format == "json":
        sys.stdout.write(
            json.dumps(
                {
                    "task": result.task.value,
                    "file": result.file_path,
                    "provider": result.provider,
                    "model": result.model,
                    "tokens_used": result.tokens_used,
                    "content": result.content,
                }
            )
            + "\n"
        )
    elif output_format == "plain":
        out.print(result.content)
    else:
        out.print(Markdown(result.content))

    if output_format not in {"json", "sarif"}:
        out.print()


def _run_analysis(args, config: AppConfig) -> None:
    task_map = {
        "review": TaskType.REVIEW,
        "bugs": TaskType.BUGS,
        "security": TaskType.SECURITY,
        "docs": TaskType.DOCS,
        "explain": TaskType.EXPLAIN,
        "refactor": TaskType.REFACTOR,
    }
    task = task_map[args.command]
    file_path = str(Path(args.file).resolve())

    pipeline_arg = getattr(args, "pipeline", None)
    if pipeline_arg and args.command == "security":
        try:
            t_provider, t_model, v_provider, v_model = _parse_pipeline_arg(pipeline_arg)
        except ValueError:
            console.print("[bold red]Pipeline format:[/] provider/model:provider/model")
            console.print("  Example: ollama/llama3:openai/gpt-5.4")
            sys.exit(1)

        try:
            source_path, source = _read_source_file(file_path, config.max_file_size_kb)
        except AnalysisError as exc:
            console.print(f"[bold red]Error:[/] {exc}")
            sys.exit(1)

        file_path = str(source_path)

        pcfg = PipelineConfig(
            triage_provider=t_provider, triage_model=t_model,
            verify_provider=v_provider, verify_model=v_model,
        )

        with console.status(
            f"[bold green]Pipeline:[/] triage ({t_model}) → verify ({v_model})...",
            spinner="dots",
        ):
            try:
                content, usage = asyncio.run(
                    run_pipeline(source, file_path, config, pcfg)
                )
            except Exception as exc:
                console.print(f"[bold red]Pipeline error:[/] {exc}")
                sys.exit(1)

        result = AnalysisResult(
            task=task, file_path=file_path, content=content,
            model=f"{t_model}→{v_model}", provider="pipeline",
            tokens_used=usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0),
            usage=usage,
        )
        _format_output(result, config.output_format)
        triage_t = usage.get("triage_tokens", 0)
        verify_t = usage.get("verify_tokens", 0)
        console.print(f"  [dim]Triage: {triage_t:,} tokens | Verify: {verify_t:,} tokens[/]")
        return

    try:
        analyzer = Analyzer(config, provider_name=args.provider)
    except ValueError as exc:
        console.print(f"[bold red]Config error:[/] {exc}")
        sys.exit(1)

    with console.status(
        f"[bold green]Analyzing[/] {Path(file_path).name} ({task.value})...",
        spinner="dots",
    ):
        try:
            result = asyncio.run(analyzer.analyze_file(
                file_path,
                task,
                extra_context=getattr(args, "context", None),
            ))
        except AnalysisError as exc:
            console.print(f"[bold red]Error:[/] {exc}")
            sys.exit(1)

    _format_output(result, config.output_format)


def _print_cost_estimate(analyzer, files: list[str], scan_root: Path, task: str) -> None:
    # Dry-run: per-file token + cost estimate, no API call.
    provider_cfg = analyzer.provider_config
    model = provider_cfg.model
    expected_output = 800 if task == "security" else 600
    total_prompt = 0
    total_output = 0
    total_cost = 0.0
    lines = []
    for fp in files:
        try:
            source = Path(fp).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        pt, ot, cost = estimate_call_cost(model, source, expected_output)
        total_prompt += pt
        total_output += ot
        total_cost += cost
        rel = _safe_relative_path(fp, scan_root)
        lines.append(f"  {rel}: ~{pt:,} in + {ot:,} out = {format_cost(cost)}")
    for line in lines[:20]:
        console.print(line, style="dim")
    if len(lines) > 20:
        console.print(f"  ... {len(lines) - 20} more", style="dim")
    console.print(
        f"\n[bold]Estimate[/] {len(files)} files, "
        f"~{total_prompt:,} in + ~{total_output:,} out tokens, "
        f"total ~{format_cost(total_cost)} on [cyan]{model}[/]"
    )
    console.print("[dim]No API call made. Drop --estimate to run for real.[/]")


def _run_scan(args, config: AppConfig) -> None:
    task_map = {"review": TaskType.REVIEW, "bugs": TaskType.BUGS, "security": TaskType.SECURITY}
    task = task_map[args.task]
    exts = {e if e.startswith(".") else f".{e}" for e in args.ext} if args.ext else None
    scan_root = Path(args.dir).resolve()

    if not scan_root.is_dir():
        console.print(f"[bold red]Error:[/] {t('directory_not_found', path=scan_root)}")
        sys.exit(1)

    files = collect_files(
        str(scan_root),
        extensions=exts,
        ignore=config.ignore_patterns,
        max_size_kb=config.max_file_size_kb,
    )

    if not files:
        console.print(f"[yellow]{t('no_source_files')}[/]")
        sys.exit(0)

    console.print(t("found_files", count=f"[bold]{len(files)}[/]", dir=f"[cyan]{scan_root}[/]"))

    try:
        analyzer = Analyzer(config, provider_name=args.provider)
    except ValueError as exc:
        console.print(f"[bold red]{t('config_error', error=exc)}[/]")
        sys.exit(1)

    if getattr(args, "estimate", False):
        _print_cost_estimate(analyzer, files, scan_root, args.task)
        sys.exit(0)

    batch_files = [(_safe_relative_path(fp, scan_root), fp) for fp in files]

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
    ) as progress:
        scan_task = progress.add_task("Scanning...", total=len(files))

        results, errors, total_tokens = asyncio.run(
            _analyze_batch(analyzer, batch_files, task, progress, scan_task)
        )

    for r in results:
        _format_output(r, config.output_format)

    summary = Text()
    summary.append(f"\n{t('files_analyzed', count=len(results))}", style="bold")
    if errors:
        summary.append(t("files_failed", count=len(errors)), style="bold red")
    summary.append(t("tokens_total", tokens=f"{total_tokens:,}"), style="dim")
    out.print(Panel(summary, border_style="green", title=t("scan_complete")))

    if errors:
        for fp, err in errors:
            console.print(f"  [red]FAIL[/] {fp}: {err}")
    exit_code = _batch_exit_code(results, errors)
    if exit_code:
        sys.exit(exit_code)


def _run_benchmark(args, config: AppConfig) -> None:
    default_pc = config.providers.get(
        config.default_provider,
        ProviderConfig(provider=config.default_provider),
    )
    models = args.models or [default_pc.model]
    provider_name = (
        args.provider
        if hasattr(args, "provider") and args.provider
        else config.default_provider
    )

    for model in models:
        console.print(f"\n[bold cyan]Benchmarking:[/] {model} ({provider_name})")
        with console.status("[bold green]Running benchmark on 8 test cases...", spinner="dots"):
            try:
                summary = asyncio.run(benchmark_model(provider_name, model, config))
            except Exception as exc:
                console.print(f"[bold red]Error:[/] {exc}")
                continue

        if getattr(args, "json", False):
            out.print(export_benchmark_json(summary))
        else:
            out.print(Markdown(format_benchmark(summary)))

    console.print()


def _run_diff(args, config: AppConfig) -> None:
    task_map = {"review": TaskType.REVIEW, "bugs": TaskType.BUGS, "security": TaskType.SECURITY}
    task = task_map[args.task]

    git_cmd = ["git", "diff"]
    if args.staged:
        git_cmd.append("--staged")
    git_cmd.extend(["--name-only", "--diff-filter=ACMR"])

    try:
        repo_root_result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        console.print("[bold red]Error:[/] git not found.")
        sys.exit(1)
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() or "Not a git repository."
        console.print(f"[bold red]Error:[/] {message}")
        sys.exit(1)

    repo_root = Path(repo_root_result.stdout.strip()).resolve()

    try:
        result = subprocess.run(
            git_cmd,
            capture_output=True,
            text=True,
            check=True,
            cwd=repo_root,
        )
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() or "git diff failed."
        console.print(f"[bold red]Error:[/] {message}")
        sys.exit(1)

    changed = [path for path in result.stdout.splitlines() if path.strip()]
    files: list[tuple[str, str]] = []
    for rel_path in changed:
        abs_path = (repo_root / rel_path).resolve()
        if not abs_path.is_relative_to(repo_root):
            continue
        if abs_path.suffix in SCAN_EXTENSIONS and abs_path.is_file():
            files.append((rel_path, str(abs_path)))

    if not files:
        console.print("[green]No changed source files to analyze.[/]")
        sys.exit(0)

    console.print(f"Found [bold]{len(files)}[/] changed files")

    try:
        analyzer = Analyzer(config, provider_name=args.provider)
    except ValueError as exc:
        console.print(f"[bold red]Config error:[/] {exc}")
        sys.exit(1)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
    ) as progress:
        scan_task = progress.add_task("Analyzing diff...", total=len(files))

        results, errors, total_tokens = asyncio.run(
            _analyze_batch(analyzer, files, task, progress, scan_task)
        )

    for r in results:
        _format_output(r, config.output_format)

    summary = Text()
    summary.append(f"\n{len(results)} changed files analyzed", style="bold")
    if errors:
        summary.append(f", {len(errors)} failed", style="bold red")
    summary.append(f" - {total_tokens:,} tokens total", style="dim")
    out.print(Panel(summary, border_style="green", title="Diff Analysis Complete"))

    if errors:
        for fp, err in errors:
            console.print(f"  [red]FAIL[/] {fp}: {err}")

    exit_code = _batch_exit_code(results, errors)
    if exit_code:
        sys.exit(exit_code)


def _run_config() -> None:
    config = load_config()
    console.print()
    console.print(Panel(
        "[bold]CodeSight Setup[/]\n[dim]Use arrow keys, Enter to select[/]",
        border_style="cyan",
        width=50,
    ))
    console.print()

    def validate_http_url(val: str) -> bool | str:
        if not val.strip().startswith("http"):
            return "Must start with http:// or https://"
        return True

    provider = questionary.select(
        "Select a provider:",
        choices=[
            questionary.Choice("OpenAI        (GPT-5.4)", value="openai"),
            questionary.Choice("Anthropic     (Claude Opus 4.6)", value="anthropic"),
            questionary.Choice(
                "Azure Foundry (Claude via Microsoft Azure)",
                value="azure",
            ),
            questionary.Choice("Google        (Gemini 3.1 Pro)", value="google"),
            questionary.Choice("Ollama        (local, free, offline)", value="ollama"),
            questionary.Separator(),
            questionary.Choice(
                "Custom        (OpenRouter / Groq / Together / any OpenAI-compat)",
                value="custom",
            ),
        ],
        default=(
            config.default_provider
            if config.default_provider in (
                "openai",
                "anthropic",
                "azure",
                "google",
                "ollama",
            )
            else "openai"
        ),
    ).ask()

    if provider is None:
        console.print("[yellow]Cancelled.[/]")
        return

    config.default_provider = provider

    if provider == "openai":
        key = questionary.password("OpenAI API key (sk-...):").ask() or ""
        model = (
            questionary.text("Model:", default=DEFAULT_OPENAI_MODEL).ask()
            or DEFAULT_OPENAI_MODEL
        )
        config.providers["openai"] = ProviderConfig(
            provider="openai",
            api_key=key,
            model=model,
        )

    elif provider == "anthropic":
        key = questionary.password("Anthropic API key (sk-ant-...):").ask() or ""
        default_m = DEFAULT_ANTHROPIC_MODEL
        model = (
            questionary.text("Model:", default=default_m).ask()
            or default_m
        )
        config.providers["anthropic"] = ProviderConfig(
            provider="anthropic",
            api_key=key,
            model=model,
        )

    elif provider == "google":
        project = questionary.text("Google Cloud Project ID:").ask() or ""
        region = questionary.text("Region:", default="us-central1").ask() or "us-central1"
        model = (
            questionary.text("Model:", default=DEFAULT_GOOGLE_MODEL).ask()
            or DEFAULT_GOOGLE_MODEL
        )
        config.providers["google"] = ProviderConfig(
            provider="google",
            project_id=project,
            region=region,
            model=model,
        )

    elif provider == "azure":
        console.print()
        console.print("  [dim]Azure AI Foundry → Claude models via Anthropic API[/]")
        console.print("  [dim]Find your resource at: https://ai.azure.com/[/]")
        console.print(
            "  [dim]Accepts resource root, full endpoint, "
            "or /api/projects/... URL (normalized automatically).[/]"
        )
        console.print()
        resource = questionary.text(
            "Resource name or full base URL:",
            instruction="(e.g. 'my-resource-name' or full https://... URL)",
        ).ask() or ""
        if not resource:
            console.print("[yellow]Cancelled.[/]")
            return

        if resource.startswith(("http://", "https://")):
            base_url = normalize_azure_base_url(resource)
        else:
            base_url = f"https://{resource}.services.ai.azure.com"

        api_key = questionary.password(
            "API key (from Foundry portal → Endpoints & keys):"
        ).ask() or ""
        model = questionary.text(
            "Deployment name (model):",
            default=DEFAULT_ANTHROPIC_MODEL,
            instruction="Must match the deployment name you created in Azure",
        ).ask() or DEFAULT_ANTHROPIC_MODEL
        label = questionary.text("Config label:", default="azure").ask() or "azure"
        config.providers[label] = ProviderConfig(
            provider="anthropic",
            api_key=api_key or None,
            base_url=base_url,
            model=model,
        )
        config.default_provider = label
        masked_base_url = _mask_url_display(base_url)
        masked_endpoint = _mask_url_display(f"{base_url}/anthropic/v1/messages")
        console.print(f"\n  [dim]Resource root: [cyan]{masked_base_url}[/][/]")

        console.print(
            f"  [dim]Endpoint:      [cyan]{masked_endpoint}[/][/]")

        console.print(
            f"  [dim]Use with:  [green]codesight -p {label} review file.py[/][/]")

    elif provider == "ollama":
        host = questionary.text(
            "Ollama host:",
            default="http://localhost:11434",
            validate=validate_http_url,
        ).ask() or "http://localhost:11434"
        model = questionary.text(
            "Model (must be pulled in Ollama):",
            default=DEFAULT_OLLAMA_MODEL,
        ).ask() or DEFAULT_OLLAMA_MODEL
        config.providers["ollama"] = ProviderConfig(
            provider="ollama",
            base_url=host,
            model=model,
        )
        console.print("\n  [dim]Start Ollama:  [green]ollama serve[/]")
        console.print(f"  [dim]Pull model:    [green]ollama pull {model}[/]")
        console.print(f"  [dim]Host:          [cyan]{host}[/]")

    elif provider == "custom":
        from .providers.custom_provider import KNOWN_PRESETS

        preset_choices = [
            Choice(f"{name:15s}  {url}", value=name)
            for name, (url, _) in KNOWN_PRESETS.items()
        ]
        preset_name = questionary.select(
            "Pick a provider (or Custom URL to enter manually):",
            choices=preset_choices,
        ).ask()
        if preset_name is None:
            console.print("[yellow]Cancelled.[/]")
            return

        preset_url, preset_model = KNOWN_PRESETS[preset_name]
        base_url = questionary.text(
            "Base URL (e.g. https://openrouter.ai/api/v1):",
            default=preset_url,
            validate=validate_http_url,
        ).ask() or preset_url
        api_key = questionary.password("API key (leave blank if not needed):").ask() or ""
        model = questionary.text(
            "Model name:",
            default=preset_model or DEFAULT_OPENAI_MODEL,
        ).ask() or (preset_model or DEFAULT_OPENAI_MODEL)
        default_label = (
            preset_name.lower().replace(" ", "-").replace("(", "").replace(")", "")
        )
        label = questionary.text(
            "Config label (used as provider name, e.g. openrouter):",
            default=default_label,
        ).ask() or "custom"

        config.providers[label] = ProviderConfig(
            provider="custom",
            api_key=api_key or None,
            base_url=base_url,
            model=model,
        )
        config.default_provider = label
        console.print(f"\n  [dim]Provider saved as: [cyan]{label}[/][/]")

        console.print(
            f"  [dim]Use with: [green]codesight -p {label} review file.py[/][/]")

    save_config(config)
    console.print(f"\n[bold green]Saved to[/] [cyan]{CONFIG_FILE}[/]")

    run_check = questionary.confirm("Run health check now?", default=True).ask()
    if run_check:
        _run_health(SimpleNamespace(provider=None), config)


def _run_health(args, config: AppConfig) -> None:
    from .config import get_provider_config

    provider_name = getattr(args, "provider", None) or config.default_provider
    console.print()
    console.print(f"  Provider: [bold cyan]{provider_name}[/]")

    try:
        pconf = get_provider_config(config, provider_name)
    except ValueError as exc:
        console.print(f"[bold red]Config error:[/] {exc}")
        sys.exit(1)

    provider_type = pconf.provider
    is_azure = provider_type == "anthropic" and is_azure_url(pconf.base_url or "")

    if provider_type == "ollama":
        host = pconf.base_url or "http://localhost:11434"
        console.print(f"  Host:     [dim]{host}[/]")
        console.print(f"  Model:    [dim]{pconf.model}[/]")
    elif is_azure:
        base_url = normalize_azure_base_url(pconf.base_url or "")
        masked_base_url = _mask_url_display(base_url)
        masked_endpoint = _mask_url_display(f"{base_url}/anthropic/v1/messages")
        key = pconf.api_key or ""
        masked = f"...{key[-4:]}" if len(key) > 6 else "[red]NOT SET[/]"
        console.print(f"  Resource: [dim]{masked_base_url}[/]")
        console.print(
            f"  Endpoint: [dim]{masked_endpoint}[/]"
        )
        console.print(f"  API key:  [dim]{masked}[/]")
        console.print(f"  Model:    [dim]{pconf.model}[/]")
    elif provider_type == "custom":
        console.print(f"  Base URL: [dim]{_mask_url_display(pconf.base_url)}[/]")
        key = pconf.api_key or ""
        if len(key) > 6:
            masked = f"...{key[-4:]}"
        elif not key:
            masked = "[dim](none)[/]"
        else:
            masked = "[red]SET[/]"
        console.print(f"  API key:  [dim]{masked}[/]")
        console.print(f"  Model:    [dim]{pconf.model}[/]")
    elif provider_type == "openai":
        key = pconf.api_key or ""
        masked = f"sk-...{key[-4:]}" if len(key) > 8 else "[red]NOT SET[/]"
        console.print(f"  API key:  [dim]{masked}[/]")
        console.print(f"  Model:    [dim]{pconf.model}[/]")
    elif provider_type == "anthropic":
        key = pconf.api_key or ""
        masked = f"sk-ant-...{key[-4:]}" if len(key) > 8 else "[red]NOT SET[/]"
        console.print(f"  API key:  [dim]{masked}[/]")
        console.print(f"  Model:    [dim]{pconf.model}[/]")
    elif provider_type == "google":
        console.print(f"  Project:  [dim]{_mask_identifier(pconf.project_id)}[/]")
        console.print(f"  Model:    [dim]{pconf.model}[/]")

    console.print()

    try:
        analyzer = Analyzer(config, provider_name=provider_name)
    except ValueError as exc:
        console.print(f"[bold red]Config error:[/] {exc}")
        sys.exit(1)

    with console.status("[bold]Testing connection...[/]", spinner="dots"):
        ok = asyncio.run(analyzer.health())

    if ok:
        console.print("[bold green]Connection OK[/]")
        return

    console.print("[bold red]Connection failed[/]\n")
    if provider_type == "ollama":
        host = pconf.base_url or "http://localhost:11434"
        console.print("  [yellow]Ollama is not running or model not found.[/]")
        console.print("  1. Start server:  [green]ollama serve[/]")
        console.print(f"  2. Pull model:    [green]ollama pull {pconf.model}[/]")
        console.print(f"  3. Check host:    {host}")
    elif is_azure:
        base_url = normalize_azure_base_url(pconf.base_url or "")
        masked_base_url = _mask_url_display(base_url)
        masked_endpoint = _mask_url_display(f"{base_url}/anthropic/v1/messages")
        console.print("  [yellow]Azure Foundry auth failed.[/]")
        console.print("  Check:")
        console.print(f"    1. Resource root is [green]{masked_base_url}[/]")
        console.print(
            f"    2. Endpoint is [green]{masked_endpoint}[/]"
        )
        console.print(
            "    3. Do not use [green]/api/projects/...[/] or paste the full "
            "[green]/anthropic/v1/messages[/] path"
        )
        console.print("    4. API key is from Foundry → Endpoints & keys")
        console.print(f"    5. Deployment name exists: [green]{pconf.model}[/]")
    elif provider_type == "openai":
        if not (pconf.api_key or ""):
            console.print("  [yellow]API key is not set.[/]")
            console.print(
                "  Run [green]codesight config[/] or set "
                "[green]OPENAI_API_KEY=sk-...[/]"
            )
        else:
            console.print("  [yellow]API key may be invalid or OpenAI is unreachable.[/]")
            console.print("  Check: https://platform.openai.com/account/api-keys")
    elif provider_type == "anthropic":
        if not (pconf.api_key or ""):
            console.print("  [yellow]API key is not set.[/]")
            console.print(
                "  Run [green]codesight config[/] or set "
                "[green]ANTHROPIC_API_KEY=sk-ant-...[/]"
            )
        else:
            console.print("  [yellow]API key may be invalid.[/]")
            console.print("  Check: https://console.anthropic.com/settings/keys")
    elif provider_type == "google":
        console.print("  [yellow]Google Cloud auth failed.[/]")
        console.print("  Run: [green]gcloud auth application-default login[/]")
    elif provider_type == "custom":
        console.print(f"  [yellow]Could not reach {_mask_url_display(pconf.base_url)}[/]")
        console.print("  Check:")
        console.print("    1. Base URL is correct (include /v1 if needed)")
        console.print("    2. API key is valid")
        console.print("    3. Model name exists on this provider")
        if pconf.base_url and "openrouter" in pconf.base_url:
            console.print("  OpenRouter models: https://openrouter.ai/models")
    sys.exit(1)


def _run_templates(args, config: AppConfig) -> None:
    action = getattr(args, "tmpl_action", None)

    if action == "list" or action is None:
        templates = list_templates()
        if not templates:
            console.print("[yellow]No templates found.[/]")
            return
        console.print(Panel("[bold]Prompt Templates[/]", border_style="cyan"))
        for slug, tmpl in templates.items():
            name = tmpl.get("name", slug)
            desc = tmpl.get("description", "")
            console.print(f"  [bold cyan]{slug}[/] - {name}")
            if desc:
                console.print(f"    [dim]{desc}[/]")
        console.print()

    elif action == "run":
        tmpl = get_template(args.template)
        if not tmpl:
            console.print(f"[bold red]Template not found:[/] {args.template}")
            console.print("Run [green]codesight templates list[/] to see available templates.")
            sys.exit(1)

        file_path = str(Path(args.file).resolve())
        try:
            analyzer = Analyzer(config, provider_name=args.provider)
            p, source = _read_source_file(file_path, config.max_file_size_kb)
        except ValueError as exc:
            console.print(f"[bold red]Config error:[/] {exc}")
            sys.exit(1)
        except AnalysisError as exc:
            console.print(f"[bold red]Error:[/] {exc}")
            sys.exit(1)

        file_path = str(p)
        ext = p.suffix

        messages = [
            Message(role="system", content=tmpl["system"]),
            Message(
                role="user",
                content=f"File: `{file_path}` ({ext})\n\n"
                f"```{ext.lstrip('.')}\n{source}\n```",
            ),
        ]

        with console.status(
            f"[bold green]Running template[/] [cyan]{args.template}[/] on {p.name}...",
            spinner="dots",
        ):
            try:
                response = asyncio.run(analyzer.complete_messages(messages))
            except Exception as exc:
                console.print(f"[bold red]Error:[/] {exc}")
                sys.exit(1)

        out.print()
        header = Text()
        header.append(" CodeSight ", style="bold white on dark_green")
        header.append(f" {tmpl.get('name', args.template)} ", style="bold")
        header.append(f" {response.provider} ", style="dim")
        header.append(f"({response.model})", style="dim")
        out.print(Panel(header, border_style="green"))
        out.print(Markdown(response.content))
        out.print()

    elif action == "add":
        name = args.name
        if not _is_valid_template_name(name):
            console.print("[bold red]Invalid template name.[/]")
            console.print("Use lowercase letters, digits, hyphens, and underscores only.")
            sys.exit(1)
        if get_template(name):
            console.print(f"[bold red]Template already exists:[/] {name}")
            console.print(
                "Choose a different name; built-in and existing templates cannot "
                "be overridden."
            )
            sys.exit(1)
        display = console.input(f"  Display name for [cyan]{name}[/]: ").strip() or name
        desc = console.input("  Description: ").strip()
        console.print("  Enter system prompt (end with an empty line):")
        lines = []
        while True:
            line = console.input("  > ").rstrip()
            if not line:
                break
            lines.append(line)
        prompt = "\n".join(lines)
        if not prompt:
            console.print("[bold red]Empty prompt, aborting.[/]")
            sys.exit(1)
        path = save_template(name, display, desc, prompt)
        console.print(f"[bold green]Saved:[/] {path}")

    elif action == "delete":
        if delete_template(args.name):
            console.print(f"[bold green]Deleted:[/] {args.name}")
        else:
            console.print(f"[yellow]Template not found:[/] {args.name}")
            console.print("[dim]Only custom templates can be deleted, not built-in ones.[/]")

def _run_interactive(config: AppConfig, provider_name: str | None = None) -> None:
    while True:
        config = load_config()
        active_provider = provider_name or config.default_provider
        console.print()
        console.print(Panel(
            f"[bold]CodeSight[/] [dim]v{__version__}[/]\n"
            f"[dim]Provider: {active_provider}[/]",
            border_style="green",
            width=48,
        ))
        console.print()

        action = questionary.select(
            "What do you want to do?",
            choices=[
                questionary.Choice("review    - code review", value="review"),
                questionary.Choice("bugs      - find logic errors & race conditions", value="bugs"),
                questionary.Choice("security  - security audit (CWE / OWASP)", value="security"),
                questionary.Choice("scan      - scan a whole directory", value="scan"),
                questionary.Choice("diff      - review git-changed files", value="diff"),
                questionary.Choice("explain   - plain-language code breakdown", value="explain"),
                questionary.Choice("refactor  - refactoring suggestions", value="refactor"),
                questionary.Separator(),
                questionary.Choice("config    - setup API keys / provider", value="config"),
                questionary.Choice("health    - test provider connection", value="health"),
                questionary.Choice("quit", value="quit"),
            ],
        ).ask()

        if action is None or action == "quit":
            return

        try:
            if action == "config":
                _run_config()
            elif action == "health":
                _run_health(SimpleNamespace(provider=provider_name), config)
            elif action == "diff":
                _run_diff(
                    SimpleNamespace(task="security", staged=False, provider=provider_name),
                    config,
                )
            elif action == "scan":
                directory = questionary.path(
                    "Directory to scan:", default=".", only_directories=True,
                ).ask()
                if directory is None:
                    continue
                directory = directory or "."
                task = questionary.select(
                    "Analysis type:",
                    choices=[
                        questionary.Choice("security  - find vulnerabilities", value="security"),
                        questionary.Choice("bugs      - find logic errors", value="bugs"),
                        questionary.Choice("review    - general code review", value="review"),
                    ],
                ).ask()
                if task is None:
                    continue
                _run_scan(
                    SimpleNamespace(
                        dir=directory,
                        task=task,
                        ext=None,
                        provider=provider_name,
                    ),
                    config,
                )
            else:
                file_path = questionary.path(
                    f"File to {action}:",
                    validate=lambda p: Path(p).is_file() or "File not found",
                ).ask()
                if not file_path:
                    continue

                _run_analysis(
                    SimpleNamespace(
                        command=action,
                        file=file_path,
                        context=None,
                        provider=provider_name,
                        pipeline=None,
                    ),
                    config,
                )
        except SystemExit:
            pass


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    config = load_config()

    lang_arg = getattr(args, "lang", None)
    set_language(lang_arg or resolve_language(config.language))

    if not args.command:
        _run_interactive(config, provider_name=args.provider)
        sys.exit(0)

    if args.output:
        config.output_format = args.output

    if args.command in ("review", "bugs", "security", "docs", "explain", "refactor"):
        _run_analysis(args, config)
    elif args.command == "scan":
        _run_scan(args, config)
    elif args.command == "diff":
        _run_diff(args, config)
    elif args.command == "benchmark":
        _run_benchmark(args, config)
    elif args.command == "config":
        _run_config()
    elif args.command == "health":
        _run_health(args, config)
    elif args.command == "templates":
        _run_templates(args, config)
    else:
        parser.error(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    main()
