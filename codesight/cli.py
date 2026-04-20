import argparse
import asyncio
import json
import sys
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn
from rich.text import Text

from . import __version__
from .analyzer import AnalysisError, Analyzer, TaskType, collect_files
from .benchmark import benchmark_model, export_benchmark_json, format_benchmark
from .config import (
    CONFIG_FILE,
    AppConfig,
    ProviderConfig,
    load_config,
    save_config,
)
from .cost import estimate_cost, format_cost
from .pipeline import PipelineConfig, run_pipeline
from .sarif import parse_findings, to_sarif_json
from .templates import delete_template, get_template, list_templates, save_template

console = Console(stderr=True)
out = Console()

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codesight",
        description="AI-powered code analysis and review tool",
    )
    parser.add_argument("-v", "--version", action="version", version=f"codesight {__version__}")
    parser.add_argument(
        "-p", "--provider",
        choices=["openai", "anthropic", "google", "ollama"],
        help="LLM provider to use (overrides config default)",
    )
    parser.add_argument(
        "-o", "--output",
        choices=["markdown", "json", "plain", "sarif"],
        default=None,
        help="Output format",
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
                help="Multi-model pipeline, e.g. ollama/llama3:openai/gpt-4o",
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

    diff = sub.add_parser("diff", help="Review only git-changed files")
    diff.add_argument(
        "-t", "--task",
        choices=["review", "bugs", "security"],
        default="security",
        help="Analysis type (default: security)",
    )
    diff.add_argument("--staged", action="store_true", help="Only staged changes")

    bench = sub.add_parser("benchmark", help="Benchmark LLMs on vulnerable code")
    bench.add_argument("--models", nargs="+", help="Models to test (e.g. gpt-4o llama3)")
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

    out.print()
    out.print(Panel(header, subtitle=str(token_text), border_style="green"))

    if output_format == "sarif":
        findings = parse_findings(result.content, result.file_path)
        out.print(to_sarif_json(findings))
    elif output_format == "json":
        out.print_json(json.dumps({
            "task": result.task.value,
            "file": result.file_path,
            "provider": result.provider,
            "model": result.model,
            "tokens_used": result.tokens_used,
            "content": result.content,
        }, indent=2))
    elif output_format == "plain":
        out.print(result.content)
    else:
        out.print(Markdown(result.content))

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
            triage_str, verify_str = pipeline_arg.split(":")
            t_provider, t_model = triage_str.split("/")
            v_provider, v_model = verify_str.split("/")
        except ValueError:
            console.print("[bold red]Pipeline format:[/] provider/model:provider/model")
            console.print("  Example: ollama/llama3:openai/gpt-4o")
            sys.exit(1)

        pcfg = PipelineConfig(
            triage_provider=t_provider, triage_model=t_model,
            verify_provider=v_provider, verify_model=v_model,
        )

        source = Path(file_path).read_text(encoding="utf-8", errors="replace")

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

        from .analyzer import AnalysisResult
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


def _run_scan(args, config: AppConfig) -> None:
    task_map = {"review": TaskType.REVIEW, "bugs": TaskType.BUGS, "security": TaskType.SECURITY}
    task = task_map[args.task]
    exts = {e if e.startswith(".") else f".{e}" for e in args.ext} if args.ext else None

    files = collect_files(
        args.dir,
        extensions=exts,
        ignore=config.ignore_patterns,
        max_size_kb=config.max_file_size_kb,
    )

    if not files:
        console.print("[yellow]No source files found.[/]")
        sys.exit(0)

    console.print(f"Found [bold]{len(files)}[/] files in [cyan]{Path(args.dir).resolve()}[/]")

    try:
        analyzer = Analyzer(config, provider_name=args.provider)
    except ValueError as exc:
        console.print(f"[bold red]Config error:[/] {exc}")
        sys.exit(1)

    results = []
    errors = []
    total_tokens = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
    ) as progress:
        scan_task = progress.add_task("Scanning...", total=len(files))

        for fp in files:
            short = str(Path(fp).relative_to(Path(args.dir).resolve()))
            progress.update(scan_task, description=f"[green]{short}[/]")
            try:
                result = asyncio.run(analyzer.analyze_file(fp, task))
                results.append(result)
                total_tokens += result.tokens_used
            except AnalysisError as exc:
                errors.append((fp, str(exc)))
            progress.advance(scan_task)

    for r in results:
        _format_output(r, config.output_format)

    summary = Text()
    summary.append(f"\n{len(results)} files analyzed", style="bold")
    if errors:
        summary.append(f", {len(errors)} failed", style="bold red")
    summary.append(f" — {total_tokens:,} tokens total", style="dim")
    out.print(Panel(summary, border_style="green", title="Scan Complete"))

    if errors:
        for fp, err in errors:
            console.print(f"  [red]✗[/] {fp}: {err}")
    all_content = " ".join(r.content for r in results).upper()
    if "CRITICAL" in all_content or "[CRIT]" in all_content:
        sys.exit(2)
    elif "HIGH" in all_content or "[WARN]" in all_content:
        sys.exit(1)


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
    import subprocess

    task_map = {"review": TaskType.REVIEW, "bugs": TaskType.BUGS, "security": TaskType.SECURITY}
    task = task_map[args.task]

    git_cmd = ["git", "diff", "--name-only", "--diff-filter=ACMR"]
    if args.staged:
        git_cmd.insert(2, "--staged")

    try:
        result = subprocess.run(git_cmd, capture_output=True, text=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        console.print("[bold red]Error:[/] Not a git repository or git not found.")
        sys.exit(1)

    changed = [f for f in result.stdout.strip().split("\n") if f.strip()]
    source_exts = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".rb",
                   ".java", ".kt", ".cs", ".cpp", ".c", ".h", ".php", ".swift"}
    files = [f for f in changed if Path(f).suffix in source_exts and Path(f).is_file()]

    if not files:
        console.print("[green]No changed source files to analyze.[/]")
        sys.exit(0)

    console.print(f"Found [bold]{len(files)}[/] changed files")

    try:
        prov = args.provider if hasattr(args, "provider") else None
        analyzer = Analyzer(config, provider_name=prov)
    except ValueError as exc:
        console.print(f"[bold red]Config error:[/] {exc}")
        sys.exit(1)

    results = []
    errors = []
    total_tokens = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
    ) as progress:
        scan_task = progress.add_task("Analyzing diff...", total=len(files))

        for fp in files:
            progress.update(scan_task, description=f"[green]{fp}[/]")
            try:
                r = asyncio.run(analyzer.analyze_file(str(Path(fp).resolve()), task))
                results.append(r)
                total_tokens += r.tokens_used
            except AnalysisError as exc:
                errors.append((fp, str(exc)))
            progress.advance(scan_task)

    for r in results:
        _format_output(r, config.output_format)

    summary = Text()
    summary.append(f"\n{len(results)} changed files analyzed", style="bold")
    if errors:
        summary.append(f", {len(errors)} failed", style="bold red")
    summary.append(f" — {total_tokens:,} tokens total", style="dim")
    out.print(Panel(summary, border_style="green", title="Diff Analysis Complete"))

    if errors:
        for fp, err in errors:
            console.print(f"  [red]✗[/] {fp}: {err}")

    all_content = " ".join(r.content for r in results).upper()
    if "CRITICAL" in all_content or "[CRIT]" in all_content:
        sys.exit(2)
    elif "HIGH" in all_content or "[WARN]" in all_content:
        sys.exit(1)


