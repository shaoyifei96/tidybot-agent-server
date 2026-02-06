#!/usr/bin/env python3
"""Test the code validator.

Run: python3 test_code_validation.py
"""

from code_executor import CodeValidator, CodeValidationResult


def test_case(name: str, code: str, expected_valid: bool):
    """Run a test case and print result."""
    validator = CodeValidator()
    result = validator.validate(code)

    status = "PASS" if result.valid == expected_valid else "FAIL"
    print(f"[{status}] {name}")
    if not result.valid:
        for err in result.errors:
            print(f"       {err}")
    if result.valid != expected_valid:
        print(f"       Expected valid={expected_valid}, got valid={result.valid}")
    print()


def main():
    print("=" * 60)
    print("Code Validator Tests")
    print("=" * 60)
    print()

    # Should PASS (valid code)
    print("--- Valid code (should pass) ---")

    test_case("Basic robot SDK usage", """
from robot_sdk import arm, gripper, sensors
import time
import math

joints = sensors.get_arm_joints()
print(f"Current joints: {joints}")

arm.move_joints([0, -0.785, 0, -2.356, 0, 1.571, 0.785])
time.sleep(1)
gripper.open()
""", expected_valid=True)

    test_case("Math and numpy", """
import math
import numpy as np

angle = math.pi / 4
arr = np.array([1, 2, 3])
print(arr * math.sin(angle))
""", expected_valid=True)

    test_case("File reading (allowed)", """
with open('/tmp/test.txt', 'r') as f:
    data = f.read()
print(data)
""", expected_valid=True)

    test_case("os.path operations (allowed)", """
import os
path = os.path.join('/home', 'user', 'file.txt')
exists = os.path.exists(path)
print(f"Path: {path}, exists: {exists}")
""", expected_valid=True)

    # Should FAIL (dangerous code)
    print("--- Dangerous code (should fail) ---")

    test_case("os.system", """
import os
os.system('ls -la')
""", expected_valid=False)

    test_case("subprocess import", """
import subprocess
subprocess.run(['ls'])
""", expected_valid=False)

    test_case("eval builtin", """
code = "print('hello')"
eval(code)
""", expected_valid=False)

    test_case("exec builtin", """
code = "x = 1"
exec(code)
""", expected_valid=False)

    test_case("os.remove", """
import os
os.remove('/tmp/file.txt')
""", expected_valid=False)

    test_case("requests import", """
import requests
r = requests.get('http://example.com')
""", expected_valid=False)

    test_case("socket import", """
import socket
s = socket.socket()
""", expected_valid=False)

    test_case("pickle import", """
import pickle
data = pickle.loads(b'...')
""", expected_valid=False)

    test_case("shutil import", """
import shutil
shutil.rmtree('/tmp/dir')
""", expected_valid=False)

    test_case("multiprocessing import", """
import multiprocessing
p = multiprocessing.Process(target=lambda: None)
""", expected_valid=False)

    test_case("os.fork", """
import os
pid = os.fork()
""", expected_valid=False)

    test_case("__import__ builtin", """
mod = __import__('os')
mod.system('ls')
""", expected_valid=False)

    test_case("from subprocess import", """
from subprocess import run, Popen
run(['ls'])
""", expected_valid=False)

    # Syntax errors
    print("--- Syntax errors (should fail) ---")

    test_case("Syntax error", """
def broken(
    print("missing paren")
""", expected_valid=False)

    print("=" * 60)
    print("Tests complete")
    print("=" * 60)


if __name__ == "__main__":
    main()
