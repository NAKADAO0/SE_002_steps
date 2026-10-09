"""
结果校验与去重聚合器 (Verifier & Dedup)
"""

from typing import List
from ..schemas.code_types import CodeSmellItem, RiskSeverity


class Verifier:
    """缺陷去重与严重度定级器"""

    SEVERITY_ORDER = {
        RiskSeverity.CRITICAL: 0,
        RiskSeverity.HIGH: 1,
        RiskSeverity.MEDIUM: 2,
        RiskSeverity.LOW: 3,
    }

    @classmethod
    def dedup_and_sort(cls, items: List[CodeSmellItem]) -> List[CodeSmellItem]:
        """按行号和分类去重，并依风险严重度升序排序"""
        seen = set()
        deduped: List[CodeSmellItem] = []

        for item in items:
            key = (item.line, item.category)
            if key not in seen:
                seen.add(key)
                deduped.append(item)

        # 排序：先按严重度，再按行号
        deduped.sort(key=lambda x: (
            cls.SEVERITY_ORDER.get(x.severity, 99),
            x.line if x.line is not None else 99999
        ))
        return deduped
