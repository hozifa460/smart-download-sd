from .bridge_server import BrowserBridgeServer, DEFAULT_BRIDGE_PORT
from .native_host import (
    get_binary_stdin,
    get_binary_stdout,
    read_message,
    send_message,
    handle_payload,
    run_host,
)
from .registry import (
    register_native_host,
    unregister_native_host,
    check_and_register_browser,
    register_browser_extensions,
    unregister_browser_extensions,
    is_registered,
    get_status,
)

handle_native_message = handle_payload
run_native_messaging_host = run_host

__all__ = [
    "BrowserBridgeServer",
    "DEFAULT_BRIDGE_PORT",
    "get_binary_stdin",
    "get_binary_stdout",
    "read_message",
    "send_message",
    "handle_payload",
    "run_host",
    "handle_native_message",
    "run_native_messaging_host",
    "register_native_host",
    "unregister_native_host",
    "check_and_register_browser",
    "register_browser_extensions",
    "unregister_browser_extensions",
    "is_registered",
    "get_status",
]
