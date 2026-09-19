from __future__ import annotations

import argparse


def main() -> int:
    parser = argparse.ArgumentParser(prog="presence-bridge")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("gui", help="Open the configuration GUI")
    sub.add_parser("daemon", help="Run the background presence daemon")
    sub.add_parser("doctor", help="Run diagnostics")

    args = parser.parse_args()

    if args.command in (None, "gui"):
        from .gui import run_gui
        return run_gui()
    if args.command == "daemon":
        from .daemon import run_daemon
        return run_daemon()
    if args.command == "doctor":
        from .doctor import run_doctor
        return run_doctor()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
