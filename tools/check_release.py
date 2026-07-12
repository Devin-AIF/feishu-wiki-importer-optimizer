#!/usr/bin/env python3
"""Run the release allowlist scanner without producing an archive."""

from build_release import main


if __name__ == "__main__":
    raise SystemExit(main(["--check-only"]))
