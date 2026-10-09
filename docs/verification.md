# 验证记录

验证日期：2026-10-08；本机 Windows，Python 路径 `E:\my_python\python.exe`。

## 已验证

完整自动测试最新结果：**38 passed**；`node --test docs/frontend-regression.cjs`：**6 passed**。pytest 有一条第三方 Starlette/AnyIO 别名弃用警告，不影响当前验证。

新的 FastAPI 工作区运行于 http://127.0.0.1:8560，`/api/settings` 与 `/api/runs` 正常。8502 属于本机 Windows 保留端口范围（8427–8526），使用 8560；原 Streamlit 可另用 8561。

- pytest 覆盖三个 Agent 完整交接、复审、恢复、修复次数和步骤上限。
- CLI 子进程固定演示完成 code → review → fix → review，completed、repairs=1。
- Streamlit AppTest 点击“运行 Workflow”完成相同流程，无界面异常。
- 模型桩触发真实 lint_code 工具并收到 tool_result；模型和静态问题合并。
- 独立审查发现的非法顶层 return、空白/注释输出、UI 回调异常已增加回归测试并修复。
- 可插入 format 节点修改顺序路由；失败修复保留上一版本；检查点 ID 不一致被拒绝。
- 新工作区 API 演示、任务历史、恢复、服务重启、并发限制、同源请求、UTF-8 输入大小和配置不泄露验证通过。
- 独立审查发现并修复：服务重启后任务卡在 running、轮询网络失败后永久停更、旧提交响应覆盖新页面。
- 前端回归执行真实 app.js，验证重试与提交切换页面竞态。

## 真实服务验证边界

用户提供的 Key 已写入本机第二次项目的 .env。采用 `deepseek-flash`，参考 [官方首次调用文档](https://api-docs.deepseek.com/zh-cn/)。Key 不保存于本文、浏览器、源码或提交包。

| 入口 | 运行 ID | 结果 |
| --- | --- | --- |
| CLI 真实平均值样例 | ae477e8a427947f3ae99abefb1323885 | completed、4 个节点、修复 1 次 |
| 新前端提交真实平均值样例 | 88ce18aadc87409d93c87f5ad088022c | completed、4 个节点、修复 1 次 |

两次均经历 code → review → fix → review，各节点实际调用 lint_code。修复后增加 count 判零，复审无剩余问题。第一轮较宽泛 Prompt 曾因风格建议达到修复上限并正确保留 needs_attention；随后收紧审查为显式需求、可定位缺陷和安全风险，并要求最小修复，两次新运行正常收敛，没有篡改未通过任务状态。

上述结果仅验证这些样例。生成代码未自动执行，不代表实际运行测试已通过，也不保证其他输入或未来模型调用成功。

## 浏览器验证

实际验证了示例填充、真实提交、四节点状态、历史查看、代码差异页签及主题切换。1440px 下三栏可见且无页面横向溢出；390px 下可展开结果面板，无页面横向溢出。1200px 桌面截图保存在 workspace-preview.jpg。

## MVP 限制

工作区拒绝同任务重复启动，最多并行执行两个不同任务。单进程服务不支持多 uvicorn worker，也不要用 CLI 和 Web 同时恢复同 ID；无分布式调度或拖拽编辑。state.json 是权威检查点。生成代码只做静态检查，不自动执行。

## 文件输入与导出验证

新接口与回归覆盖文件上传、中文文件名、大小/路径/编码限制、自然语言路由、只审查原样交接、UTF-8导出与GBK声明规范化、未完成任务拒绝导出、上传异步响应隔离。真实浏览器上传 average_bug.py，输入自然语言启动，运行 ae3b0a509fd547de8678a578a23c61f4 完成四节点、修复一次，初始源码完整保留。浏览器原生附件下载成功，保留 average_bug.py 文件名（同名文件已有时浏览器自动附加序号）。已有源码的编码节点现在执行确定性静态验证/交接，审查与修复节点实际调用 DeepSeek 与 lint 工具。
