# Benchmarking Large Language Models for Automated Code Security Analysis

**Yevhenii Boiko**
AvixoSec | contact@avixosec.xyz
https://github.com/AvixoSec/codesight

April 2026

## Abstract

Static analysis tools match patterns and miss logic bugs. This paper presents CodeSight, an open-source CLI that sends code to LLMs and gets back security findings. We tested five models (GPT-5.4, Claude Opus 4.7, Gemini 3.1 Pro, Llama 4 Maverick, DeepSeek V3.2) on three known-vulnerable codebases and compared detection rates with Semgrep. LLMs found roughly twice as many vulnerabilities as pattern matching, with the biggest gains in auth bypasses and business logic bugs. CodeSight is MIT licensed: https://github.com/AvixoSec/codesight.

## 1. Introduction

Most open-source code never gets a security audit. The reason is simple: good tools cost money. Snyk Code and Checkmarx run $500-2000/month per seat. Semgrep and Bandit are free but they only match patterns. They'll catch `SELECT * FROM users WHERE id = ' + input` but they won't catch "this auth check runs but the result is never used".

LLMs can actually read code. They understand control flow, they follow data through functions, they notice when a permission check doesn't do anything. The question is: how well do they actually work for security analysis, and which model is best at it?

We built CodeSight to answer that. It's a CLI that:
- Breaks code into chunks that fit a model's context window
- Sends each chunk to whatever LLM you want
- Collects findings, deduplicates them, spits out a report
- Works with GPT-5.4, Claude Opus 4.7, Gemini 3.1, Llama 4, DeepSeek, or anything via Ollama

This paper covers how it works, what we found when we ran five models against three vulnerable codebases, and how that compares to Semgrep.

## 2. Related Work

**Pattern matchers.** Semgrep, Bandit, ESLint security plugins. They match known bad patterns in ASTs. Low false positive rate, but they literally cannot find anything they don't have a rule for. Zero detection on logic bugs.

**Commercial tools.** Snyk Code, Checkmarx, GitHub Advanced Security. They use ML models trained on vulnerability data. They work, but they're closed source, expensive, and vendor-locked.

**LLM research.** Thapa et al. (2024) tested GPT-4 on vulnerability detection and got mixed results depending on CWE category. But they used synthetic benchmarks, not real codebases, and didn't release a usable tool.

## 3. Architecture

CodeSight is a Python CLI. You run `codesight scan --task security` on a directory and get a report. Under the hood:

**3.1 File Collection.** Walk the directory, skip .gitignore'd files, filter by extension. Supports Python, JS, TS, Go, Rust, Java, C/C++, Solidity, PHP, and more.

**3.2 Chunking.** Big files get split so they fit in the model's context window. The splitter keeps functions and classes intact so the model sees complete units of code, not random slices.

**3.3 LLM Analysis.** Each chunk goes to the model with a security-focused prompt. The prompt tells the model to look for injection, auth bypass, crypto issues, race conditions, info leaks, and logic bugs. The model returns structured findings with severity, CWE ID, line numbers, and a fix.

**3.4 Report.** Findings from all chunks get collected, deduplicated, and formatted. Terminal output (with colors), JSON, or Markdown.

The provider system is pluggable. One class with a `complete()` method. Currently: OpenAI (GPT-5.4, Codex), Anthropic (Claude Opus 4.7, Sonnet 4.6, Haiku 4.5), Google (Gemini 3.1 Pro, Gemini 3 Deep Think), and local models through Ollama (Llama 4 Maverick, Qwen 3.6, DeepSeek V3.2, Mistral Small 4).

## 4. Preliminary Evaluation

### 4.1 Test Corpora

Three intentionally vulnerable apps:
- **OWASP Juice Shop** (TypeScript/Node.js) - fake e-commerce store with 100+ known vulns
- **DVWA** (PHP) - classic vulnerable web app used for training
- **WebGoat** (Java) - OWASP's teaching platform with categorized vulnerabilities

### 4.2 Models Evaluated

| Model | Provider | Context Window | Cost per 1M tokens |
|-------|----------|---------------|-------------------|
| GPT-5.4 | OpenAI | 1M (922K in / 128K out) | $1.25 input / $10 output |
| Claude Opus 4.7 | Anthropic | 1M | $5 input / $25 output |
| Gemini 3.1 Pro | Google | 1M | $1.25 input / $10 output |
| Llama 4 Maverick | Local (Ollama) | 1M | Free |
| DeepSeek V3.2 | Local (Ollama) | 128K | Free |

### 4.3 Methodology

We scanned each corpus with each model using CodeSight's default security prompt. We tracked:
- True positives (TP): real vulns the model found
- False positives (FP): things the model flagged that aren't actually vulns
- False negatives (FN): real vulns the model missed
- Time and cost per scan

### 4.4 Preliminary Results

Results on OWASP Juice Shop (100+ known vulns):

| Model | TP | FP | FN | Precision | Recall | Cost |
|-------|-----|-----|-----|-----------|--------|------|
| GPT-5.4 | 86 | 6 | 19 | 0.93 | 0.82 | $3.40 |
| Claude Opus 4.7 | 89 | 4 | 16 | 0.96 | 0.85 | $8.20 |
| Gemini 3.1 Pro | 82 | 8 | 23 | 0.91 | 0.78 | $3.50 |
| Llama 4 Maverick | 64 | 13 | 41 | 0.83 | 0.61 | Free |
| DeepSeek V3.2 | 62 | 12 | 43 | 0.84 | 0.59 | Free |

What stands out:
- Claude Opus 4.7 has the best precision and recall. 96% precision, catches 85% of known vulns.
- GPT-5.4 is the best value at this tier. Within a few points of Opus 4.7 at less than half the price.
- Gemini 3.1 Pro is competitive. Google finally shipped something on par with the top models.
- Llama 4 Maverick catches 61% of vulns for free. Huge jump from Llama 3.
- DeepSeek V3.2 is basically tied with Llama 4. Great for self-hosting.
- Race conditions and TOCTOU are still hard for every model, even Opus 4.7.

### 4.5 Comparison with Pattern-Based Tools

Running Semgrep with default rules on the same Juice Shop corpus:

| Tool | TP | FP | FN | Precision | Recall |
|------|-----|-----|-----|-----------|--------|
| Semgrep (default) | 31 | 3 | 74 | 0.91 | 0.30 |
| Bandit (Python only) | N/A | N/A | N/A | N/A | N/A |
| CodeSight + GPT-5.4 | 86 | 6 | 19 | 0.93 | 0.82 |
| CodeSight + Claude Opus 4.7 | 89 | 4 | 16 | 0.96 | 0.85 |

Semgrep has great precision but terrible recall. It finds what it has rules for and nothing else. The LLM-based approach finds roughly twice as many real vulns, with a few more false positives.

## 5. Vulnerability Classes

Analysis of true positives by CWE category:

| CWE Category | GPT-5.4 | Opus 4.7 | Semgrep |
|--------------|---------|----------|--------|
| CWE-89 SQL Injection | 14/14 | 14/14 | 10/14 |
| CWE-79 XSS | 11/11 | 11/11 | 8/11 |
| CWE-287 Auth Bypass | 10/10 | 10/10 | 2/10 |
| CWE-362 Race Condition | 5/7 | 6/7 | 0/7 |
| CWE-200 Info Disclosure | 8/8 | 8/8 | 3/8 |
| CWE-840 Business Logic | 8/9 | 9/9 | 0/9 |

The biggest gap is in auth bypasses and business logic. Semgrep gets 2/10 auth bypasses and 0/9 logic bugs. Claude Opus 4.7 gets 10/10 and 9/9. Pattern matching can't reason about what code is supposed to do.

## 6. Limitations

- These are intentionally vulnerable apps. Real codebases will have different detection rates.
- LLMs are non-deterministic. Two scans of the same code can give slightly different results.
- Cost goes up linearly with code size. A 100K line project costs $10-20 per full scan.
- If a vulnerability spans multiple files and those files end up in different chunks, the model might miss it.
- We haven't tested on real production codebases with unknown vulnerabilities yet. That's next.

## 7. What's Next

- Test on 10+ real open-source projects, not just training apps
- Multi-model setup: one model finds bugs, a second one verifies them
- Diff-based scanning for CI/CD: only scan the code that changed in a PR
- Fine-tune Llama 4 or DeepSeek on security data to close the gap with paid models
- Find and disclose real CVEs using CodeSight
- Figure out the cheapest model combination that still catches most bugs

## 8. Conclusion

LLMs find security bugs that pattern matchers miss. That's the short version. Claude Opus 4.7 and GPT-5.4 roughly 2.5-3x the detection rate compared to Semgrep, and the difference is biggest in the categories that matter most: auth bypasses and business logic. Free models like Llama 4 and DeepSeek still beat pattern matching, just not by as much.

CodeSight is open source. Pick a model, point it at your code, get a security report. No accounts, no SaaS, no vendor lock-in.

Code and data: https://github.com/AvixoSec/codesight (MIT license).

## References

1. OWASP Foundation. OWASP Top 10:2021. https://owasp.org/Top10/
2. Verizon. 2024 Data Breach Investigations Report.
3. Semgrep. https://semgrep.dev/
4. Thapa, C. et al. (2024). Can LLMs Find Vulnerabilities? A Systematic Evaluation.
5. OWASP Juice Shop. https://owasp.org/www-project-juice-shop/
6. Meta AI. Llama 4 Maverick. https://llama.meta.com/
7. OpenAI. GPT-5.4. https://openai.com/index/introducing-gpt-5-4/
8. Anthropic. Claude Opus 4.7. https://anthropic.com/news/claude-opus-4-7
9. Google DeepMind. Gemini 3.1 Pro. https://blog.google/products-and-platforms/products/gemini/gemini-3/
10. DeepSeek. DeepSeek V3.2. https://deepseek.com/
