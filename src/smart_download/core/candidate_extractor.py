"""
HTML candidate discovery, web scraping parser, and redirect resolution.
"""
import os
import sys
import re
import ssl
import urllib.request
import urllib.parse
import urllib.error
from html.parser import HTMLParser
from typing import List, Dict, Optional, Tuple, Any

from .chunk import get_permissive_ssl_context
from ..utils.url_utils import (
    is_downloadable_url,
    derive_download_filename,
    is_potential_html_url,
    parse_filename_from_cd_header,
    COMMON_DOWNLOAD_EXTENSIONS,
)

class _HtmlCandidateExtractor(HTMLParser):
    """
    Extracts structured download candidates and page metadata from HTML.
    Collects <a> tags, <meta refresh>, and data attributes.
    """
    def __init__(self):
        super().__init__()
        self.raw_items: List[Dict[str, Any]] = []
        self._current_tag: Optional[str] = None
        self._current_attrs: Dict[str, str] = {}
        self._current_text: List[str] = []
        self.page_title: str = ""
        self._in_title: bool = False

    def handle_starttag(self, tag, attrs):
        attr_dict = {k.lower(): (v or "") for k, v in attrs}
        tag_lower = tag.lower()

        if tag_lower == "title":
            self._in_title = True
        elif tag_lower == "a":
            self._current_tag = "a"
            self._current_attrs = attr_dict
            self._current_text = []
        elif tag_lower == "meta" and attr_dict.get("http-equiv", "").lower() == "refresh":
            content = attr_dict.get("content", "")
            m = re.search(r"url\s*=\s*(?:['\"]([^'\"]+)['\"]|([^;\s'\"]+))", content, re.IGNORECASE)
            if m:
                u = m.group(1) or m.group(2)
                if u:
                    self.raw_items.append({
                        "href": u.strip(),
                        "text": "Auto Redirect",
                        "title": "",
                        "aria_label": "",
                        "download": "",
                        "tag": "meta"
                    })

        for k, v in attr_dict.items():
            if k.startswith("data-download") or k in ("data-href", "data-url", "data-src", "data-link"):
                if v and tag_lower != "a":
                    self.raw_items.append({
                        "href": v.strip(),
                        "text": attr_dict.get("title") or attr_dict.get("aria-label") or "",
                        "title": attr_dict.get("title", ""),
                        "aria_label": attr_dict.get("aria-label", ""),
                        "download": attr_dict.get("download", ""),
                        "tag": tag_lower
                    })

    def handle_data(self, data):
        if self._in_title:
            self.page_title += data
        if self._current_tag == "a":
            self._current_text.append(data)

    def handle_endtag(self, tag):
        tag_lower = tag.lower()
        if tag_lower == "title":
            self._in_title = False
        elif tag_lower == "a" and self._current_tag == "a":
            href = self._current_attrs.get("href", "").strip()
            if href:
                text_content = " ".join("".join(self._current_text).split())
                self.raw_items.append({
                    "href": href,
                    "text": text_content,
                    "title": self._current_attrs.get("title", ""),
                    "aria_label": self._current_attrs.get("aria-label", ""),
                    "download": self._current_attrs.get("download", ""),
                    "tag": "a"
                })
            self._current_tag = None
            self._current_attrs = {}
            self._current_text = []


