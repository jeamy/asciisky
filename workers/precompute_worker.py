#!/usr/bin/env python3
"""Compatibility entry point for the former dedicated precompute worker.

All production processing lives in :mod:`unified_worker`; keeping this small
wrapper avoids breaking existing operational commands while preventing the two
workers from drifting in retry, claim, cache and data-reload behaviour.
"""

try:  # Supports both ``python workers/precompute_worker.py`` and package imports.
    from .unified_worker import main
except ImportError:  # pragma: no cover - direct-script execution has no package
    from unified_worker import main


if __name__ == "__main__":
    main()
