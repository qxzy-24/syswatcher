"""Backward-compatibility entry point for syswatch.

This module now functions as a shim delegating to the structured syswatcher package.
For new installations, prefer:
    python -m syswatcher
Or using the installed command-line script:
    syswatcher
"""

from syswatcher.daemon import main

if __name__ == "__main__":
    main()
