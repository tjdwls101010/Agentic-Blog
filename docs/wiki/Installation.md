# Installation

Agentic Blog 0.1.0 is a read-only client for publicly available Naver Blog
content. It needs Python 3.11 or newer and network access to Naver. It does
not require an account, API key, cookie file, browser, or setup command.

This page covers source and built-artifact installation. It does **not** claim
that the package is published on PyPI.

## Install from source

Clone or otherwise obtain the 0.1.0 source tree, then install it with pip:

```bash
python -m pip install .
```

For an isolated installation, create and activate a Python 3.11+ virtual
environment before running that command.

## Install a built artifact

When a wheel or source distribution has been built from this project, install
the local artifact path instead:

```bash
python -m pip install /path/to/agentic_blog-0.1.0-py3-none-any.whl
```

The installed distribution provides the `agentic-blog` command. The same CLI
is available as `python -m agentic_blog`.

## Confirm the installation

These offline commands confirm the installed version and expose the live CLI
surface without making a network request:

```bash
agentic-blog --version
agentic-blog catalog
agentic-blog schema --json
```

`catalog` prints a machine-readable list of commands and arguments. `schema
--json` prints the generated JSON Schema for result objects.

Continue with [Quick Start](Quick-Start.md) for an anonymous public-content
read, or see [Configuration](Configuration.md) for storage and runtime
limits.
