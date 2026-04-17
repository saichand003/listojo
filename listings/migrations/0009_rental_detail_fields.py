from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('listings', '0008_add_available_from'),
    ]

    operations = [
        migrations.AddField(
            model_name='listing',
            name='accommodation_type',
            field=models.CharField(
                blank=True, default='', max_length=20,
                choices=[('room', 'Room'), ('whole', 'Whole property')],
            ),
        ),
        migrations.AddField(
            model_name='listing',
            name='property_type',
            field=models.CharField(
                blank=True, default='', max_length=20,
                choices=[
                    ('apartment', 'Apartment'), ('condo', 'Condo'),
                    ('house', 'House'), ('townhouse', 'Townhouse'),
                    ('basement', 'Basement'), ('loft', 'Loft'),
                    ('studio', 'Studio'), ('trailer', 'Trailer'),
                ],
            ),
        ),
        migrations.AddField(
            model_name='listing',
            name='bills_included',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='listing',
            name='security_deposit',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
    ]
