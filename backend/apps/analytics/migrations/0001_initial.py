# Generated manually
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('polls', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='PollAnalytics',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('total_votes', models.IntegerField(default=0)),
                ('unique_voters', models.IntegerField(default=0)),
                ('last_updated', models.DateTimeField(auto_now=True)),
                ('poll', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='analytics', to='polls.poll')),
            ],
            options={
                'verbose_name_plural': 'Poll Analytics',
            },
        ),
    ]

