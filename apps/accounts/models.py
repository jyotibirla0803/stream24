from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    phone = models.CharField(max_length=15, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.username}'s Profile"
    
    class Meta:
        verbose_name = 'User Profile'
        verbose_name_plural = 'User Profiles'


class YouTubeAccount(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='youtube_accounts')
    channel_id = models.CharField(max_length=255, unique=True)
    channel_title = models.CharField(max_length=255)
    access_token = models.TextField()
    refresh_token = models.TextField()
    token_expiry = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.channel_title} - {self.user.username}"
    
    def is_token_expired(self):
        return timezone.now() >= self.token_expiry
    
    class Meta:
        verbose_name = 'YouTube Account'
        verbose_name_plural = 'YouTube Accounts'
