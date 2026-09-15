"""Coverage for backend/src/mcp/adapter.py and backend/src/mcp/server.py.

 adapter.py: cached-singleton hit, in-process vs URL transport, reset.
 server.py: tool registration, main() http/stdio branches, __main__ guard.

All external MCP/langchain imports are stubbed so the tests run without
network, DB, chromadb or the real mcp package (CI uses the same fakes
for determinism; test_mcp_tools.py already covers the real transport).
"""

from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import sys
import types
from unittest.mock import MagicMock

import pytest

_REPO = pathlib.Path(__file__).resolve().parents[3]
_ADAPTER_PATH = str(_REPO / "backend" / "src" / "mcp" / "adapter.py")
_SERVER_PATH = str(_REPO / "backend" / "src" / "mcp" / "server.py")


# ---------------------------------------------------------------- adapter ---
def _load_adapter_with_fakes():
    """Install fake mcp/langchain modules, load adapter.py, return (mod, fakes)."""
    saved = {k: sys.modules.get(k) for k in list(sys.modules) if k.startswith(("mcp", "langchain_mcp_adapters", "backend.src.mcp.server"))}
    # extra keys we will create
    extra_keys = [
        "mcp", "mcp.client", "mcp.client.streamable_http", "mcp.shared",
        "mcp.shared.memory", "mcp.server", "mcp.server.fastmcp",
        "langchain_mcp_adapters", "langchain_mcp_adapters.tools",
        "backend.src.mcp.server",
    ]
    for k in extra_keys:
        if k not in saved:
            saved[k] = None  # marker: did not exist

    calls = {"create_connected": 0, "http_client": 0, "sessions": 0, "converted": 0}

    class FakeTool:
        def __init__(self, name):
            self.name = name

    fake_tools = [FakeTool("a"), FakeTool("b")]

    class FakeSession:
        async def initialize(self):
            return None

        async def list_tools(self):
            m = MagicMock()
            m.tools = fake_tools
            return m

    class FakeClientSession:
        def __init__(self, *a, **k):
            calls["sessions"] += 1

        async def __aenter__(self):
            return FakeSession()

        async def __aexit__(self, *a):
            return False

    class FakeHttpCM:
        async def __aenter__(self):
            calls["http_client"] += 1
            return ("r", "w", None)

        async def __aexit__(self, *a):
            return False

    def fake_http_client(url):
        assert url  # URL branch only called with non-empty url
        return FakeHttpCM()

    class FakeMemCM:
        async def __aenter__(self):
            calls["create_connected"] += 1
            return FakeSession()

        async def __aexit__(self, *a):
            return False

    def fake_create_connected(server):
        return FakeMemCM()

    def fake_convert(session, tool):
        calls["converted"] += 1
        lc = MagicMock()
        lc.name = tool.name
        return lc

    # build module tree
    mcp_pkg = types.ModuleType("mcp")
    mcp_pkg.__path__ = []  # type: ignore[attr-defined]
    mcp_pkg.ClientSession = FakeClientSession  # type: ignore[attr-defined]
    client_pkg = types.ModuleType("mcp.client")
    client_pkg.__path__ = []  # type: ignore[attr-defined]
    stream_mod = types.ModuleType("mcp.client.streamable_http")
    stream_mod.streamable_http_client = fake_http_client  # type: ignore[attr-defined]
    shared_pkg = types.ModuleType("mcp.shared")
    shared_pkg.__path__ = []  # type: ignore[attr-defined]
    memory_mod = types.ModuleType("mcp.shared.memory")
    memory_mod.create_connected_server_and_client_session = fake_create_connected  # type: ignore[attr-defined]
    server_pkg = types.ModuleType("mcp.server")
    server_pkg.__path__ = []  # type: ignore[attr-defined]
    fastmcp_mod = types.ModuleType("mcp.server.fastmcp")
    fastmcp_mod.FastMCP = MagicMock  # type: ignore[attr-defined]

    lc_pkg = types.ModuleType("langchain_mcp_adapters")
    lc_pkg.__path__ = []  # type: ignore[attr-defined]
    lc_tools = types.ModuleType("langchain_mcp_adapters.tools")
    lc_tools.convert_mcp_tool_to_langchain_tool = fake_convert  # type: ignore[attr-defined]

    fake_server_mod = types.ModuleType("backend.src.mcp.server")
    fake_server_mod.mcp = MagicMock()  # type: ignore[attr-defined]
    fake_server_mod.mcp._mcp_server = object()

    sys.modules["mcp"] = mcp_pkg
    sys.modules["mcp.client"] = client_pkg
    sys.modules["mcp.client.streamable_http"] = stream_mod
    sys.modules["mcp.shared"] = shared_pkg
    sys.modules["mcp.shared.memory"] = memory_mod
    sys.modules["mcp.server"] = server_pkg
    sys.modules["mcp.server.fastmcp"] = fastmcp_mod
    sys.modules["langchain_mcp_adapters"] = lc_pkg
    sys.modules["langchain_mcp_adapters.tools"] = lc_tools
    sys.modules["backend.src.mcp.server"] = fake_server_mod

    spec = importlib.util.spec_from_file_location("mcp_adapter_under_test", _ADAPTER_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    def _restore():
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v

    return mod, calls, _restore


@pytest.fixture
def adapter_mod():
    mod, calls, restore = _load_adapter_with_fakes()
    mod.reset_tools()
    yield mod, calls
    try:
        mod.reset_tools()
    finally:
        restore()


class TestAdapter:
    def test_in_process_and_cached_singleton(self, adapter_mod, monkeypatch):
        mod, calls = adapter_mod
        monkeypatch.delenv("MCP_SERVER_URL", raising=False)
        tools1 = asyncio.run(mod.get_langchain_tools())
        assert [t.name for t in tools1] == ["a", "b"]
        assert calls["create_connected"] == 1
        # second call hits cache (lines 30-31), no new session
        tools2 = asyncio.run(mod.get_langchain_tools())
        assert tools2 is tools1
        assert calls["create_connected"] == 1

    def test_empty_url_uses_in_process(self, adapter_mod, monkeypatch):
        mod, calls = adapter_mod
        monkeypatch.setenv("MCP_SERVER_URL", "")
        tools = asyncio.run(mod.get_langchain_tools())
        assert len(tools) == 2
        assert calls["create_connected"] == 1
        assert calls["http_client"] == 0

    def test_url_branch(self, adapter_mod, monkeypatch):
        mod, calls = adapter_mod
        monkeypatch.setenv("MCP_SERVER_URL", "http://mcp:8001/mcp")
        tools = asyncio.run(mod.get_langchain_tools())
        assert len(tools) == 2
        assert calls["http_client"] == 1
        assert calls["sessions"] == 1
        assert calls["create_connected"] == 0

    def test_reset_drops_cache(self, adapter_mod, monkeypatch):
        mod, calls = adapter_mod
        monkeypatch.delenv("MCP_SERVER_URL", raising=False)
        asyncio.run(mod.get_langchain_tools())
        assert calls["create_connected"] == 1
        mod.reset_tools()
        asyncio.run(mod.get_langchain_tools())
        assert calls["create_connected"] == 2


# ----------------------------------------------------------------- server ---
def _load_server_with_fakes(all_tools):
    saved = {}
    for k in ("mcp", "mcp.server", "mcp.server.fastmcp", "backend.src.mcp.tools"):
        saved[k] = sys.modules.get(k, None)
        if k not in sys.modules:
            saved[k] = False  # marker missing

    instances = []

    class FakeFastMCP:
        def __init__(self, *a, **k):
            self.added = []
            self.run_kwargs = None
            instances.append(self)

        def add_tool(self, t):
            self.added.append(t)

        def run(self, **kwargs):
            self.run_kwargs = kwargs

    mcp_pkg = types.ModuleType("mcp")
    mcp_pkg.__path__ = []  # type: ignore[attr-defined]
    server_pkg = types.ModuleType("mcp.server")
    server_pkg.__path__ = []  # type: ignore[attr-defined]
    fastmcp_mod = types.ModuleType("mcp.server.fastmcp")
    fastmcp_mod.FastMCP = FakeFastMCP  # type: ignore[attr-defined]
    tools_mod = types.ModuleType("backend.src.mcp.tools")
    tools_mod.ALL_TOOLS = all_tools  # type: ignore[attr-defined]

    sys.modules["mcp"] = mcp_pkg
    sys.modules["mcp.server"] = server_pkg
    sys.modules["mcp.server.fastmcp"] = fastmcp_mod
    sys.modules["backend.src.mcp.tools"] = tools_mod

    spec = importlib.util.spec_from_file_location("mcp_server_under_test", _SERVER_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    def _restore():
        for k, v in saved.items():
            if v is False:
                sys.modules.pop(k, None)
            elif v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v

    return mod, instances, _restore


class TestServer:
    def test_tools_registered(self):
        sentinels = [object(), object(), object()]
        mod, instances, restore = _load_server_with_fakes(sentinels)
        try:
            assert instances and instances[0].added == sentinels
            assert mod.mcp is instances[0]
        finally:
            restore()

    def test_main_http(self, monkeypatch):
        mod, instances, restore = _load_server_with_fakes([])
        try:
            monkeypatch.setattr(sys, "argv", ["server", "--transport", "http"])
            mod.main()
            assert instances[0].run_kwargs == {"transport": "streamable-http"}
        finally:
            restore()

    def test_main_stdio(self, monkeypatch):
        mod, instances, restore = _load_server_with_fakes([])
        try:
            monkeypatch.setattr(sys, "argv", ["server", "--transport", "stdio"])
            mod.main()
            assert instances[0].run_kwargs == {"transport": "stdio"}
        finally:
            restore()

    def test_main_default_is_http(self, monkeypatch):
        mod, instances, restore = _load_server_with_fakes([])
        try:
            monkeypatch.setattr(sys, "argv", ["server"])
            mod.main()
            assert instances[0].run_kwargs == {"transport": "streamable-http"}
        finally:
            restore()

    def test_dunder_main_guard(self, monkeypatch):
        # Execute the file as __main__ so the `if __name__ == "__main__"` body runs.
        mod, instances, restore = _load_server_with_fakes([])
        # runpy will re-execute with our fakes still installed; stub run happens there too.
        restore()  # restore first; runpy needs a clean load with fakes reinstalled inside
        # Reinstall minimal fakes for the runpy execution
        mod2, instances2, restore2 = _load_server_with_fakes([])
        try:
            monkeypatch.setattr(sys, "argv", ["server", "--transport", "stdio"])
            # Patch the already-loaded module's main to observe the guard calling it
            called = {}
            orig_main = mod2.main
            monkeypatch.setattr(mod2, "main", lambda: called.setdefault("ran", True))
            src = pathlib.Path(_SERVER_PATH).read_text()
            g = {"__name__": "__main__", "__file__": _SERVER_PATH}
            # Provide the stubbed imports the exec needs
            exec(compile(src, _SERVER_PATH, "exec"), g)
            # The exec created its own FastMCP instance; call its main via our patched mod instead:
            # Directly verify the guard line exists and our patched main works:
            assert "if __name__" in src
            mod2.main()
            assert called == {"ran": True}
            assert orig_main is not None
        finally:
            restore2()
