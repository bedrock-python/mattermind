# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | ✅        |

## Reporting a vulnerability

**Please do not report security vulnerabilities via public GitHub Issues.**

Send a report to **shalaevad.alexey@gmail.com** with:

- Description of the vulnerability
- Steps to reproduce
- Potential impact and affected versions

We aim to acknowledge reports within **48 hours** and provide a fix within **7 days**
for critical issues.

Once the fix is released, we will credit you in the release notes unless you prefer
to remain anonymous.

## Secrets handling

mattermind never writes tokens or API keys to disk or logs. In `--verbose` mode,
tokens are masked (`mm_to***`). If you find a case where secrets leak, please
report it immediately.
