"""Deploy 2 of the organizations rollout.

Safe because Deploy 1 already backfilled every IncomeClient.organization
(migration 0008) and all application writes set it; CompanyProfile has been
unused since org_for replaced profile_for.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payslip", "0009_proposal_history"),
    ]

    operations = [
        migrations.AlterField(
            model_name="incomeclient",
            name="organization",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="income_clients",
                to="payslip.organization",
            ),
        ),
        migrations.DeleteModel(name="CompanyProfile"),
    ]
