# Generated migration file for adding thumbnail field to Stream model

from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('streaming', '0001_initial'),  # Replace with your actual last migration
    ]

    operations = [
        migrations.AddField(
            model_name='stream',
            name='thumbnail',
            field=models.ImageField(blank=True, null=True, upload_to='uploads/stream_thumbnails/'),
        ),
    ]