def resolve_all_download_candidates(
    url_or_html: str,
    base_url: str = "",
    timeout: float = 10.0,
    ssl_context: Optional[ssl.SSLContext] = None
) -> List[Dict[str, Any]]:
    """
    Extracts and ranks all valid downloadable links from an HTML document or landing URL.

    Filters out non-downloadable links (nav links, terms of service, social media, anchors).
    Deduplicates and cleans candidate URLs.

    Each candidate dict contains:
        {
            "url": direct_url,
            "filename": filename,
            "ext": ext,
            "size_bytes": None or int,
            "title": text_label,
            "score": score
        }
    Guaranteed never to raise unhandled exceptions.
    """
    raw_input = str(url_or_html or "").strip()
    if not raw_input:
        return []

    is_url = False
    html_text = ""
    effective_base_url = str(base_url or "").strip()

    # Detect if raw_input is an HTTP URL rather than raw HTML markup
    if (raw_input.startswith(("http://", "https://")) and
        "\n" not in raw_input and
        "<html" not in raw_input.lower() and
        "<body" not in raw_input.lower() and
        "<a " not in raw_input.lower()):
        is_url = True

    if is_url:
        if not effective_base_url:
            effective_base_url = raw_input
        ctx = ssl_context if ssl_context is not None else get_permissive_ssl_context()
        custom_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }
        try:
            req = urllib.request.Request(raw_input, headers=custom_headers)
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                final_u = resp.geturl() or raw_input
                effective_base_url = final_u
                ct = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                if ct not in ("text/html", "application/xhtml+xml"):
                    return []
                raw_bytes = resp.read(1024 * 1024)
                charset = resp.headers.get_content_charset() or "utf-8"
                try:
                    html_text = raw_bytes.decode(charset, errors="replace")
                except Exception:
                    html_text = raw_bytes.decode("utf-8", errors="replace")
        except Exception:
            return []
    else:
        html_text = raw_input

    if not html_text:
        return []

    extractor = _HtmlCandidateExtractor()
    try:
        extractor.feed(html_text)
    except Exception:
        pass

    raw_items = list(extractor.raw_items)

    # Inline script navigation and fallback regexes
    script_patterns = [
        r'(?:window\.)?location(?:\.href)?\s*=\s*[\'"]([^\'"]+)[\'"]',
        r'(?:window\.)?location\.(?:assign|replace)\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)',
        r'window\.open\s*\(\s*[\'"]([^\'"]+)[\'"]',
        r'(?:data-download[a-z0-9_-]*|data-href|data-url)\s*=\s*[\'"]([^\'"]+)[\'"]',
        r'<meta[^>]*?content=[\'"][^>]*?url=([^;\'"\s>]+)[\'"]'
    ]
    for pat in script_patterns:
        for m in re.finditer(pat, html_text, re.IGNORECASE):
            u = m.group(1).strip()
            if u:
                raw_items.append({
                    "href": u,
                    "text": "Script Redirect",
                    "title": "",
                    "aria_label": "",
                    "download": "",
                    "tag": "script"
                })

    for s_m in re.finditer(r'<script[^>]*>(.*?)</script>', html_text, re.IGNORECASE | re.DOTALL):
        script_body = s_m.group(1).replace(r'\/', '/')
        for url_m in re.finditer(r'https?://[^\s"\'<>\\]+', script_body, re.IGNORECASE):
            raw_items.append({
                "href": url_m.group(0),
                "text": "Script Link",
                "title": "",
                "aria_label": "",
                "download": "",
                "tag": "script"
            })

    ignored_schemes = ("#", "javascript:", "mailto:", "tel:", "data:", "about:")
    ignored_exts = {
        ".css", ".js", ".woff", ".woff2", ".svg", ".png", ".jpg", ".jpeg",
        ".gif", ".ico", ".webmanifest", ".map", ".ttf", ".eot", ".otf"
    }
    preferred_installer_exts = {
        ".exe", ".msi", ".zip", ".7z", ".rar", ".dmg", ".apk", ".iso",
        ".appx", ".appxbundle", ".msix", ".msixbundle", ".pkg", ".deb", ".rpm"
    }
    social_domains = {
        "twitter.com", "x.com", "facebook.com", "fb.com", "instagram.com",
        "linkedin.com", "t.me", "telegram.org", "reddit.com", "tiktok.com",
        "discord.gg", "discord.com", "pinterest.com"
    }
    non_download_keywords = {
        "privacy", "terms", "about", "contact", "login", "signin", "signup",
        "register", "logout", "faq", "help", "support", "license", "cookie",
        "legal", "blog", "pricing"
    }

    base_p_split = urllib.parse.urlsplit(effective_base_url) if effective_base_url else None
    base_clean = (base_p_split.scheme.lower(), base_p_split.netloc.lower(), base_p_split.path.rstrip("/")) if base_p_split else None

    src_query = (base_p_split.query or "").lower() if base_p_split else ""
    platform_tokens: List[str] = []
    if any(k in src_query for k in ("platform=windows", "os=win", "os=windows", "windows", "win")):
        platform_tokens = ["windows", "win", "x64", "win64", "x86"]
    elif any(k in src_query for k in ("platform=mac", "os=mac", "macos", "darwin", "osx")):
        platform_tokens = ["mac", "macos", "darwin", "dmg", "pkg"]
    elif any(k in src_query for k in ("platform=linux", "os=linux", "linux")):
        platform_tokens = ["linux", "appimage", "deb", "rpm", "tar.gz"]
    elif sys.platform == "win32":
        platform_tokens = ["windows", "win", "x64", "setup", "installer"]

    seen_dict: Dict[str, Dict[str, Any]] = {}

    for item in raw_items:
        raw_href = item["href"].strip("\"' \t\r\n")
        if not raw_href or raw_href.startswith(ignored_schemes):
            continue

        try:
            abs_url = urllib.parse.urljoin(effective_base_url, raw_href) if effective_base_url else raw_href
            p = urllib.parse.urlsplit(abs_url)
            if p.scheme.lower() not in ("http", "https") or not p.netloc:
                continue

            netloc_lower = p.netloc.lower()
            if any(netloc_lower == sd or netloc_lower.endswith("." + sd) for sd in social_domains):
                continue

            # Skip self-referencing links
            cand_clean = (p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"))
            if base_clean and cand_clean == base_clean and not p.query:
                continue

            path_lower = p.path.lower()
            query_lower = (p.query or "").lower()
            combined_target = path_lower + ("?" + query_lower if query_lower else "")

            # Multi-part extension support
            ext = ""
            for multi_ext in (".tar.gz", ".tar.bz2", ".tar.xz", ".user.js"):
                if path_lower.endswith(multi_ext):
                    ext = multi_ext
                    break
            if not ext:
                _, ext = os.path.splitext(path_lower)

            if ext in ignored_exts:
                continue

            # Determine whether link is downloadable
            has_dl_ext = (ext in preferred_installer_exts) or (ext in COMMON_DOWNLOAD_EXTENSIONS)
            has_dl_attr = bool(item.get("download"))
            has_dl_path = any(dp in path_lower for dp in ("/download", "/downloads", "/releases/download/", "/files/", "/get_file/", "/releases/"))
            has_dl_query = any(dq in query_lower for dq in ("download=", "export=download", "dl=1", "action=download", "file="))

            link_text = (item.get("text") or "").strip()
            link_title = (item.get("title") or item.get("aria_label") or "").strip()
            text_lower = (link_text + " " + link_title).lower()
            has_dl_text = any(tok in text_lower for tok in ("download", "\u062a\u062d\u0645\u064a\u0644", "installer", "setup", "portable", "x64", "64-bit", "32-bit", "arm64", "build"))

            if not (has_dl_ext or has_dl_attr or has_dl_path or has_dl_query or has_dl_text):
                continue

            if not has_dl_ext:
                if any(kw in path_lower or kw in query_lower for kw in non_download_keywords):
                    continue

            # Derive filename
            cd_fn = item.get("download", "").strip()
            if cd_fn:
                filename = cd_fn
            else:
                base_fn = os.path.basename(urllib.parse.unquote(p.path.rstrip("/")))
                if base_fn and base_fn not in (".", ".."):
                    filename = base_fn
                else:
                    filename = derive_download_filename(abs_url)

            cand_ext = ""
            for multi_ext in (".tar.gz", ".tar.bz2", ".tar.xz", ".user.js"):
                if filename.lower().endswith(multi_ext):
                    cand_ext = multi_ext
                    break
            if not cand_ext:
                _, cand_ext = os.path.splitext(filename.lower())

            text_label = link_text or link_title or filename
            if len(text_label) > 100:
                text_label = text_label[:97] + "..."

            size_bytes: Optional[int] = None
            size_m = re.search(r'\(?\b(\d+(?:\.\d+)?)\s*(KB|MB|GB|Bytes)\b\)?', text_lower, re.IGNORECASE)
            if size_m:
                val = float(size_m.group(1))
                unit = size_m.group(2).upper()
                if unit == "KB":
                    size_bytes = int(val * 1024)
                elif unit == "MB":
                    size_bytes = int(val * 1024 * 1024)
                elif unit == "GB":
                    size_bytes = int(val * 1024 * 1024 * 1024)
                elif unit == "BYTES":
                    size_bytes = int(val)

            score = 0
            if cand_ext in preferred_installer_exts:
                score += 1000
            elif cand_ext in COMMON_DOWNLOAD_EXTENSIONS:
                score += 500

            if "/releases/download/" in path_lower:
                score += 350
            elif "/download" in path_lower or "/downloads" in path_lower:
                score += 200

            if any(tok in combined_target or tok in text_lower for tok in platform_tokens):
                score += 250

            if has_dl_attr:
                score += 200
            if has_dl_text:
                score += 100

            if path_lower in ("", "/"):
                score -= 600

            canonical_url = urllib.parse.urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path, p.query, ""))

            candidate_obj = {
                "url": abs_url,
                "filename": filename,
                "ext": cand_ext,
                "size_bytes": size_bytes,
                "title": text_label,
                "score": score
            }

            if canonical_url in seen_dict:
                existing = seen_dict[canonical_url]
                if score > existing["score"]:
                    seen_dict[canonical_url] = candidate_obj
                elif score == existing["score"] and len(text_label) > len(existing["title"]):
                    seen_dict[canonical_url] = candidate_obj
            else:
                seen_dict[canonical_url] = candidate_obj

        except Exception:
            continue

    candidates = list(seen_dict.values())
    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates

