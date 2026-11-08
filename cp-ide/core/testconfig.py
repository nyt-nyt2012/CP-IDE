"""Parser for the test point configuration file.

The configuration file describes the global judging parameters and the list of
test points.  Several syntaxes are accepted so that the file can be written
in whichever way is most convenient:

1. **INI style** (recommended)::

       [config]
       std = c++14
       time_limit = 1000
       memory_limit = 256
       checker = default

       [tests]
       1 | 1.in | 1.out | 1000 | 256
       2 | 2.in | 2.out

2. **Plain list** - a file without any section header is treated as a list of
   test points; ``key = value`` lines are still recognised as global options.

3. **JSON** - a JSON object with ``config`` and ``tests`` keys.

Every test point line is split by ``|``, ``;`` or a comma into the fields::

    编号 | 输入文件 | 输出文件 | 时间限制(ms) | 空间限制(MB) | checker

Only the input and the output file are mandatory; the remaining fields fall
back to the global defaults.  ``*`` can be used as a wildcard for the file
names, e.g. ``1-10.in`` and ``1-10.out`` expand into ten test points.
"""

from __future__ import annotations

import glob
import json
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .checker import CHECKER_CHOICES

DEFAULT_TIME_LIMIT = 1000
DEFAULT_MEMORY_LIMIT = 256
DEFAULT_CHECKER = "default"
DEFAULT_OUTPUT_LIMIT = 256


class ConfigError(Exception):
    """Raised when the configuration file cannot be understood."""


@dataclass
class GlobalConfig:
    std: str = "c++14"
    time_limit: int = DEFAULT_TIME_LIMIT
    memory_limit: int = DEFAULT_MEMORY_LIMIT
    checker: str = DEFAULT_CHECKER
    output_limit: int = DEFAULT_OUTPUT_LIMIT
    compile_args: str = ""
    runner_args: str = ""
    ncmp_eps: float = 1e-6
    extra: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "std": self.std,
            "time_limit": self.time_limit,
            "memory_limit": self.memory_limit,
            "checker": self.checker,
            "output_limit": self.output_limit,
            "compile_args": self.compile_args,
            "runner_args": self.runner_args,
            "ncmp_eps": self.ncmp_eps,
            "extra": self.extra,
        }


@dataclass
class TestPoint:
    index: int
    name: str
    input_file: str
    output_file: str
    time_limit: int = DEFAULT_TIME_LIMIT
    memory_limit: int = DEFAULT_MEMORY_LIMIT
    checker: str = DEFAULT_CHECKER
    ncmp_eps: float = 1e-6

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "name": self.name,
            "input_file": self.input_file,
            "output_file": self.output_file,
            "time_limit": self.time_limit,
            "memory_limit": self.memory_limit,
            "checker": self.checker,
        }


@dataclass
class TestConfig:
    global_config: GlobalConfig = field(default_factory=GlobalConfig)
    test_points: List[TestPoint] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    source: str = ""

    def to_dict(self) -> dict:
        return {
            "global": self.global_config.to_dict(),
            "tests": [t.to_dict() for t in self.test_points],
            "warnings": self.warnings,
        }


# --------------------------------------------------------------------------- #
#  helpers
# --------------------------------------------------------------------------- #
def _strip_comment(line: str) -> str:
    """Remove a trailing ``;``/``#`` comment that is not inside a quoted value."""
    out = []
    quote = None
    for ch in line:
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
            out.append(ch)
            continue
        if ch in ";#":
            break
        out.append(ch)
    return "".join(out).strip()


def _to_int(value: str, default: int) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _to_float(value: str, default: float) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def _split_fields(line: str) -> List[str]:
    """Split a test point line on ``|``, ``;`` or a comma."""
    for sep in ("|", ";", ","):
        if sep in line:
            return [part.strip() for part in line.split(sep)]
    return line.split()


_RANGE_RE = re.compile(r"^(?P<prefix>.*?)(?P<start>\d+)\s*-\s*(?P<end>\d+)(?P<suffix>\D*)$")


def _expand_wildcard(pattern: str, available: List[str]) -> List[str]:
    """Expand ``1-10.in`` / ``*.in`` into the list of matching file names."""
    pattern = pattern.strip()
    if not pattern:
        return []

    if "*" in pattern or "?" in pattern:
        return sorted(glob.glob(pattern))

    m = _RANGE_RE.match(pattern)
    if m:
        prefix, start, end, suffix = (
            m.group("prefix"),
            int(m.group("start")),
            int(m.group("end")),
            m.group("suffix"),
        )
        width = len(m.group("start"))
        expanded = []
        for number in range(start, end + 1):
            candidate = "%s%0*d%s" % (prefix, width, number, suffix)
            if candidate in available or not available:
                expanded.append(candidate)
        if expanded:
            return expanded

    return [pattern]


