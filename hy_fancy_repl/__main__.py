"""
For testing, this is useful, but you'd normally use the `hy-repl` entrypoint.
"""

from hy_fancy_repl.repl import HyREPL

if __name__ == "__main__":
    console = HyREPL()
    console.run()
