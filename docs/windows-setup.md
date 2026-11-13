# Windows 执行器部署

这份文档是之后部署的操作说明，不代表本次整理重新操作了任何 LabVIEW 工程。

1. 在独立的 Windows 机器／会话安装并授权 LabVIEW 开发环境。先前验证环境为 LabVIEW 2025 Q3（25.3.2f2）；其他版本需要重新验证。需要启用所用 VI Server／VI Scripting 接口。
2. 选择专属可写目录，例如 `C:\ZhixinNI_Agent`，把 `remote/` 内的 `.cs`、`.ps1` 平铺复制进去，包括 `agent-config.ps1`。不要覆盖正在运行的工程。
3. 从自己的 NI 安装准备兼容的 Automation interop 程序集，默认路径为 `interop\LabVIEW.Automation.dll`。执行器源码使用命名空间 `LabVIEWAutomation`。如使用其他命名空间，应相应调整 C# 源码；仓库不含此 DLL。
4. 在本地安装上游读写工具与 Python 依赖，运行 `python scripts/prepare_helpers.py`。把生成的 `gui-tools/*.vi` 复制到执行器根目录下的 `gui-tools/`。
5. 在本机 SSH 配置中创建 `labview-host` 别名。远端 SSH 用户必须具有相应文件权限，并与已登录的 LabVIEW 桌面用户一致。执行器通过该用户的交互式计划任务调用 NI，不保存账户密码。
6. 用 `NI_AGENT_REMOTE_HOST` 和 `NI_AGENT_WINDOWS_ROOT` 配置助手，确认目标正确后才设置 `NI_AGENT_ENABLE_REMOTE=1`。先检查合成数据示例，再由界面显式提交生成／验证任务。

`agent-config.ps1` 默认使用自身所在的部署目录作为根目录。如设置 `NI_AGENT_INTEROP_DLL`，应确保交互式计划任务也能读取该环境变量；仅在 SSH 会话中临时设置变量不会自动传给另一进程。

运行结果、源设计、原生截图及哈希位于 `runs/<run-id>/`。它们可能含路径或测试数据，不应直接提交到 Git。固定辅助 VI 中的目标路径只应指向这套助手生成的工件。

遇到文件仍驻留、被项目持有、弹出重载提示或修改确认时，停止更新该文件。先结束本次 VI、关闭相关面板／项目并释放引用，再在新候选路径加载。不要在当前加载的 VI 上反复覆盖；不要用重启或强制退出替代未保存内容的确认。
