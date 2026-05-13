#!/usr/bin/env python3
"""Wrapper for the installed doctor command."""

from barebones_optimizer.doctor import run_doctor


if __name__ == "__main__":
    raise SystemExit(run_doctor())
