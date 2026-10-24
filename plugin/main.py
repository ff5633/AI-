import asyncio
import json
from pathlib import Path
import time

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

OWNER_PATH = Path('/AstrBot/data/host_monitor/owner_qq')
SOCKET_PATH = '/AstrBot/data/host_monitor/status.sock'


async def read_status():
    writer = None
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_unix_connection(SOCKET_PATH), timeout=3)
        raw = await asyncio.wait_for(reader.readuntil(b'\n'), timeout=8)
        if len(raw) > 65536:
            raise ValueError('oversized response')
        payload = json.loads(raw)
        age = time.time() - float(payload['collected_at_epoch'])
        if age < -5 or age > 15:
            return {'ok': False, 'error': '本次采集时间异常，请检查宿主机时钟。'}
        return {'ok': True, 'age_seconds': max(0, round(age)), 'metrics': payload,
                'note': '本次查询实时采集宿主机数据；CPU使用率采样1秒。温度缺失时不得猜测。'}
    except (OSError, ValueError, KeyError, TypeError, asyncio.TimeoutError,
            asyncio.IncompleteReadError, asyncio.LimitOverrunError):
        return {'ok': False, 'error': '实时采集失败，请检查宿主机的dafeiyu-host-monitor.socket及采集服务日志。'}
    finally:
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass


def authorized(event):
    # Check trusted platform metadata, never names or the message text.
    try:
        return (event.get_platform_name() == 'aiocqhttp'
                and str(event.get_sender_id()) == OWNER_PATH.read_text().strip()
                and not event.get_group_id())
    except Exception:
        return False


@register('host_monitor', 'fzz', '小主机只读状态查询，仅指定QQ私聊可用', '2.0.0')
class HostMonitorPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    async def query(self, event):
        if not authorized(event):
            return {'ok': False, 'error': '系统状态只允许指定QQ账号在私聊中查询。'}
        return await read_status()

    @filter.llm_tool(name='get_linux_host_status')
    async def get_linux_host_status(self, event: AstrMessageEvent) -> str:
        """查询用户Linux小主机宿主机的CPU温度、CPU使用率、内存、Swap、根磁盘、负载和运行时长。

        用户问小主机温度、内存占用、系统负载等状态时调用。无参数；只读，按需采样，不接受命令参数。
        结果含采集时间与数据年龄；失败或过期时应说明原因，不得编造数值。
        """
        return json.dumps(await self.query(event), ensure_ascii=False)

    @filter.command('主机状态')
    async def host_status_command(self, event: AstrMessageEvent):
        payload = await self.query(event)
        if not payload['ok']:
            yield event.plain_result(payload['error'])
            return
        m = payload['metrics']
        temperatures = m['cpu']['temperatures']
        package = [t for t in temperatures if t['label'].startswith('Package id')]
        selected = package or temperatures
        temp_text = '、'.join(f"{t['label']}: {t['celsius']:.1f}℃" for t in selected) or '未读到温度传感器'
        gib = 1024 ** 3
        mem, disk = m['memory'], m['root_disk']
        load = ', '.join(f'{n:.2f}' for n in m['cpu']['load_average_1_5_15m'])
        text = (f"小主机状态（{payload['age_seconds']}秒前采集）\n"
                f"CPU温度：{temp_text}\nCPU使用率：{m['cpu']['usage_percent']}%（短时采样）\n"
                f"内存：{mem['used_bytes']/gib:.2f}/{mem['total_bytes']/gib:.2f} GiB，{mem['used_percent']}%\n"
                f"可用内存：{mem['available_bytes']/gib:.2f} GiB\n"
                f"Swap已用：{m['swap']['used_bytes']/gib:.2f} GiB\n"
                f"根磁盘：{disk['used_percent']}%，可用 {disk['available_bytes']/gib:.1f} GiB\n"
                f"负载（1/5/15分钟）：{load}\n运行时长：{m['uptime_seconds']//3600}小时")
        yield event.plain_result(text)
