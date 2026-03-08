from django.db import models
from django.contrib.auth.models import User, Group


class TelegramAdmin(models.Model):
    """Telegram administrators who can create bulk users"""
    telegram_id = models.BigIntegerField(unique=True)
    username = models.CharField(max_length=100, blank=True, null=True)
    first_name = models.CharField(max_length=100, blank=True, null=True)
    last_name = models.CharField(max_length=100, blank=True, null=True)
    is_admin = models.BooleanField(default=False)  # Full admin privileges
    is_support = models.BooleanField(default=False)  # Support privileges
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'telegram_admin'
        verbose_name = 'Telegram Admin'
        verbose_name_plural = 'Telegram Admins'
    
    def __str__(self):
        role = "Admin" if self.is_admin else "Support"
        return f"{self.username or self.telegram_id} ({role})"


class BulkUserRequest(models.Model):
    """Track bulk user creation requests"""
    telegram_admin = models.ForeignKey(TelegramAdmin, on_delete=models.CASCADE)
    prefix = models.CharField(max_length=20)
    count = models.IntegerField()
    groups = models.ManyToManyField(Group, blank=True)
    status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed')
    ], default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, null=True)
    
    class Meta:
        db_table = 'bulk_user_request'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.prefix} x{self.count} by {self.telegram_admin}"


class GeneratedUser(models.Model):
    """Store generated usernames and passwords"""
    bulk_request = models.ForeignKey(BulkUserRequest, on_delete=models.CASCADE)
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    username = models.CharField(max_length=150)
    password = models.CharField(max_length=8)  # Store plain password for admin use
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'generated_user'
        ordering = ['username']
    
    def __str__(self):
        return f"{self.username} - {self.password}"