from celery import shared_task
from django.utils import timezone
from datetime import timedelta
import logging
import os
import signal

from .models import Stream, StreamLog
from .stream_manager import StreamManager

logger = logging.getLogger(__name__)


@shared_task
def check_stream_health():
    """
    Periodic task to check health of all running streams
    Runs every 5 minutes via Celery Beat
    """
    running_streams = Stream.objects.filter(status__in=['running', 'starting'])
    
    for stream in running_streams:
        try:
            manager = StreamManager(stream)
            status = manager.get_stream_status()
            
            # If process is dead but status is running, update it
            if status == 'stopped' and stream.status == 'running':
                stream.status = 'error'
                stream.error_message = 'Stream process died unexpectedly'
                stream.stopped_at = timezone.now()
                stream.process_id = None
                stream.save()
                
                StreamLog.objects.create(
                    stream=stream,
                    level='ERROR',
                    message='Stream process died unexpectedly - auto-detected'
                )
                
                logger.error(f"Stream {stream.id} process died unexpectedly")
            
            # Check if stream has been running too long without issues (health check)
            elif status == 'running' and stream.started_at:
                running_duration = timezone.now() - stream.started_at
                
                # Log every 6 hours that stream is healthy
                if running_duration.total_seconds() % 21600 < 300:  # Within 5 min window
                    StreamLog.objects.create(
                        stream=stream,
                        level='INFO',
                        message=f'Stream healthy - running for {running_duration}'
                    )
                    
        except Exception as e:
            logger.error(f"Error checking stream {stream.id}: {str(e)}")
            StreamLog.objects.create(
                stream=stream,
                level='ERROR',
                message=f'Health check failed: {str(e)}'
            )
    
    logger.info(f"Checked health of {running_streams.count()} streams")
    return f"Checked {running_streams.count()} streams"


@shared_task
def cleanup_old_logs():
    """
    Clean up stream logs older than 30 days
    Runs weekly via Celery Beat
    """
    thirty_days_ago = timezone.now() - timedelta(days=30)
    deleted_count, _ = StreamLog.objects.filter(created_at__lt=thirty_days_ago).delete()
    
    logger.info(f"Cleaned up {deleted_count} old log entries")
    return f"Deleted {deleted_count} old logs"


@shared_task
def start_stream_async(stream_id):
    """
    Async task to start a stream
    """
    try:
        stream = Stream.objects.get(id=stream_id)
        manager = StreamManager(stream)
        
        # Create YouTube broadcast
        broadcast_id = manager.create_broadcast()
        if not broadcast_id:
            raise Exception("Failed to create YouTube broadcast")
        
        # Start FFmpeg streaming
        process_id = manager.start_ffmpeg_stream()
        if not process_id:
            raise Exception("Failed to start streaming process")
        
        StreamLog.objects.create(
            stream=stream,
            level='INFO',
            message='Stream started successfully via async task'
        )
        
        return f"Stream {stream_id} started successfully"
        
    except Stream.DoesNotExist:
        logger.error(f"Stream {stream_id} not found")
        return f"Stream {stream_id} not found"
    except Exception as e:
        logger.error(f"Failed to start stream {stream_id}: {str(e)}")
        
        try:
            stream = Stream.objects.get(id=stream_id)
            stream.status = 'error'
            stream.error_message = str(e)
            stream.save()
            
            StreamLog.objects.create(
                stream=stream,
                level='ERROR',
                message=f'Failed to start stream: {str(e)}'
            )
        except:
            pass
        
        return f"Failed to start stream: {str(e)}"


@shared_task
def stop_stream_async(stream_id):
    """
    Async task to stop a stream
    """
    try:
        stream = Stream.objects.get(id=stream_id)
        manager = StreamManager(stream)
        manager.stop_stream()
        
        StreamLog.objects.create(
            stream=stream,
            level='INFO',
            message='Stream stopped successfully via async task'
        )
        
        return f"Stream {stream_id} stopped successfully"
        
    except Stream.DoesNotExist:
        logger.error(f"Stream {stream_id} not found")
        return f"Stream {stream_id} not found"
    except Exception as e:
        logger.error(f"Failed to stop stream {stream_id}: {str(e)}")
        return f"Failed to stop stream: {str(e)}"


@shared_task
def restart_stream_async(stream_id):
    """
    Async task to restart a stream
    """
    try:
        # Stop the stream first
        stop_result = stop_stream_async(stream_id)
        
        # Wait a bit
        import time
        time.sleep(5)
        
        # Start it again
        start_result = start_stream_async(stream_id)
        
        return f"Stream {stream_id} restarted: Stop={stop_result}, Start={start_result}"
        
    except Exception as e:
        logger.error(f"Failed to restart stream {stream_id}: {str(e)}")
        return f"Failed to restart stream: {str(e)}"
