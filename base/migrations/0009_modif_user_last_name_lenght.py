# -*- coding: utf-8 -*-
# Generated by Django 1.9 on 2016-09-28 15:49
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0008_auto_20170123_1405'),
    ]

    operations = [
        migrations.RunSQL("alter table auth_user alter column username type varchar(254);"),
        migrations.RunSQL("alter table auth_user alter column last_name type varchar(254)")
    ]