from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('listings', '0017_listing_expires_at_listing_hoa_fee_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='listinginquiry',
            name='is_read',
            field=models.BooleanField(default=False),
        ),
    ]
