from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('listings', '0013_alter_listing_property_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='listing',
            name='status',
            field=models.CharField(
                choices=[
                    ('active',  'Active'),
                    ('draft',   'Draft'),
                    ('pending', 'Pending Review'),
                    ('flagged', 'Flagged'),
                ],
                default='active',
                max_length=10,
            ),
        ),
    ]
