"""Entry point for ``python -m leadgen.auth``."""

import sys

from leadgen.auth.cli import main

if __name__ == "__main__":
    sys.exit(main())
