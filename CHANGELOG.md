# Changelog

所有格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [2.0.0] — 2026-06-16

### 新增

- 交互式 HTML 控制面板（三栏布局），展示余额、消费趋势和模型级用量细分
- GTK 设置窗口，支持图形化修改 API Key、轮询间隔和告警阈值
- 右键面板图标 →「Open Control Panel」直接打开控制面板
- DeepSeek Usage API 集成，展示详细的 Token 消费记录
- 中英文双语 README 及语言切换入口

### 变更

- 项目重命名：`deepseek-monitor` → `PanelWhale`
- 图标更换为新品牌图标
- 安装目录从 `/opt/deepseek-monitor/` 迁移至 `/opt/panelwhale/`
- systemd 服务名称从 `deepseek-monitor.service` 更改为 `panelwhale.service`

### 移除

- 每周报告邮件服务（`*-report.service` / `*-report.timer`），改为按需查看控制面板
- 旧版自动启动 `.desktop` 文件支持

### 修复

- install.sh 新增旧版 `deepseek-monitor` 服务自动清理逻辑，避免开机启动两个实例

## [1.0.0] — 2026-06-12

### 新增

- GNOME 顶部面板 DeepSeek API 余额实时显示
- 可配置的余额告警阈值（黄色/红色），低于阈值时更换图标颜色并弹出桌面通知
- systemd 用户服务实现开机自启
- `install.sh` / `uninstall.sh` 一键安装/卸载脚本
- 每周余额报告邮件（systemd timer 周一早 8 点触发）
