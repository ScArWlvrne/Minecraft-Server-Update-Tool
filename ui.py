"""
User-facing helpers for prompts and logging setup.
"""

import logging
import sys
from typing import Optional


def setup_logging(log_file: Optional[str] = None, level: int = logging.INFO) -> None:
    """
    Configure root logger to emit to stdout and optional file.
    """
    handlers = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file, mode="w"))
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers,
    )


def prompt_yes_no(message: str, assume_yes: bool = False) -> bool:
    """
    Prompt the user for yes/no. Honors assume_yes to auto-confirm.
    """
    if assume_yes:
        return True
    while True:
        resp = input(f"{message} [y/N]: ").strip().lower()
        if resp in ("y", "yes"):
            return True
        if resp in ("n", "no", ""):
            return False
        print("Please enter y or n.")
