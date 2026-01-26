## 🦑 hy-fancy-repl

*A [Hy](https://hylang.org) enhanced REPL.*

Probably compatible with Hy 1.2.0 and later.


### Install

```bash
$ pip install -U hy-fancy-repl
```


### The REPL

The REPL implements multi-line editing, completion, live input validation, live
syntax highlighting, and interactive matplotlib plots.

```bash
$ hy-repl
```

or

```bash
$ hy-fancy-repl
```


The behaviour of the repl may be modified with the following environment
variables.

- `HY_HISTORY`: Path to a file for storing command history. Defaults to `~/.hy-history`.
- `HY_LIVE_COMPLETION`: If set, enables live/interactive autocompletion in a dropdown menu as you type. Defaults to off.
- `HY_PYGMENTS_STYLE`: The name of a pygments style to use for highlighting. Defaults to `lightbulb`.
- `HY_VI_MODE`: If set, enable vi line-editing mode (rather than the default emacs mode).


### Acknowledgements

The REPL uses [pygments](https://pygments.org/) and [prompt-toolkit](https://python-prompt-toolkit.readthedocs.io/).
Plus, of course, [Hy](https://hylang.org), whose REPL `hy-fancy-repl` extends.


### Docs

Try clicking below.

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/atisharma/hy-fancy-repl)
