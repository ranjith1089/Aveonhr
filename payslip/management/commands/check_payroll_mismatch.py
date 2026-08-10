from django.core.management.base import BaseCommand
from decimal import Decimal
from payslip.models import PayrollRun, PayslipEntry
from payslip.services.payroll_calc import compute_entry


class Command(BaseCommand):
    help = 'Check and fix payroll mismatch for a given run'

    def add_arguments(self, parser):
        parser.add_argument('run_id', type=int, help='Payroll Run ID to check')
        parser.add_argument('--fix', action='store_true', help='Fix the mismatch')

    def handle(self, *args, **options):
        run_id = options['run_id']
        fix = options['fix']

        try:
            run = PayrollRun.objects.get(pk=run_id)
        except PayrollRun.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Payroll Run {run_id} not found'))
            return

        self.stdout.write(f'Checking Payroll Run: {run}')
        self.stdout.write(f'Period: {run.period}')
        self.stdout.write(f'Status: {run.status}\n')

        entries = run.entries.select_related('employee').order_by('employee__name')

        self.stdout.write(f'{'Employee Name':30} | {'Stored Net':>12} | {'Calculated':>12} | {'Diff':>10}')
        self.stdout.write('-' * 80)

        total_stored = Decimal('0')
        total_calculated = Decimal('0')
        mismatches = []

        for entry in entries:
            # Get the salary structure for this run
            from payslip.models import salary_structure_for, payroll_settings_for
            structure = salary_structure_for(run.organization, run.period)
            settings = payroll_settings_for(run.organization)

            # Recalculate the entry
            try:
                computation = compute_entry(
                    monthly_package=entry.monthly_package,
                    total_working_days=entry.total_working_days,
                    emp_leave_days=entry.emp_leave_days,
                    lop_days=entry.lop_days,
                    internet_allowance=entry.internet_allowance,
                    salary_arrear_allowance=entry.salary_arrear_allowance,
                    salary_advance=entry.salary_advance,
                    tds=entry.tds,
                    is_esi_eligible=entry.is_esi_eligible,
                    is_pf_applicable=entry.is_pf_applicable,
                    settings=settings,
                )
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error calculating {entry.employee.name}: {e}'))
                continue

            calculated_net = computation.net_payable
            stored_net = entry.net_payable
            diff = calculated_net - stored_net

            total_stored += stored_net
            total_calculated += calculated_net

            if diff != 0:
                mismatches.append({
                    'entry': entry,
                    'stored': stored_net,
                    'calculated': calculated_net,
                    'diff': diff,
                    'computation': computation,
                })
                status = self.style.ERROR(f'{entry.employee.name:30} | {stored_net:12.2f} | {calculated_net:12.2f} | {diff:10.2f}')
            else:
                status = f'{entry.employee.name:30} | {stored_net:12.2f} | {calculated_net:12.2f} | {diff:10.2f}'

            self.stdout.write(status)

        self.stdout.write('-' * 80)
        diff_total = total_calculated - total_stored
        self.stdout.write(f'{'TOTAL':30} | {total_stored:12.2f} | {total_calculated:12.2f} | {diff_total:10.2f}')

        if mismatches:
            self.stdout.write(self.style.WARNING(f'\nFound {len(mismatches)} mismatch(es)'))

            if fix:
                from django.db import transaction
                with transaction.atomic():
                    for m in mismatches:
                        entry = m['entry']
                        computation = m['computation']

                        # Update the entry with recalculated values
                        entry.present_days = computation.present_days
                        entry.pay_days = computation.pay_days
                        entry.basic = computation.basic
                        entry.da = computation.da
                        entry.hra = computation.hra
                        entry.transport_allowance = computation.transport_allowance
                        entry.food_allowance = computation.food_allowance
                        entry.gross_salary = computation.gross_salary
                        entry.esi_employee = computation.esi_employee
                        entry.esi_employer = computation.esi_employer
                        entry.pf_employee = computation.pf_employee
                        entry.pf_employer = computation.pf_employer
                        entry.total_deductions = computation.total_deductions
                        entry.net_payable = computation.net_payable
                        entry.save()

                        self.stdout.write(f'Fixed {entry.employee.name}: {m["diff"]:+.2f}')

                self.stdout.write(self.style.SUCCESS('\nAll mismatches fixed!'))
        else:
            self.stdout.write(self.style.SUCCESS('\nNo mismatches found - all values are correct!'))
