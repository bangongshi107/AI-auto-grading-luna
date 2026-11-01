import os
import re

import ui_schema
from api_service import PROVIDER_CONFIGS, get_provider_id_from_ui_text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI_PATH = os.path.join(ROOT, "setting", ui_schema.UI_FILE_NAME)


def _ui_text():
    with open(UI_PATH, encoding="utf-8") as f:
        return f.read()


def _parse_modified(tmp_path, transform):
    path = tmp_path / "modified.ui"
    path.write_text(transform(_ui_text()), encoding="utf-8")
    return ui_schema.parse_ui_schema(str(path))


def test_real_ui_has_no_problems():
    schema = ui_schema.parse_ui_schema(UI_PATH)
    assert schema.problems == ()
    assert schema.max_questions == 7


def test_every_ui_provider_text_maps_to_a_provider():
    schema = ui_schema.parse_ui_schema(UI_PATH)
    ids = [get_provider_id_from_ui_text(t) for t in schema.provider_texts]
    assert None not in ids
    assert set(ids) == set(PROVIDER_CONFIGS)


def test_unknown_provider_text_is_reported(tmp_path):
    schema = _parse_modified(tmp_path, lambda t: t.replace("<string>DeepSeek</string>", "<string>腾讯混元</string>"))
    assert any("腾讯混元" in p for p in schema.problems)
    assert any("deepseek" in p for p in schema.problems)


def test_missing_widget_is_reported(tmp_path):
    schema = _parse_modified(tmp_path, lambda t: t.replace('name="score_rounding_step_3"', 'name="step_renamed"'))
    assert any("score_rounding_step_3" in p for p in schema.problems)


def test_removing_a_question_tab_changes_max_questions(tmp_path):
    schema = _parse_modified(tmp_path, lambda t: t.replace('name="tab_question7"', 'name="tab_other"'))
    assert schema.max_questions == 6


def test_code_only_references_widgets_that_exist_in_ui():
    """代码里按名字访问的控件必须都在 .ui 里，否则 get_ui_element 会静默返回 None。"""
    import xml.etree.ElementTree as ET

    names = {w.get("name") for w in ET.parse(UI_PATH).getroot().iter("widget")}
    source_path = os.path.join(ROOT, "ui_components", "main_window.py")
    with open(source_path, encoding="utf-8") as f:
        source = f.read()

    pattern = re.compile(r"(?:get_ui_element|_safe_set_enabled)\(\s*(f?)(['\"])([^'\"]+)\2")
    found = pattern.findall(source)
    assert found, "未扫描到任何控件引用，检查正则是否失效"
    missing = []
    for is_f, _, name in found:
        candidate = re.sub(r"\{[^}]+\}", "1", name) if is_f else name
        if candidate not in names:
            missing.append(name)
    assert not missing, f"main_window.py 引用了 .ui 中不存在的控件: {sorted(set(missing))}"
