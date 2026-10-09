"""Fixed offline fixture, deliberately not a general-purpose language model."""
import json
from code_analyzer.core.llm_client import LLMResponse
from code_analyzer.query.rule_engine import RuleEngine

REQUIREMENT = "实现 average(values)，返回数值列表的平均值，空列表返回 0.0。"
BUG = "def average(values):\n    return sum(values) / len(values)\n"
FIX = "def average(values):\n    total = sum(values)\n    count = len(values)\n    if count == 0:\n        return 0.0\n    return total / count\n"


class DemoLLM:
    def chat(self, messages, tools=None):
        role = messages[0]["content"]
        payload = json.loads(messages[-1]["content"])
        if "你是编码 Agent" in role:
            output = {"code": BUG, "summary": "固定演示：含空列表缺陷的初始版本"}
        elif "你是修复 Agent" in role:
            output = {"code": FIX, "summary": "固定演示：增加除数判零"}
        else:
            issues = RuleEngine().analyze_source(payload["code"])["issues"]
            output = {"summary": "固定示例静态审查", "issues": [i.model_dump(mode="json") for i in issues]}
        return LLMResponse(content=json.dumps(output, ensure_ascii=False))
