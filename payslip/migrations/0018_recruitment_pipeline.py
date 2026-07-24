# Generated manually - recruitment pipeline models

import django.db.models.deletion
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payslip', '0017_employee_agreement_signed'),
    ]

    operations = [
        # --- JobOpening ---
        migrations.CreateModel(
            name='JobOpening',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200)),
                ('department', models.CharField(blank=True, default='', max_length=100)),
                ('positions', models.PositiveIntegerField(default=1)),
                ('location', models.CharField(blank=True, default='', max_length=200)),
                ('description', models.TextField(blank=True, default='')),
                ('status', models.CharField(choices=[('OPEN', 'Open'), ('ON_HOLD', 'On Hold'), ('CLOSED', 'Closed')], default='OPEN', max_length=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='job_openings', to='payslip.organization')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        # --- Person recruitment fields ---
        migrations.AddField(
            model_name='person',
            name='source',
            field=models.CharField(blank=True, choices=[('CAMPUS', 'Campus Drive'), ('REFERRAL', 'Referral'), ('PORTAL', 'Job Portal'), ('WALKIN', 'Walk-in'), ('OTHER', 'Other')], default='', max_length=12),
        ),
        migrations.AddField(
            model_name='person',
            name='stage',
            field=models.CharField(blank=True, choices=[('NEW', 'New'), ('SCREENING', 'Screening'), ('SHORTLISTED', 'Shortlisted'), ('INTERVIEW', 'Interview'), ('SELECTED', 'Selected'), ('OFFERED', 'Offered'), ('JOINED', 'Joined'), ('REJECTED', 'Rejected'), ('ON_HOLD', 'On Hold')], default='', max_length=12),
        ),
        migrations.AddField(
            model_name='person',
            name='applied_for',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='applicants', to='payslip.jobopening'),
        ),
        migrations.AddField(
            model_name='person',
            name='expected_ctc',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name='person',
            name='stage_updated_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        # --- InterviewRound ---
        migrations.CreateModel(
            name='InterviewRound',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('round_name', models.CharField(max_length=100)),
                ('scheduled_at', models.DateTimeField(blank=True, null=True)),
                ('interviewer', models.CharField(blank=True, default='', max_length=100)),
                ('feedback', models.TextField(blank=True, default='')),
                ('rating', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('result', models.CharField(choices=[('PENDING', 'Pending'), ('PASSED', 'Passed'), ('FAILED', 'Failed')], default='PENDING', max_length=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('person', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='interviews', to='payslip.person')),
            ],
            options={
                'ordering': ['created_at'],
            },
        ),
    ]
