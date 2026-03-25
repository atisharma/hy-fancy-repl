"""
A fancy REPL for Hy.

This module provides a feature-rich interactive console for Hy by
extending ``hy.repl.REPL`` with ``prompt_toolkit`` and ``pygments``.
It offers a significantly improved user experience over the standard
REPL with syntax highlighting for input, output, and context-aware
tracebacks that show the relevant source code.

It also offers context-aware tab completion, integrating the native
Hy REPL's completer with ``prompt_toolkit``.

The primary public class is :class:`HyREPL`, which can be instantiated and
used to start a custom interactive session.

.. rubric:: Environment Variables

The REPL's behavior can be configured with the following environment variables:

- ``HY_HISTORY``: Path to a file for storing command history. Defaults to
  ``~/.hy-history``.
- ``HY_PYGMENTS_STYLE``: The name of a pygments style to use for
  highlighting. Defaults to ``friendly``.
- ``HY_LIVE_COMPLETION``: If set, enables live/interactive autocompletion
  in a dropdown menu as you type.
- ``HY_VI_MODE``: If set, enables vi mode in the REPL (default is emacs).

.. rubric:: Example

.. code-block:: bash

    $ hyrepl

.. code-block:: python

    from hy_fancy_repl.repl import HyREPL

    # Create and start the REPL
    repl = HyREPL()
    repl.run()

"""

import asyncio
import builtins
import os
import platform
import re
import sys
import traceback
from types import TracebackType
from typing import Any, Generator, Iterable, Optional, Tuple, Type

from hy import mangle, repr as hy_repr, completer as hy_completer
import hy.repl

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion, CompleteEvent
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import FormattedText, ANSI
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.lexers import PygmentsLexer
from prompt_toolkit.layout.processors import Processor, Transformation, TransformationInput
from prompt_toolkit.application.current import get_app
from prompt_toolkit.styles import style_from_pygments_cls, Style as PTStyle, merge_styles
from prompt_toolkit.patch_stdout import patch_stdout

from pygments import highlight, lex
from pygments.formatters import TerminalFormatter
from pygments.lexers import HyLexer, PythonTracebackLexer, get_lexer_by_name
from pygments.styles import get_style_by_name, get_all_styles
from pygments.token import Token

from beautifhy.highlight import hylight
from colorist import Effect

try:
    import matplotlib.pyplot as pyplot
    import matplotlib._pylab_helpers as mpl_helpers

    HAS_MPL = True
except ModuleNotFoundError:
    HAS_MPL = False


# --- REPL history, persisted in a file --- #

history_file = os.environ.get("HY_HISTORY", os.path.expanduser("~/.hy-history"))
history = FileHistory(history_file)


# --- REPL syntax highlighting and completion --- #

# Read environment variable for theme
style_name = os.environ.get("HY_PYGMENTS_STYLE", "lightbulb")
bg = "dark"  # default, usually fine
if ":" in style_name:
    style_name, bg = style_name.split(":", 1)
if style_name not in get_all_styles():
    style_name = "lightbulb"  # fallback

# Convert pygments style to prompt_toolkit style and add matching-bracket style
pygments_style = style_from_pygments_cls(get_style_by_name(style_name))
pt_style = merge_styles([
    pygments_style,
    PTStyle.from_dict({
        'matching-bracket': 'bg:#888888 #ffffff bold',
    })
])


class HyCompleter(Completer):
    """
    Wrap prompt_toolkit's completion API around Hy's.
    """

    def __init__(self, namespace: Optional[dict[str, Any]] = None) -> None:
        self.namespace: dict[str, Any] = namespace or {}
        self.c = hy_completer.Completer(self.namespace)
        # Hy symbols may not use these chars (or ., but we keep that for attrs)
        self._pattern = re.compile(r"[^()\[\]{}\"';`,~\\#\s]+")

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Generator[Completion, None, None]:
        # Update namespace reference as it may have changed
        self.c.namespace = self.namespace
        fragment = document.get_word_before_cursor(pattern=self._pattern)
        state = 0
        while True:
            match = self.c.complete(fragment, state)
            if match is None:
                break
            yield Completion(match, start_position=-len(fragment))
            state += 1


