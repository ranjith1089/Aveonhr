# Generated manually - PO and Agreement document upload fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payslip', '0018_recruitment_pipeline'),
    ]

    operations = [
        migrations.AddField(
            model_name='clientonboarding',
            name='po_document',
            field=models.BinaryField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='clientonboarding',
            name='po_filename',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='clientonboarding',
            name='agreement_document',
            field=models.BinaryField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='clientonboarding',
            name='agreement_filename',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
    ]
