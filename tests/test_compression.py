from codesight.compression import CodeMap, build_code_map, compress_for_prompt


def test_code_map_ratio():
    cm = CodeMap("f.py", "py", [], [], "", original_lines=100, compressed_lines=30)
    assert cm.ratio == 0.7


def test_code_map_ratio_zero():
    cm = CodeMap("f.py", "py", [], [], "", original_lines=0, compressed_lines=0)
    assert cm.ratio == 0.0


def test_build_code_map_python(tmp_path):
    f = tmp_path / "sample.py"
    f.write_text(
        "import os\n"
        "from pathlib import Path\n"
        "\n"
        "class Foo:\n"
        "    def bar(self):\n"
        "        pass\n"
        "\n"
        "def baz(x):\n"
        "    return x + 1\n"
    )
    cm = build_code_map(str(f))
    assert cm.language == "py"
    assert "import os" in cm.imports
    assert any("class Foo" in s for s in cm.symbols)
    assert any("def baz" in s for s in cm.symbols)
    assert cm.original_lines == 9


def test_build_code_map_js(tmp_path):
    f = tmp_path / "app.js"
    f.write_text(
        "import React from 'react';\n"
        "\n"
        "export function App() {\n"
        "  return null;\n"
        "}\n"
    )
    cm = build_code_map(str(f))
    assert cm.language == "js"
    assert any("import" in i for i in cm.imports)
    assert any("function App" in s for s in cm.symbols)


def test_compress_short_file_unchanged(tmp_path):
    f = tmp_path / "small.py"
    source = "x = 1\ny = 2\n"
    f.write_text(source)
    result = compress_for_prompt(str(f), source, max_lines=300)
    assert result == source


def test_compress_large_file_produces_map(tmp_path):
    f = tmp_path / "big.py"
    lines = ["import os\n", "def foo():\n", "    pass\n"]
    lines += [f"    x_{i} = {i}\n" for i in range(400)]
    source = "".join(lines)
    f.write_text(source)
    result = compress_for_prompt(str(f), source, max_lines=50)
    assert "compressed code map" in result
    assert "IMPORTS:" in result
    assert "SYMBOLS:" in result
    assert "STRUCTURE:" in result


def test_build_code_map_unknown_ext(tmp_path):
    f = tmp_path / "data.txt"
    f.write_text("hello world\n")
    cm = build_code_map(str(f))
    assert cm.language == "txt"
    assert cm.imports == []
    assert cm.symbols == []
