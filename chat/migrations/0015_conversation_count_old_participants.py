# Generated by Django 5.1.1 on 2025-05-03 13:29

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0014_segment_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='conversation',
            name='count_old_participants',
            field=models.PositiveIntegerField(default=0),
        ),
    ]
