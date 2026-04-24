# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.3.x   | Yes       |

## Reporting a Vulnerability

If you find a security vulnerability in CodeSight, **do not open a public issue**.

Email us at **AvixoSec@gmail.com** with:

- Description of the vulnerability
- Steps to reproduce
- Impact assessment
- Suggested fix (if any)

We'll respond within 48 hours and work on a fix before any public disclosure.

## Scope

CodeSight is a **defensive** security tool. It analyzes code for vulnerabilities but does not:
- Execute untrusted code
- Exfiltrate data
- Provide offensive capabilities

API keys are stored locally in `~/.codesight/config.json` and are never transmitted to any server other than the configured LLM provider.
