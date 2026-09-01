import pytest

from app.services.chat import _chat_answer_text, _deduplicated_reasons, _reason_title


@pytest.mark.parametrize(
    ("question", "question_type", "decision", "primary", "reason", "missing", "expected_title", "focus_fact"),
    [
        ("我今年有几天年假？", "quota", "allowed", "你今年可享受 5 天年假。", "你累计工龄为 3.5 年，适用满 1 年不满 10 年档位。", [], "为什么是5 天？", "5 天"),
        ("差旅报销最晚什么时候提交？", "deadline", "informational", "最晚应在出差结束后 10 个工作日内提交。", "期限自出差结束次日起计算。", [], "时间要求", "10 个工作日"),
        ("试用期可以休年假吗？", "eligibility", "denied", "不可以申请年假。", "你当前处于试用期，制度将试用期员工列为排除对象。", [], "为什么不可以？", "不可以"),
        ("漏打卡怎么补卡？", "procedure", "informational", "请在考勤入口提交补卡申请。", "完整办理步骤已整理在右侧办理助手。", [], None, "提交补卡申请"),
        ("补卡找谁审批？", "approver", "informational", "先由直属负责人王强审批，再由 HRBP 李娜复核。", "审批人来自当前员工档案。", [], None, "王强"),
        ("报销需要什么材料？", "materials", "informational", "需要准备发票、行程凭证和报销申请单。", "材料须真实、完整且与本次差旅一致。", [], "需要准备", "发票"),
        ("年假怎么申请？", "procedure", "informational", "请从休假入口提交年假申请。", "完整流程已整理在右侧办理助手。", [], None, "提交年假申请"),
        ("我的年假额度是多少？", "quota", "conditional", "条件不足，暂时无法判断。", "条件不足，暂时无法判断。", ["累计工作年限"], None, "右侧补充"),
    ],
)
def test_eight_employee_questions_have_one_focused_short_answer(
    question, question_type, decision, primary, reason, missing, expected_title, focus_fact,
):
    reasons = _deduplicated_reasons(primary, [primary, reason], question_type)
    text = _chat_answer_text(
        primary,
        reasons,
        question_type=question_type,
        decision=decision,
        missing_conditions=missing,
    )

    assert text.count(primary) == 1, question
    assert focus_fact in text, question
    assert "结合当前情况，原因是" not in text
    assert len(text) <= 180
    if expected_title:
        assert f"【{expected_title}】" in text
    if decision == "conditional":
        assert "请在右侧补充后，我会重新判断" in text
        assert reasons == []


def test_semantic_formatter_removes_rephrased_primary_answer_but_keeps_rule_match():
    primary = "根据你当前的员工情况，你今年可享受 5 天年假。"
    reasons = _deduplicated_reasons(
        primary,
        [
            "你今年可享受 5 天年假。",
            "你累计工龄为 3.5 年，适用累计工作满 1 年不满 10 年的制度档位。",
            "按照当前员工情况，你今年能够休 5 天年假。",
        ],
        "quota",
    )

    assert reasons == ["你累计工龄为 3.5 年，适用累计工作满 1 年不满 10 年的制度档位。"]
    assert _reason_title("quota", "allowed", primary) == "为什么是5 天？"