def _run_config() -> None:
    config = load_config()
    console.print(Panel("[bold]CodeSight Configuration[/]", border_style="cyan"))

    provider = console.input(
        f"  Default provider [green]\\[openai/anthropic/google][/] "
        f"(current: [cyan]{config.default_provider}[/]): "
    ).strip() or config.default_provider
    config.default_provider = provider

    if provider == "openai":
        key = console.input("  OpenAI API Key: ").strip()
        model = console.input("  Model [dim]\\[gpt-5.4][/]: ").strip() or "gpt-5.4"
        config.providers["openai"] = ProviderConfig(
            provider="openai", api_key=key, model=model,
        )
    elif provider == "anthropic":
        key = console.input("  Anthropic API Key: ").strip()
        default_m = "claude-opus-4-6-20251101"
        model = console.input(
            f"  Model [dim]\\[{default_m}][/]: "
        ).strip() or default_m
        config.providers["anthropic"] = ProviderConfig(
            provider="anthropic", api_key=key, model=model,
        )
    elif provider == "google":
        project = console.input("  Google Cloud Project ID: ").strip()
        region = console.input("  Region [dim]\\[us-central1][/]: ").strip() or "us-central1"
        model = console.input("  Model [dim]\\[gemini-3.1-pro][/]: ").strip() or "gemini-3.1-pro"
        config.providers["google"] = ProviderConfig(
            provider="google", project_id=project, region=region, model=model,
        )
    elif provider == "ollama":
        host = console.input("  Ollama host [dim]\\[http://localhost:11434][/]: ").strip() or "http://localhost:11434"
        model = console.input("  Model [dim]\\[llama3][/]: ").strip() or "llama3"
        config.providers["ollama"] = ProviderConfig(
            provider="ollama", base_url=host, model=model,
        )
    else:
        console.print(f"[bold red]Unknown provider:[/] {provider}")
        sys.exit(1)

    save_config(config)
    console.print(f"\n[bold green]✓[/] Configuration saved to [cyan]{CONFIG_FILE}[/]")


def _run_health(args, config: AppConfig) -> None:
    try:
        analyzer = Analyzer(config, provider_name=args.provider)
    except ValueError as exc:
        console.print(f"[bold red]Config error:[/] {exc}")
        sys.exit(1)

    with console.status("[bold green]Checking provider...", spinner="dots"):
        ok = asyncio.run(analyzer.health())

    if ok:
        console.print("[bold green]✓[/] Provider is reachable and healthy.")
    else:
        console.print("[bold red]✗[/] Could not reach the provider. Check your credentials.")
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
            console.print(f"  [bold cyan]{slug}[/] — {name}")
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
        except ValueError as exc:
            console.print(f"[bold red]Config error:[/] {exc}")
            sys.exit(1)

        p = Path(file_path)
        source = p.read_text(encoding="utf-8", errors="replace")
        ext = p.suffix

        from .providers.base import Message as Msg
        messages = [
            Msg(role="system", content=tmpl["system"]),
            Msg(
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
                response = asyncio.run(analyzer._provider.complete(
                    messages,
                    max_tokens=config.providers.get(
                        config.default_provider,
                        ProviderConfig(provider=config.default_provider),
                    ).max_tokens,
                ))
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


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if not args.command:
        console.print(
            Panel(
                "[bold]CodeSight[/] — AI-powered code analysis and review\n\n"
                f"Version: [cyan]{__version__}[/]\n"
                "Run [green]codesight --help[/] for usage.",
                border_style="green",
            )
        )
        sys.exit(0)

    config = load_config()
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


if __name__ == "__main__":
    main()
