# 来源与第三方声明

本仓库整理项目自身的助手服务、IR、适配和执行器源码。仓库公开展示；没有为项目自有部分额外授予开源许可。

原生 VI 读写依赖 Zühlke 的 MIT 开源项目 `Zuehlke/labview-mcp`，开发对应 commit：

`4939b406cd2fa8f598439c30cf9bc7e2269b5d9b`

上游地址：https://github.com/Zuehlke/labview-mcp

部分固定 VI Server 辅助 AIXML 与原生读写适配以该项目为基础。相关 MIT 声明保存在 `third_party/licenses/labview-mcp-MIT.txt`。本仓库没有捆绑其完整发布包、Windows Python 发行版或 NI 安装文件。

LabVIEW、TestStand、Nigel 等名称归各自权利人。NI Automation interop DLL、NI 产品许可证及运行环境应由使用方合法准备，未随此源码分发。仓库不包含 Nigel 内部取证 DLL、登录／订阅绕过实现或客户原始需求资料。
