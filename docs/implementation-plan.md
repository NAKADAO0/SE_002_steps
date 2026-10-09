# 三 Agent 代码审查 Workflow 实施计划

用户已选择代码审查流程。独立项目位于第二次/CodeReviewWorkflow，使用 E:\my_python\python.exe。

设计：CodingAgent → ReviewAgent → FixAgent → ReviewAgent。编排器用共享 Pydantic 状态和显式消息信封传递需求、代码版本和问题。通过审查才完成；达到修复/步骤上限标记需人工处理。每一步持久化 JSON 检查点和事件日志，失败保持原节点，可恢复。真实模型与明确标注的固定样例离线演示分开。

- [x] 先添加顺序、跨节点输入、分支、循环上限、失败恢复、非法输出和状态持久化的测试，运行确认失败。
- [x] 复制第一次的模型、Agent 基类、审查 Agent、规则引擎和工具实现，记录来源；不复制真实凭证、缓存或 Git。
- [x] 实现 state.py、agents.py、engine.py、storage.py，各模块只负责状态、节点、编排和持久化。
- [x] 实现明确固定样例的 DemoLLM 和 CLI，支持真实需求、输入文件、恢复检查点和导出。
- [x] 实现 Streamlit Workflow 状态面板，显示执行图、消息、代码版本、问题与日志。
- [x] 完成 README/Design、评审要求对应表、验证记录和安全打包。
- [x] 跑完整测试、离线端到端与真实模型流程，记录实际结果。

不自动执行生成的代码，不声称复审证明行为正确；源码和 Markdown/JSON 成果可下载。流程路由与节点注册分别定义，便于扩展。MVP 不引入分布式任务队列或并行调度。

阶段记录：初版交付时为 22 项测试、仅离线演示验证；用户随后提供 Key 并要求新前端。最新验证已升级为 29 项 Python 测试、3 项前端回归及 CLI/新前端两次真实 DeepSeek 完整流程，详见 verification.md。Key 仅位于本机 .env，提交包排除该文件。
