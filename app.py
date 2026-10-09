"""Streamlit workflow dashboard; no user-generated code is executed."""
import streamlit as st
from workflow.demo import REQUIREMENT, BUG
from workflow.service import ROOT, create_workflow
from workflow.state import WorkflowState
from workflow.storage import RunStore

st.set_page_config(page_title="三 Agent 代码审查", page_icon="🔄", layout="wide")
st.title("三 Agent 代码审查 Workflow")
st.caption("编码 → 审查 → 修复 → 复审 · 顺序编排 / 共享状态 / 检查点恢复")
st.graphviz_chart('digraph {rankdir=LR; user[label="需求 / 初始代码"]; code[label="编码 Agent"]; review[label="审查 Agent"]; fix[label="修复 Agent"]; done[label="完成 / 待人工处理"]; user->code; code->review; review->fix[label="有问题且未超限"]; fix->review[label="复审"]; review->done[label="通过或达上限"];}')
demo = st.sidebar.checkbox("离线固定示例", value=True)
st.sidebar.info("演示只处理内置平均值示例，不调用 LLM。关闭后支持自定义需求和 Python 代码，需要配置 API Key。")
limit = st.sidebar.number_input("最多修复次数", min_value=0, max_value=10, value=2)
requirement = st.text_area("需求", value=REQUIREMENT, disabled=demo)
source = st.text_area("初始 Python 代码（可选）", value=BUG, height=150, disabled=demo)
resume_id = st.sidebar.text_input("失败运行 ID")
run_clicked = st.button("运行 Workflow", type="primary")
resume_clicked = st.sidebar.button("恢复失败运行")
progress = st.empty()

if run_clicked or resume_clicked:
    try:
        if resume_clicked:
            state = RunStore(ROOT / "runs").load(resume_id.strip())
            if state.status != "failed":
                raise ValueError("只需要恢复 failed 状态；超限任务请调整参数后新建运行")
        else:
            if len(source.encode("utf-8")) > 100_000:
                raise ValueError("输入源码不能大于 100KB")
            state = WorkflowState(requirement=REQUIREMENT if demo else requirement,
                                  source_code=BUG if demo else source,
                                  mode="demo" if demo else "live", max_repairs=int(limit))
        flow = create_workflow(state.mode)
        with st.spinner("Agent 正在协作，请等待..."):
            st.session_state.result = flow.run(state, on_event=lambda s:
                progress.info(f"{s.events[-1].node} / {s.events[-1].kind} · 已完成 {s.steps} 个节点"))
    except Exception as exc:
        st.error(str(exc))

if "result" in st.session_state:
    result = st.session_state.result
    st.subheader(f"执行状态：{result.status}")
    st.caption(f"运行 ID：{result.run_id} | 模式：{result.mode} | 修复次数：{result.repairs}")
    if result.error:
        st.error(result.error)
    st.write(result.summary)
    st.info("completed 表示审查未发现剩余问题。系统不会执行生成代码，不代表运行测试通过。")
    st.code(result.code, language="python")
    st.download_button("下载当前代码", result.code, "final_code.py")
    st.download_button("下载完整状态", result.model_dump_json(indent=2), "state.json")
    st.subheader("剩余问题")
    st.json(result.issues)
    st.subheader("执行日志")
    st.dataframe([e.model_dump() for e in result.events], use_container_width=True)
    with st.expander("Agent 间消息与代码版本"):
        st.json([m.model_dump(mode="json") for m in result.messages])
        for index, code in enumerate(result.revisions, 1):
            st.markdown(f"版本 {index}")
            st.code(code, language="python")
