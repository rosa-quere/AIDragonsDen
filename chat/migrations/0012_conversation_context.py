# Generated by Django 5.1.1 on 2025-05-01 08:58

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0011_conversation_summary_posted_date'),
    ]

    operations = [
        migrations.AddField(
            model_name='conversation',
            name='context',
            field=models.TextField(blank=True, null=True),
        ),
    ]
