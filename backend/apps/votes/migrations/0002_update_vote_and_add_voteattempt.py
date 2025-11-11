# Generated manually
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('polls', '0002_add_poll_fields_and_rename_choice'),
        ('votes', '0001_initial'),
    ]

    operations = [
        # Update Vote model: rename choice to option
        migrations.RenameField(
            model_name='vote',
            old_name='choice',
            new_name='option',
        ),
        # Update Vote foreign key to use PollOption
        migrations.AlterField(
            model_name='vote',
            name='option',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='votes', to='polls.polloption'),
        ),
        # Add new fields to Vote
        migrations.AddField(
            model_name='vote',
            name='voter_token',
            field=models.CharField(db_index=True, help_text='Token for anonymous/guest voting', max_length=64),
        ),
        migrations.AddField(
            model_name='vote',
            name='ip_address',
            field=models.GenericIPAddressField(blank=True, db_index=True, help_text='IP address of voter', null=True),
        ),
        migrations.AddField(
            model_name='vote',
            name='user_agent',
            field=models.TextField(blank=True, help_text='User agent string'),
        ),
        migrations.AddField(
            model_name='vote',
            name='fingerprint',
            field=models.CharField(blank=True, db_index=True, help_text='Browser/device fingerprint', max_length=128),
        ),
        # Remove old indexes
        migrations.RemoveIndex(
            model_name='vote',
            name='votes_vote_user_id_poll_id_idx',
        ),
        migrations.RemoveIndex(
            model_name='vote',
            name='votes_vote_poll_id_created_idx',
        ),
        # Add new indexes to Vote
        migrations.AddIndex(
            model_name='vote',
            index=models.Index(fields=['poll', 'voter_token'], name='votes_vote_poll_id_voter_t_idx'),
        ),
        migrations.AddIndex(
            model_name='vote',
            index=models.Index(fields=['idempotency_key'], name='votes_vote_idempotency_idx'),
        ),
        migrations.AddIndex(
            model_name='vote',
            index=models.Index(fields=['ip_address', 'created_at'], name='votes_vote_ip_addr_created_idx'),
        ),
        migrations.AddIndex(
            model_name='vote',
            index=models.Index(fields=['user', 'poll'], name='votes_vote_user_id_poll_id_idx'),
        ),
        migrations.AddIndex(
            model_name='vote',
            index=models.Index(fields=['poll', 'created_at'], name='votes_vote_poll_id_created_idx'),
        ),
        migrations.AddIndex(
            model_name='vote',
            index=models.Index(fields=['fingerprint', 'created_at'], name='votes_vote_fingerprint_created_idx'),
        ),
        # Create VoteAttempt model
        migrations.CreateModel(
            name='VoteAttempt',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('voter_token', models.CharField(blank=True, db_index=True, help_text='Token for anonymous/guest voting', max_length=64)),
                ('idempotency_key', models.CharField(db_index=True, help_text='Idempotency key used in attempt', max_length=64)),
                ('ip_address', models.GenericIPAddressField(blank=True, db_index=True, null=True)),
                ('user_agent', models.TextField(blank=True)),
                ('fingerprint', models.CharField(blank=True, db_index=True, max_length=128)),
                ('success', models.BooleanField(default=False, help_text='Whether the vote attempt was successful')),
                ('error_message', models.TextField(blank=True, help_text='Error message if attempt failed')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('option', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='vote_attempts', to='polls.polloption')),
                ('poll', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='vote_attempts', to='polls.poll')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='vote_attempts', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        # Add indexes to VoteAttempt
        migrations.AddIndex(
            model_name='voteattempt',
            index=models.Index(fields=['poll', 'voter_token'], name='votes_voteattempt_poll_voter_idx'),
        ),
        migrations.AddIndex(
            model_name='voteattempt',
            index=models.Index(fields=['idempotency_key'], name='votes_voteattempt_idempotency_idx'),
        ),
        migrations.AddIndex(
            model_name='voteattempt',
            index=models.Index(fields=['ip_address', 'created_at'], name='votes_voteattempt_ip_created_idx'),
        ),
        migrations.AddIndex(
            model_name='voteattempt',
            index=models.Index(fields=['success', 'created_at'], name='votes_voteattempt_success_created_idx'),
        ),
        migrations.AddIndex(
            model_name='voteattempt',
            index=models.Index(fields=['poll', 'created_at'], name='votes_voteattempt_poll_created_idx'),
        ),
    ]

