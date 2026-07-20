"""One-time historical import of the Salary Excel register into the
in-app Payroll module.

Dry-run by default; pass --commit to write. Uses openpyxl's data_only=True
load, which resolves every formula cell (including "New Salary"'s manually
typed running-sum string) to its last-cached numeric value directly - no
formula parsing or eval() needed.

Safely re-runnable: a period that already has a PayrollRun for the target
organization is skipped entirely on a later run.

Duplicate (period, employee) rows: the first row wins. The source sheet
has one known exact-duplicate block (identical values, order doesn't
matter) and one known conflicting duplicate (two rows with different
attendance figures for the same employee/month, where the first row sits
in the correctly-positioned block and the second is a mislabeled entry
from a different month's block) - first-row-wins resolves both correctly.
"""
from __future__ import annotations

import datetime
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from payslip.models import Employee, PayrollRun, PayslipEntry, payroll_settings_for
from payslip.services.payroll_calc import compute_entry

# Sheet1 column letters (verified against the real workbook).
COL_MONTH = "A"
COL_NAME = "C"
COL_DESIGNATION = "D"
COL_TWD = "E"
COL_CL = "F"
COL_EMP_LEAVE = "G"
COL_LOP = "H"
COL_PRESENT = "I"
COL_PAY_DAYS = "J"
COL_NEW_SALARY = "K"
COL_BASIC = "L"
COL_DA = "M"
COL_HRA = "N"
COL_TRANSPORT = "O"
COL_FOOD = "P"
COL_INTERNET = "Q"
COL_ARREAR = "R"
COL_GROSS = "S"
COL_ESI_EMP = "T"
COL_ESI_ER = "U"
COL_PF_EMP = "V"
COL_PF_ER = "W"
COL_ADVANCE = "X"
COL_TDS = "Y"
COL_TOTAL_DED = "Z"
COL_NET = "AA"
COL_REMARKS = "AH"

# Sheet4 (employee master) column letters.
S4_NAME = "C"
S4_DOJ = "H"
S4_REMARKS = "K"

TWO_DP = Decimal("0.01")


def _dec(value, default="0") -> Decimal:
    """Cell -> Decimal, tolerant of None/float-binary-noise."""
    if value is None or value == "":
        return Decimal(default)
    try:
        return Decimal(str(round(float(value), 2)))
    except (TypeError, ValueError, InvalidOperation):
        return Decimal(default)


def _period(value) -> datetime.date | None:
    if isinstance(value, datetime.datetime):
        return value.date().replace(day=1)
    if isinstance(value, datetime.date):
        return value.replace(day=1)
    return None


