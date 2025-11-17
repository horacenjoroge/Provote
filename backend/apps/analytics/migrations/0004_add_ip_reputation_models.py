"""
Migration for IP reputation system models.
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('analytics', '0003_add_fingerprintblock'),
    ]

    operations = [
        migrations.CreateModel(
            name='IPReputation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ip_address', models.GenericIPAddressField(db_index=True, help_text='IP address being tracked', unique=True)),
                ('reputation_score', models.IntegerField(default=100, help_text='Reputation score (0-100, higher is better)')),
                ('violation_count', models.IntegerField(default=0, help_text='Number of violations (failed attempts, fraud, etc.)')),
                ('successful_attempts', models.IntegerField(default=0, help_text='Number of successful vote attempts')),
                ('failed_attempts', models.IntegerField(default=0, help_text='Number of failed vote attempts')),
                ('first_seen', models.DateTimeField(auto_now_add=True, help_text='When this IP was first seen')),
                ('last_seen', models.DateTimeField(auto_now=True, help_text='When this IP was last seen')),
                ('last_violation_at', models.DateTimeField(blank=True, help_text='When the last violation occurred', null=True)),
            ],
            options={
                'verbose_name': 'IP Reputation',
                'verbose_name_plural': 'IP Reputations',
                'ordering': ['-last_seen'],
            },
        ),
        migrations.CreateModel(
            name='IPBlock',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ip_address', models.GenericIPAddressField(db_index=True, help_text='Blocked IP address', unique=True)),
                ('reason', models.TextField(help_text='Reason for blocking')),
                ('blocked_at', models.DateTimeField(auto_now_add=True, help_text='When the IP was blocked')),
                ('is_active', models.BooleanField(db_index=True, default=True, help_text='Whether this block is currently active')),
                ('is_manual', models.BooleanField(default=False, help_text='Whether this block was manually created by admin')),
                ('auto_unblock_at', models.DateTimeField(blank=True, help_text='When to automatically unblock (null for manual blocks or permanent blocks)', null=True)),
                ('unblocked_at', models.DateTimeField(blank=True, help_text='When the IP was unblocked (if applicable)', null=True)),
                ('blocked_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='blocked_ips', to=settings.AUTH_USER_MODEL, help_text='User/admin who blocked this IP (null if auto-blocked)')),
                ('unblocked_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='unblocked_ips', to=settings.AUTH_USER_MODEL, help_text='User/admin who unblocked this IP')),
            ],
            options={
                'verbose_name': 'Blocked IP',
                'verbose_name_plural': 'Blocked IPs',
                'ordering': ['-blocked_at'],
            },
        ),
        migrations.CreateModel(
            name='IPWhitelist',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ip_address', models.GenericIPAddressField(db_index=True, help_text='Whitelisted IP address', unique=True)),
                ('reason', models.TextField(blank=True, help_text='Reason for whitelisting')),
                ('created_at', models.DateTimeField(auto_now_add=True, help_text='When the IP was whitelisted')),
                ('is_active', models.BooleanField(db_index=True, default=True, help_text='Whether this whitelist entry is active')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='whitelisted_ips', to=settings.AUTH_USER_MODEL, help_text='User/admin who whitelisted this IP')),
            ],
            options={
                'verbose_name': 'Whitelisted IP',
                'verbose_name_plural': 'Whitelisted IPs',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='ipreputation',
            index=models.Index(fields=['ip_address'], name='analytics_i_ip_addr_idx'),
        ),
        migrations.AddIndex(
            model_name='ipreputation',
            index=models.Index(fields=['reputation_score', 'last_seen'], name='analytics_i_reputat_idx'),
        ),
        migrations.AddIndex(
            model_name='ipreputation',
            index=models.Index(fields=['violation_count', 'last_seen'], name='analytics_i_violati_idx'),
        ),
        migrations.AddIndex(
            model_name='ipblock',
            index=models.Index(fields=['ip_address', 'is_active'], name='analytics_i_ip_addr_idx'),
        ),
        migrations.AddIndex(
            model_name='ipblock',
            index=models.Index(fields=['is_active', 'auto_unblock_at'], name='analytics_i_is_acti_idx'),
        ),
        migrations.AddIndex(
            model_name='ipblock',
            index=models.Index(fields=['is_manual', 'is_active'], name='analytics_i_is_manu_idx'),
        ),
        migrations.AddIndex(
            model_name='ipwhitelist',
            index=models.Index(fields=['ip_address', 'is_active'], name='analytics_i_ip_addr_idx'),
        ),
    ]

