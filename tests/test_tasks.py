"""Tests tasks."""

# Note: Use pytest for writing tests!
import pytest

# from src.tasks import command

def test_task_command():
    """Test command task."""

    ret = "some dummy return value"
    assert isinstance(ret,str)
