from django.db import models
from django.contrib.auth.models import User
from apps.accounts.models import YouTubeAccount
import uuid

class MediaFile(models.Model):
    MEDIA_TYPES = [
        ('video', 'Video'),
        ('audio', 'Audio'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='media_files')
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to='uploads/media/')
    thumbnail = models.ImageField(upload_to='uploads/thumbnails/', blank=True, null=True)
    media_type = models.CharField(max_length=10, choices=MEDIA_TYPES)
    sequence = models.PositiveIntegerField(default=0)
    duration = models.FloatField(default=0.0)  # in seconds
    file_size = models.BigIntegerField(default=0)  # in bytes
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = 'Media File'
        verbose_name_plural = 'Media Files'
        ordering = ['sequence', 'created_at']

class Stream(models.Model):
    STATUS_CHOICES = [
        ('idle', 'Idle'),
        ('starting', 'Starting'),
        ('running', 'Running'),
        ('stopping', 'Stopping'),
        ('stopped', 'Stopped'),
        ('error', 'Error'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='streams')
    youtube_account = models.ForeignKey(YouTubeAccount, on_delete=models.CASCADE, related_name='streams')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    thumbnail = models.ImageField(upload_to='uploads/stream_thumbnails/', blank=True, null=True)  # NEW FIELD
    media_files = models.ManyToManyField(MediaFile, related_name='streams')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='idle')
    stream_key = models.CharField(max_length=255, blank=True)
    broadcast_id = models.CharField(max_length=255, blank=True)
    stream_url = models.URLField(blank=True)
    loop_enabled = models.BooleanField(default=True)
    process_id = models.IntegerField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    stopped_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} - {self.user.username}"

    class Meta:
        verbose_name = 'Stream'
        verbose_name_plural = 'Streams'
        ordering = ['-created_at']

class StreamLog(models.Model):
    stream = models.ForeignKey(Stream, on_delete=models.CASCADE, related_name='logs')
    level = models.CharField(max_length=20)  # INFO, WARNING, ERROR
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.stream.title} - {self.level} - {self.created_at}"

    class Meta:
        verbose_name = 'Stream Log'
        verbose_name_plural = 'Stream Logs'
        ordering = ['-created_at']
