import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

# The SDK is supplied by the user's AstrBot container.
for name in ('astrbot', 'astrbot.api', 'astrbot.api.event', 'astrbot.api.star'):
    sys.modules[name] = types.ModuleType(name)
identity = lambda *a, **k: lambda fn: fn
sys.modules['astrbot.api.event'].AstrMessageEvent = object
sys.modules['astrbot.api.event'].filter = types.SimpleNamespace(llm_tool=identity, command=identity)
sys.modules['astrbot.api.star'].Context = object
sys.modules['astrbot.api.star'].Star = object
sys.modules['astrbot.api.star'].register = identity
plugin = load('monitor_plugin', ROOT / 'plugin/main.py')
collector = load('collector', ROOT / 'collector.py')

class Checks(unittest.IsolatedAsyncioTestCase):
    def test_permissions(self):
        with tempfile.TemporaryDirectory() as folder:
            plugin.OWNER_PATH = Path(folder)/'owner_qq'
            plugin.OWNER_PATH.write_text('123456789')
            def event(sender='123456789', group='', platform='aiocqhttp'):
                return types.SimpleNamespace(get_sender_id=lambda: sender,
                    get_group_id=lambda: group, get_platform_name=lambda: platform)
            self.assertTrue(plugin.authorized(event()))
            self.assertFalse(plugin.authorized(event(sender='987654321')))
            self.assertFalse(plugin.authorized(event(group='123')))
            self.assertFalse(plugin.authorized(event(platform='other')))
            plugin.OWNER_PATH.unlink()
            self.assertFalse(plugin.authorized(event()))

    async def test_real_socket_and_collector(self):
        with tempfile.TemporaryDirectory() as folder:
            plugin.SOCKET_PATH = str(Path(folder)/'status.sock')
            calls = []
            async def serve(reader, writer):
                calls.append(1)
                data = await asyncio.to_thread(collector.collect)
                writer.write(json.dumps(data).encode()+b'\n')
                await writer.drain()
                writer.close()
                await writer.wait_closed()
            try:
                server = await asyncio.start_unix_server(serve, plugin.SOCKET_PATH)
            except PermissionError:
                self.skipTest('Environment prohibits Unix sockets')
            async with server:
                await asyncio.sleep(.05)
                self.assertEqual(calls, [])  # no polling while idle
                result = await plugin.read_status()
                self.assertTrue(result['ok'], result)
                self.assertEqual(len(calls), 1)
                self.assertEqual(result['metrics']['cpu']['sample_seconds'], 1)
                self.assertGreater(result['metrics']['memory']['total_bytes'], 0)
            self.assertFalse((await plugin.read_status())['ok'])

    async def test_response_over_mocked_transport(self):
        data = await asyncio.to_thread(collector.collect)
        class Writer:
            def close(self): pass
            async def wait_closed(self): pass
        async def connection(path):
            reader = asyncio.StreamReader()
            reader.feed_data(json.dumps(data).encode() + b'\n')
            reader.feed_eof()
            return reader, Writer()
        with patch.object(asyncio, 'open_unix_connection', connection):
            self.assertTrue((await plugin.read_status())['ok'])
        data['collected_at_epoch'] -= 100
        with patch.object(asyncio, 'open_unix_connection', connection):
            self.assertFalse((await plugin.read_status())['ok'])

    async def test_bad_response(self):
        with tempfile.TemporaryDirectory() as folder:
            plugin.SOCKET_PATH = str(Path(folder)/'status.sock')
            async def serve(reader, writer):
                writer.write(b'{bad json}\n')
                await writer.drain()
                writer.close()
                await writer.wait_closed()
            try:
                server = await asyncio.start_unix_server(serve, plugin.SOCKET_PATH)
            except PermissionError:
                self.skipTest('Environment prohibits Unix sockets')
            async with server:
                self.assertFalse((await plugin.read_status())['ok'])

if __name__ == '__main__':
    unittest.main()