def _match_file(candidates: List[str], name: str) -> Optional[str]:
    """Find *name* among *candidates*, tolerating a missing extension."""
    if not name:
        return None
    if name in candidates:
        return name
    lowered = {c.lower(): c for c in candidates}
    if name.lower() in lowered:
        return lowered[name.lower()]
    stem, ext = os.path.splitext(name)
    if not ext:
        for candidate in candidates:
            if os.path.splitext(candidate)[0].lower() == stem.lower():
                return candidate
    for candidate in candidates:
        if candidate.lower().endswith(name.lower()):
            return candidate
    return None


# --------------------------------------------------------------------------- #
#  parsing
# --------------------------------------------------------------------------- #
def parse_config(
    text: str,
    available_files: Optional[List[str]] = None,
) -> TestConfig:
    """Parse a test point configuration file.

    *available_files* is the list of file names that were uploaded together
    with the configuration; it is used to resolve wildcards and to detect
    typos in the file names.
    """
    available_files = list(available_files or [])
    text = text or ""
    stripped = text.strip()

    if stripped.startswith("{"):
        return _parse_json(stripped, available_files)

    config = TestConfig(source=text)
    g = config.global_config
    section = ""
    pending: List[str] = []

    for raw_line in text.splitlines():
        line = _strip_comment(raw_line).strip()
        if not line:
            continue

        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
            continue

        if section in ("config", "global", "options", "设置"):
            _apply_option(g, line, config.warnings)
            continue

        if section in ("tests", "test", "测试点", "points"):
            pending.append(line)
            continue

        # no section header yet
        if "=" in line and not _looks_like_test_line(line):
            _apply_option(g, line, config.warnings)
        else:
            pending.append(line)

    _build_test_points(config, pending, available_files)
    return config


def _looks_like_test_line(line: str) -> bool:
    """A test line contains a file name, never ``key = value``."""
    if "=" in line:
        head = line.split("=", 1)[0].strip()
        # ``1.in 1.out`` style lines never contain '='
        return False
    return True


def _apply_option(g: GlobalConfig, line: str, warnings: List[str]) -> None:
    if "=" not in line:
        # ``key: value`` style
        if ":" in line:
            key, _, value = line.partition(":")
        else:
            return
    else:
        key, _, value = line.partition("=")
    key = key.strip().lower().replace("-", "_").replace(" ", "_")
    value = value.strip().strip('"').strip("'")

    if key in ("std", "standard", "cxx_standard"):
        g.std = value
    elif key in ("time_limit", "timelimit", "tl", "时间限制"):
        g.time_limit = _to_int(value, g.time_limit)
    elif key in ("memory_limit", "memlimit", "ml", "空间限制", "内存限制"):
        g.memory_limit = _to_int(value, g.memory_limit)
    elif key in ("checker", "比较器", "评测方式"):
        checker = value.lower()
        if checker not in CHECKER_CHOICES:
            warnings.append("未知的 checker「%s」，已回退为 default。" % value)
            checker = DEFAULT_CHECKER
        g.checker = checker
    elif key in ("output_limit", "输出限制"):
        g.output_limit = _to_int(value, g.output_limit)
    elif key in ("compile_args", "compiler_args", "编译参数"):
        g.compile_args = value
    elif key in ("runner_args", "run_args", "运行参数"):
        g.runner_args = value
    elif key in ("ncmp_eps", "eps", "容差"):
        g.ncmp_eps = _to_float(value, g.ncmp_eps)
    else:
        g.extra[key] = value


