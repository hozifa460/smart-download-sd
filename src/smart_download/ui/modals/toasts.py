"""
Toast notifications: FetchingLinkToast & StartupWelcomeToast.
Re-exported from modular implementations for full backward compatibility.
"""
from __future__ import annotations

from .fetching_toast import FetchingLinkToast
from .welcome_toast import StartupWelcomeToast

__all__ = ["FetchingLinkToast", "StartupWelcomeToast"]
