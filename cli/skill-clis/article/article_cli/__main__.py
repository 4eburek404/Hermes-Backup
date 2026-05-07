#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from article_cli import __version__


DEFAULT_USER_AGENT = "article-cli/0.1 (+local-codex-tool)"
BLOCK_TAGS = {
    "article",
    "aside",
    "blockquote",
    "br",
    "dd",
    "div",
    "dl",
    "dt",
    "figcaption",
    "figure",
    "footer",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "hr",
    "li",
    "main",
    "nav",
    "ol",
    "p",
    "pre",
    "section",
    "table",
    "td",
    "th",
    "tr",
    "ul",
}
SKIP_TAGS = {"script", "style", "noscript", "svg", "canvas", "template"}


class CliError(Exception):
    def __init__(
        self,
        kind: str,
        message: str,
        *,
        status: int | None = None,
        details: Any = None,
        exit_code: int = 1,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.status = status
        self.details = details
        self.exit_code = exit_code


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.links: list[dict[str, str]] = []
        self.images: list[dict[str, str]] = []
        self.skip_depth = 0
        self.heading_stack: list[int] = []
        self.in_pre = False
        self.current_link: str | None = None
        self.current_link_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attrs_dict = {k.lower(): v for k, v in attrs if v is not None}
        if tag in SKIP_TAGS:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag in BLOCK_TAGS:
            self._newline()
        if re.fullmatch(r"h[1-6]", tag):
            self.heading_stack.append(min(int(tag[1]), 3))
            self._newline()
            self.parts.append("#" * min(int(tag[1]), 3) + " ")
        elif tag == "li":
            self.parts.append("- ")
        elif tag == "pre":
            self.in_pre = True
            self.parts.append("```\n")
        elif tag == "a":
            href = attrs_dict.get("href")
            if href:
                self.current_link = href
                self.current_link_text = []
        elif tag == "img":
            alt = (attrs_dict.get("alt") or "").strip()
            src = attrs_dict.get("src") or ""
            if alt:
                self.parts.append(f"[Image: {alt}]")
            if alt or src:
                self.images.append({"alt": alt, "src": src})

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in SKIP_TAGS:
            if self.skip_depth:
                self.skip_depth -= 1
            return
        if self.skip_depth:
            return
        if re.fullmatch(r"h[1-6]", tag):
            if self.heading_stack:
                self.heading_stack.pop()
            self._newline()
        elif tag == "pre":
            self.in_pre = False
            self.parts.append("\n```\n")
        elif tag == "a":
            if self.current_link:
                text = clean_inline(" ".join(self.current_link_text))
                self.links.append({"text": text, "href": self.current_link})
                self.current_link = None
                self.current_link_text = []
        if tag in BLOCK_TAGS:
            self._newline()

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        if not data:
            return
        if self.current_link is not None:
            self.current_link_text.append(data)
        self.parts.append(data if self.in_pre else clean_inline(data))

    def _newline(self) -> None:
        if not self.parts or self.parts[-1].endswith("\n"):
            return
        self.parts.append("\n")

    def text(self) -> str:
        raw = "".join(self.parts)
        raw = html.unescape(raw)
        raw = re.sub(r"[ \t]+\n", "\n", raw)
        raw = re.sub(r"\n[ \t]+", "\n", raw)
        raw = re.sub(r"[ \t]{2,}", " ", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        lines = [line.rstrip() for line in raw.splitlines()]
        return "\n".join(lines).strip()


def clean_inline(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def is_url(source: str) -> bool:
    parsed = urllib.parse.urlparse(source)
    return parsed.scheme in ("http", "https")


def source_kind(source: str) -> str:
    if source == "-":
        return "stdin"
    if is_url(source):
        return "url"
    if source.startswith("file://"):
        return "file"
    return "file"


def read_source(source: str, *, timeout: float, user_agent: str, max_bytes: int | None = None) -> dict[str, Any]:
    kind = source_kind(source)
    if kind == "stdin":
        raw = sys.stdin.buffer.read(max_bytes or -1)
        return {
            "source": source,
            "kind": kind,
            "status": None,
            "final_url": None,
            "headers": {},
            "bytes": len(raw),
            "content_type": None,
            "body": raw.decode("utf-8", errors="replace"),
        }
    if kind == "file":
        path = Path(source[7:] if source.startswith("file://") else source).expanduser()
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise CliError("read_error", f"Cannot read file: {path}", details=str(exc))
        if max_bytes is not None:
            raw = raw[:max_bytes]
        return {
            "source": source,
            "kind": kind,
            "status": None,
            "final_url": str(path),
            "headers": {},
            "bytes": len(raw),
            "content_type": guess_content_type(path),
            "body": raw.decode("utf-8", errors="replace"),
        }

    headers = {"User-Agent": user_agent, "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.8"}
    request = urllib.request.Request(source, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(max_bytes or -1)
            charset = response.headers.get_content_charset() or "utf-8"
            return {
                "source": source,
                "kind": kind,
                "status": response.status,
                "final_url": response.geturl(),
                "headers": safe_headers(dict(response.headers.items())),
                "bytes": len(raw),
                "content_type": response.headers.get("Content-Type"),
                "body": raw.decode(charset, errors="replace"),
            }
    except urllib.error.HTTPError as exc:
        details = exc.read(1000).decode("utf-8", errors="replace")
        raise CliError("http_error", f"HTTP {exc.code} while fetching URL", status=exc.code, details=details)
    except urllib.error.URLError as exc:
        raise CliError("network_error", "Network request failed", details=str(exc.reason))
    except TimeoutError:
        raise CliError("timeout", "Network request timed out")


def guess_content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in (".html", ".htm"):
        return "text/html"
    if suffix in (".md", ".markdown"):
        return "text/markdown"
    return "text/plain"


def safe_headers(headers: dict[str, str]) -> dict[str, str]:
    blocked = {"authorization", "cookie", "set-cookie", "proxy-authorization"}
    return {k: ("***" if k.lower() in blocked else v) for k, v in headers.items()}


def find_title(html_text: str) -> str | None:
    patterns = [
        r"<meta[^>]+property=['\"]og:title['\"][^>]+content=['\"]([^'\"]+)['\"]",
        r"<meta[^>]+name=['\"]twitter:title['\"][^>]+content=['\"]([^'\"]+)['\"]",
        r"<title[^>]*>(.*?)</title>",
        r"<h1[^>]*>(.*?)</h1>",
    ]
    for pattern in patterns:
        match = re.search(pattern, html_text, re.IGNORECASE | re.DOTALL)
        if match:
            return clean_plain(match.group(1))
    return None


def clean_plain(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def extract_fragment(html_text: str, selector: str) -> tuple[str, str]:
    selectors = [selector] if selector != "auto" else ["article", "main", "body"]
    for tag in selectors:
        if tag == "body":
            pattern = r"<body\b[^>]*>(.*?)</body>"
        elif tag in ("article", "main"):
            pattern = rf"<{tag}\b[^>]*>(.*?)</{tag}>"
        else:
            continue
        match = re.search(pattern, html_text, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1), tag
    return html_text, "document"


def extract_article(source_info: dict[str, Any], *, selector: str = "auto") -> dict[str, Any]:
    body = source_info["body"]
    content_type = (source_info.get("content_type") or "").lower()
    is_html = "<html" in body.lower() or "<article" in body.lower() or "text/html" in content_type
    title = find_title(body) if is_html else None
    if is_html:
        fragment, selector_used = extract_fragment(body, selector)
        parser = TextExtractor()
        parser.feed(fragment)
        text = parser.text()
        links = parser.links
        images = parser.images
    else:
        selector_used = "plain_text"
        text = body.strip()
        links = []
        images = []
    headings = extract_headings(text)
    markdown = normalize_markdown(text, title)
    return {
        "source": {
            "input": source_info["source"],
            "kind": source_info["kind"],
            "status": source_info["status"],
            "final_url": source_info["final_url"],
            "content_type": source_info["content_type"],
            "bytes": source_info["bytes"],
        },
        "title": title,
        "selector_used": selector_used,
        "text": text,
        "markdown": markdown,
        "headings": headings,
        "links": links,
        "images": images,
        "stats": {
            "chars": len(text),
            "words": count_words(text),
            "heading_count": len(headings),
            "link_count": len(links),
            "image_count": len(images),
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        },
    }


def normalize_markdown(text: str, title: str | None) -> str:
    out = text.strip()
    if title and not out.lstrip().startswith("# "):
        out = f"# {title}\n\n{out}"
    return out.strip() + "\n"


def extract_headings(markdown: str) -> list[dict[str, Any]]:
    headings = []
    for line_no, line in enumerate(markdown.splitlines(), start=1):
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if match:
            headings.append({"level": len(match.group(1)), "line": line_no, "text": match.group(2)})
    return headings


def count_words(text: str) -> int:
    return len(re.findall(r"\w+", text, flags=re.UNICODE))


def truncate_text(text: str, max_chars: int | None) -> tuple[str, bool]:
    if max_chars is None or max_chars <= 0 or len(text) <= max_chars:
        return text, False
    cut = text[:max_chars].rstrip()
    paragraph = cut.rfind("\n\n")
    if paragraph > max_chars * 0.5:
        cut = cut[:paragraph].rstrip()
    return cut + "\n", True


def command_doctor(args: argparse.Namespace) -> dict[str, Any]:
    result: dict[str, Any] = {
        "version": __version__,
        "python": sys.version.split()[0],
        "auth_required": False,
        "network_required": False,
        "default_user_agent": args.user_agent,
        "commands": {
            "python3": shutil.which("python3"),
        },
        "url_check": {"ran": False},
    }
    if args.check_url:
        started = time.monotonic()
        info = read_source(args.check_url, timeout=args.timeout, user_agent=args.user_agent, max_bytes=8192)
        result["url_check"] = {
            "ran": True,
            "status": info["status"],
            "content_type": info["content_type"],
            "bytes_read": info["bytes"],
            "elapsed_seconds": round(time.monotonic() - started, 2),
        }
    return result


def read_and_extract(args: argparse.Namespace) -> dict[str, Any]:
    source = args.url
    info = read_source(source, timeout=args.timeout, user_agent=args.user_agent, max_bytes=args.max_bytes)
    article = extract_article(info, selector=args.selector)
    content = article["markdown"] if args.format == "md" else article["text"]
    content, truncated = truncate_text(content, args.max_chars)
    article["content"] = content
    article["format"] = args.format
    article["truncated"] = truncated
    if args.no_links:
        article.pop("links", None)
    if args.no_images:
        article.pop("images", None)
    return article


def command_summary_input(args: argparse.Namespace) -> dict[str, Any]:
    args.format = "md"
    article = read_and_extract(args)
    content, truncated = truncate_text(article["markdown"], args.max_chars)
    return {
        "source": article["source"],
        "title": article["title"],
        "selector_used": article["selector_used"],
        "content": content,
        "truncated": truncated,
        "stats": article["stats"],
        "prompt_hint": "Summarize key claims, evidence, caveats, and relevance to the user's context.",
    }


def command_request_get(args: argparse.Namespace) -> dict[str, Any]:
    info = read_source(args.url, timeout=args.timeout, user_agent=args.user_agent, max_bytes=args.max_bytes)
    body = info.pop("body")
    preview, truncated = truncate_text(body, args.preview_chars)
    return {
        **info,
        "body_preview": preview,
        "body_preview_truncated": truncated,
    }


def render_human(args: argparse.Namespace, data: dict[str, Any]) -> str:
    if args.command in ("read", "extract"):
        return data["content"]
    if args.command == "summary-input":
        return data["content"]
    return json.dumps(data, ensure_ascii=False, indent=2)


def emit(args: argparse.Namespace, command: str, data: dict[str, Any]) -> None:
    if args.json:
        print(json.dumps({"ok": True, "command": command, "data": data}, ensure_ascii=False, indent=2, default=json_default))
        return
    print(render_human(args, data), end="" if args.command in ("read", "extract", "summary-input") else "\n")


def fail(args: argparse.Namespace | None, error: CliError) -> int:
    payload = {
        "ok": False,
        "error": {
            "type": error.kind,
            "message": error.message,
            "status": error.status,
            "details": error.details,
        },
    }
    if args is not None and getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=json_default), file=sys.stderr)
    else:
        print(f"article: {error.message}", file=sys.stderr)
        if error.details:
            print(str(error.details), file=sys.stderr)
    return error.exit_code


def add_fetch_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("url", help="URL, local file path, file:// path, or '-' for stdin.")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    parser.add_argument("--max-bytes", type=int, default=None, help="Maximum source bytes to read.")


def add_extract_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--selector", choices=("auto", "article", "main", "body"), default="auto")
    parser.add_argument("--format", choices=("md", "text"), default="md")
    parser.add_argument("--max-chars", type=int, default=None, help="Truncate extracted content.")
    parser.add_argument("--no-links", action="store_true")
    parser.add_argument("--no-images", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="article",
        description="Fetch and extract clean article text as Markdown, text, or JSON.",
    )
    parser.add_argument("--json", action="store_true", help="Emit stable JSON envelope.")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="Check local runtime and optional URL reachability.")
    doctor.add_argument("--timeout", type=float, default=10.0)
    doctor.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    doctor.add_argument("--check-url", help="Optional read-only URL check.")
    doctor.set_defaults(func=command_doctor, command_name="doctor")

    read = sub.add_parser("read", help="Fetch and extract an article.")
    add_fetch_args(read)
    add_extract_args(read)
    read.set_defaults(func=read_and_extract, command_name="read")

    extract = sub.add_parser("extract", help="Alias for read, useful in pipelines.")
    add_fetch_args(extract)
    add_extract_args(extract)
    extract.set_defaults(func=read_and_extract, command_name="extract")

    summary = sub.add_parser("summary-input", help="Prepare bounded Markdown input for summarization.")
    add_fetch_args(summary)
    summary.add_argument("--selector", choices=("auto", "article", "main", "body"), default="auto")
    summary.add_argument("--max-chars", type=int, default=12000)
    summary.add_argument("--no-links", action="store_true")
    summary.add_argument("--no-images", action="store_true")
    summary.set_defaults(func=command_summary_input, command_name="summary-input")

    request = sub.add_parser("request", help="Raw read-only HTTP/file request helpers.")
    request_sub = request.add_subparsers(dest="request_command", required=True)
    get = request_sub.add_parser("get", help="GET a URL or read a local file and return metadata plus preview.")
    add_fetch_args(get)
    get.add_argument("--preview-chars", type=int, default=2000)
    get.set_defaults(func=command_request_get, command_name="request get")

    return parser


def preprocess_argv(argv: list[str]) -> tuple[list[str], bool]:
    json_flag = False
    cleaned = []
    for item in argv:
        if item == "--json":
            json_flag = True
        else:
            cleaned.append(item)
    return cleaned, json_flag


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    cleaned_argv, json_flag = preprocess_argv(raw_argv)
    parser = build_parser()
    args: argparse.Namespace | None = None
    try:
        args = parser.parse_args(cleaned_argv)
        args.json = bool(args.json or json_flag)
        data = args.func(args)
        emit(args, args.command_name, data)
        return 0
    except CliError as exc:
        return fail(args, exc)
    except KeyboardInterrupt:
        return fail(args, CliError("interrupted", "Interrupted", exit_code=130))


if __name__ == "__main__":
    raise SystemExit(main())
