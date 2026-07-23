from django.db import migrations


def carry_recruitment_right_into_people(apps, schema_editor):
    """Recruitment is merging into the People module. Any membership that
    had can_recruitment=True but can_people=False gets can_people=True so
    no one loses access."""
    Membership = apps.get_model('payslip', 'Membership')
    Membership.objects.filter(can_recruitment=True, can_people=False).update(can_people=True)


class Migration(migrations.Migration):

    dependencies = [
        ('payslip', '0018_recruitment'),
    ]

    operations = [
        migrations.RunPython(carry_recruitment_right_into_people, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='membership',
            name='can_recruitment',
        ),
    ]
