"""Entry point for the packaged apps (Windows .exe, macOS .app): start the dashboard and open the browser."""
import multiprocessing
import sys

from . import __version__


def self_test():
    from pathlib import Path
    import sqlite3
    import keyring
    from carconnectivity_connectors.vw_eu_data_act.client import EudaApiClient  # noqa: F401
    from carconnectivity_connectors.vw_eu_data_act.dataset import Dataset  # noqa: F401
    from . import db, server
    static = server.STATIC
    assert (static / "index.html").is_file() and (static / "app.js").is_file(), f"static files missing in {static}"
    con = db.connect(":memory:")
    con.close()
    print("self-test OK", __version__, sqlite3.sqlite_version, type(keyring.get_keyring()).__name__)
    return 0


def main():
    multiprocessing.freeze_support()
    import os
    for name in ("stdout", "stderr"):      # windowed apps may have no console attached
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w"))
    if "--version" in sys.argv:
        print(__version__)
        return 0
    if "--self-test" in sys.argv:        # used by the build to check that everything got bundled
        return self_test()
    from .cli import main as cli_main
    argv = [a for a in sys.argv[1:]]
    if not argv or argv[0].startswith("-"):
        argv = ["serve"] + argv
    return cli_main(argv)


if __name__ == "__main__":
    sys.exit(main())
