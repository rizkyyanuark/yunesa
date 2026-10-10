#!/usr/bin/env python3
"""Remove credentials from JSON network evidence before sharing it."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

REDACTED = "[REDACTED]"
SENSITIVE_NAME = re.compile(
    r"password|passwd|pwd|secret|token|credential|authorization|cookie|"
    r"apikey|privatekey|accesskey|sessionid|csrf|xsrf",
    re.IGNORECASE,
)
MULTIPART_PART = re.compile(
    r"(?P<headers>Content-Disposition:\s*form-data;[^\r\n]*"
    r"(?:\r?\n(?!\r?\n)[^\r\n]*)*\r?\n\r?\n)"
    r"(?P<value>.*?)(?=\r?\n--[^\r\n]+(?:\r?\n|$))",
    re.IGNORECASE | re.DOTALL,
)
MULTIPART_NAME = re.compile(r'\bname="(?P<name>[^"\r\n]+)"', re.IGNORECASE)
AUTH_VALUE = re.compile(r"\b(?:Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
PRIVATE_KEY = re.compile(
    r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----.*?"
    r"-----END (?:[A-Z ]+ )?PRIVATE KEY-----",
    re.DOTALL,
)
PROVIDER_TOKEN = re.compile(
    r"\b(?:glpat-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{20,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|AIza[A-Za-z0-9_-]{30,}|"
    r"sk-[A-Za-z0-9_-]{16,}|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)\b"
)
TEXT_FIELD = re.compile(
    r"(?P<prefix>\b(?:password|passwd|pwd|secret|api[_-]?key|"
    r"access[_-]?token|refresh[_-]?token|authorization|cookie)[\"']?\s*[:=]\s*)"
    r"(?P<value>[^\r\n]+)",
    re.IGNORECASE,
)


def sensitive_name(name: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", name.lower())
    if normalized in {
        "accesscontrolallowcredentials",
        "tokentype",
        "tokencount",
        "maxtokens",
        "inputtokens",
        "outputtokens",
        "totaltokens",
        "completiontokens",
        "prompttokens",
    }:
        return False
    return normalized == "key" or SENSITIVE_NAME.search(normalized) is not None


def sensitive_query_name(name: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", name.lower())
    return normalized in {"code", "state", "sig", "signature", "xamzsignature"} or sensitive_name(name)


class Sanitizer:
    def __init__(self) -> None:
        self.redactions = 0

    def redact(self, value: object) -> str:
        if value not in (None, "", REDACTED):
            self.redactions += 1
        return REDACTED

    def sanitize(self, value: object) -> object:
        if isinstance(value, dict):
            named_secret = isinstance(value.get("name"), str) and sensitive_name(value["name"])
            return {
                name: self.redact(item)
                if sensitive_name(name) or (name == "value" and named_secret)
                else self.sanitize(item)
                for name, item in value.items()
            }
        if isinstance(value, list):
            return [self.sanitize(item) for item in value]
        if isinstance(value, str):
            return self.sanitize_text(value)
        return value

    def sanitize_text(self, value: str) -> str:
        if value == REDACTED:
            return value
        stripped = value.strip()
        if stripped.startswith(("{", "[")):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                pass
            else:
                sanitized = self.sanitize(parsed)
                if parsed != sanitized:
                    return json.dumps(sanitized, ensure_ascii=False)
                return value

        def redact_part(match: re.Match[str]) -> str:
            field = MULTIPART_NAME.search(match.group("headers"))
            if field is not None and sensitive_name(field.group("name")):
                return match.group("headers") + self.redact(match.group("value"))
            return match.group(0)

        value = MULTIPART_PART.sub(redact_part, value)
        structured_fields = False
        if stripped.startswith(("http://", "https://", "ws://", "wss://")) or (
            stripped.startswith("/") and ("?" in stripped or "#" in stripped)
        ):
            value = self.sanitize_url(value)
            structured_fields = True
        elif "=" in value and "\n" not in value:
            fields = parse_qsl(value, keep_blank_values=True)
            if any(sensitive_name(name) for name, _ in fields):
                value = urlencode(
                    [(name, self.redact(item) if sensitive_name(name) else item) for name, item in fields]
                )
                structured_fields = True

        value = PRIVATE_KEY.sub(lambda match: self.redact(match.group(0)), value)
        value = AUTH_VALUE.sub(lambda match: self.redact(match.group(0)), value)
        value = PROVIDER_TOKEN.sub(lambda match: self.redact(match.group(0)), value)
        if structured_fields:
            return value
        return TEXT_FIELD.sub(lambda match: match.group("prefix") + self.redact(match.group("value")), value)

    def sanitize_url(self, value: str) -> str:
        try:
            parts = urlsplit(value)
        except ValueError:
            return self.redact(value)
        fields = parse_qsl(parts.query, keep_blank_values=True)
        query = parts.query
        if any(sensitive_query_name(name) for name, _ in fields):
            query = urlencode(
                [(name, self.redact(item) if sensitive_query_name(name) else item) for name, item in fields]
            )
        netloc = parts.netloc
        if "@" in netloc:
            credentials, host = netloc.rsplit("@", 1)
            self.redact(credentials)
            netloc = host
        fragment = parts.fragment
        fragment_fields = parse_qsl(fragment, keep_blank_values=True)
        if any(sensitive_query_name(name) for name, _ in fragment_fields):
            fragment = urlencode(
                [(name, self.redact(item) if sensitive_query_name(name) else item) for name, item in fragment_fields]
            )
        return urlunsplit((parts.scheme, netloc, parts.path, query, fragment))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Exit 1 if more redaction is needed")
    mode.add_argument("--write", action="store_true", help="Sanitize JSON files in place")
    parser.add_argument("paths", type=Path, nargs="+")
    args = parser.parse_args()
    unsafe = False
    for path in args.paths:
        try:
            original = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            print(f"{path.name}: cannot inspect JSON ({type(error).__name__})")
            return 2
        sanitizer = Sanitizer()
        sanitized = sanitizer.sanitize(original)
        changed = original != sanitized
        unsafe = unsafe or changed
        if args.write and changed:
            try:
                path.write_text(json.dumps(sanitized, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            except (OSError, UnicodeError) as error:
                print(f"{path.name}: cannot save sanitized JSON ({type(error).__name__})")
                return 2
        status = "sanitized" if args.write and changed else "needs redaction" if changed else "clean"
        print(f"{path.name}: {status}; additional redactions={sanitizer.redactions}")
    return 1 if args.check and unsafe else 0


if __name__ == "__main__":
    raise SystemExit(main())