class Command(BaseCommand):
    help = "Import the historical Salary Excel register into the Payroll module."

    def add_arguments(self, parser):
        parser.add_argument("path", help="Path to Salary_25_26.xlsx")
        parser.add_argument("--commit", action="store_true", help="Actually write to the database.")
        parser.add_argument("--username", help="User whose organization receives the import "
                                               "(default: earliest staff user).")
        parser.add_argument("--tolerance", type=str, default="1.00",
                            help="Rupee tolerance for cross-validation warnings.")

    def _resolve_org(self, username):
        from django.contrib.auth.models import User
        from payslip.models import membership_for

        if username:
            user = User.objects.filter(username=username).first()
            if user is None:
                raise CommandError(f"No user named {username!r}.")
        else:
            user = User.objects.filter(is_staff=True).order_by("date_joined", "pk").first()
            if user is None:
                raise CommandError("No staff user found - pass --username to pick the owning org.")
        return membership_for(user).organization

    def handle(self, *args, **options):
        import openpyxl

        path = options["path"]
        tolerance = Decimal(options["tolerance"])
        org = self._resolve_org(options.get("username"))
        settings_obj = payroll_settings_for(org)

        try:
            wb = openpyxl.load_workbook(path, data_only=True)
        except FileNotFoundError:
            raise CommandError(f"File not found: {path}")

        ws = wb["Sheet1"]

        # --- Pass 1: parse Sheet1, dedup on (period, name), first row wins ---
        rows: dict[tuple[datetime.date, str], dict] = {}
        skipped_blank = 0
        for r in range(2, ws.max_row + 1):
            name = ws[f"{COL_NAME}{r}"].value
            if not name or not str(name).strip():
                skipped_blank += 1
                continue
            period = _period(ws[f"{COL_MONTH}{r}"].value)
            if period is None:
                skipped_blank += 1
                continue
            name = str(name).strip()

            twd = ws[f"{COL_TWD}{r}"].value
            try:
                twd = int(twd)
            except (TypeError, ValueError):
                continue  # not a real data row (e.g. a stray formula-only row)

            key = (period, name)
            if key in rows:
                continue  # first row wins - see class docstring

            rows[key] = {
                "designation": (ws[f"{COL_DESIGNATION}{r}"].value or "").strip(),
                "total_working_days": twd,
                "cl_credit": _dec(ws[f"{COL_CL}{r}"].value),
                "emp_leave_days": _dec(ws[f"{COL_EMP_LEAVE}{r}"].value),
                "lop_days": _dec(ws[f"{COL_LOP}{r}"].value),
                "new_salary": _dec(ws[f"{COL_NEW_SALARY}{r}"].value),
                "internet_allowance": _dec(ws[f"{COL_INTERNET}{r}"].value),
                "salary_arrear_allowance": _dec(ws[f"{COL_ARREAR}{r}"].value),
                "salary_advance": _dec(ws[f"{COL_ADVANCE}{r}"].value),
                "tds": _dec(ws[f"{COL_TDS}{r}"].value),
                "remarks": (ws[f"{COL_REMARKS}{r}"].value or ""),
                # Sheet's own cached results, for cross-validation + the
                # authoritative historical record (see class docstring).
                "sheet_basic": _dec(ws[f"{COL_BASIC}{r}"].value),
                "sheet_da": _dec(ws[f"{COL_DA}{r}"].value),
                "sheet_hra": _dec(ws[f"{COL_HRA}{r}"].value),
                "sheet_transport": _dec(ws[f"{COL_TRANSPORT}{r}"].value),
                "sheet_food": _dec(ws[f"{COL_FOOD}{r}"].value),
                "sheet_gross": _dec(ws[f"{COL_GROSS}{r}"].value),
                "sheet_esi_emp": _dec(ws[f"{COL_ESI_EMP}{r}"].value),
                "sheet_esi_er": _dec(ws[f"{COL_ESI_ER}{r}"].value),
                "sheet_pf_emp": _dec(ws[f"{COL_PF_EMP}{r}"].value),
                "sheet_pf_er": _dec(ws[f"{COL_PF_ER}{r}"].value),
                "sheet_total_ded": _dec(ws[f"{COL_TOTAL_DED}{r}"].value),
                "sheet_net": _dec(ws[f"{COL_NET}{r}"].value),
            }

        self.stdout.write(f"Parsed {len(rows)} unique (period, employee) rows "
                          f"({skipped_blank} rows skipped as blank/non-data).")

        # --- Cross-validate every row against our calc engine ------------
        warnings = []
        for (period, name), data in rows.items():
            # ROUNDUP means any positive base yields at least 1 rupee, so a
            # literal-0 cell reliably means "not enrolled this period" -
            # confirmed against the sheet for both ESI and PF.
            is_esi_eligible = data["sheet_esi_emp"] > 0
            is_pf_applicable = data["sheet_pf_emp"] > 0
            computed = compute_entry(
                monthly_package=data["new_salary"],
                total_working_days=data["total_working_days"],
                emp_leave_days=data["emp_leave_days"],
                lop_days=data["lop_days"],
                internet_allowance=data["internet_allowance"],
                salary_arrear_allowance=data["salary_arrear_allowance"],
                salary_advance=data["salary_advance"],
                tds=data["tds"],
                is_esi_eligible=is_esi_eligible,
                is_pf_applicable=is_pf_applicable,
                settings=settings_obj,
            )
            data["is_esi_eligible"] = is_esi_eligible
            data["is_pf_applicable"] = is_pf_applicable
            data["computed"] = computed
            checks = [
                ("basic", computed.basic, data["sheet_basic"]),
                ("gross", computed.gross_salary, data["sheet_gross"]),
                ("esi_employee", computed.esi_employee, data["sheet_esi_emp"]),
                ("pf_employee", computed.pf_employee, data["sheet_pf_emp"]),
                ("net_payable", computed.net_payable, data["sheet_net"]),
            ]
            for field, ours, theirs in checks:
                if abs(ours - theirs) > tolerance:
                    warnings.append(
                        f"  {name} {period:%b %Y}: {field} computed={ours} sheet={theirs}"
                    )

        expected_total_net = sum((d["sheet_net"] for d in rows.values()), Decimal("0"))
        self.stdout.write(f"Expected grand total Net Payable (from the sheet itself): "
                          f"{expected_total_net}")
        self.stdout.write(f"Cross-validation warnings: {len(warnings)}")
        for line in warnings[:15]:
            self.stdout.write(self.style.WARNING(line))
        if len(warnings) > 15:
            self.stdout.write(self.style.WARNING(f"  ... and {len(warnings) - 15} more."))

        # --- Pass 2: Sheet4 employee master enrichment --------------------
        ws4 = wb["Sheet4"]
        doj_by_name: dict[str, datetime.date] = {}
        notes_by_name: dict[str, str] = {}
        for r in range(1, ws4.max_row + 1):
            name = ws4[f"{S4_NAME}{r}"].value
            if not name or not str(name).strip():
                continue
            name = str(name).strip()
            doj_val = ws4[f"{S4_DOJ}{r}"].value
            if isinstance(doj_val, (datetime.datetime, datetime.date)):
                doj_by_name[name] = (doj_val.date() if isinstance(doj_val, datetime.datetime)
                                     else doj_val)
            remark = ws4[f"{S4_REMARKS}{r}"].value
            if remark:
                notes_by_name[name] = str(remark).strip()

        employee_names = sorted({name for _, name in rows})
        periods = sorted({period for period, _ in rows})
        self.stdout.write(f"Unique employees: {len(employee_names)}; "
                          f"unique periods: {len(periods)} "
                          f"({periods[0]:%b %Y} - {periods[-1]:%b %Y})." if periods else
                          f"Unique employees: {len(employee_names)}; no periods found.")
        self.stdout.write(f"Target organization: {org}")

        if not options["commit"]:
            self.stdout.write(self.style.WARNING(
                "Dry run only - pass --commit to write. Review the warnings above first."))
            return

        # --- Commit ---------------------------------------------------------
        with transaction.atomic():
            employees_created = 0
            employees_by_name: dict[str, Employee] = {}
            next_code = Employee.objects.filter(organization=org).count()

            latest_package: dict[str, tuple[datetime.date, Decimal]] = {}
            latest_designation: dict[str, str] = {}
            for (period, name), data in rows.items():
                prev = latest_package.get(name)
                if prev is None or period > prev[0]:
                    latest_package[name] = (period, data["new_salary"])
                    latest_designation[name] = data["designation"]

            # Master flags follow the LATEST period's actual value, not
            # "ever true" - enrollment status is what matters for future
            # (not-yet-imported) runs, not history.
            latest_esi: dict[str, tuple[datetime.date, bool]] = {}
            latest_pf: dict[str, tuple[datetime.date, bool]] = {}
            for (period, name), data in rows.items():
                if name not in latest_esi or period > latest_esi[name][0]:
                    latest_esi[name] = (period, data["is_esi_eligible"])
                if name not in latest_pf or period > latest_pf[name][0]:
                    latest_pf[name] = (period, data["is_pf_applicable"])

            for name in employee_names:
                employee = Employee.objects.filter(organization=org, name=name).first()
                if employee is None:
                    next_code += 1
                    employee = Employee.objects.create(
                        organization=org, employee_code=f"EMP-{next_code:04d}",
                        name=name, designation=latest_designation.get(name, ""),
                        current_monthly_package=latest_package[name][1],
                        doj=doj_by_name.get(name),
                        notes=notes_by_name.get(name, ""),
                        is_esi_eligible=latest_esi[name][1],
                        is_pf_applicable=latest_pf[name][1],
                    )
                    employees_created += 1
                employees_by_name[name] = employee

            runs_created = 0
            runs_skipped = 0
            entries_created = 0
            for period in periods:
                run, created = PayrollRun.objects.get_or_create(
                    organization=org, period=period,
                    defaults={"status": PayrollRun.Status.FINALIZED,
                             "notes": "Imported from Salary_25_26.xlsx"},
                )
                if not created:
                    runs_skipped += 1
                    continue
                runs_created += 1
                new_entries = []
                for (p, name), data in rows.items():
                    if p != period:
                        continue
                    computed = data["computed"]
                    new_entries.append(PayslipEntry(
                        organization=org, run=run, employee=employees_by_name[name],
                        monthly_package=data["new_salary"],
                        total_working_days=data["total_working_days"],
                        cl_credit=data["cl_credit"], emp_leave_days=data["emp_leave_days"],
                        lop_days=data["lop_days"],
                        present_days=data["total_working_days"] - data["emp_leave_days"],
                        pay_days=data["total_working_days"] - data["lop_days"],
                        internet_allowance=data["internet_allowance"],
                        salary_arrear_allowance=data["salary_arrear_allowance"],
                        salary_advance=data["salary_advance"], tds=data["tds"],
                        remarks=data["remarks"],
                        # Historical figures are the sheet's own actual values,
                        # not silently overwritten by our recompute (see the
                        # class docstring) - the warnings above are for review.
                        basic=data["sheet_basic"], da=data["sheet_da"], hra=data["sheet_hra"],
                        transport_allowance=data["sheet_transport"], food_allowance=data["sheet_food"],
                        gross_salary=data["sheet_gross"],
                        is_esi_eligible=data["is_esi_eligible"],
                        is_pf_applicable=data["is_pf_applicable"],
                        esi_employee=data["sheet_esi_emp"], esi_employer=data["sheet_esi_er"],
                        pf_employee=data["sheet_pf_emp"], pf_employer=data["sheet_pf_er"],
                        total_deductions=data["sheet_total_ded"], net_payable=data["sheet_net"],
                    ))
                PayslipEntry.objects.bulk_create(new_entries)
                entries_created += len(new_entries)

        self.stdout.write(self.style.SUCCESS(
            f"Done: {employees_created} employees created, {runs_created} payroll runs "
            f"created ({runs_skipped} periods already existed and were skipped), "
            f"{entries_created} payslip entries created."
        ))
