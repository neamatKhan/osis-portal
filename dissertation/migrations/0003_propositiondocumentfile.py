# -*- coding: utf-8 -*-
# Generated by Django 1.9 on 2016-10-06 12:55
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('osis_common', '0006_modifications_documentfile'),
        ('dissertation', '0002_dissertationdocumentfile'),
    ]

    operations = [
        migrations.CreateModel(
            name='PropositionDocumentFile',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('document_file', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='osis_common.DocumentFile')),
                ('proposition', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='dissertation.PropositionDissertation')),
            ],
        ),
    ]