def _build_test_points(
    config: TestConfig, lines: List[str], available_files: List[str]
) -> None:
    g = config.global_config
    pending_entries: List[Tuple[List[str], int]] = []
    auto_index = 0

    for line in lines:
        fields = _split_fields(line)
        if not fields or not any(fields):
            continue
        auto_index += 1
        pending_entries.append((fields, auto_index))

    # Expand the wildcard input files first, then pair them with the outputs.
    expanded: List[Tuple[List[str], int]] = []
    for fields, auto_idx in pending_entries:
        if len(fields) >= 2 and ("*" in fields[1] or "?" in fields[1]):
            inputs = _expand_wildcard(fields[1], available_files)
            if not inputs:
                config.warnings.append("通配符 %s 没有匹配到任何文件。" % fields[1])
                continue
            output_pattern = fields[2] if len(fields) >= 3 else ""
            for position, input_name in enumerate(inputs):
                new_fields = list(fields)
                new_fields[1] = input_name
                if output_pattern:
                    replaced = _expand_wildcard(output_pattern, available_files)
                    if len(replaced) == len(inputs):
                        new_fields[2] = replaced[position]
                    else:
                        stem = os.path.splitext(input_name)[0]
                        new_fields[2] = stem + ".out"
                expanded.append((new_fields, len(expanded) + 1))
        else:
            expanded.append((fields, len(expanded) + 1))

    for fields, auto_idx in expanded:
        if not fields:
            continue
        # A leading pure number is the test point id.
        index = auto_idx
        rest = fields
        if fields and re.fullmatch(r"\d+", fields[0]):
            index = int(fields[0])
            rest = fields[1:]
        if not rest:
            config.warnings.append("第 %d 行缺少输入文件名，已跳过。" % auto_idx)
            continue

        input_file = rest[0]
        output_file = rest[1] if len(rest) > 1 else ""
        time_limit = _to_int(rest[2], g.time_limit) if len(rest) > 2 else g.time_limit
        memory_limit = (
            _to_int(rest[3], g.memory_limit) if len(rest) > 3 else g.memory_limit
        )
        checker = g.checker
        if len(rest) > 4 and rest[4]:
            candidate = rest[4].lower()
            if candidate in CHECKER_CHOICES:
                checker = candidate
            else:
                config.warnings.append(
                    "测试点 %d 的 checker「%s」未知，已回退为 %s。"
                    % (index, rest[4], g.checker)
                )

        resolved_in = _match_file(available_files, input_file) or input_file
        resolved_out = (
            _match_file(available_files, output_file) or output_file if output_file else ""
        )
        if available_files and resolved_in not in available_files:
            config.warnings.append("测试点 %d 的输入文件「%s」不存在。" % (index, input_file))
        if output_file and available_files and resolved_out not in available_files:
            config.warnings.append(
                "测试点 %d 的输出文件「%s」不存在。" % (index, output_file)
            )

        name = os.path.splitext(os.path.basename(resolved_in))[0] or ("测试点 %d" % index)

        config.test_points.append(
            TestPoint(
                index=index,
                name=name,
                input_file=resolved_in,
                output_file=resolved_out,
                time_limit=time_limit,
                memory_limit=memory_limit,
                checker=checker,
                ncmp_eps=g.ncmp_eps,
            )
        )


def _parse_json(text: str, available_files: List[str]) -> TestConfig:
    config = TestConfig(source=text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigError("JSON 解析失败：%s" % exc) from exc

    g = config.global_config
    global_block = data.get("config") or data.get("global") or {}
    if isinstance(global_block, dict):
        for key, value in global_block.items():
            _apply_option(g, "%s=%s" % (key, value), config.warnings)

    tests = data.get("tests") or data.get("test_points") or []
    lines = []
    if isinstance(tests, list):
        for item in tests:
            if isinstance(item, dict):
                lines.append(
                    " | ".join(
                        str(item.get(key, ""))
                        for key in (
                            "index",
                            "input",
                            "output",
                            "time_limit",
                            "memory_limit",
                            "checker",
                        )
                    )
                )
            elif isinstance(item, (list, tuple)):
                lines.append(" | ".join(str(part) for part in item))
            else:
                lines.append(str(item))
    _build_test_points(config, lines, available_files)
    return config


# --------------------------------------------------------------------------- #
#  automatic pairing
# --------------------------------------------------------------------------- #
def auto_pair_files(file_names: List[str]) -> List[Tuple[str, str]]:
    """Pair ``*.in`` with ``*.out`` automatically, sorted by name."""
    ins = sorted(f for f in file_names if f.lower().endswith(".in"))
    outs = sorted(f for f in file_names if f.lower().endswith(".out"))
    out_by_stem = {}
    for name in outs:
        out_by_stem[os.path.splitext(name)[0].lower()] = name

    pairs: List[Tuple[str, str]] = []
    used = set()
    for name in ins:
        stem = os.path.splitext(name)[0]
        candidate = out_by_stem.get(stem.lower())
        if candidate and candidate not in used:
            pairs.append((name, candidate))
            used.add(candidate)
        else:
            pairs.append((name, ""))
    return pairs
