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


from .candidate_extractor import (
    _HtmlCandidateExtractor,
    resolve_all_download_candidates,
)

class _HtmlLinkCandidateParser(HTMLParser):
    """Parses HTML document to collect candidate download hyperlinks and refresh targets."""
    def __init__(self):
        super().__init__()
        self.raw_candidates: List[str] = []

    def handle_starttag(self, tag, attrs):
        attr_dict = {k.lower(): (v or "") for k, v in attrs}
        tag_lower = tag.lower()

        if tag_lower == "a" and "href" in attr_dict:
            self.raw_candidates.append(attr_dict["href"])

        if tag_lower == "meta" and attr_dict.get("http-equiv", "").lower() == "refresh":
            content = attr_dict.get("content", "")
            m = re.search(r"url\s*=\s*(?:['\"]([^'\"]+)['\"]|([^;\s'\"]+))", content, re.IGNORECASE)
            if m:
                u = m.group(1) or m.group(2)
                if u:
                    self.raw_candidates.append(u.strip())

        for k, v in attr_dict.items():
            if k.startswith("data-download") or k in ("data-href", "data-url", "data-src", "data-link"):
                if v:
                    self.raw_candidates.append(v.strip())


def resolve_real_download_url(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    ssl_context: Optional[ssl.SSLContext] = None,
    timeout: float = 10.0
) -> Dict[str, Any]:
    """
    Probes a candidate download URL to verify whether it returns a direct downloadable file
    or an HTML landing / thank-you page. If an HTML page is returned, parses and ranks
    candidate download links, probes them, and returns the real direct file download URL.

    Returns:
        {
            "url": final_url,
            "is_html": bool,
            "resolved": bool,
            "content_type": str,
            "size": int,
            "filename": str,
            "error": str
        }
    Guaranteed never to raise exceptions.
    """
    clean_url = str(url or "").strip()
    result: Dict[str, Any] = {
        "url": clean_url,
        "is_html": False,
        "resolved": False,
        "content_type": "",
        "size": 0,
        "filename": "",
        "error": "",
        "candidates": [],
        "page_title": ""
    }

    if not clean_url:
        result["error"] = "URL cannot be empty."
        return result

    try:
        parsed_src = urllib.parse.urlsplit(clean_url)
        if parsed_src.scheme.lower() not in ("http", "https") or not parsed_src.netloc:
            result["error"] = "URL must start with http:// or https:// and include a valid host."
            return result
    except Exception as e:
        result["error"] = str(e)
        return result

    ctx = ssl_context if ssl_context is not None else get_permissive_ssl_context()
    custom_headers = dict(headers or {})
    if not any(k.lower() == "user-agent" for k in custom_headers):
        custom_headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    if not any(k.lower() == "accept" for k in custom_headers):
        custom_headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"

    try:
        req = urllib.request.Request(clean_url, headers=custom_headers)
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            final_url = resp.geturl() or clean_url
            raw_ct = resp.headers.get("Content-Type", "")
            content_type = raw_ct.split(";")[0].strip().lower()
            cl = resp.headers.get("Content-Length")
            size = int(cl) if cl and cl.isdigit() else 0
            cd = resp.headers.get("Content-Disposition", "")
            filename = parse_filename_from_cd_header(cd)
            if not filename:
                try:
                    p = urllib.parse.urlsplit(final_url).path
                    base_p = os.path.basename(urllib.parse.unquote(p.rstrip("/")))
                    if base_p and base_p not in (".", ".."):
                        filename = base_p
                except Exception:
                    pass

            is_html = content_type in ("text/html", "application/xhtml+xml")
            if not is_html:
                return {
                    "url": final_url,
                    "is_html": False,
                    "resolved": False,
                    "content_type": content_type,
                    "size": size,
                    "filename": filename or derive_download_filename(final_url),
                    "error": ""
                }

            # Response is HTML. Read up to 512 KB of body for link extraction.
            raw_body = resp.read(512 * 1024)
            charset = resp.headers.get_content_charset() or "utf-8"
            try:
                html_text = raw_body.decode(charset, errors="replace")
            except Exception:
                html_text = raw_body.decode("utf-8", errors="replace")

    except Exception as e:
        result["error"] = str(e)
        return result

    result["url"] = final_url
    result["is_html"] = True
    result["content_type"] = content_type
    result["size"] = size
    result["filename"] = filename or derive_download_filename(final_url)

    # Extract all candidates and page title
    all_candidates = resolve_all_download_candidates(html_text, base_url=final_url)
    result["candidates"] = all_candidates

    extractor_title = ""
    try:
        _pe = _HtmlCandidateExtractor()
        _pe.feed(html_text)
        extractor_title = _pe.page_title.strip()
    except Exception:
        pass
    result["page_title"] = extractor_title

    # Collect link candidates
    parser = _HtmlLinkCandidateParser()
    try:
        parser.feed(html_text)
    except Exception:
        pass

    raw_candidates = list(parser.raw_candidates)

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
                raw_candidates.append(u)

    # Extract absolute URLs and paths from inline <script> blocks
    for s_m in re.finditer(r'<script[^>]*>(.*?)</script>', html_text, re.IGNORECASE | re.DOTALL):
        script_body = s_m.group(1)
        clean_script = script_body.replace(r'\/', '/')
        for url_m in re.finditer(r'https?://[^\s"\'<>\\]+', clean_script, re.IGNORECASE):
            raw_candidates.append(url_m.group(0))

    ignored_exts = {
        ".css", ".js", ".woff", ".woff2", ".svg", ".png", ".jpg", ".jpeg",
        ".gif", ".ico", ".webmanifest", ".map", ".ttf", ".eot", ".otf"
    }
    preferred_installer_exts = {
        ".exe", ".msi", ".zip", ".7z", ".rar", ".dmg", ".apk", ".iso"
    }

    # Extract platform hints from source query
    src_query = (parsed_src.query or "").lower()
    platform_tokens: List[str] = []
    if any(k in src_query for k in ("platform=windows", "os=win", "os=windows", "windows", "win")):
        platform_tokens = ["windows", "win", "x64", "win64", "x86"]
    elif any(k in src_query for k in ("platform=mac", "os=mac", "macos", "darwin", "osx")):
        platform_tokens = ["mac", "macos", "darwin", "dmg", "pkg"]
    elif any(k in src_query for k in ("platform=linux", "os=linux", "linux")):
        platform_tokens = ["linux", "appimage", "deb", "rpm", "tar.gz"]
    elif sys.platform == "win32":
        platform_tokens = ["windows", "win", "x64"]

    final_split = urllib.parse.urlsplit(final_url)
    clean_final_no_frag = (final_split.scheme, final_split.netloc, final_split.path)
    src_split_no_frag = (parsed_src.scheme, parsed_src.netloc, parsed_src.path)

    seen = set()
    scored_candidates: List[Tuple[int, str]] = []

    for raw in raw_candidates:
        u_str = raw.strip("\"' \t\r\n")
        if not u_str or u_str.startswith(("#", "javascript:", "mailto:", "tel:", "data:", "about:")):
            continue
        try:
            abs_u = urllib.parse.urljoin(final_url, u_str)
            p = urllib.parse.urlsplit(abs_u)
            if p.scheme.lower() not in ("http", "https") or not p.netloc:
                continue

            # Skip self-referencing links
            cand_no_frag = (p.scheme, p.netloc, p.path)
            if cand_no_frag == clean_final_no_frag or cand_no_frag == src_split_no_frag:
                continue

            path_lower = p.path.lower()
            query_lower = (p.query or "").lower()
            cand_str = path_lower + ("?" + query_lower if query_lower else "")

            _, ext = os.path.splitext(path_lower)
            if ext in ignored_exts:
                continue

            if abs_u in seen:
                continue
            seen.add(abs_u)

            score = 0
            if ext in preferred_installer_exts:
                score += 1000
            elif ext in COMMON_DOWNLOAD_EXTENSIONS:
                score += 500

            has_dl = ("/download" in path_lower or "/downloads" in path_lower)
            has_plat = any(tok in cand_str for tok in platform_tokens)

            if has_dl and has_plat:
                score += 400
            elif has_dl:
                score += 150
            elif has_plat:
                score += 100

            if "/releases/download/" in path_lower:
                score += 350
            elif "/releases/" in path_lower:
                score += 150

            if path_lower in ("", "/"):
                score -= 600

            scored_candidates.append((score, abs_u))
        except Exception:
            continue

    scored_candidates.sort(key=lambda x: x[0], reverse=True)
    top_candidates = [u for _, u in scored_candidates[:5]]

    probe_headers = dict(custom_headers)
    for cand_url in top_candidates:
        # Probe with HEAD
        head_ok = False
        try:
            h_req = urllib.request.Request(cand_url, method="HEAD", headers=probe_headers)
            with urllib.request.urlopen(h_req, timeout=timeout, context=ctx) as c_resp:
                c_final = c_resp.geturl() or cand_url
                c_ct = (c_resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                c_cl = c_resp.headers.get("Content-Length")
                c_size = int(c_cl) if c_cl and c_cl.isdigit() else 0
                c_cd = c_resp.headers.get("Content-Disposition", "")
                c_fn = parse_filename_from_cd_header(c_cd)
                if not c_fn:
                    try:
                        c_p = urllib.parse.urlsplit(c_final).path
                        c_base = os.path.basename(urllib.parse.unquote(c_p.rstrip("/")))
                        if c_base and c_base not in (".", ".."):
                            c_fn = c_base
                    except Exception:
                        pass

                if c_ct and c_ct not in ("text/html", "application/xhtml+xml"):
                    return {
                        "url": c_final,
                        "is_html": False,
                        "resolved": True,
                        "content_type": c_ct,
                        "size": c_size,
                        "filename": c_fn or derive_download_filename(c_final),
                        "error": "",
                        "candidates": all_candidates,
                        "page_title": extractor_title
                    }
                if not c_ct:
                    head_ok = False
                else:
                    head_ok = True
        except Exception:
            head_ok = False

        # Fallback to GET Range: bytes=0-0
        if not head_ok:
            try:
                g_headers = dict(probe_headers)
                g_headers["Range"] = "bytes=0-0"
                g_req = urllib.request.Request(cand_url, headers=g_headers)
                with urllib.request.urlopen(g_req, timeout=timeout, context=ctx) as c_resp:
                    c_final = c_resp.geturl() or cand_url
                    c_ct = (c_resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                    c_cr = c_resp.headers.get("Content-Range", "")
                    c_size = 0
                    if "/" in c_cr:
                        tot = c_cr.split("/")[-1].strip()
                        if tot.isdigit():
                            c_size = int(tot)
                    if c_size == 0:
                        c_cl = c_resp.headers.get("Content-Length")
                        c_size = int(c_cl) if c_cl and c_cl.isdigit() else 0

                    c_cd = c_resp.headers.get("Content-Disposition", "")
                    c_fn = parse_filename_from_cd_header(c_cd)
                    if not c_fn:
                        try:
                            c_p = urllib.parse.urlsplit(c_final).path
                            c_base = os.path.basename(urllib.parse.unquote(c_p.rstrip("/")))
                            if c_base and c_base not in (".", ".."):
                                c_fn = c_base
                        except Exception:
                            pass

                    if c_ct and c_ct not in ("text/html", "application/xhtml+xml"):
                        return {
                            "url": c_final,
                            "is_html": False,
                            "resolved": True,
                            "content_type": c_ct,
                            "size": c_size,
                            "filename": c_fn or derive_download_filename(c_final),
                            "error": ""
                        }
            except Exception:
                pass

    return result


def validate_refresh_url(
    new_url: str,
    expected_size: int = 0,
    check_range: bool = True,
    timeout: float = 12.0,
    ssl_context: Optional[ssl.SSLContext] = None,
    headers: Optional[Dict[str, str]] = None
) -> Tuple[bool, str, int, bool]:
    """
    Validates a candidate refresh URL via HTTP HEAD and GET Range requests.
    Verifies that the new URL is accessible, points to the same file size (if expected_size > 0),
    and accepts HTTP Range byte requests (if check_range is True).
    Returns: (is_valid: bool, status_message: str, resolved_total_size: int, supports_ranges: bool)
    """
    clean_url = str(new_url or "").strip()
    if not clean_url:
        return False, "URL cannot be empty.", 0, False

    try:
        parsed = urllib.parse.urlsplit(clean_url)
        if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
            return False, "URL must start with http:// or https:// and include a valid domain.", 0, False
    except Exception as e:
        return False, f"Malformed URL: {e}", 0, False

    ctx = ssl_context if ssl_context is not None else get_permissive_ssl_context()
    custom_headers = dict(headers or {})
    if not any(k.lower() == "user-agent" for k in custom_headers):
        custom_headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0"

    resolved_size = 0
    supports_ranges = False
    head_ok = False
    head_error_code = None
    head_error_reason = ""

    # 1. Attempt HTTP HEAD probe
    try:
        head_req = urllib.request.Request(clean_url, method="HEAD", headers=custom_headers)
        with urllib.request.urlopen(head_req, timeout=timeout, context=ctx) as resp:
            head_ok = True
            cl = resp.headers.get("Content-Length")
            ar = resp.headers.get("Accept-Ranges", "").lower()
            if cl and cl.isdigit():
                resolved_size = int(cl)
            if ar == "bytes":
                supports_ranges = True
    except urllib.error.HTTPError as e:
        e.close()
        head_error_code = e.code
        head_error_reason = str(getattr(e, "reason", e))
        # Note: Do not abort immediately on HEAD 401/403/405/501!
        # Many S3 pre-signed URLs, Cloudflare tokens, and media CDNs only sign GET,
        # rejecting HEAD with 403 or 405. We fall through to verify with GET Range probe.
    except urllib.error.URLError as e:
        return False, f"Failed to connect to host: {e.reason}", 0, False
    except Exception as e:
        return False, f"Connection error: {e}", 0, False

    # 2. Test Range support with GET Range: bytes=0-0 if check_range requested or HEAD didn't confirm ranges/size
    if check_range or not head_ok or resolved_size == 0 or not supports_ranges:
        try:
            range_req = urllib.request.Request(clean_url, headers=custom_headers)
            range_req.add_header("Range", "bytes=0-0")
            with urllib.request.urlopen(range_req, timeout=timeout, context=ctx) as resp:
                code = resp.getcode()
                cr = resp.headers.get("Content-Range", "")

                try:
                    resp.read(min(1024, resolved_size or 1024))
                except Exception:
                    pass

                if code == 206:
                    supports_ranges = True
                    if "/" in cr:
                        total_part = cr.split("/")[-1].strip()
                        if total_part.isdigit():
                            resolved_size = int(total_part)
                    # Note: If code == 206, do NOT use Content-Length as total size,
                    # because in a 206 Partial Content response for bytes=0-0,
                    # Content-Length is 1 (the slice length), NOT the total file size!
                elif code == 200:
                    # Server responded with 200 OK to a Range request, which means
                    # it IGNORED the Range header and sent the whole file body!
                    # Therefore, byte-range resuming is NOT supported!
                    supports_ranges = False
                    if not resolved_size:
                        cl = resp.headers.get("Content-Length")
                        if cl and cl.isdigit():
                            resolved_size = int(cl)
                else:
                    supports_ranges = False
        except urllib.error.HTTPError as e:
            e.close()
            if e.code in (401, 403, 410):
                return False, f"Server returned HTTP {e.code} ({e.reason}) — the download link is expired or unauthorized.", 0, False
            if e.code == 404:
                return False, f"Server returned HTTP 404: Not Found — file does not exist at this address.", 0, False
            if not head_ok:
                return False, f"Server returned HTTP {e.code} ({e.reason}).", 0, False
        except Exception as e:
            if not head_ok:
                return False, f"Range connection test failed: {e}", 0, False

    # If HEAD failed with 401/403/410 and GET Range was not verified or supported
    if not head_ok and head_error_code in (401, 403, 410) and not supports_ranges and resolved_size == 0:
        return False, f"Server returned HTTP {head_error_code} ({head_error_reason}) — link is expired or unauthorized.", 0, False

    # 3. Size match validation if an expected size was provided
    if expected_size > 0 and resolved_size > 0:
        if resolved_size != expected_size:
            return (
                False,
                f"File size mismatch: New link points to {resolved_size:,} bytes, "
                f"but existing download is {expected_size:,} bytes.",
                resolved_size,
                supports_ranges
            )

    # 4. Range requirement validation if partial chunks exist
    if check_range and not supports_ranges:
        return (
            False,
            "Server does not support HTTP Range requests (HTTP 206), which is required to resume partial chunks without restarting.",
            resolved_size,
            False
        )

    return True, "URL verified successfully.", resolved_size, supports_ranges

