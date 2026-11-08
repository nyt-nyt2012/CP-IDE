"""Output comparison ("checker") implementations.

Several judging modes are supported, mirroring the ones commonly found in OI
tools:

``default``
    Ignore trailing spaces on every line and ignore trailing empty lines.
``strict``
    Byte-for-byte comparison after normalising line endings.
``ignore_trailing_space``
    Ignore *all* whitespace differences.
``wcmp``
    Compare token by token, whitespace insensitive.
``ncmp``
    Numeric comparison: tokens that look like numbers are compared with a
    relative tolerance, other tokens must match exactly.
``custom``
    A user supplied checker program (compiled from C++ source) decides.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

CHECKER_CHOICES = (
    "default",
    "strict",
    "ignore_trailing_space",
    "wcmp",
    "ncmp",
    "custom",
)

#: Human readable labels used by the front-end.
CHECKER_LABELS = {
    "default": "默认（忽略行末空格与末尾空行）",
    "strict": "严格（完全一致）",
    "ignore_trailing_space": "忽略所有空白",
    "wcmp": "按空白分词比较",
    "ncmp": "数值比较（带容差）",
    "custom": "自定义 Checker",
}

_NUMBER_RE = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$")


@dataclass
class CheckResult:
    ok: bool
    status: str = "accept"        # accept | wrong_answer | presentation_error | ...
    message: str = ""
    diff: Optional[str] = None
    first_mismatch: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "status": self.status,
            "message": self.message,
            "diff": self.diff,
            "first_mismatch": self.first_mismatch,
        }


def _normalise_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _split_lines(text: str) -> List[str]:
    return _normalise_newlines(text).split("\n")


def _strip_trailing_empty_lines(lines: List[str]) -> List[str]:
    out = list(lines)
    while out and out[-1].strip() == "":
        out.pop()
    return out


def _first_difference(a: List[str], b: List[str]) -> Optional[dict]:
    for index in range(max(len(a), len(b))):
        left = a[index] if index < len(a) else None
        right = b[index] if index < len(b) else None
        if left != right:
            return {"line": index + 1, "expected": right, "actual": left}
    return None


def _build_diff(expected: str, actual: str, limit: int = 4000) -> str:
    """A compact unified-ish diff between the expected and the actual output."""
    exp_lines = _split_lines(expected)
    act_lines = _split_lines(actual)
    chunks: List[str] = []
    import difflib

    diff = difflib.unified_diff(
        exp_lines, act_lines, fromfile="expected", tofile="actual", lineterm=""
    )
    for line in diff:
        chunks.append(line)
        if sum(len(c) for c in chunks) > limit:
            chunks.append("... (diff truncated)")
            break
    if not chunks:
        return ""
    return "\n".join(chunks)


# --------------------------------------------------------------------------- #
#  individual comparators
# --------------------------------------------------------------------------- #
def check_default(output: str, expected: str) -> CheckResult:
    """Ignore trailing spaces on each line and trailing blank lines."""
    out_lines = _strip_trailing_empty_lines(
        [line.rstrip() for line in _split_lines(output)]
    )
    exp_lines = _strip_trailing_empty_lines(
        [line.rstrip() for line in _split_lines(expected)]
    )
    if out_lines == exp_lines:
        return CheckResult(ok=True)
    return CheckResult(
        ok=False,
        status="wrong_answer",
        message="输出与答案不一致",
        diff=_build_diff(expected, output),
        first_mismatch=_first_difference(exp_lines, out_lines),
    )


def check_strict(output: str, expected: str) -> CheckResult:
    if _normalise_newlines(output) == _normalise_newlines(expected):
        return CheckResult(ok=True)
    return CheckResult(
        ok=False,
        status="wrong_answer",
        message="输出与答案不一致（严格比较）",
        diff=_build_diff(expected, output),
        first_mismatch=_first_difference(_split_lines(expected), _split_lines(output)),
    )


def check_ignore_trailing_space(output: str, expected: str) -> CheckResult:
    def squash(text: str) -> str:
        return re.sub(r"\s+", "", _normalise_newlines(text))

    if squash(output) == squash(expected):
        return CheckResult(ok=True)
    return CheckResult(
        ok=False,
        status="wrong_answer",
        message="输出与答案不一致（忽略所有空白）",
        diff=_build_diff(expected, output),
    )


def _tokens(text: str) -> List[str]:
    return re.split(r"\s+", _normalise_newlines(text).strip()) if text.strip() else []


def check_wcmp(output: str, expected: str) -> CheckResult:
    out_tokens = _tokens(output)
    exp_tokens = _tokens(expected)
    if out_tokens == exp_tokens:
        return CheckResult(ok=True)
    return CheckResult(
        ok=False,
        status="wrong_answer",
        message="输出与答案不一致（按空白分词比较）",
        diff=_build_diff(expected, output),
        first_mismatch=_first_difference(exp_tokens, out_tokens),
    )


def check_ncmp(output: str, expected: str, eps: float = 1e-6) -> CheckResult:
    """Numeric comparison with a relative tolerance, token by token."""
    out_tokens = _tokens(output)
    exp_tokens = _tokens(expected)
    if len(out_tokens) != len(exp_tokens):
        return CheckResult(
            ok=False,
            status="wrong_answer",
            message="输出的数字个数与答案不一致（期望 %d 个，实际 %d 个）"
            % (len(exp_tokens), len(out_tokens)),
            diff=_build_diff(expected, output),
        )
    for index, (left, right) in enumerate(zip(out_tokens, exp_tokens)):
        left_num = _NUMBER_RE.match(left)
        right_num = _NUMBER_RE.match(right)
        if left_num and right_num:
            try:
                lv = float(left)
                rv = float(right)
            except ValueError:
                if left != right:
                    return _ncmp_mismatch(index, exp_tokens, out_tokens, expected, output)
                continue
            if lv != rv:
                tolerance = eps * max(1.0, abs(rv))
                if abs(lv - rv) > tolerance:
                    return _ncmp_mismatch(index, exp_tokens, out_tokens, expected, output)
        elif left != right:
            return _ncmp_mismatch(index, exp_tokens, out_tokens, expected, output)
    return CheckResult(ok=True)


def _ncmp_mismatch(
    index: int, exp_tokens: List[str], out_tokens: List[str], expected: str, output: str
) -> CheckResult:
    return CheckResult(
        ok=False,
        status="wrong_answer",
        message="第 %d 个输出与答案不一致（期望 %r，实际 %r）"
        % (index + 1, exp_tokens[index], out_tokens[index]),
        diff=_build_diff(expected, output),
        first_mismatch={
            "line": index + 1,
            "expected": exp_tokens[index],
            "actual": out_tokens[index],
        },
    )


# --------------------------------------------------------------------------- #
#  dispatcher
# --------------------------------------------------------------------------- #
def compare(
    output: str,
    expected: Optional[str],
    checker: str = "default",
    ncmp_eps: float = 1e-6,
) -> CheckResult:
    """Compare the program output with the expected output.

    ``expected`` is ``None`` when the test point has no answer file; in that
    case the output is accepted but flagged, because there is nothing to
    compare against.
    """
    checker = (checker or "default").strip().lower()
    if expected is None:
        return CheckResult(ok=True, status="accept", message="该测试点没有答案文件，跳过答案比对")
    if checker == "strict":
        return check_strict(output, expected)
    if checker == "ignore_trailing_space":
        return check_ignore_trailing_space(output, expected)
    if checker == "wcmp":
        return check_wcmp(output, expected)
    if checker == "ncmp":
        return check_ncmp(output, expected, ncmp_eps)
    return check_default(output, expected)
