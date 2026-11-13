# 架构与执行边界

```mermaid
flowchart TD
  UI[本机中文交互界面] --> API[localhost HTTP API / 会话校验]
  API --> MODEL[Codex CLI 或 OpenAI 兼容模型]
  MODEL --> IR[声明式 IR / 新版本设计]
  IR --> VALIDATE[表达式白名单 / 类型 / 连接器 / 预算校验]
  VALIDATE --> COMPILE[原生 AIXML 与 VI 编译适配]
  COMPILE --> REVIEW[用户审阅并显式提交验证]
  REVIEW --> SSH[系统 SSH / 独立工件目录]
  SSH --> WORKER[Windows 交互式 PowerShell + C#]
  WORKER --> NI[实际 LabVIEW VI / GUI 事件]
  NI --> PROOF[输出 / Get Errors / 保存文件 / 原生图像]
  PROOF --> CHECK[下载与哈希 / 结构 / 类型 / 用例核对]
  CHECK --> UI
```

模型不持有 SSH 凭据或执行器回调。Codex CLI 请求在临时空目录执行，使用只读 sandbox 并关闭该次请求的 Shell／MCP 工具；模型只返回设计，后端选择可信编译器路径。IR 的表达式由专用解析和解释逻辑处理，不通过 `eval` 执行任意 Python。

`vi_service.py` 将设计、父版本、差异、编译及验证结果分别保存。复杂已知 VI 的导入通过已保存二进制哈希匹配原始 IR；它不是任意二进制 VI 的通用逆向编辑器。

UI 程序的事件分支、Timeout 和真实按钮验证由不同层负责。模型给出的预期结果、Python 解释结果、LabVIEW 实际结果必须分开记录。是否创建了 `.vi` 文件，也不能代替原生编译错误检查和运行测试。

原生读写依赖上游 `labview-mcp` 的公开实现和发布工具。此仓库只保留项目适配、IR、执行器及固定辅助源码，第三方软件依赖在本地安装。
