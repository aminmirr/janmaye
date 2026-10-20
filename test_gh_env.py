"""On a runner there is no gh login, only GH_TOKEN — build_site must use it as is.

Run: python3 test_gh_env.py
"""
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_site   # noqa: E402

called = []
real = subprocess.run
build_site.subprocess.run = lambda *a, **k: called.append(a) or real(["true"])
os.environ["GH_TOKEN"] = "tok-123"
env = build_site._gh_env()
assert env["GH_TOKEN"] == "tok-123"
assert not called, called
print("ok")
