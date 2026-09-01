from __future__ import annotations

from typing import Any


EMPTY_WORKFLOW_CARD: dict[str, Any] = {
    "conclusion": "",
    "applicable_conditions": [],
    "tasks": [],
    "process_flow": [],
    "estimated_completion": None,
    "generation_source": "structured_template",
    "basis_evidence_ids": [],
    # Compatibility fields for older clients.
    "timeline": [],
    "materials": [],
    "cautions": [],
    "next_steps": [],
}


def _evidence_ids(evidence: list[dict[str, Any]], *keywords: str) -> list[str]:
    matched = []
    for item in evidence:
        haystack = f"{item.get('policy_title', '')}\n{item.get('section_path', '')}\n{item.get('quote', '')}"
        if not keywords or any(keyword in haystack for keyword in keywords):
            matched.append(str(item["id"]))
    return list(dict.fromkeys(matched))[:3]


def _person_or_role(
    scenario: dict[str, Any],
    field: str,
    role: str,
    *,
    department_scoped: bool = False,
) -> tuple[str, bool]:
    person = scenario.get(field)
    department = scenario.get("department") if department_scoped else None
    if isinstance(person, str) and person.strip():
        scoped_role = f"{department} {role}" if department else role
        return f"{person.strip()}（{scoped_role}）", True
    scoped_role = f"{department} {role}" if department else role
    return f"{scoped_role}（当前系统未配置具体人员）", False


def _task(
    identifier: str,
    title: str,
    description: str,
    evidence_ids: list[str],
    category: str = "action",
) -> dict[str, Any]:
    return {
        "id": identifier,
        "title": title,
        "description": description,
        "evidence_ids": evidence_ids,
        "category": category,
    }


def _flow(
    identifier: str,
    label: str,
    detail: str,
    evidence_ids: list[str],
    *,
    person_configured: bool | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": identifier,
        "label": label,
        "detail": detail,
        "evidence_ids": evidence_ids,
    }
    if person_configured is not None:
        result["person_configured"] = person_configured
    return result


