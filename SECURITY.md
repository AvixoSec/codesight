# Security Policy

## Supported Versions

- `0.3.x`: supported

## Reporting a Vulnerability

If you find a security vulnerability in CodeSight, **do not open a public issue**.

Use a private GitHub security advisory:

https://github.com/AvixoSec/codesight/security/advisories/new

Include:

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
