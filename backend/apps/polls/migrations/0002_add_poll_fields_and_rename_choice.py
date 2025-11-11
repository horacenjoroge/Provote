# Generated manually
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('polls', '0001_initial'),
    ]

    operations = [
        # Add new fields to Poll
        migrations.AddField(
            model_name='poll',
            name='settings',
            field=models.JSONField(blank=True, default=dict, help_text='Poll settings (e.g., allow_multiple_votes, show_results)'),
        ),
        migrations.AddField(
            model_name='poll',
            name='security_rules',
            field=models.JSONField(blank=True, default=dict, help_text='Security rules (e.g., require_authentication, ip_whitelist)'),
        ),
        migrations.AddField(
            model_name='poll',
            name='cached_total_votes',
            field=models.IntegerField(default=0, help_text='Cached total vote count'),
        ),
        migrations.AddField(
            model_name='poll',
            name='cached_unique_voters',
            field=models.IntegerField(default=0, help_text='Cached unique voter count'),
        ),
        # Rename Choice to PollOption
        migrations.RenameModel(
            old_name='Choice',
            new_name='PollOption',
        ),
        # Update PollOption fields
        migrations.AddField(
            model_name='polloption',
            name='order',
            field=models.IntegerField(default=0, help_text='Display order for options'),
        ),
        migrations.AddField(
            model_name='polloption',
            name='cached_vote_count',
            field=models.IntegerField(default=0, help_text='Cached vote count for performance'),
        ),
        # Update PollOption ordering
        migrations.AlterModelOptions(
            name='polloption',
            options={'ordering': ['order', 'id']},
        ),
        # Update PollOption related_name
        migrations.AlterField(
            model_name='polloption',
            name='poll',
            field=models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='options', to='polls.poll'),
        ),
        # Add indexes to Poll
        migrations.AddIndex(
            model_name='poll',
            index=models.Index(fields=['created_at'], name='polls_poll_created_idx'),
        ),
        migrations.AddIndex(
            model_name='poll',
            index=models.Index(fields=['is_active', 'starts_at', 'ends_at'], name='polls_poll_is_acti_idx'),
        ),
        # Add indexes to PollOption
        migrations.AddIndex(
            model_name='polloption',
            index=models.Index(fields=['poll', 'order'], name='polls_pollopt_poll_id_order_idx'),
        ),
    ]

