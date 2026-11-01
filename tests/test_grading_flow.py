import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from auto_thread import GradingThread
from config_manager import ConfigManager
from ui_schema import load_ui_schema

GOOD = json.dumps(
    {"student_answer_summary": "s", "scoring_basis": "b", "itemized_scores": [45]},
    ensure_ascii=False,
)


class FakeApi:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def call_api(self, img_str, prompt):
        self.calls += 1
        return self.outcomes.pop(0)


@pytest.fixture
def make_thread():
    def _make(outcomes):
        cm = ConfigManager.__new__(ConfigManager)
        cm.max_questions = load_ui_schema().max_questions
        cm._init_default_config()
        thread = GradingThread(FakeApi(outcomes), cm)
        thread._RETRY_DELAY_SECONDS = 0
        thread.running = True
        thread.completion_status = "running"
        return thread, cm

    return _make


def test_success_on_first_attempt_calls_api_once(make_thread):
    thread, cm = make_thread([(GOOD, None)])
    result = thread.evaluate_answer("data:image/jpeg;base64,AAAA", {"system": "S", "user": "U"}, cm.question_configs["1"])
    assert result[0] == 45.0
    assert thread.api_service.calls == 1


def test_transient_failure_retries_same_api(make_thread):
    thread, cm = make_thread([(None, "timeout"), (GOOD, None)])
    result = thread.evaluate_answer("data:image/jpeg;base64,AAAA", {"system": "S", "user": "U"}, cm.question_configs["1"])
    assert result[0] == 45.0
    assert thread.api_service.calls == 2
    assert thread.running


def test_all_attempts_failing_stops_grading(make_thread):
    thread, cm = make_thread([(None, "timeout")] * GradingThread._MAX_API_ATTEMPTS)
    result = thread.evaluate_answer("data:image/jpeg;base64,AAAA", {"system": "S", "user": "U"}, cm.question_configs["1"])
    assert result[0] is None
    assert thread.api_service.calls == GradingThread._MAX_API_ATTEMPTS
    assert not thread.running
    assert thread.completion_status == "error"


def test_prompt_puts_stable_rubric_last_and_is_deterministic(make_thread):
    thread, _ = make_thread([])
    first = thread.select_and_build_prompt("细则A", "Holistic_Evaluation_Open")
    second = thread.select_and_build_prompt("细则A", "Holistic_Evaluation_Open")
    assert first == second
    assert first["user"].rstrip().endswith("细则A")
    assert "学生答案文本" not in first["system"] + first["user"]