# --- REPL traceback handling and highlighting --- #

ExcInfo = Tuple[Type[BaseException], BaseException, TracebackType]


def _set_last_exc(exc_info: Optional[ExcInfo] = None) -> ExcInfo:
    """
    Setting `sys.last_exc`, or `sys.last_type` on earlier Pythons,
    makes it easier for the user to call the debugger.
    """
    # this is from the standard Hy REPL
    t, v, tb = exc_info or sys.exc_info()
    sys.last_type, sys.last_value, sys.last_traceback = t, v, tb
    return t, v, tb


def _get_lang_from_filename(filename: str) -> Optional[str]:
    """
    Guess the language from the filename extension.
    """
    ext = os.path.splitext(filename)[1][1:]  # Remove the leading dot
    match ext:
        case "py":
            return "python"
        case "hy":
            return "hylang"
        case "pytb":
            return "pytb"
        case "py3tb":
            return "py3tb"
        case _:
            return None


def _read_file(filename: str) -> str:
    """Read the contents of a file."""
    with open(filename, "r", encoding="utf-8") as f:
        return f.read()


def _output_traceback(
    exc_type: Type[BaseException],
    exc_value: BaseException,
    tb: TracebackType,
    *,
    bg: str = bg,
    limit: int = 5,
    lines_around: int = 2,
    linenos: bool = True,
    ignore: Iterable[str] = (),
) -> int:
    """
    Syntax highlighted traceback.
    """
    _tb = tb
    lang: Optional[str] = None
    filename = ""
    while _tb:
        filename = _tb.tb_frame.f_code.co_filename
        lang = _get_lang_from_filename(filename)
        if lang and not any(filename.endswith(suffix) for suffix in ignore):
            try:
                source = _read_file(filename)
            except (IOError, OSError):
                _tb = _tb.tb_next
                continue
            lineno = _tb.tb_lineno
            lines = source.split("\n")[
                max(0, lineno - lines_around) : lineno + lines_around
            ]
            code_lexer = get_lexer_by_name(lang)
            code_formatter = TerminalFormatter(bg=bg, stripall=True, linenos=linenos)
            code_formatter._lineno = lineno - lines_around
            sys.stderr.write(f"  File {Effect.BOLD}{filename}{Effect.OFF}, line {lineno}\n")
            sys.stderr.write(highlight("\n".join(lines), code_lexer, code_formatter))
            sys.stderr.write("\n")
            break
        else:
            _tb = _tb.tb_next
    fexc = traceback.format_exception(exc_type, exc_value, tb, limit=limit)
    exc_formatter = TerminalFormatter(bg=bg, stripall=True)
    return sys.stderr.write(
        highlight("".join(fexc), PythonTracebackLexer(), exc_formatter)
    )


# --- Multiline input --- #


def _indent_depths(text: str) -> list[int]:
    """
    Calculate indentation for the next line, counting parens using HyLexer.
    Returns [parens, brackets, braces] depths.
    """
    tokens = list(lex(text, HyLexer()))
    depths = [0, 0, 0]  # parens, brackets, braces
    for ttype, val in tokens:
        # Ignore strings/comments
        if ttype in Token.Literal.String or ttype in Token.Comment:
            continue
        # Increase/decrease depth for parens/brackets/braces
        depths[0] += val.count("(")
        depths[0] -= val.count(")")
        depths[1] += val.count("[")
        depths[1] -= val.count("]")
        depths[2] += val.count("{")
        depths[2] -= val.count("}")
    return depths


# --- Bracket matching that respects Hy syntax (ignores strings/comments) --- #

_BRACKETS = {"(": ")", "[": "]", "{": "}", ")": "(", "]": "[", "}": "{"}
_CLOSING = ")]}"


