"""
🦑 - hy-fancy-repl, an enhanced Hy REPL.
"""

from hy_fancy_repl.repl import HyREPL

# set the package version
# the major.minor version simply match the assumed Hy version
__version__ = "1.2.0"
__version_info__ = __version__.split(".")


def __cli_repl():
    """
    A prettier hy REPL.
    """
    console = HyREPL()
    console.run()
