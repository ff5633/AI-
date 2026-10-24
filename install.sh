#!/usr/bin/env bash
set -euo pipefail
source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_dir="$(realpath -e -- "${1:?用法: bash install.sh ~/dafeiyu 你的QQ号}")"
owner_qq="${2:?请在第二个参数填写允许查询的QQ号}"
monitor_user="$(id -un)"
monitor_group="$(id -gn)"
[[ "$owner_qq" =~ ^[1-9][0-9]{4,14}$ ]] || { echo 'QQ号格式不正确' >&2; exit 1; }
[ "$monitor_user" != root ] || { echo '请用普通账号运行，脚本会调用sudo。' >&2; exit 1; }
[[ "$project_dir" =~ ^/[a-zA-Z0-9_./-]+$ ]] || { echo '项目路径仅支持英文、数字、下划线、点、横线和斜线。' >&2; exit 1; }
[ -f "$project_dir/astrbot.yml" ] && [ -d "$project_dir/data" ] || { echo '未找到astrbot.yml和data，请核对项目路径。' >&2; exit 1; }
command -v python3 >/dev/null
command -v systemctl >/dev/null
sudo -v
plugin_dir="$project_dir/data/plugins/astrbot_plugin_host_monitor"
# Keep backups outside the plugins directory to avoid duplicate loading.
if sudo test -d "$plugin_dir"; then
    sudo install -d -m 755 "$project_dir/data/host_monitor_backups"
    sudo cp -a "$plugin_dir" "$project_dir/data/host_monitor_backups/plugin-$(date +%Y%m%d-%H%M%S)-$$"
fi
for unit in dafeiyu-host-monitor.timer dafeiyu-host-monitor.service dafeiyu-host-monitor.socket; do
    if systemctl cat "$unit" >/dev/null 2>&1; then
        sudo systemctl disable --now "$unit"
    fi
done
sudo install -d -m 755 "$project_dir/data/host_monitor" "$plugin_dir" /usr/local/lib/dafeiyu-host-monitor
sudo install -m 644 "$source_dir/collector.py" /usr/local/lib/dafeiyu-host-monitor/collector.py
sudo install -m 644 "$source_dir/plugin/main.py" "$source_dir/plugin/metadata.yaml" "$plugin_dir/"
printf '%s\n' "$owner_qq" | sudo tee "$project_dir/data/host_monitor/owner_qq" >/dev/null
sudo chmod 644 "$project_dir/data/host_monitor/owner_qq"
sudo tee /etc/systemd/system/dafeiyu-host-monitor.socket >/dev/null <<UNIT
[Unit]
Description=Dafeiyu on-demand host metrics socket

[Socket]
ListenStream=$project_dir/data/host_monitor/status.sock
Accept=yes
SocketMode=0666
RemoveOnStop=true
MaxConnections=4

[Install]
WantedBy=sockets.target
UNIT
sudo tee /etc/systemd/system/dafeiyu-host-monitor@.service >/dev/null <<UNIT
[Unit]
Description=Dafeiyu single host metrics query

[Service]
Type=exec
User=$monitor_user
Group=$monitor_group
ExecStart=/usr/bin/python3 /usr/local/lib/dafeiyu-host-monitor/collector.py
StandardInput=socket
StandardOutput=socket
StandardError=journal
RuntimeMaxSec=10
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectControlGroups=true
RestrictAddressFamilies=AF_UNIX
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now dafeiyu-host-monitor.socket
python3 - "$project_dir/data/host_monitor/status.sock" <<'PY'
import json, socket, sys
with socket.socket(socket.AF_UNIX) as client:
    client.settimeout(10)
    client.connect(sys.argv[1])
    with client.makefile('rb') as stream:
        result = json.loads(stream.readline(65537))
    print('宿主机实时采集测试成功，时间：', result['collected_at'])
PY
echo '安装完成。请执行 sudo docker restart astrbot，然后QQ私聊发送 /主机状态。'
