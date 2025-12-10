import sys
from pathlib import Path

import pytest

# Ensure repo root on path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ui import prompt_yes_no


def test_prompt_yes_no_assume_yes():
    assert prompt_yes_no("Proceed?", assume_yes=True) is True


def test_prompt_yes_no_user_input_yes(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "y")
    assert prompt_yes_no("Proceed?", assume_yes=False) is True


def test_prompt_yes_no_user_input_no(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "n")
    assert prompt_yes_no("Proceed?", assume_yes=False) is False


def test_prompt_yes_no_reprompt(monkeypatch):
    responses = iter(["maybe", "yes"])
    monkeypatch.setattr("builtins.input", lambda _: next(responses))
    assert prompt_yes_no("Proceed?", assume_yes=False) is True
