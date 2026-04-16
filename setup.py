from setuptools import setup, find_packages
from pathlib import Path

long_description = (Path(__file__).parent / "README.md").read_text(encoding="utf-8")

setup(
    name="codesight",
    version="0.1.0",
    description="AI-powered code analysis and review tool",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="AvixoSec",
    url="https://github.com/AvixoSec/codesight",
    license="MIT",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "httpx>=0.27",
        "anthropic>=0.40",
        "google-auth>=2.29",
    ],
    extras_require={
        "dev": ["pytest", "pytest-asyncio", "ruff", "mypy"],
    },
    entry_points={
        "console_scripts": [
            "codesight=codesight.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Quality Assurance",
    ],
)
