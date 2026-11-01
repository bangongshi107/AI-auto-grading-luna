# ui_schema.py - 界面选项的读取与一致性检查：setting/七题.ui
#
# 分工：.ui 决定“显示什么、有几题”；代码决定“每个选项真正做什么”（供应商接口）。
# 两边必须保持一致，这里在启动时检查并报出不一致（UiSchema.problems），而不是静默失效。
# 直接解析 .ui 的 XML（不依赖 Qt），因此 ConfigManager 与 MainWindow 读到的是同一份数据。

import os
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from functools import lru_cache
from typing import List, Tuple

UI_FILE_NAME = "七题.ui"

_PROVIDER_COMBOS = ("first_api_url",)

# 运行时代码会按名字访问这些控件；改名/删除会在启动时被明确报出，而不是静默失效
_REQUIRED_GLOBAL_WIDGETS = (
    "questionTabs", "first_api_url", "first_api_key", "first_modelID",
    "subject_text", "cycle_number", "wait_time", "log_text",
)
_REQUIRED_PER_QUESTION_WIDGETS = (
    "enableQuestion{i}", "configQuestion{i}", "StandardAnswer_text_{i}",
    "score_rounding_step_{i}",
)


@dataclass(frozen=True)
class UiSchema:
    provider_texts: Tuple[str, ...]
    max_questions: int
    problems: Tuple[str, ...]


def ui_file_path() -> str:
    if getattr(sys, "frozen", False):
        base_path = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, "setting", UI_FILE_NAME)


def _combo_item_texts(widget: ET.Element) -> List[str]:
    texts = []
    for item in widget.findall("item"):
        for prop in item.findall("property"):
            if prop.get("name") == "text":
                node = prop.find("string")
                texts.append((node.text or "").strip() if node is not None else "")
    return texts


def _combo_provider_problems(widgets: dict) -> List[str]:
    """provider 下拉框的每个选项必须能对应到 api_service 里的某个供应商。"""
    from api_service import PROVIDER_CONFIGS, get_provider_id_from_ui_text

    problems = []
    offered = set()
    for combo_name in _PROVIDER_COMBOS:
        widget = widgets.get(combo_name)
        if widget is None:
            continue
        for text in _combo_item_texts(widget):
            provider_id = get_provider_id_from_ui_text(text)
            if provider_id is None:
                problems.append(f"{combo_name} 的选项“{text}”没有对应的接口配置（api_service.PROVIDER_CONFIGS），选中后将无法使用")
            else:
                offered.add(provider_id)
    for provider_id in PROVIDER_CONFIGS:
        if provider_id not in offered:
            problems.append(f"接口 {provider_id} 已在代码中配置，但 .ui 的下拉框里没有对应选项")
    return problems


def load_ui_schema() -> UiSchema:
    return _load_ui_schema_cached()


@lru_cache(maxsize=1)
def _load_ui_schema_cached() -> UiSchema:
    return parse_ui_schema(ui_file_path())


def parse_ui_schema(path: str) -> UiSchema:
    root = ET.parse(path).getroot()
    widgets = {w.get("name"): w for w in root.iter("widget") if w.get("name")}
    problems: List[str] = []

    tabs = widgets.get("questionTabs")
    tab_numbers = []
    if tabs is not None:
        for child in tabs.findall("widget"):
            m = re.fullmatch(r"tab_question(\d+)", child.get("name") or "")
            if m:
                tab_numbers.append(int(m.group(1)))
    max_questions = max(tab_numbers) if tab_numbers else 0
    if not tab_numbers or sorted(tab_numbers) != list(range(1, max_questions + 1)):
        problems.append(f"questionTabs 中的题目页必须是连续的 tab_question1..N，当前为：{sorted(tab_numbers)}")

    provider_texts: Tuple[str, ...] = ()
    first_combo = widgets.get("first_api_url")
    if first_combo is not None:
        provider_texts = tuple(_combo_item_texts(first_combo))
    if not provider_texts:
        problems.append("first_api_url 下拉框没有任何选项")
    problems.extend(_combo_provider_problems(widgets))

    for name in _REQUIRED_GLOBAL_WIDGETS:
        if name not in widgets:
            problems.append(f"缺少控件：{name}")
    for i in range(1, max_questions + 1):
        for template in _REQUIRED_PER_QUESTION_WIDGETS:
            name = template.format(i=i)
            if name not in widgets:
                problems.append(f"缺少控件：{name}")

    return UiSchema(
        provider_texts=provider_texts,
        max_questions=max_questions,
        problems=tuple(problems),
    )
