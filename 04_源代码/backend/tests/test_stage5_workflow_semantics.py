from app.services.chat import _enrich_scenario
from app.services.workflow_templates import build_workflow_card


def evidence(identifier: str, title: str, quote: str) -> dict:
    return {
        "id": identifier,
        "policy_title": title,
        "section_path": "办理章节",
        "quote": quote,
    }


def assert_operational_card(card: dict, forbidden_policy_title: str) -> None:
    assert card["generation_source"] == "structured_template"
    assert card["tasks"] and card["process_flow"]
    assert all(item["id"] and item["title"] for item in card["tasks"])
    assert all(forbidden_policy_title not in item["title"] for item in card["tasks"])
    assert all(item["title"] != "按规定" for item in card["tasks"])
    assert card["estimated_completion"] is None


def test_annual_leave_checklist_and_flow_use_profile_people_without_policy_copy():
    policy = evidence("e-1", "休假管理制度", "年假提前 5 个工作日申请，超过 3 天由部门负责人和 HR 共同批准。")
    card = build_workflow_card(
        "可以申请", {
            "matter_type": "annual_leave", "duration_days": 5,
            "annual_leave_balance": 6, "direct_manager": "王强",
            "hrbp": "李敏", "department": "产品技术中心",
        }, [policy], ["员工状态：正式员工"],
    )
    assert_operational_card(card, "休假管理制度")
    assert card["tasks"][1]["title"] == "核对系统年假余额（当前 6 天）"
    labels = [item["label"] for item in card["process_flow"]]
    assert "王强（直属负责人）" in labels
    assert "李敏（产品技术中心 HRBP）" in labels


def test_missed_punch_checklist_has_concrete_actions_and_never_invents_hr_name():
    card = build_workflow_card(
        "可以补卡", {"matter_type": "attendance", "attendance_issue": "missed_punch", "direct_manager": "王强", "department": "产品技术中心"},
        [evidence("e-1", "考勤管理制度", "漏打卡须在 2 个工作日内提交补卡申请，由直属负责人审批。")], [],
    )
    assert_operational_card(card, "考勤管理制度")
    assert [item["title"] for item in card["tasks"]][:3] == ["确认漏打卡日期和时间", "填写漏打卡原因", "提交补卡申请"]
    hr_step = next(item for item in card["process_flow"] if item["id"] == "missed_punch.hr")
    assert hr_step["label"] == "产品技术中心 HRBP / 考勤负责人（当前系统未配置具体人员）"
    assert hr_step["person_configured"] is False


def test_travel_reimbursement_checklist_separates_materials_and_process_roles():
    card = build_workflow_card(
        "最晚十个工作日内提交", {"matter_type": "travel", "direct_manager": "王强"},
        [
            evidence("e-1", "差旅报销制度", "出差申请由直属负责人批准。"),
            evidence("e-2", "差旅报销制度", "报销须附合法票据、行程凭证和已批准的出差申请。"),
        ], [],
    )
    assert_operational_card(card, "差旅报销制度")
    material_task = next(item for item in card["tasks"] if item["id"] == "travel.collect_documents")
    assert material_task["title"] == "确认差旅报销材料齐全"
    assert "合法票据、行程凭证" in material_task["description"]
    assert any("财务报销经办角色（当前系统未配置具体人员）" == item["label"] for item in card["process_flow"])
    assert card["materials"]


def test_overtime_and_comp_time_use_preapproval_flow_without_fabricated_quota():
    scenario = _enrich_scenario("加班后怎么申请调休？", {})
    assert scenario == {"matter_type": "attendance", "attendance_issue": "overtime"}
    card = build_workflow_card(
        "需要事前批准", {**scenario, "direct_manager": "王强"},
        [evidence("e-1", "考勤管理制度", "加班须事前获得部门负责人批准。")], [],
    )
    assert_operational_card(card, "考勤管理制度")
    assert "在加班前提交给王强（直属负责人）审批" in [item["title"] for item in card["tasks"]]
    assert all("天调休" not in item["title"] for item in card["tasks"])


def test_resignation_checklist_uses_real_manager_and_unconfigured_hrbp_role():
    card = build_workflow_card(
        "需要提前通知", {"matter_type": "resignation", "employee_status": "regular", "direct_manager": "王强", "department": "产品技术中心"},
        [
            evidence("e-1", "入离职管理制度", "正式员工主动离职原则上提前 30 日书面通知。"),
            evidence("e-2", "入离职管理制度", "离职员工应完成工作、资产、账号和资料交接，IT 在离职当日关闭权限。"),
        ], [],
    )
    assert_operational_card(card, "入离职管理制度")
    labels = [item["label"] for item in card["process_flow"]]
    assert "王强（直属负责人）" in labels
    assert "产品技术中心 HRBP（当前系统未配置具体人员）" in labels
    assert any("工作、资产、账号和资料交接清单" in item["title"] for item in card["tasks"])
