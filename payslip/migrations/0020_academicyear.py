# Generated manually - centralized AcademicYear model for Income module

import django.core.validators
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('payslip', '0019_onboarding_documents'),
    ]

    operations = [
        migrations.CreateModel(
            name='AcademicYear',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True,
                                        serialize=False, verbose_name='ID')),
                ('label', models.CharField(
                    max_length=9,
                    validators=[django.core.validators.RegexValidator(
                        r'^\d{4}-\d{4}$', 'Use the format 2025-2026.')],
                )),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('organization', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='academic_years',
                    to='payslip.organization',
                )),
            ],
            options={
                'ordering': ['-label'],
                'unique_together': {('organization', 'label')},
            },
        ),
    ]