def _annual_leave(
    scenario: dict[str, Any], evidence: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    application_ids = _evidence_ids(evidence, "年假", "年休假", "休假申请")
    approval_ids = _evidence_ids(evidence, "批准", "审批", "负责人", "HR")
    manager, manager_configured = _person_or_role(scenario, "direct_manager", "直属负责人")
    hrbp, hrbp_configured = _person_or_role(scenario, "hrbp", "HRBP", department_scoped=True)
    balance = scenario.get("annual_leave_balance")
    balance_title = (
        f"核对系统年假余额（当前 {balance:g} 天）"
        if isinstance(balance, (int, float)) and not isinstance(balance, bool)
        else "核对系统中的年假可用余额"
    )
    tasks = [
        _task("annual_leave.confirm_plan", "确认计划休假日期和天数", "先确认起止日期，避免申请天数与实际安排不一致。", application_ids),
        _task("annual_leave.check_balance", balance_title, "以系统当前显示的真实可用余额为准。", application_ids),
        _task("annual_leave.submit", "填写并提交年假申请", "在公司现有请假入口填写日期、天数和必要说明。", application_ids),
        _task("annual_leave.manager_review", f"等待{manager}审批", "提交后由当前档案对应的直属负责人处理；未配置姓名时仅展示角色。", approval_ids),
    ]
    duration = scenario.get("duration_days")
    if isinstance(duration, (int, float)) and not isinstance(duration, bool) and duration > 3:
        tasks.append(_task("annual_leave.hrbp_review", f"等待{hrbp}复核", "连续休假超过 3 天时进入 HR 共同审批环节。", approval_ids))
    tasks.append(_task("annual_leave.confirm_record", "确认请假记录和年假余额已更新", "审批完成后再核对系统记录，不把提交申请视为已经办结。", application_ids))
    flow = [
        _flow("annual_leave.employee", "员工发起年假申请", "填写日期、天数和申请说明。", application_ids),
        _flow("annual_leave.manager", manager, "直属负责人处理申请。", approval_ids, person_configured=manager_configured),
    ]
    if isinstance(duration, (int, float)) and not isinstance(duration, bool) and duration > 3:
        flow.append(_flow("annual_leave.hrbp", hrbp, "按制度完成 HR 共同审批。", approval_ids, person_configured=hrbp_configured))
    flow.extend([
        _flow("annual_leave.record", "休假记录更新", "系统记录审批结果并更新可用余额。", application_ids),
        _flow("annual_leave.complete", "完成", "员工自行确认记录无误。", []),
    ])
    return tasks, flow


def _missed_punch(
    scenario: dict[str, Any], evidence: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ids = _evidence_ids(evidence, "漏打卡", "补卡", "考勤")
    manager, manager_configured = _person_or_role(scenario, "direct_manager", "直属负责人")
    hrbp, hrbp_configured = _person_or_role(
        scenario, "hrbp", "HRBP / 考勤负责人", department_scoped=True,
    )
    tasks = [
        _task("missed_punch.confirm_time", "确认漏打卡日期和时间", "核对异常考勤记录对应的班次和时间点。", ids),
        _task("missed_punch.reason", "填写漏打卡原因", "如实说明未打卡原因，并准备系统要求的可验证说明。", ids),
        _task("missed_punch.submit", "提交补卡申请", "在补卡时限内从现有考勤入口提交。", ids),
        _task("missed_punch.manager_review", f"等待{manager}审批", "提交后由直属负责人处理。", ids),
        _task("missed_punch.hr_review", f"等待{hrbp}复核", "由 HRBP 或考勤负责角色复核考勤记录；未配置姓名时仅展示角色。", ids),
        _task("missed_punch.confirm_record", "确认考勤记录已更新", "审批通过后检查异常记录是否已经消除。", ids),
    ]
    flow = [
        _flow("missed_punch.employee", "员工发起补卡申请", "填写漏打卡时间和原因。", ids),
        _flow("missed_punch.manager", manager, "直属负责人审批补卡申请。", ids, person_configured=manager_configured),
        _flow("missed_punch.hr", hrbp, "复核并处理考勤记录。", ids, person_configured=hrbp_configured),
        _flow("missed_punch.record", "考勤记录更新", "系统记录处理结果。", ids),
        _flow("missed_punch.complete", "完成", "员工自行确认记录无误。", []),
    ]
    return tasks, flow


def _overtime(
    scenario: dict[str, Any], evidence: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ids = _evidence_ids(evidence, "加班", "调休", "事前", "批准")
    manager, manager_configured = _person_or_role(scenario, "direct_manager", "直属负责人")
    tasks = [
        _task("overtime.confirm_plan", "确认加班日期、时段和工作任务", "先明确业务原因和计划时长。", ids),
        _task("overtime.preapprove", f"在加班前提交给{manager}审批", "未获得事前批准时，不把延时停留当作已确认加班。", ids),
        _task("overtime.record", "完成加班记录", "按现有考勤入口记录实际加班时间。", ids),
        _task("overtime.confirm_result", "确认加班或调休记录已更新", "制度未明确调休额度时，不自行推算可调休时长。", ids),
    ]
    flow = [
        _flow("overtime.employee", "员工提交加班申请", "填写日期、时段、任务和原因。", ids),
        _flow("overtime.manager", manager, "在加班发生前完成审批。", ids, person_configured=manager_configured),
        _flow("overtime.record", "考勤记录确认", "记录实际发生的加班时间。", ids),
        _flow("overtime.complete", "完成", "员工自行核对加班或调休记录。", []),
    ]
    return tasks, flow


def _travel(
    scenario: dict[str, Any], evidence: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    trip_ids = _evidence_ids(evidence, "出差申请", "直属负责人", "目的地", "预算")
    reimbursement_ids = _evidence_ids(evidence, "报销", "票据", "行程凭证")
    manager, manager_configured = _person_or_role(scenario, "direct_manager", "直属负责人")
    finance = "财务报销经办角色（当前系统未配置具体人员）"
    tasks = [
        _task("travel.confirm_expenses", "核对出差日期和费用明细", "按本次出差逐项核对交通、住宿和其他费用。", reimbursement_ids),
        _task("travel.collect_documents", "确认差旅报销材料齐全", "核对合法票据、行程凭证和已批准的出差申请；缺少真实凭证时不要标记为材料齐全。", reimbursement_ids, "material"),
        _task("travel.fill_form", "填写并提交差旅报销单", "在制度规定期限内从现有报销入口提交。", reimbursement_ids),
        _task("travel.manager_review", f"等待{manager}确认", "由当前档案对应的直属负责人处理业务确认环节。", trip_ids),
        _task("travel.finance_review", f"等待{finance}审核", "系统没有财务经办人字段，因此只展示角色，不显示姓名。", reimbursement_ids),
        _task("travel.confirm_payment", "确认报销结果和到账记录", "提交不代表已经审核或付款，需自行核对最终结果。", reimbursement_ids),
    ]
    flow = [
        _flow("travel.employee", "员工提交差旅报销", "填写费用明细并上传真实凭证。", reimbursement_ids),
        _flow("travel.manager", manager, "确认出差事项和业务真实性。", trip_ids, person_configured=manager_configured),
        _flow("travel.finance", finance, "审核票据和报销标准。", reimbursement_ids, person_configured=False),
        _flow("travel.payment", "报销结果处理", "以真实财务系统状态为准。", reimbursement_ids),
        _flow("travel.complete", "完成", "员工自行确认结果或到账记录。", []),
    ]
    return tasks, flow


def _resignation(
    scenario: dict[str, Any], evidence: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    notice_ids = _evidence_ids(evidence, "离职", "通知", "提前")
    handover_ids = _evidence_ids(evidence, "交接", "资产", "账号", "资料", "IT", "工资")
    manager, manager_configured = _person_or_role(scenario, "direct_manager", "直属负责人")
    hrbp, hrbp_configured = _person_or_role(scenario, "hrbp", "HRBP", department_scoped=True)
    tasks = [
        _task("resignation.notice", "按适用期限提交书面离职申请", "根据当前员工状态核对通知期限后再提交。", notice_ids),
        _task("resignation.handover_list", "整理工作、资产、账号和资料交接清单", "逐项列明交接对象和完成情况。", handover_ids),
        _task("resignation.manager_review", f"与{manager}确认工作交接", "由当前档案对应的直属负责人确认工作安排。", handover_ids),
        _task("resignation.hr_process", f"与{hrbp}确认离职手续", "未配置姓名时仅展示 HRBP 角色。", notice_ids + handover_ids),
        _task("resignation.assets", "归还公司资产并确认账号权限处理", "资产归还和权限关闭均以实际系统或经办记录为准。", handover_ids),
        _task("resignation.documents", "核对离职证明和薪资结算安排", "不要把提交离职申请视为证明已开具或工资已结清。", handover_ids),
    ]
    flow = [
        _flow("resignation.employee", "员工提交书面离职申请", "按当前员工状态适用的通知期限发起。", notice_ids),
        _flow("resignation.manager", manager, "确认离职安排和工作交接。", handover_ids, person_configured=manager_configured),
        _flow("resignation.hrbp", hrbp, "办理人事手续。", notice_ids + handover_ids, person_configured=hrbp_configured),
        _flow("resignation.it", "IT / 资产经办角色（当前系统未配置具体人员）", "处理账号权限和资产事项。", handover_ids, person_configured=False),
        _flow("resignation.settlement", "证明与薪资结算", "以真实办理和发薪记录为准。", handover_ids),
        _flow("resignation.complete", "完成", "员工自行核对全部交接结果。", []),
    ]
    return tasks, flow


def build_workflow_card(
    summary: str,
    scenario: dict[str, Any],
    evidence: list[dict[str, Any]],
    conditions: list[str],
) -> dict[str, Any]:
    matter_type = scenario.get("matter_type")
    attendance_issue = scenario.get("attendance_issue")
    builder = None
    if matter_type == "annual_leave":
        builder = _annual_leave
    elif matter_type == "travel":
        builder = _travel
    elif matter_type == "resignation":
        builder = _resignation
    elif matter_type == "attendance" and attendance_issue == "missed_punch":
        builder = _missed_punch
    elif matter_type == "attendance" and attendance_issue == "overtime":
        builder = _overtime
    if builder is None or not evidence:
        return {**EMPTY_WORKFLOW_CARD, "conclusion": summary, "applicable_conditions": conditions}

    tasks, process_flow = builder(scenario, evidence)
    basis_ids = list(dict.fromkeys(
        identifier
        for item in [*tasks, *process_flow]
        for identifier in item.get("evidence_ids", [])
    ))
    # Compatibility groups remain operational actions; policy quotes are never copied into them.
    materials = [item for item in tasks if item.get("category") == "material"]
    cautions = [item for item in tasks if item.get("category") != "material"]
    timeline = [
        {
            "id": item["id"],
            "title": item["label"],
            "description": item["detail"],
            "evidence_ids": item["evidence_ids"],
        }
        for item in process_flow
    ]
    return {
        "conclusion": summary,
        "applicable_conditions": conditions,
        "tasks": tasks,
        "process_flow": process_flow,
        "estimated_completion": None,
        "generation_source": "structured_template",
        "basis_evidence_ids": basis_ids,
        "timeline": timeline,
        "materials": materials,
        "cautions": cautions,
        "next_steps": [
            {"text": item["title"], "evidence_ids": item["evidence_ids"]}
            for item in tasks
        ],
    }
