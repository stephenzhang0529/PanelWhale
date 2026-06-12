<p align="center">
  <img src="https://img.shields.io/badge/python-3.8+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/platform-Ubuntu%2020.04--26.04-orange.svg" alt="Platform">
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License">
  <img src="https://img.shields.io/badge/memory-~25MB-lightgrey.svg" alt="Memory">
</p>

# 🐋 PanelWhale

一款轻量级 Ubuntu 桌面应用，在顶部状态栏显示 [DeepSeek](https://platform.deepseek.com) API 余额，支持消耗统计、余额不足告警和会话日志持久化。

> *A whale in your panel, watching your DeepSeek balance.*

<p align="center">
  <b>💎 ¥108.32</b> &nbsp;·&nbsp; <b>🟡 ¥4.50</b> &nbsp;·&nbsp; <b>🔴 ¥0.80</b>
</p>

## ✨ 功能特性

- **面板常驻** — 余额直接显示在 GNOME 顶部状态栏，DeepSeek 鲸鱼 logo 一目了然
- **右键菜单** — 查看余额详情、过去 5 分钟 / 30 分钟 / 3 小时消耗、今日累计
- **余额告警** — ≤¥5 黄色提醒 🟡、≤¥1 红色警告 🔴，跨阈值时弹出桌面通知
- **持久化日志** — 每次会话的消耗记录以 JSON 格式存储，重启后自动恢复今日累计
- **优雅退出** — 退出或关机时最后一次查询 API，失败则强制刷盘，数据不丢失
- **手动刷新** — 菜单一键刷新，15 秒防抖
- **systemd 托管** — 不依赖终端、崩溃自动重启、开机自启
- **资源友好** — 约 25MB 内存，空闲 CPU 使用率为零

## 🖥️ 兼容性

| Ubuntu 版本 | GNOME 版本 | 支持 |
|-------------|-----------|------|
| 20.04 LTS | 3.36 | ✅ |
| 22.04 LTS | 42 | ✅ |
| 24.04 LTS | 46 | ✅ |
| 26.04 LTS | 48 | ✅ |

启动时自动检测 AppIndicator3 / AyatanaAppIndicator3 后端。

## 📁 项目结构

```
~/Desktop/api_monitor/
├── main.py                       # 入口
├── config.yaml                    # 配置模板
├── deepseek-monitor.service       # systemd 用户服务
├── deepseek-color.png             # DeepSeek logo 图标
├── install.sh                     # 一键安装
├── uninstall.sh                   # 卸载
└── monitor/
    ├── config.py                  # 配置加载（YAML + 环境变量）
    ├── api.py                     # DeepSeek API 封装
    ├── store.py                   # 余额历史 + 日志持久化
    └── indicator.py               # 面板图标、菜单、通知

~/.local/share/deepseek-monitor/logs/   # 运行时日志（自动创建）
~/.config/deepseek-monitor/config.yaml  # 用户配置
```

## 🚀 安装

```bash
cd ~/Desktop/api_monitor
chmod +x install.sh
./install.sh
```

安装脚本自动完成：
1. 检测 Ubuntu 版本并安装系统依赖
2. 复制程序到 `/opt/deepseek-monitor/`
3. 引导配置 DeepSeek API Key
4. 安装 systemd 用户服务并启用开机自启
5. 立即启动

> sudo 仅用于安装系统包。程序本身以普通用户身份运行。

## ⚙️ 配置

编辑 `~/.config/deepseek-monitor/config.yaml`：

```yaml
api_key: "sk-your-api-key-here"
poll_interval_seconds: 300          # 轮询间隔（秒），最小 30
alert_threshold_yellow: 5.0         # ≤5 元 → 黄色
alert_threshold_red: 1.0            # ≤1 元 → 红色
```

也可用环境变量：

```bash
export DEEPSEEK_API_KEY="sk-xxx"
```

改配置后重启：`systemctl --user restart deepseek-monitor`

## 📖 使用

### 日常命令

```bash
systemctl --user status   deepseek-monitor   # 查看状态
systemctl --user stop     deepseek-monitor   # 停止
systemctl --user start    deepseek-monitor   # 启动
systemctl --user restart  deepseek-monitor   # 重启
journalctl --user -u deepseek-monitor -f     # 实时日志
```

### 右键菜单

```
────────── 💰 余额详情 ──────────
总余额: ¥108.32
  ├ 充值余额: ¥100.00
  └ 赠送余额: ¥8.32
────────── 📊 消耗统计 ──────────
过去5分钟:  ¥0.00
过去30分钟: ¥0.32
过去3小时:  ¥1.68
今日累计:   ¥5.20
────────────────────────────────
🔄 立即刷新
────────────────────────────────
上次更新: 2026-06-11 15:30:00
────────────────────────────────
❌ 退出
```

### 图标颜色

| 图标 | 余额 | 含义 |
|------|---------|------|
| 💎 | > ¥5 | 正常 |
| 🟡 | ¥1 – ¥5 | 余额偏低 |
| 🔴 | < ¥1 | 严重不足，立即充值 |
| ⚠️ | — | 网络错误或 API Key 无效 |

## 🔄 数据流

```
每 5 分钟 → GET /user/balance
                │
                ▼
        ┌── 成功 ──→ 计算消耗 → 追加日志 → 更新 UI
        │
        └── 失败 ──→ 显示 ⚠️ → 下周期自动重试

退出 / 关机
    │
    ├── 尝试最后一次查询
    │   ├─ 成功 → 计入最终消耗 → 写 SUM 到日志
    │   └─ 失败 → 强制刷盘，保留已累积数据
    │
    └── 下次启动 → 扫描当日日志 → 恢复今日累计
```

## 📊 日志持久化

每次会话的消耗记录以 JSON 格式存储：

```
~/.local/share/deepseek-monitor/logs/
├── 2026-06-11T09-30-00+08-00.json   # 上午会话
└── 2026-06-11T14-15-00+08-00.json   # 下午会话
```

单文件结构：

```json
{
  "session_start": "2026-06-11T14:15:00+08:00",
  "entries": [
    {"ts": "2026-06-11T14:20:00", "consumption": 0.50, "balance": 107.82},
    {"ts": "2026-06-11T14:25:00", "consumption": 0.32, "balance": 107.50}
  ],
  "session_end": "2026-06-11T14:27:30+08:00",
  "sum_consumption": 0.82
}
```

- 保留最近 7 天，过期自动清理
- "今日累计" = 当日所有日志的 `sum_consumption` + 当前会话消费

## ❓ 常见问题

<details>
<summary><b>状态栏没有图标？</b></summary>

```bash
systemctl --user status deepseek-monitor
journalctl --user -u deepseek-monitor -n 30
```

通常是 API Key 未配置或无效。
</details>

<details>
<summary><b>显示 ⚠️ 无连接？</b></summary>

网络问题或 API Key 无效。下个轮询周期自动重试，网络恢复后自动正常。
</details>

<details>
<summary><b>重启后今日累计变成 0？</b></summary>

关机时网络已断导致最终查询失败。当前版本已修复：失败时强制刷盘保留已有数据。更新到最新版本即可。
</details>

<details>
<summary><b>能监控单个 API Key 的用量吗？</b></summary>

不能。DeepSeek 的 `/user/balance` 返回的是整个账户的余额，所有 API Key 共享同一余额池。
</details>

## 🧹 卸载

```bash
cd ~/Desktop/api_monitor
chmod +x uninstall.sh
./uninstall.sh
```

停止服务、删除程序文件，询问是否保留配置和历史数据。

## 📄 许可证

MIT
