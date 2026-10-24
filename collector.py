#!/usr/bin/env python3
"""Collect fixed, read-only host metrics; no external commands or network."""
import datetime
import json
import os
from pathlib import Path
import shutil
import sys
import time


def cpu_ticks():
    values = list(map(int, Path('/proc/stat').read_text().splitlines()[0].split()[1:]))
    # guest and guest_nice are already included in user/nice.
    return sum(values[:8]), values[3] + (values[4] if len(values) > 4 else 0)


def temperatures(root=Path('/sys/class/hwmon')):
    result = []
    for chip in sorted(root.glob('hwmon*')):
        try:
            if (chip / 'name').read_text().strip() != 'coretemp':
                continue
        except OSError:
            continue
        for item in sorted(chip.glob('temp*_input')):
            try:
                label_path = chip / item.name.replace('_input', '_label')
                label = label_path.read_text().strip() if label_path.exists() else item.stem
                value = float(item.read_text().strip()) / 1000
                if -50 <= value <= 200:
                    result.append({'sensor': 'coretemp', 'label': label, 'celsius': value})
            except (OSError, ValueError):
                continue
    return result


def collect():
    start_total, start_idle = cpu_ticks()
    time.sleep(1.0)
    end_total, end_idle = cpu_ticks()
    elapsed = end_total - start_total
    cpu_percent = round(100 * (1 - (end_idle - start_idle) / elapsed), 1) if elapsed > 0 else None
    mem = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        name, value = line.split(':', 1)
        mem[name] = int(value.strip().split()[0]) * 1024
    total, available = mem['MemTotal'], mem['MemAvailable']
    disk = shutil.disk_usage('/')
    now = time.time()
    return {
        'schema_version': 1,
        'source': 'linux-host',
        'collected_at': datetime.datetime.fromtimestamp(now, datetime.timezone.utc).isoformat(),
        'collected_at_epoch': now,
        'cpu': {'usage_percent': cpu_percent, 'sample_seconds': 1.0, 'logical_count': os.cpu_count(),
                'load_average_1_5_15m': list(os.getloadavg()), 'temperatures': temperatures()},
        'memory': {'total_bytes': total, 'available_bytes': available,
                   'used_bytes': total - available,
                   'used_percent': round(100 * (total - available) / total, 1),
                   'definition': 'MemTotal - MemAvailable; reclaimable cache is not all counted as used'},
        'swap': {'total_bytes': mem.get('SwapTotal', 0),
                 'used_bytes': mem.get('SwapTotal', 0) - mem.get('SwapFree', 0)},
        'root_disk': {'mount': '/', 'total_bytes': disk.total, 'used_bytes': disk.used,
                      'available_bytes': disk.free,
                      'used_percent': round(100 * disk.used / (disk.used + disk.free), 1)},
        'uptime_seconds': int(float(Path('/proc/uptime').read_text().split()[0])),
    }


def main():
    # systemd Accept=yes connects stdout directly to the requesting Unix socket.
    json.dump(collect(), sys.stdout, ensure_ascii=False, allow_nan=False)
    sys.stdout.write('\n')
    sys.stdout.flush()


if __name__ == '__main__':
    main()
