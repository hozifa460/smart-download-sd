"""
Speed parsing and formatting utilities for Smart Download (SD).
"""
import re
from typing import Any


def parse_speed_limit(val_str: Any) -> float:
    """
    Parses speed limit string into bytes per second. Returns 0.0 for unlimited.
    Accepts: 'Unlimited', '500 KB/s', '1 MB/s', '2.5 MB/s', '1024', etc.
    """
    if not val_str:
        return 0.0
    s = str(val_str).strip().lower()
    if s in ("unlimited", "0", "0.0", "none", "off", "max", ""):
        return 0.0

    # 1. Gigabytes per second
    m_gb = re.search(r"([\d\.]+)\s*(gb/s|g/s|gbps|gib/s|gib|gb)", s)
    if m_gb:
        try:
            return float(m_gb.group(1)) * 1024.0 * 1024.0 * 1024.0
        except ValueError:
            return 0.0
    # 2. Megabytes per second
    m_mb = re.search(r"([\d\.]+)\s*(mb/s|m/s|mbps|mib/s|mib|mb)", s)
    if m_mb:
        try:
            return float(m_mb.group(1)) * 1024.0 * 1024.0
        except ValueError:
            return 0.0
    # 3. Kilobytes per second
    m_kb = re.search(r"([\d\.]+)\s*(kb/s|k/s|kbps|kib/s|kib|kb)", s)
    if m_kb:
        try:
            return float(m_kb.group(1)) * 1024.0
        except ValueError:
            return 0.0
    # 4. Bytes per second
    m_b = re.search(r"([\d\.]+)\s*(bytes/s|byte/s|bytes|b/s|bps|b)", s)
    if m_b:
        try:
            return float(m_b.group(1))
        except ValueError:
            return 0.0
    # 5. Short single-letter suffixes e.g. '10m', '500k', '1g'
    m_suf = re.search(r"^([\d\.]+)\s*([gmkb])$", s)
    if m_suf:
        try:
            val = float(m_suf.group(1))
            unit = m_suf.group(2)
            if unit == "g":
                return val * 1024.0 * 1024.0 * 1024.0
            if unit == "m":
                return val * 1024.0 * 1024.0
            if unit == "k":
                return val * 1024.0
            if unit == "b":
                return val
        except ValueError:
            return 0.0
    try:
        val = float(s)
        if val < 100000.0:
            return val * 1024.0
        return val
    except ValueError:
        return 0.0


def format_speed(speed: Any, allow_unlimited: bool = False) -> str:
    """Format speed value in bytes/sec into a human-readable string (e.g. '0 B/s', '500 B/s', '1.0 KB/s', '2.50 MB/s', '1.00 GB/s')."""
    try:
        val = float(speed)
    except (TypeError, ValueError):
        val = 0.0

    if val <= 0:
        return "Unlimited" if allow_unlimited else "0 B/s"

    if val >= 1024 * 1024 * 1024:
        return f"{val / (1024 * 1024 * 1024):.2f} GB/s"
    if val >= 1024 * 1024:
        return f"{val / (1024 * 1024):.2f} MB/s"
    if val >= 1024:
        return f"{val / 1024:.1f} KB/s"
    return f"{val:.0f} B/s"


__all__ = ["parse_speed_limit", "format_speed"]
