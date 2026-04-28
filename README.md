# 🐟 闲鱼超级管家

<div align="center">

**闲鱼店铺全自动运营管理平台**

[![License](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![React](https://img.shields.io/badge/React-19-blue.svg)](https://reactjs.org/)
[![Docker](https://img.shields.io/badge/Docker-Supported-2496ED?logo=docker)](https://www.docker.com/)

基于 [zhinianboke/xianyu-auto-reply](https://github.com/zhinianboke/xianyu-auto-reply) 二次开发

</div>

---

## 📖 简介

闲鱼超级管家是一个闲鱼店铺全自动运营管理平台，支持**多账号同时在线**，提供智能自动回复、AI 议价、虚拟商品自动发货、订单管理、消息通知推送等一站式解决方案。

---

## ⭐ 功能总览

### 🤖 智能自动回复
- 关键词匹配自动回复（支持精确/模糊匹配）
- **AI 智能议价**：接入 DeepSeek、通义千问、Gemini 等大模型，自动与买家讨价还价，支持自定义折扣规则
- 默认回复 / 商品专属回复配置
- AI 语义分类（价格协商 / 技术咨询 / 通用对话）

### 🚚 自动发货与订单处理
- 虚拟商品（卡券/兑换码/文本内容）**自动发货**，支持多规格、多数量
- 延时发货设置，模拟真人发货节奏
- 卡券库存管理与消费追踪
- 发货规则灵活配置（按商品/规格匹配）
- **自动确认收货**（可开关）
- **自动免拼发货**

### 📦 订单管理
- 所有订单列表查看，多维度筛选（全部 / 待发货 / 已发货 / 已取消 / 其他）
- **一键批量刷新**：Playwright 浏览器实时抓取最新订单状态与收货人信息
- 订单详情侧边面板，收货人信息一目了然
- **补发功能**：支持「仅修改发货状态」或「完整发货（匹配卡券并发送）」
- 单条订单同步 / 删除

### 📱 多账号管理
- 多闲鱼账号同时在线，独立运行互不干扰
- **三种登录方式**：二维码扫码 / 密码登录 / 手动输入 Cookie
- 账号启用/禁用、备注管理、暂停时长配置
- 每账号独立 AI 议价规则配置
- 浏览器实例池（最多 3 实例），高效复用资源

### 🔔 消息通知推送
- **多通道支持**：钉钉、飞书/Lark、企业微信、Telegram、Bark、邮箱（SMTP）、自定义 Webhook、QQ
- **事件类型**：
  - Token 刷新异常 / 滑块验证提醒
  - 自动发货成功/失败通知
  - 账号登录成功 / Cookie 过期 / 需重新登录
  - 实例重启异常
  - 人脸验证提醒（带截图附件）
- **智能防骚扰**：Token 类异常 3 小时冷却，普通通知 5 分钟冷却，避免重复推送

### 📊 数据统计
- Dashboard 工作台：销售概览、趋势图表
- 订单统计与收入分析
- Excel 批量导入/导出

### 👥 多用户权限管理
- 管理员 / 普通用户角色
- 用户注册（可开关）/ 登录验证
- JWT 认证，用户级 Cookie 隔离
- **邮件验证码**注册（SMTP 配置）

### 🧩 验证码与风控
- 滑块验证码自动解决，成功率 ~99%
- 远程人工接管验证（WebSocket 远程控制）
- 验证失败自动重试，附截图推送到通知渠道
- 风控日志追踪

### 🔍 其他
- 商品搜索与浏览
- Dashboard 活动流日志
- 系统级配置管理（前端 UI 直接修改）

---

## 🏗️ 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI + Uvicorn（全异步） |
| 语言 | Python 3.11+ |
| 数据库 | SQLite（WAL 模式、性能索引） |
| 浏览器自动化 | Playwright + DrissionPage |
| 消息通信 | WebSocket（asyncio） |
| AI 引擎 | OpenAI 兼容 SDK（DeepSeek / Qwen / Gemini 等） |
| OCR | PaddleOCR |
| 前端 | React 19 + TypeScript + Vite 6 |
| 样式 | Tailwind CSS 3 |
| 图表 | Recharts |
| 图标 | Lucide React |
| 容器化 | Docker + docker-compose（可选 Nginx 反代） |

---

## 🚀 快速开始

### 本地运行

```bash
# 1. 克隆并进入项目
git clone https://github.com/Mrstongtong828/xianyu.git
cd xianyu-super-butler

# 2. 安装 Python 依赖
pip install -r requirements.txt

# 3. 安装浏览器内核
playwright install chromium

# 4. 构建前端
cd frontend && npm install && npm run build && cd ..

# 5. 启动
python Start.py
# 访问 http://localhost:8080
```

> `Start.py` 会自动完成：数据库迁移 → 前端构建 → Playwright 检查 → 启动所有已启用账号 → 启动 Web 服务。

### Docker 部署

```bash
docker-compose up -d                           # 仅应用 (8080)
docker-compose --profile with-nginx up -d      # 带 Nginx (80/443)
```

### 前端开发模式

```bash
# 终端 1：启动后端
python Start.py

# 终端 2：启动前端 HMR
cd frontend && npm run dev
# 访问 http://localhost:3000
```

### 🔐 默认账号

```
用户名: admin
密码:   admin123
```

> ⚠️ 首次登录后请立即修改默认密码！

---

## 📁 项目结构

```
xianyu-super-butler/
├── Start.py                         # 入口：启动所有服务
├── reply_server.py                  # FastAPI 应用（REST API + 静态文件）
├── XianyuAutoAsync.py               # 核心引擎：WebSocket 连接、消息处理、自动回复/发货
├── ai_reply_engine.py               # AI 回复引擎（OpenAI 兼容接口）
├── XianyuAgent.py                   # AI Agent（意图分类、议价、技术支持）
├── order_status_handler.py          # 订单状态状态机
├── db_manager.py                    # 数据库层（用户/账号/订单/关键词/通知配置等）
├── cookie_manager.py                # 多账号生命周期管理
├── config.py                        # 配置加载器
├── global_config.yml                # 主配置文件
├── requirements.txt                 # Python 依赖
├── Dockerfile / docker-compose.yml  # 容器化部署
│
├── utils/                           # 工具模块
│   ├── browser_pool.py              # 浏览器实例池（最多 3 实例复用）
│   ├── xianyu_utils.py              # 闲鱼加密/签名/设备 ID 生成
│   ├── xianyu_slider_stealth.py     # 滑块验证码隐身方案
│   ├── qr_login.py                  # 二维码扫码登录
│   ├── order_fetcher_optimized.py   # 批量订单抓取
│   ├── order_detail_fetcher.py      # 订单详情获取
│   ├── ocr_engine.py                # PaddleOCR 封装
│   ├── rate_limiter.py              # API 限流器
│   ├── image_utils.py               # 图片管理
│   └── captcha_remote_control.py    # 远程验证码控制
│
├── secure_confirm_decrypted.py      # 自动确认收货模块
├── secure_freeshipping_decrypted.py # 自动免拼发货模块
│
├── prompts/                         # AI 提示词模板
├── frontend/                        # React 前端源码
│   ├── App.tsx                      # 应用入口
│   ├── components/
│   │   ├── Dashboard.tsx            # 工作台/数据统计
│   │   ├── AccountList.tsx          # 账号管理
│   │   ├── OrderList.tsx            # 订单管理（含补发弹窗）
│   │   ├── CardList.tsx             # 卡券管理
│   │   ├── ItemList.tsx             # 商品管理
│   │   ├── Keywords.tsx             # 关键词配置
│   │   └── Settings.tsx             # 系统设置（AI/SMTP/通知等全局配置）
│   ├── lib/                         # 请求封装
│   └── vite.config.ts
├── static/                          # 前端构建产物（FastAPI 直接托管）
├── data/                            # SQLite 数据库文件存储
├── logs/                            # 运行日志
└── nginx/                           # Nginx 配置（Docker 反向代理）
```

---

## ⚙️ 配置说明

核心配置在 `.env`（需自行创建）和 `global_config.yml` 中：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `DB_PATH` | 数据库路径 | `data/xianyu_data.db` |
| `AI_REPLY_ENABLED` | 启用 AI 回复 | `false` |
| `DEFAULT_AI_MODEL` | AI 模型名 | `deepseek-chat` |
| `DEFAULT_AI_BASE_URL` | AI API 地址 | `https://api.deepseek.com` |
| `WEBSOCKET_URL` | 闲鱼 WebSocket | `wss://wss-goofish.dingtalk.com/` |
| `LOG_LEVEL` | 日志级别 | `INFO` |

系统设置（AI 配置、SMTP、通知通道等）也可通过前端「系统设置」页面直接修改。

---

## 📄 开源协议

[MIT License](https://opensource.org/licenses/MIT)

> ⚠️ **免责声明**
>
> 本项目仅供学习研究使用，严禁用于商业用途。使用本项目时请遵守相关法律法规，因使用本项目而产生的一切后果由使用者自行承担。

---

<div align="center">

基于 [xianyu-auto-reply](https://github.com/zhinianboke/xianyu-auto-reply) 开发

</div>
