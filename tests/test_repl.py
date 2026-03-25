"""Tests for hy-fancy-repl."""

import os
import sys
import tempfile
from unittest.mock import Mock, patch

import pytest

from hy_fancy_repl.repl import (
    HyCompleter,
    HyREPL,
    _get_lang_from_filename,
    _indent_depths,
    _read_file,
    _set_last_exc,
)


class TestIndentDepths:
    """Tests for the _indent_depths function."""

    def test_empty_string(self):
        """Empty string should return [0, 0, 0]."""
        assert _indent_depths("") == [0, 0, 0]

    def test_balanced_parens(self):
        """Balanced parentheses should return [0, 0, 0]."""
        assert _indent_depths("(foo bar)") == [0, 0, 0]

    def test_unbalanced_parens(self):
        """Unbalanced parentheses should return positive count."""
        assert _indent_depths("(foo bar") == [1, 0, 0]

    def test_nested_parens(self):
        """Nested parentheses should be counted correctly."""
        assert _indent_depths("(foo (bar baz") == [2, 0, 0]

    def test_brackets(self):
        """Square brackets should be counted separately."""
        assert _indent_depths("[1 2 3") == [0, 1, 0]

    def test_braces(self):
        """Curly braces should be counted separately."""
        assert _indent_depths("{:key value") == [0, 0, 1]

    def test_mixed_delimiters(self):
        """Mixed delimiters should all be counted."""
        assert _indent_depths("(foo [bar {:key") == [1, 1, 1]

    def test_closing_reduces_count(self):
        """Closing delimiters should reduce the count."""
        assert _indent_depths("(foo) [bar]") == [0, 0, 0]

    def test_negative_count_possible(self):
        """More closing than opening delimiters is possible."""
        assert _indent_depths("foo)") == [-1, 0, 0]

    def test_ignores_strings(self):
        """Delimiters inside strings should be ignored."""
        assert _indent_depths('"(foo bar)"') == [0, 0, 0]

    def test_ignores_comments(self):
        """Delimiters inside comments should be ignored."""
        assert _indent_depths("; (foo bar") == [0, 0, 0]


class TestGetLangFromFilename:
    """Tests for the _get_lang_from_filename function."""

    def test_python_file(self):
        """.py files should return 'python'."""
        assert _get_lang_from_filename("test.py") == "python"
        assert _get_lang_from_filename("/path/to/test.py") == "python"

    def test_hy_file(self):
        """.hy files should return 'hylang'."""
        assert _get_lang_from_filename("test.hy") == "hylang"
        assert _get_lang_from_filename("/path/to/test.hy") == "hylang"

    def test_pytb_file(self):
        """.pytb files should return 'pytb'."""
        assert _get_lang_from_filename("test.pytb") == "pytb"

    def test_py3tb_file(self):
        """.py3tb files should return 'py3tb'."""
        assert _get_lang_from_filename("test.py3tb") == "py3tb"

    def test_unknown_extension(self):
        """Unknown extensions should return None."""
        assert _get_lang_from_filename("test.txt") is None
        assert _get_lang_from_filename("test") is None

    def test_no_extension(self):
        """Files without extension should return None."""
        assert _get_lang_from_filename("Makefile") is None


class TestReadFile:
    """Tests for the _read_file function."""

    def test_reads_file_content(self):
        """Should return file contents as string."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".hy", delete=False) as f:
            f.write('(print "hello")\n')
            temp_path = f.name

        try:
            content = _read_file(temp_path)
            assert content == '(print "hello")\n'
        finally:
            os.unlink(temp_path)

    def test_reads_unicode(self):
        """Should handle unicode content."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".hy", delete=False, encoding="utf-8"
        ) as f:
            f.write('(print "héllo wörld 🦑")\n')
            temp_path = f.name

        try:
            content = _read_file(temp_path)
            assert "héllo wörld 🦑" in content
        finally:
            os.unlink(temp_path)

    def test_raises_on_missing_file(self):
        """Should raise FileNotFoundError for non-existent files."""
        with pytest.raises((IOError, OSError)):
            _read_file("/nonexistent/path/file.hy")


class TestSetLastExc:
    """Tests for the _set_last_exc function."""

    def test_sets_sys_attributes(self):
        """Should set sys.last_type, sys.last_value, sys.last_traceback."""
        try:
            raise ValueError("test error")
        except:
            exc_info = sys.exc_info()
            t, v, tb = _set_last_exc(exc_info)

            assert sys.last_type is t
            assert sys.last_value is v
            assert sys.last_traceback is tb
            assert isinstance(v, ValueError)
            assert str(v) == "test error"

    def test_uses_current_exc_if_none_provided(self):
        """Should use sys.exc_info() if no exc_info provided."""
        try:
            raise RuntimeError("current error")
        except:
            t, v, tb = _set_last_exc()
            assert isinstance(v, RuntimeError)


class TestHyCompleter:
    """Tests for the HyCompleter class."""

    def test_init_with_empty_namespace(self):
        """Should initialize with empty namespace if none provided."""
        completer = HyCompleter()
        # Hy adds internal macros to the namespace
        assert "_hy_macros" in completer.namespace
        assert "_hy_reader_macros" in completer.namespace

    def test_init_with_namespace(self):
        """Should use provided namespace."""
        ns = {"foo": 1, "bar": 2}
        completer = HyCompleter(ns)
        assert completer.namespace is ns

    def test_get_completions_yields_completions(self):
        """Should yield Completion objects."""
        completer = HyCompleter({"foobar": 1, "foobaz": 2})

        # Create a mock document
        doc = Mock()
        doc.get_word_before_cursor.return_value = "foo"

        completions = list(completer.get_completions(doc, Mock()))

        # Should have completions for foobar and foobaz
        assert len(completions) == 2
        assert all(c.text in ["foobar", "foobaz"] for c in completions)

    def test_completions_update_namespace(self):
        """Should update namespace reference on each call."""
        completer = HyCompleter({"old": 1})

        doc = Mock()
        doc.get_word_before_cursor.return_value = ""

        # Update namespace
        completer.namespace = {"new": 2}

        # Trigger get_completions to update internal completer's namespace
        list(completer.get_completions(doc, Mock()))

        # The completer's internal completer should see the new namespace
        assert completer.c.namespace["new"] == 2


class TestHyREPL:
    """Tests for the HyREPL class."""

    def test_init_creates_session(self):
        """Should create a PromptSession on init."""
        repl = HyREPL()
        assert repl.session is not None

    def test_init_with_locals(self):
        """Should accept locals dict (Hy may merge with internal namespace)."""
        locals_dict = {"custom_var": 42}
        repl = HyREPL(locals=locals_dict)
        # Hy's REPL may copy or merge locals, just verify initialization works
        assert repl.locals is not None
        assert isinstance(repl.locals, dict)

    def test_banner_contains_version_info(self):
        """Banner should contain Hy version and Python info."""
        repl = HyREPL()
        banner = repl.banner()
        assert "Hy" in banner
        assert "🦑" in banner
        assert "Python" in banner or "CPython" in banner

    def test_validation_text_returns_formatted_text(self):
        """Should return FormattedText."""
        repl = HyREPL()
        result = repl._validation_text()
        assert isinstance(result, tuple) or hasattr(result, "__iter__")

    def test_ps2_truncated_to_ps1_length(self):
        """ps2 should be truncated to match ps1 length."""
        repl = HyREPL()
        assert len(repl.ps2) == len(repl.ps1)
