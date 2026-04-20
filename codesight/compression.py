import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CodeMap:
    file_path: str
    language: str
    imports: list[str]
    symbols: list[str]
    structure: str
    original_lines: int
    compressed_lines: int

    @property
    def ratio(self) -> float:
        if self.original_lines == 0:
            return 0.0
        return 1 - (self.compressed_lines / self.original_lines)


LANG_PATTERNS = {
    "py": {
        "class": re.compile(r"^(class\s+\w+[^:]*:)", re.MULTILINE),
        "function": re.compile(r"^((?:async\s+)?def\s+\w+\s*\([^)]*\)[^:]*:)", re.MULTILINE),
        "import": re.compile(r"^((?:from\s+\S+\s+)?import\s+.+)$", re.MULTILINE),
        "decorator": re.compile(r"^(@\w+[\w.]*(?:\([^)]*\))?)", re.MULTILINE),
        "docstring_start": re.compile(r'^\s*(""".*?"""|\'\'\'.*?\'\'\')', re.MULTILINE | re.DOTALL),
    },
    "js": {
        "class": re.compile(r"^((?:export\s+)?class\s+\w+[^{]*)", re.MULTILINE),
        "function": re.compile(
            r"^((?:export\s+)?(?:async\s+)?function\s+\w+\s*\([^)]*\))", re.MULTILINE
        ),
        "arrow": re.compile(
            r"^((?:export\s+)?(?:const|let|var)\s+\w+\s*=\s*(?:async\s+)?\([^)]*\)\s*=>)",
            re.MULTILINE,
        ),
        "import": re.compile(r"^(import\s+.+)$", re.MULTILINE),
    },
    "ts": None,
    "go": {
        "function": re.compile(r"^(func\s+(?:\([^)]+\)\s+)?\w+\s*\([^)]*\)[^{]*)", re.MULTILINE),
        "struct": re.compile(r"^(type\s+\w+\s+struct\s*\{)", re.MULTILINE),
        "interface": re.compile(r"^(type\s+\w+\s+interface\s*\{)", re.MULTILINE),
        "import": re.compile(r"^(import\s+.+)$", re.MULTILINE),
    },
    "rs": {
        "function": re.compile(
            r"^((?:pub\s+)?(?:async\s+)?fn\s+\w+[^{]*)", re.MULTILINE
        ),
        "struct": re.compile(r"^((?:pub\s+)?struct\s+\w+[^{]*)", re.MULTILINE),
        "impl": re.compile(r"^(impl(?:<[^>]+>)?\s+\w+[^{]*)", re.MULTILINE),
        "import": re.compile(r"^(use\s+.+;)$", re.MULTILINE),
    },
    "java": {
        "class": re.compile(
            r"^((?:public|private|protected)?\s*(?:static\s+)?(?:abstract\s+)?class\s+\w+[^{]*)",
            re.MULTILINE,
        ),
        "method": re.compile(
            r"^\s*((?:public|private|protected)\s+(?:static\s+)?[\w<>\[\]]+\s+\w+\s*\([^)]*\))",
            re.MULTILINE,
        ),
        "import": re.compile(r"^(import\s+.+;)$", re.MULTILINE),
    },
}

LANG_PATTERNS["ts"] = LANG_PATTERNS["js"]
LANG_PATTERNS["jsx"] = LANG_PATTERNS["js"]
LANG_PATTERNS["tsx"] = LANG_PATTERNS["js"]
LANG_PATTERNS["kt"] = LANG_PATTERNS["java"]


EXT_TO_LANG = {
    ".py": "py", ".js": "js", ".ts": "ts", ".jsx": "jsx", ".tsx": "tsx",
    ".go": "go", ".rs": "rs", ".java": "java", ".kt": "kt",
}


def _extract_symbols(source: str, patterns: dict) -> tuple[list[str], list[str]]:
    imports = []
    symbols = []

    for match in patterns.get("import", re.compile(r"$^")).finditer(source):
        imports.append(match.group(1).strip())

    for key in ("decorator", "class", "function", "arrow", "method", "struct", "interface", "impl"):
        pat = patterns.get(key)
        if pat is None:
            continue
        for match in pat.finditer(source):
            symbols.append(match.group(1).strip())

    return imports, symbols


def _build_structure(source: str, language: str) -> str:
    lines = source.splitlines()
    indent_map = []

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("//"):
            continue

        indent = len(line) - len(line.lstrip())
        indent_map.append((i, indent, stripped))

    structure_lines = []
    prev_indent = -1

    for line_no, indent, content in indent_map:
        is_sig = False
        if language == "py":
            is_sig = content.startswith(("class ", "def ", "async def ", "@"))
        elif language in ("js", "ts", "jsx", "tsx"):
            is_sig = any(
                content.startswith(kw)
                for kw in ("class ", "function ", "async function ", "export ", "const ", "let ", "import ")
            )
        elif language == "go":
            is_sig = content.startswith(("func ", "type ", "import "))
        elif language == "rs":
            is_sig = content.startswith(("fn ", "pub fn ", "pub async fn ", "struct ", "pub struct ", "impl ", "use "))
        elif language in ("java", "kt"):
            is_sig = any(
                content.startswith(kw)
                for kw in ("public ", "private ", "protected ", "class ", "import ", "interface ")
            )

        if is_sig:
            structure_lines.append(f"  {'  ' * (indent // 4)}L{line_no}: {content}")
            prev_indent = indent
        elif indent <= prev_indent and prev_indent >= 0:
            prev_indent = -1

    return "\n".join(structure_lines)


def build_code_map(file_path: str) -> CodeMap:
    p = Path(file_path)
    ext = p.suffix
    language = EXT_TO_LANG.get(ext, ext.lstrip("."))
    source = p.read_text(encoding="utf-8", errors="replace")
    original_lines = len(source.splitlines())

    patterns = LANG_PATTERNS.get(language, {})
    if patterns is None:
        patterns = {}

    imports, symbols = _extract_symbols(source, patterns)
    structure = _build_structure(source, language)
    compressed_lines = len(imports) + len(symbols) + structure.count("\n") + 1

    return CodeMap(
        file_path=file_path,
        language=language,
        imports=imports,
        symbols=symbols,
        structure=structure,
        original_lines=original_lines,
        compressed_lines=compressed_lines,
    )


def compress_for_prompt(file_path: str, source: str, max_lines: int = 300) -> str:
    lines = source.splitlines()
    if len(lines) <= max_lines:
        return source

    code_map = build_code_map(file_path)

    parts = [
        f"[compressed code map — {code_map.original_lines} lines, {code_map.ratio:.0%} reduction]\n",
        "IMPORTS:",
        *code_map.imports,
        "",
        "SYMBOLS:",
        *code_map.symbols,
        "",
        "STRUCTURE:",
        code_map.structure,
    ]

    return "\n".join(parts)
