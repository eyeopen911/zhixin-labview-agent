# 执信 LabVIEW 助手

把中文需求转换成可审阅的结构化设计，生成原生 LabVIEW VI／子 VI／共享 typedef，再由单独配置的 Windows 执行器运行、读取真实结果和导出前面板、框图。默认使用本机 Codex CLI，也可接入兼容 OpenAI Chat Completions 的模型接口。

本仓库是从开发工作区整理出的 **v0.6.1 源码快照**。不包含客户工程、私人配置、登录信息、机器日志、NI 取证文件或已安装软件副本。它是独立项目，与 NI Nigel 没有隶属关系。

## 已有能力和边界

| 功能 | 当前情况 |
| --- | --- |
| DBL、Boolean、int32、表达式及连接器映射 | 支持受限 IR 的生成与校验 |
| 一维数组、For／While、移位寄存器、Case 状态机 | 支持已实现的结构与节点集合 |
| GUI 按钮 Value Change、定时 Timeout | 支持，Windows 执行器通过真实 `Value(Signaling)` 驱动测试 |
| 主 VI 拆分职责子 VI、状态簇及共享 `.ctl` | 已实现生成、绑定与二进制检查路径 |
| 自然语言修改 | 修改结构化设计并生成新版本；原始导入文件另存 |
| 导入任意已有 VI 并无损修改 | **不支持**。复杂 VI 需要与原始结构化设计及二进制哈希对应；未知结构会拒绝或受限导入 |
| 任意硬件、实时系统、ActiveX 设备或大型旧工程 | 没有通用交付保证，需要专项适配和实机验证 |
| TestStand | 保留计划入口；本源码包不包含客户序列或 TestStand 执行适配器 |

模型生成的是声明式 IR，不是任意远程脚本。后端解析、类型检查并编译 IR；远端执行器验证输出、连接器、原生结构与工件哈希。设计成功、源码测试通过与 LabVIEW 实机验收是不同的状态。

## 本地启动

需要 Python 3.10+。以下操作不会连接远端机器：

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python run.py
```

打开 `http://127.0.0.1:8766`。服务仅绑定本机，默认关闭远程执行。设计和聊天还需要可用的模型后端。

默认选择 PATH 中的 `codex`；请先使用 Codex 官方工具完成本机登录。本助手不会读取或复制 Codex 登录文件。也可以手动设置：

```sh
export NI_AGENT_PROVIDER=openai
export NI_AGENT_BASE_URL=https://api.openai.com/v1
export NI_AGENT_MODEL=YOUR_MODEL_NAME
# API key 只通过本机环境变量设置；不要写进源码或提交到 Git。
```

`.env.example` 仅是配置示例；程序不会自动加载 `.env`。真实 `.env`、SSH 配置与密钥不属于仓库内容。

## 生成原生 VI 所需依赖

编译／导出层依赖上游 MIT 项目 [Zuehlke/labview-mcp](https://github.com/Zuehlke/labview-mcp)，对应开发快照 commit `4939b406cd2fa8f598439c30cf9bc7e2269b5d9b`。第三方发布包不随本仓库重新打包。

从上游取得兼容发布包，将其包含 `scripts/` 和 `pylabview/app/` 的 `bin` 目录放到 `tools/labview-mcp-release/package/bin/`，或设置 `NI_AGENT_LABVIEW_MCP_BIN` 指向该目录。适配层会用当前 Python 运行其中的纯 Python 读写工具；不能用 Windows `.pyd` 替代本机 Python 的依赖包。

```sh
python scripts/check_environment.py
python scripts/prepare_helpers.py
```

第二条命令仅在本机生成固定的 GUI／typedef 辅助 VI，**不启动或调用 LabVIEW**。辅助源码已在 `gui-tools/`；NI Automation interop DLL 必须从用户自己的合法安装环境准备，不随仓库分发。

## 连接 Windows 执行器

先阅读 [Windows 部署](docs/windows-setup.md)。本次源码整理期间没有部署或重新运行 Windows 工程。

```sh
export NI_AGENT_REMOTE_HOST=labview-host
export NI_AGENT_WINDOWS_ROOT='C:\ZhixinNI_Agent'
export NI_AGENT_ENABLE_REMOTE=1
python run.py
```

`labview-host` 是用户自己在 `~/.ssh/config` 中配置的别名。使用系统 SSH 认证，不把密码、私钥、Cookie 或个人 IP 写进程序。远端只接受后端允许的工件、动作与数值参数，不能让模型直接执行 Shell。

关闭远程执行后应重启本地服务，使前端状态与配置一致。请使用独立可写目录和空闲的 LabVIEW 会话；不要覆盖仍在内存中、打开或运行的 VI。

## 目录

- `backend.py`、`run.py`、`index.html`：本机 HTTP 服务、模型接入及界面。
- `vi_design.py`、`vi_structured.py`、`vi_gui.py`：IR、解释器、类型与结构检查、GUI 事件编译。
- `vi_engineering.py`、`vi_typedef.py`、`state_layout.py`：子 VI 拆分、状态和类型契约。
- `vi_service.py`、`dispatcher.py`、`settings.py`：版本、工件、远端白名单执行与配置。
- `remote/`：Windows PowerShell／C# 执行器源码，不含 NI DLL。
- `gui-tools/`、`scripts/`：Agent 执行器的固定 VI Server 辅助源码及本地编译／导出适配，属于工具实现，不包含业务 VI 或生成工件。
- `examples/`：合成数据的结构化示例。
- `docs/`：架构、部署、验证边界及源码整理记录。

运行时会创建 `designs/`、`imports/` 和 `artifacts/`；这些内容默认被 Git 忽略。

## 验证

```sh
python -m unittest discover -s . -p 'tests_*.py' -q
python scripts/scan_source.py
```

本次整理后的源码回归为 **62 项通过**，覆盖模型调用隔离、HTTP 会话校验、数值／类型／结构／GUI 设计和远程执行默认关闭。它不代表在新机器上重新完成了 LabVIEW 原生运行验收。

本仓库只整理 Agent 自身代码。本次源码打包没有重新进行 Windows 原生集成验收；不附带它生成的温度监测、DQMH 或客户业务程序，也不附带截图和原始运行记录。

## 安全与来源

发布前检查见 [安全说明](SECURITY.md)、[来源与第三方声明](NOTICE.md) 和 [整理记录](docs/release-notes.md)。源码包中不附带任何 NI 软件、Nigel 登录资料或客户 TestStand 工程。
