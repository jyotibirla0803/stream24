import os
import logging
from celery import Celery
from celery.schedules import crontab

logger = logging.getLogger(__name__)

# Set the default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('youtube_streamer')

# Load config from Django settings with CELERY_ prefix
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks from all registered Django apps
app.autodiscover_tasks()

# Celery Beat Schedule for periodic tasks
app.conf.beat_schedule = {
    # Check stream health every 5 minutes
    'check-stream-health': {
        'task': 'apps.streaming.tasks.check_stream_health',
        'schedule': crontab(minute='*/5'),  # Every 5 minutes
    },
    # Check subscription expiry daily
    'check-subscription-expiry': {
        'task': 'apps.payments.tasks.check_subscription_expiry',
        'schedule': crontab(hour=0, minute=0),  # Daily at midnight
    },
    # Clean up old logs weekly
    'cleanup-old-logs': {
        'task': 'apps.streaming.tasks.cleanup_old_logs',
        'schedule': crontab(hour=2, minute=0, day_of_week=0),  # Sunday at 2 AM
    },
}

def cleanup_stale_streams():
    from apps.streaming.models import Stream
    from apps.streaming.stream_manager import StreamManager
    stale_streams = Stream.objects.filter(status='running', process_id__isnull=True)
    for s in stale_streams:
        manager = StreamManager(s)
        manager.authenticate_youtube()
        if s.broadcast_id:
            try:
                manager.youtube.liveBroadcasts().transition(
                    broadcastStatus='complete',
                    id=s.broadcast_id,
                    part='status'
                ).execute()
                s.status = 'stopped'
                s.save()
            except Exception as e:
                logger.error(f"Failed to cleanup stale broadcast {s.id}: {e}")

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
