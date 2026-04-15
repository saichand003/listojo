from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chatapp', '0002_guestchatmessage'),
    ]

    operations = [
        migrations.AddField(
            model_name='guestchatmessage',
            name='guest_session_key',
            field=models.CharField(blank=True, db_index=True, max_length=40),
        ),
    ]
