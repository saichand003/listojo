"""
Rename 'Las Colinas Urban Center' to 'Downtown Las Colinas'.

seed_downtowns matches rows on name, so changing the seed list alone would
create a second row and leave existing listings pointed at the old one. This
renames in place, which keeps every Listing.nearest_downtown FK intact.
"""
from django.db import migrations

OLD = 'Las Colinas Urban Center'
NEW = 'Downtown Las Colinas'


def _swap(apps, old, new):
    Downtown = apps.get_model('listings', 'Downtown')
    # `name` is unique — bail out rather than trip the constraint if a row
    # under the target name already exists (a fresh deploy seeds the new name).
    if Downtown.objects.filter(name=new).exists():
        return
    Downtown.objects.filter(name=old).update(name=new)


def forwards(apps, schema_editor):
    _swap(apps, OLD, NEW)


def backwards(apps, schema_editor):
    _swap(apps, NEW, OLD)


class Migration(migrations.Migration):

    dependencies = [
        ('listings', '0035_downtown_grocerystore_and_more'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
