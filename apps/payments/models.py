from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta

class Subscription(models.Model):
    PLAN_CHOICES = [
        ('monthly', 'Monthly Plan'),
        ('annual', 'Annual Plan'),
        ('oneday' , 'OneDay Plan'),
    ]

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='subscriptions')
    plan_type = models.CharField(max_length=20, choices=PLAN_CHOICES)
    razorpay_order_id = models.CharField(max_length=255, unique=True)
    razorpay_payment_id = models.CharField(max_length=255, blank=True)
    razorpay_signature = models.CharField(max_length=255, blank=True)
    amount = models.IntegerField()  # in paise
    max_streams = models.IntegerField()
    # NEW: Storage limit for subscription plan
    storage_limit = models.BigIntegerField()  # in bytes (1GB = 1073741824 bytes, 2GB = 2147483648 bytes)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    is_active = models.BooleanField(default=True)
    start_date = models.DateTimeField(auto_now_add=True)
    end_date = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.plan_type} - {self.status}"

    def is_expired(self):
        return timezone.now() > self.end_date

    def get_storage_limit_display(self):
        """Display storage limit in GB"""
        return round(self.storage_limit / (1024 ** 3), 2)  # Convert bytes to GB

    def save(self, *args, **kwargs):
        if not self.end_date:
            from django.conf import settings
            plan_config = settings.SUBSCRIPTION_PLANS.get(self.plan_type)
            self.end_date = timezone.now() + timedelta(days=plan_config['duration_days'])
            self.max_streams = plan_config['max_streams']

            # NEW: Set storage limit based on plan type
            
            if self.plan_type == 'monthly':
                self.storage_limit = 1 * (1024 ** 3)  # 1GB in bytes
            elif self.plan_type == 'oneday':
                self.storage_limit = 0.5 * (1024 ** 3)  # 0.5 GB in bytes
            elif self.plan_type == 'annual':
                self.storage_limit = 2 * (1024 ** 3)  # 2GB in bytes

        super().save(*args, **kwargs)

    class Meta:
        verbose_name = 'Subscription'
        verbose_name_plural = 'Subscriptions'
        ordering = ['-created_at']

class Payment(models.Model):
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name='payments')
    razorpay_payment_id = models.CharField(max_length=255, unique=True)
    amount = models.IntegerField()
    currency = models.CharField(max_length=10, default='INR')
    status = models.CharField(max_length=50)
    method = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Payment {self.razorpay_payment_id} - {self.amount/100} INR"

    class Meta:
        verbose_name = 'Payment'
        verbose_name_plural = 'Payments'
        ordering = ['-created_at']
