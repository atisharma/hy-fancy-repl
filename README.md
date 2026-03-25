## 🦑 hy-fancy-repl

*A [Hy](https://hylang.org) enhanced REPL.*

Compatible with Hy 1.2.0 and later.


### Install

```bash
$ pip install -U hy-fancy-repl
```


### The REPL

The REPL implements multi-line editing, completion, live input validation, live
syntax highlighting, bracket matching, enhanced tracebacks, and interactive
matplotlib plots.

```bash
$ hy-repl
```

or

```bash
$ hy-fancy-repl
```


### Features

- **Multi-line editing** with smart indentation
- **Syntax highlighting** via Pygments
- **Bracket matching** that ignores brackets inside strings and comments
- **Tab completion** with Hy's native completer
- **Live validation** - shows a red 'x' when parentheses are unbalanced
- **Enhanced tracebacks** - shows syntax-highlighted source snippets
- **Interactive matplotlib** - async plot updates when available
- **History persistence** - saved to `~/.hy-history` by default


### Environment Variables

The REPL's behaviour may be modified with the following environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `HY_HISTORY` | Path to command history file | `~/.hy-history` |
| `HY_LIVE_COMPLETION` | Enable live autocompletion dropdown | unset (off) |
| `HY_PYGMENTS_STYLE` | Pygments style for highlighting | `lightbulb` |
| `HY_VI_MODE` | Enable vi line-editing mode | unset (emacs) |
| `HY_TRACEBACK_IGNORE` | Comma-separated list of files to hide in tracebacks | sensible defaults |


### Traceback Filtering

By default, the REPL hides infrastructure files in tracebacks to show your code.
The default ignore list includes Hy internals, funcparserlib, and multimethod.

Override with `HY_TRACEBACK_IGNORE`:
```bash
$ HY_TRACEBACK_IGNORE="hy/repl.py,code.py" hy-fancy-repl
```

Or modify at runtime:
```python
from hy_fancy_repl.repl import TRACEBACK_IGNORE
# TRACEBACK_IGNORE is a tuple of file path suffixes to ignore
```


### Acknowledgements

The REPL uses [pygments](https://pygments.org/), [prompt-toolkit](https://python-prompt-toolkit.readthedocs.io/),
[colorist](https://jakob-bagterp.github.io/colorist-for-python/), and [Hy](https://hylang.org).


### Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and contribution guidelines.


### Docs

Try clicking below.

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/atisharma/hy-fancy-repl)
