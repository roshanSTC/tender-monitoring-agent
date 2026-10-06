"""
Windows Asyncio & Proactor Socket Patch
Suppresses harmless [WinError 10054] ConnectionResetError tracebacks
when browser tabs disconnect, refresh, or reconnect WebSockets.
"""

import sys
import logging

if sys.platform == "win32":
    # Silence asyncio logger warnings
    logging.getLogger("asyncio").setLevel(logging.CRITICAL)
    logging.getLogger("tornado.general").setLevel(logging.ERROR)

    try:
        from asyncio.proactor_events import _ProactorBasePipeTransport

        _orig_call_connection_lost = _ProactorBasePipeTransport._call_connection_lost

        def _silenced_call_connection_lost(self, exc=None):
            try:
                _orig_call_connection_lost(self, exc)
            except (ConnectionResetError, BrokenPipeError, OSError):
                # Harmless client socket disconnect on Windows (WinError 10054)
                pass

        _ProactorBasePipeTransport._call_connection_lost = _silenced_call_connection_lost
    except Exception:
        pass