def _find_matching_bracket(text: str, pos: int, max_distance: int = 1000) -> int | None:
    """Find the matching bracket position, respecting Hy syntax (ignoring strings/comments)."""
    char = text[pos]
    if char not in _BRACKETS:
        return None

    target = _BRACKETS[char]
    is_closing = char in _CLOSING

    # Tokenize and track positions
    tokens = list(lex(text, HyLexer()))

    # Build list of (position, char, is_in_string_or_comment)
    bracket_positions = []
    current_pos = 0
    for ttype, val in tokens:
        val_len = len(val)
        is_special = ttype in Token.Literal.String or ttype in Token.Comment
        for i, c in enumerate(val):
            if c in _BRACKETS:
                bracket_positions.append((current_pos + i, c, is_special))
        current_pos += val_len

    # Find our position in the list
    try:
        idx = next(i for i, (p, c, _) in enumerate(bracket_positions) if p == pos and c == char)
    except StopIteration:
        return None

    # Count brackets to find match
    depth = 1
    step = -1 if is_closing else 1
    i = idx + step

    while 0 <= i < len(bracket_positions) and abs(bracket_positions[i][0] - pos) <= max_distance:
        _, c, is_special = bracket_positions[i]
        if is_special:
            i += step
            continue
        if c == char:
            depth += 1
        elif c == target:
            depth -= 1
            if depth == 0:
                return bracket_positions[i][0]
        i += step

    return None


class HyMatchingBracketProcessor(Processor):
    """
    Highlight matching brackets, but ignore brackets inside strings and comments.
    """

    def __init__(self, max_distance: int = 1000) -> None:
        self.max_distance = max_distance

    def apply_transformation(self, transformation_input: TransformationInput) -> Transformation:
        buffer_control, document, lineno, source_to_display, fragments, _, _ = transformation_input.unpack()

        # Don't highlight when application is done
        if get_app().is_done:
            return Transformation(fragments)

        # Check if cursor is on a bracket
        cursor_pos = document.cursor_position
        
        # Check character under cursor, or before cursor if at end
        if cursor_pos >= len(document.text):
            if cursor_pos > 0 and document.text[cursor_pos - 1] in _CLOSING:
                cursor_pos -= 1
            else:
                return Transformation(fragments)
        
        char = document.text[cursor_pos]
        if char not in _BRACKETS:
            return Transformation(fragments)

        # Find matching bracket
        match_pos = _find_matching_bracket(document.text, cursor_pos, self.max_distance)
        if match_pos is None:
            return Transformation(fragments)

        # Get positions for this line
        line_start = document.translate_row_col_to_index(lineno, 0)
        line_end = document.translate_row_col_to_index(lineno, len(document.lines[lineno]))
        
        # Determine which positions to highlight on this line
        positions_to_highlight = set()
        
        # Cursor position
        if line_start <= cursor_pos < line_end:
            positions_to_highlight.add(cursor_pos - line_start)
        
        # Match position (if on same line)
        if line_start <= match_pos < line_end:
            positions_to_highlight.add(match_pos - line_start)
        
        if not positions_to_highlight:
            return Transformation(fragments)

        # Build new fragments with highlights
        new_fragments = []
        source_col = 0
        
        for style, text_val, *rest in fragments:
            display_col = source_to_display(source_col)
            text_len = len(text_val)
            
            # Check if any position to highlight falls within this fragment
            highlight_in_fragment = [p for p in positions_to_highlight 
                                     if display_col <= p < display_col + text_len]
            
            if not highlight_in_fragment:
                new_fragments.append((style, text_val, *rest))
            else:
                # Split fragment at highlight positions
                current_pos = display_col
                last_split = 0
                
                for highlight_pos in sorted(highlight_in_fragment):
                    # Text before highlight
                    before_end = highlight_pos - display_col
                    if before_end > last_split:
                        new_fragments.append((style, text_val[last_split:before_end], *rest))
                    
                    # The highlighted character
                    new_fragments.append((style + " class:matching-bracket", 
                                         text_val[before_end:before_end + 1], *rest))
                    
                    last_split = before_end + 1
                    current_pos = highlight_pos + 1
                
                # Remaining text after last highlight
                if last_split < text_len:
                    new_fragments.append((style, text_val[last_split:], *rest))
            
            source_col += text_len

        return Transformation(new_fragments)


