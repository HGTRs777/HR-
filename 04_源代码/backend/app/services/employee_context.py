from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from ..models import EmployeeUser


PROFILE_FIELDS = (
    "department",
    "job_title",
    "hire_date",
    "employee_status",
    "tenure_years",
    "company_tenure_years",
    "direct_manager",
    "hrbp",
    "annual_leave_entitlement",
    "annual_leave_balance",
)

PROFILE_RELEVANCE = {
    "annual_leave": PROFILE_FIELDS,
    "travel": ("department", "job_title", "direct_manager", "hrbp"),
    "resignation": (
        "department", "job_title", "hire_date", "company_tenure_years",
        "employee_status", "direct_manager", "hrbp",
    ),
    "attendance": ("department", "job_title", "employee_status", "direct_manager", "hrbp"),
    "onboarding": (
        "department", "job_title", "hire_date", "company_tenure_years",
        "employee_status", "direct_manager", "hrbp",
    ),
}


@dataclass(frozen=True)
class EmployeeBusinessContext:
    profile_snapshot: dict[str, Any]
    conditions: dict[str, Any]
    sources: dict[str, str]


def _company_tenure_years(hire_date: date | None, as_of: date) -> float | None:
    if hire_date is None or hire_date > as_of:
        return None
    completed_months = (as_of.year - hire_date.year) * 12 + as_of.month - hire_date.month
    if as_of.day < hire_date.day:
        completed_months -= 1
    return round(max(completed_months, 0) / 12, 2)


def employee_profile_payload(employee: EmployeeUser) -> dict[str, Any]:
    return {
        "department": employee.department,
        "job_title": employee.job_title,
        "hire_date": employee.hire_date.isoformat() if employee.hire_date else None,
        "employee_status": employee.employee_status,
        # This is explicitly cumulative working experience, which may include employment before this company.
        "tenure_years": employee.tenure_years,
        "direct_manager": employee.direct_manager,
        "hrbp": employee.hrbp,
        "annual_leave_entitlement": employee.annual_leave_entitlement,
        "annual_leave_balance": employee.annual_leave_balance,
    }


def build_employee_business_context(
    employee: EmployeeUser | None,
    *,
    as_of: date | None = None,
) -> EmployeeBusinessContext:
    today = as_of or date.today()
    if employee is None:
        snapshot = {field: None for field in PROFILE_FIELDS}
        return EmployeeBusinessContext(profile_snapshot=snapshot, conditions={}, sources={})

    snapshot = employee_profile_payload(employee)
    snapshot["company_tenure_years"] = _company_tenure_years(employee.hire_date, today)
    conditions = {field: value for field, value in snapshot.items() if value is not None}
    sources = {
        field: "derived_from_hire_date" if field == "company_tenure_years" else "employee_profile"
        for field in conditions
    }
    return EmployeeBusinessContext(profile_snapshot=snapshot, conditions=conditions, sources=sources)
