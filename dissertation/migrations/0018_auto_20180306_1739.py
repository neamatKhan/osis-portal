# -*- coding: utf-8 -*-
# Generated by Django 1.9 on 2018-03-06 16:39
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dissertation', '0017_auto_20171010_1535'),
    ]

    operations = [
        migrations.AlterField(
            model_name='dissertationupdate',
            name='justification',
            field=models.TextField(blank=True),
        ),
    ]