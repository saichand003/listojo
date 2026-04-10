from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('listings', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='listing',
            name='category',
            field=models.CharField(
                choices=[
                    ('roommates', 'Roommates'),
                    ('rentals', 'Rentals'),
                    ('local_services', 'Local Services'),
                    ('jobs', 'Jobs'),
                    ('buy_sell', 'Buy & Sell'),
                    ('events', 'Events'),
                ],
                default='local_services',
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name='listing',
            name='city',
            field=models.CharField(default='Unknown', max_length=100),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='listing',
            name='contact_phone',
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name='listing',
            name='country',
            field=models.CharField(default='USA', max_length=100),
        ),
        migrations.AddField(
            model_name='listing',
            name='featured',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='listing',
            name='state',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AlterField(
            model_name='listing',
            name='price',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AlterModelOptions(
            name='listing',
            options={'ordering': ['-featured', '-created_at']},
        ),
        migrations.CreateModel(
            name='ListingInquiry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120)),
                ('email', models.EmailField(max_length=254)),
                ('phone', models.CharField(blank=True, max_length=30)),
                ('message', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('listing', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='inquiries', to='listings.listing')),
            ],
            options={'ordering': ['-created_at']},
        ),
    ]
