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


# All quantifiers bounded to avoid catastrophic backtracking.
_W = r"\w{1,200}"
_PAREN = r"[^)]{0,1000}"
_NOTCURLY = r"[^{]{0,500}"
_NOTCOLON = r"[^:]{0,500}"

LANG_PATTERNS = {
    "py": {
        "class": re.compile(rf"^(class\s{{1,10}}{_W}{_NOTCOLON}:)", re.MULTILINE),
        "function": re.compile(
            rf"^((?:async\s{{1,5}})?def\s{{1,5}}{_W}\s{{0,5}}\({_PAREN}\){_NOTCOLON}:)",
            re.MULTILINE,
        ),
        "import": re.compile(
            r"^((?:from\s{1,5}\S{1,300}\s{1,5})?import\s{1,5}.{1,500})$",
            re.MULTILINE,
        ),
        "decorator": re.compile(
            rf"^(@{_W}(?:\.{_W}){{0,10}}(?:\({_PAREN}\))?)",
            re.MULTILINE,
        ),
        "docstring_start": re.compile(
            r'^\s{0,20}(""".{0,2000}?"""|\'\'\'.{0,2000}?\'\'\')',
            re.MULTILINE | re.DOTALL,
        ),
    },
    "js": {
        "class": re.compile(rf"^((?:export\s{{1,5}})?class\s{{1,5}}{_W}{_NOTCURLY})", re.MULTILINE),
        "function": re.compile(
            rf"^((?:export\s{{1,5}})?(?:async\s{{1,5}})?function\s{{1,5}}{_W}\s{{0,5}}\({_PAREN}\))",
            re.MULTILINE,
        ),
        "arrow": re.compile(
            rf"^((?:export\s{{1,5}})?(?:const|let|var)\s{{1,5}}{_W}\s{{0,5}}=\s{{0,5}}(?:async\s{{1,5}})?\({_PAREN}\)\s{{0,5}}=>)",
            re.MULTILINE,
        ),
        "import": re.compile(r"^(import\s{1,5}.{1,500})$", re.MULTILINE),
    },
    "ts": None,
    "go": {
        "function": re.compile(
            rf"^(func\s{{1,5}}(?:\({_PAREN}\)\s{{1,5}})?{_W}\s{{0,5}}\({_PAREN}\){_NOTCURLY})",
            re.MULTILINE,
        ),
        "struct": re.compile(rf"^(type\s{{1,5}}{_W}\s{{1,5}}struct\s{{0,5}}\{{)", re.MULTILINE),
        "interface": re.compile(
            rf"^(type\s{{1,5}}{_W}\s{{1,5}}interface\s{{0,5}}\{{)",
            re.MULTILINE,
        ),
        "import": re.compile(r"^(import\s{1,5}.{1,500})$", re.MULTILINE),
    },
    "rs": {
        "function": re.compile(
            rf"^((?:pub\s{{1,5}})?(?:async\s{{1,5}})?fn\s{{1,5}}{_W}{_NOTCURLY})",
            re.MULTILINE,
        ),
        "struct": re.compile(rf"^((?:pub\s{{1,5}})?struct\s{{1,5}}{_W}{_NOTCURLY})", re.MULTILINE),
        "impl": re.compile(rf"^(impl(?:<[^>]{{0,200}}>)?\s{{1,5}}{_W}{_NOTCURLY})", re.MULTILINE),
        "import": re.compile(r"^(use\s{1,5}.{1,500};)$", re.MULTILINE),
    },
    "java": {
        "class": re.compile(
            rf"^((?:public|private|protected)?\s{{0,5}}(?:static\s{{1,5}})?(?:abstract\s{{1,5}})?class\s{{1,5}}{_W}{_NOTCURLY})",
            re.MULTILINE,
        ),
        "method": re.compile(
            rf"^\s{{0,20}}((?:public|private|protected)\s{{1,5}}(?:static\s{{1,5}})?[\w<>\[\]]{{1,200}}\s{{1,5}}{_W}\s{{0,5}}\({_PAREN}\))",
            re.MULTILINE,
        ),
        "import": re.compile(r"^(import\s{1,5}.{1,500};)$", re.MULTILINE),
    },
}

LANG_PATTERNS["ts"] = LANG_PATTERNS["js"]
LANG_PATTERNS["jsx"] = LANG_PATTERNS["js"]
LANG_PATTERNS["tsx"] = LANG_PATTERNS["js"]
LANG_PATTERNS["kt"] = LANG_PATTERNS["java"]
LANG_PATTERNS["sol"] = {
    "class": re.compile(
        rf"^((?:abstract\s{{1,5}})?contract\s{{1,5}}{_W}{_NOTCURLY})", re.MULTILINE
    ),
    "interface": re.compile(
        rf"^((?:interface|library)\s{{1,5}}{_W}{_NOTCURLY})", re.MULTILINE
    ),
    "function": re.compile(
        rf"^\s{{0,20}}(function\s{{1,5}}{_W}\s{{0,5}}\({_PAREN}\)[^{{;]{{0,500}})", re.MULTILINE
    ),
    "import": re.compile(r"^(import\s{1,5}.{1,500};)$", re.MULTILINE),
    "struct": re.compile(rf"^\s{{0,20}}(struct\s{{1,5}}{_W}\s{{0,5}}\{{)", re.MULTILINE),
    "method": re.compile(
        rf"^\s{{0,20}}(modifier\s{{1,5}}{_W}\s{{0,5}}\({_PAREN}\))", re.MULTILINE
    ),
}


EXT_TO_LANG = {
    ".py": "py", ".js": "js", ".ts": "ts", ".jsx": "jsx", ".tsx": "tsx",
    ".go": "go", ".rs": "rs", ".java": "java", ".kt": "kt",
    ".sol": "sol", ".vy": "vy",
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


_SIG_STARTS: dict[str, tuple[str, ...]] = {
    "py": ("class ", "def ", "async def ", "@"),
    "js": ("class ", "function ", "async function ", "export ", "const ", "let ", "import "),
    "go": ("func ", "type ", "import "),
    "rs": ("fn ", "pub fn ", "pub async fn ", "struct ", "pub struct ", "impl ", "use "),
    "java": ("public ", "private ", "protected ", "class ", "import ", "interface "),
    "sol": (
        "contract ", "abstract contract ", "interface ", "library ",
        "function ", "modifier ", "struct ", "enum ", "event ",
        "mapping", "import ", "pragma ",
    ),
}
_SIG_STARTS["ts"] = _SIG_STARTS["js"]
_SIG_STARTS["jsx"] = _SIG_STARTS["js"]
_SIG_STARTS["tsx"] = _SIG_STARTS["js"]
_SIG_STARTS["kt"] = _SIG_STARTS["java"]


def _build_structure(source: str, language: str) -> str:
    starts = _SIG_STARTS.get(language)
    if not starts:
        return ""
    lines = source.splitlines()
    structure_lines: list[str] = []
    for line_no, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("//"):
            continue
        if not stripped.startswith(starts):
            continue
        indent = len(line) - len(line.lstrip(" \t"))
        depth = indent // 4 if indent >= 0 else 0
        depth = min(depth, 12)  # bound nesting to avoid silly output on tab-abuse files
        structure_lines.append(f"  {'  ' * depth}L{line_no}: {stripped}")
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
        f"[compressed code map - {code_map.original_lines} lines, "
        f"{code_map.ratio:.0%} reduction]\n",
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
