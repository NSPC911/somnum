"""The spec is the conformance test: run spec.num and diff against spec.expected."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


def run_program(
    source_path: Path, stdin_text: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "somnum", str(source_path)],
        input=stdin_text,
        capture_output=True,
        text=True,
    )


def test_spec_output_matches_expected() -> None:
    result = run_program(ROOT / "spec.num", (ROOT / "spec.stdin").read_text())
    assert result.returncode == 0, result.stderr
    assert result.stdout == (ROOT / "spec.expected").read_text()


def test_repl() -> None:
    lines = [
        "10 = 5",  # assignment is silent
        "5 + 10",  # bare expressions are echoed
        "9 = & (0) => (1) {",
        "    1 = 0 + 0",
        "}",  # multi-line input
        "$9 (6)",  # calls are echoed too
        "4 / 0",  # errors go to stderr and the repl survives
        "exit",  # letters are comments so this is a blank line
        "7",
    ]
    result = subprocess.run(
        [sys.executable, "-m", "somnum"],
        input="\n".join(lines) + "\n",
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["10", "12", "7"]
    assert "error: division by zero" in result.stderr


def test_fizzbuzz_example() -> None:
    expected = []
    for n in range(1, 101):
        if n % 15 == 0:
            expected.append("FizzBuzz")
        elif n % 3 == 0:
            expected.append("Fizz")
        elif n % 5 == 0:
            expected.append("Buzz")
        else:
            expected.append(str(n))
    result = run_program(ROOT / "examples" / "fizzbuzz.num")
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == expected


def test_fibonacci_example() -> None:
    result = run_program(ROOT / "examples" / "fibonacci.num", "15\n")
    assert result.returncode == 0, result.stderr
    fib = [0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377]
    assert result.stdout.splitlines() == [str(n) for n in fib]


def test_echo_example() -> None:
    result = run_program(ROOT / "examples" / "echo.num", "good morning\n")
    assert result.returncode == 0, result.stderr
    assert result.stdout == "good morning\n"


def test_gcd_example() -> None:
    result = run_program(ROOT / "examples" / "gcd.num", "48 18\n")
    assert result.returncode == 0, result.stderr
    assert result.stdout == "6\n"


def test_sparse_set_example() -> None:
    result = run_program(ROOT / "examples" / "sparse_set.num")
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["0", "1", "1"]


def test_error_cases(tmp_path: Path) -> None:
    cases = {
        "lone unary minus": "- 3 >>",
        "bare expression": "5 - 3",
        "assign to negative slot": "-3 = 7",
        "empty return group": "9 = & () => () { }",
        "repeated parameter slot": "9 = & (0, 0) => (1) { }",
        "wrong argument count": "9 = & (0) => (0) { }  $9 (1, 2)",
        "calling a non function": "$9 (1)",
        "division by zero": "4 / 0 >>",
        "negative exponent": "4 ^ -1 >>",
        "negative slot in signature": "9 = & (-1) => (0) { }",
        "forget a negative slot": "-3 ~",
        "innocence check without an address": "~(9) >>",
    }
    for name, src in cases.items():
        prog = tmp_path / "case.num"
        prog.write_text(src + "\n")
        result = run_program(prog)
        assert result.returncode == 1, f"{name!r} should be an error"
        assert result.stderr.startswith("error:"), name