# Key bindings: Enter accepts if complete, otherwise inserts newline.
kb = KeyBindings()


@kb.add("enter")
def _(event: KeyPressEvent) -> None:
    """
    Enter accepts if ([{}])s balance, otherwise inserts newline.
    """
    buf = event.app.current_buffer
    text = buf.document.text

    if any(_indent_depths(text)):
        # Insert newline + smart indentation
        indent = max(0, sum(_indent_depths(text))) * "  "
        buf.insert_text("\n" + indent)
    else:
        buf.validate_and_handle()


# --- The custom REPL --- #


class HyREPL(hy.repl.REPL):
    """
    A subclass of :class:`hy.repl.REPL`, which is itself a subclass of
    :class:`code.InteractiveConsole`, for Hy.

    This Hy REPL console that uses prompt_toolkit for input, instead of
    hy.REPL's builtin/readline `input` function.

    The REPL's behavior can be configured with the following environment variables:

    - ``HY_HISTORY``: Path to a file for storing command history. Defaults to
      ``~/.hy-history``.
    - ``HY_PYGMENTS_STYLE``: The name of a pygments style to use for
      highlighting. Defaults to ``friendly``.
    - ``HY_LIVE_COMPLETION``: If set, enables live/interactive autocompletion
      in a dropdown menu as you type.
    - ``HY_VI_MODE``: If set, enables vi mode in the REPL (default is emacs).
    """

    def __init__(
        self,
        locals: Optional[dict[str, Any]] = None,
        filename: str = "<stdin>",
        status: Optional[Any] = None,
    ) -> None:
        super().__init__(locals, filename)

        # default ps2 should be of same length as ps1
        self.ps2 = self.ps2[: len(self.ps1)]

        # Create the prompt session and store it in the instance
        self.session = PromptSession(
            lexer=PygmentsLexer(HyLexer),
            history=history,
            completer=HyCompleter(self.locals),
            complete_while_typing=bool(os.environ.get("HY_LIVE_COMPLETION")),
            vi_mode=bool(os.environ.get("HY_VI_MODE", False)),
            bottom_toolbar=status,
            rprompt=self._validation_text,
            key_bindings=kb,
            message=ANSI(self.ps1),
            prompt_continuation=ANSI(self.ps2),
            multiline=True,
            style=pt_style,
            input_processors=[HyMatchingBracketProcessor()],
        )

        # override repr, otherwise keep super's choice, set by HYSTARTUP
        if self.output_fn is hy_repr:
            self.output_fn = hylight

        if HAS_MPL:
            pyplot.ion()  # Enable interactive mode by default
            self.pyplot = pyplot
            self.locals["pyplot"] = (
                pyplot  # add pyplot instance to the REPL namespace too
            )
        else:
            self.pyplot = None

    async def get_input(self) -> str:
        """Override the default raw_input to use our prompt_toolkit session."""
        try:
            with patch_stdout():
                return await self.session.prompt_async()
        except EOFError:
            # Raise clean exit to base class's interact() loop
            raise SystemExit

    def _error_wrap(self, exc_info_override: bool = False, *args: Any, **kwargs: Any) -> None:
        """
        Wrap Hy errors with source resolution and syntax highlighting.
        """
        # When `exc_info_override` is true, use a traceback that
        # doesn't have the REPL frames.
        t, v, tb = _set_last_exc(exc_info_override and self.locals.get("_hy_exc_info"))
        if exc_info_override:
            sys.last_type = self.locals.get("_hy_last_type", t)
            sys.last_value = self.locals.get("_hy_last_value", v)
            sys.last_traceback = self.locals.get("_hy_last_traceback", tb)
        # Ignore REPL internals to show user's code
        _output_traceback(t, v, tb, ignore=("hy_fancy_repl/repl.py", "hy/repl.py", "code.py"))
        self.locals[mangle("*e")] = v

    def _validation_text(self) -> FormattedText:
        """Return a red 'x' if parentheses don't balance."""
        if any(_indent_depths(self.session.app.current_buffer.text)):
            return FormattedText([("class:red", "x")])
        else:
            return FormattedText()

    async def _update_plots(self) -> None:
        """
        Callback to update Matplotlib plots (or other supported GUI).
        """
        if not self.pyplot or not self.pyplot.isinteractive():
            return

        while True:
            await asyncio.sleep(0.01)
            try:
                for fig_manager in mpl_helpers.Gcf.get_all_fig_managers():
                    if fig_manager.canvas.figure.stale:
                        fig_manager.canvas.draw_idle()
                    fig_manager.canvas.flush_events()
            except Exception as e:
                sys.stderr.write(repr(e))

    def run(self) -> int:
        """Start running the REPL in the asyncio loop. Return 0 when done."""
        # When the user uses exit() or quit() in their interactive shell
        # they probably just want to exit the created shell, not the whole
        # process. exit and quit in builtins closes sys.stdin which makes
        # it super difficult to restore
        #
        # When self.local_exit is True, we overwrite the builtins so
        # exit() and quit() only raises SystemExit and we can catch that
        # to only exit the interactive shell

        sentinel: list[Any] = []
        saved_values = (
            getattr(sys, "ps1", sentinel),
            getattr(sys, "ps2", sentinel),
            builtins.quit,
            builtins.exit,
            builtins.help,
        )

        try:
            sys.ps1 = self.ps1
            sys.ps2 = self.ps2
            builtins.quit = hy.repl.HyQuitter("quit")
            builtins.exit = hy.repl.HyQuitter("exit")
            builtins.help = hy.repl.HyHelper()

            with (
                hy.repl.filtered_hy_exceptions(),
                hy.repl.extend_linecache(self.cmdline_cache),
            ):
                asyncio.run(self.interact(self.banner()))

        finally:
            sys.ps1, sys.ps2, builtins.quit, builtins.exit, builtins.help = saved_values
            for a in "ps1", "ps2":
                if getattr(sys, a) is sentinel:
                    delattr(sys, a)

        return 0

    async def interact(self, banner: Optional[str] = None, exitmsg: Optional[str] = None) -> None:
        """
        An async version of `InteractiveConsole.interact`.
        """
        if banner:
            self.write("%s\n" % str(banner))

        plot_task: Optional[asyncio.Task[None]] = None
        if self.pyplot:
            plot_task = asyncio.create_task(self._update_plots())

        try:
            while True:
                try:
                    try:
                        line = await self.get_input()
                    except EOFError:
                        self.write("\n")
                        break
                    else:
                        self.push(line)
                except KeyboardInterrupt:
                    self.write("\nKeyboardInterrupt\n")
                    self.resetbuffer()
                except SystemExit as e:
                    if self.local_exit:
                        self.write("\n")
                        break
                    else:
                        raise e
        finally:
            if exitmsg is None:
                self.write("now exiting %s...\n" % self.__class__.__name__)
            elif exitmsg != "":
                self.write("%s\n" % exitmsg)

            if plot_task:
                plot_task.cancel()
                try:
                    await plot_task
                except asyncio.CancelledError:
                    pass

    def banner(self) -> str:
        """Return the REPL banner string."""
        return (
            "🦑 Hy {version}{nickname} using {py}({build}) {pyversion} on {os}".format(
                version=hy.__version__,
                nickname="" if hy.nickname is None else f" ({hy.nickname})",
                py=platform.python_implementation(),
                build=platform.python_build()[0],
                pyversion=platform.python_version(),
                os=platform.system(),
            )
        )
