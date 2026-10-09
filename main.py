"""Command-line entry point: python main.py --demo."""
import argparse
from pathlib import Path
from workflow.demo import REQUIREMENT, BUG
from workflow.service import ROOT, create_workflow
from workflow.state import WorkflowState
from workflow.storage import RunStore


def main(argv=None):
    parser = argparse.ArgumentParser(description="三 Agent 代码审查 Workflow")
    parser.add_argument("--demo", action="store_true", help="固定平均值示例，不调用真实模型")
    parser.add_argument("--requirement", help="真实模式的需求")
    parser.add_argument("--file", help="项目目录内的 Python 初始代码，相对项目根目录")
    parser.add_argument("--resume", help="从失败检查点恢复，自动使用原来的 demo/live 模式")
    parser.add_argument("--output-dir", default=str(ROOT / "runs"))
    parser.add_argument("--max-repairs", type=int, default=2)
    args = parser.parse_args(argv)
    try:
        if args.resume:
            if args.demo or args.requirement or args.file:
                raise ValueError("恢复时不同时传入新需求、文件或 --demo")
            state = RunStore(args.output_dir).load(args.resume)
        else:
            if args.demo and (args.requirement or args.file):
                raise ValueError("--demo 仅支持固定示例；自定义需求或代码请使用真实模式")
            source = ""
            if args.file:
                path = (ROOT / args.file).resolve()
                if not path.is_relative_to(ROOT) or path.suffix != ".py":
                    raise ValueError("--file 必须是项目目录内的 .py 文件")
                if path.stat().st_size > 100_000:
                    raise ValueError("输入源码不能大于 100KB")
                source = path.read_text(encoding="utf-8")
            state = WorkflowState(requirement=REQUIREMENT if args.demo else (args.requirement or ""),
                                  source_code=BUG if args.demo else source,
                                  mode="demo" if args.demo else "live", max_repairs=args.max_repairs)
        flow = create_workflow(state.mode, args.output_dir)
        result = flow.run(state, on_event=lambda s: print(
            f"[{s.events[-1].kind}] {s.events[-1].node}: {s.events[-1].message}"))
        print(f"状态: {result.status}\n运行 ID: {result.run_id}\n输出: {flow.store.directory(result.run_id)}")
        if result.error:
            print(result.error)
        return 0 if result.status == "completed" else (2 if result.status == "needs_attention" else 1)
    except (ValueError, OSError) as exc:
        print(f"输入或配置错误: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
