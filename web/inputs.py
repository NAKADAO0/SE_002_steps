"""Bounded Python file decoding and explicit natural-language workflow routing."""
import io
import re
import tokenize

MAX_SOURCE_BYTES = 100000


def utf8_source(source: str) -> str:
    """Keep Python's encoding cookie consistent with exported UTF-8 bytes."""
    lines = source.splitlines(keepends=True)
    cookie = re.compile(r"^([ \t\f]*#.*?coding[:=][ \t]*)([-\w.]+)")
    for index in range(min(2, len(lines))):
        lines[index] = cookie.sub(lambda match: match[1] + "utf-8", lines[index], count=1)
    return "".join(lines)


def validate_filename(name: str) -> str:
    if (not name or len(name) > 120 or "/" in name or "\\" in name
            or any(ord(char) < 32 for char in name) or ":" in name
            or not name.lower().endswith(".py") or len(name) <= 3):
        raise ValueError("文件名必须是不含路径的 .py 文件名，最长 120 字符")
    return name


def decode_python(filename: str, content: bytes) -> dict:
    validate_filename(filename)
    if len(content) > MAX_SOURCE_BYTES:
        raise ValueError("文件不能超过 100KB")
    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(content).readline)
        source = content.decode(encoding)
    except (SyntaxError, UnicodeError, LookupError) as exc:
        raise ValueError("无法解码源码，请使用 UTF-8 或有效的 Python 编码声明") from exc
    if not source.strip():
        raise ValueError("上传的代码文件不能为空")
    if len(source.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise ValueError("转换为 UTF-8 后源码不能超过 100KB")
    return {"filename": filename, "source_code": source}


def resolve_input(requirement, source_code, filename, max_repairs):
    if filename:
        validate_filename(filename)
        if not source_code.strip():
            raise ValueError("文件名必须关联非空源码")
    requirement = requirement.strip()
    if not requirement and source_code.strip():
        requirement = "请审查并修复这份 Python 代码，保留正常输入行为，解决实际缺陷。"
    only_review = bool(re.search(
        r"(?<!不)(?:只|仅)(?:进行)?(?:审查|检查)|(?:不要|不)(?:进行)?(?:修复|修改)(?:代码|源码|源代码|文件|这个文件|这份代码)?(?=[\s，,。.!！;；]|$)|review\s+only|do\s+not\s+(?:fix|modify)",
        requirement, re.IGNORECASE)) or max_repairs == 0
    intent = "review_only" if only_review else ("review_fix" if source_code.strip() else "generate")
    return requirement, intent, 0 if only_review else max_repairs
