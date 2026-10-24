# 小主机实时状态查询（AstrBot / Docker）

按需读取 Linux **宿主机**的 CPU 温度、1 秒 CPU 使用率、内存、Swap、根分区、负载和运行时间。没有定时器、后台轮询或常驻 Python 采集进程；systemd 保留 Unix socket 监听，每次连接启动一个采集进程，返回 JSON 后退出。

## 安装

适用 Ubuntu / Debian、systemd、Python 3，以及大肥鱼项目的 `astrbot.yml` 和 `data` 布局。Docker 必须将项目的 `data` 挂载到 `/AstrBot/data`。无需 privileged、Docker socket 或宿主机根目录挂载。

下载或 clone 本仓库后，用普通 Linux 账号执行：

```bash
bash install.sh ~/dafeiyu 你的QQ号
sudo docker restart astrbot
```

将 `你的QQ号` 替换成发消息的账号。安装器会调用 sudo，执行一次实时采集自检。如果已经安装旧的 30 秒采集版，会停用旧定时器，并将原插件备份到 `data/host_monitor_backups`。重复安装同样会备份和更新。

QQ 私聊发送 `/主机状态`。成功后在鱼菲人格的工具权限中允许 `get_linux_host_status`，即可问“现在小主机多少度、内存占用多少”。不需要开启终端命令执行权限。

## 权限与数据

仅 `data/host_monitor/owner_qq` 中的 QQ 号可通过 OneBot v11 私聊查询，群聊和其他账号拒绝。QQ号由安装参数写入，不包含在公开源码里。

Unix socket 位于 `data/host_monitor/status.sock`，允许宿主机和共享该目录的容器中的本地进程读取这些固定指标，不接受任何命令、路径或采集参数。不要将宿主机上不可信的容器挂载到此目录。采集程序不读取私人文件、不执行外部命令、不联网。

温度仅筛选 `coretemp`（适合当前 Intel 小主机）；其他 CPU 可能显示未读到传感器。内存使用量按 `MemTotal - MemAvailable` 计算，可能和 `free` 的 used 列不同。CPU 使用率是 1 秒采样，通常查询需要约 1 秒。没有采集到的指标不应猜测。

## 排查

```bash
systemctl status dafeiyu-host-monitor.socket
sudo journalctl --since '10 minutes ago' -u 'dafeiyu-host-monitor@*' --no-pager
sudo docker logs --since 5m astrbot
```

若宿主机自检通过而 QQ 查询失败，检查 `data` 挂载、socket 文件和插件日志。安装器不会自动修改 Docker 配置或重启容器。

## 停用

```bash
sudo systemctl disable --now dafeiyu-host-monitor.socket
```

然后在 AstrBot 中停用“ 小主机只读监控 ”插件。此操作保留源码、QQ配置及备份。
