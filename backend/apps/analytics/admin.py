"""
Admin interface for Analytics app.
"""

from django.contrib import admin
from django.utils.html import format_html

from .models import (
    AuditLog,
    FingerprintBlock,
    FraudAlert,
    IPBlock,
    IPReputation,
    IPWhitelist,
    PollAnalytics,
)


@admin.register(PollAnalytics)
class PollAnalyticsAdmin(admin.ModelAdmin):
    """Admin for PollAnalytics."""

    list_display = ["poll", "total_votes", "unique_voters", "last_updated"]
    readonly_fields = ["poll", "total_votes", "unique_voters", "last_updated"]
    search_fields = ["poll__title"]


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Admin for AuditLog."""

    list_display = ["method", "path", "status_code", "ip_address", "user", "created_at"]
    list_filter = ["method", "status_code", "created_at"]
    search_fields = ["path", "ip_address", "user__username"]
    readonly_fields = [
        "user",
        "method",
        "path",
        "query_params",
        "request_body",
        "status_code",
        "ip_address",
        "user_agent",
        "request_id",
        "response_time",
        "created_at",
    ]
    date_hierarchy = "created_at"


@admin.register(FingerprintBlock)
class FingerprintBlockAdmin(admin.ModelAdmin):
    """Admin for FingerprintBlock."""

    list_display = ["fingerprint_short", "reason", "is_active", "blocked_at", "blocked_by"]
    list_filter = ["is_active", "blocked_at"]
    search_fields = ["fingerprint"]
    readonly_fields = ["fingerprint", "blocked_at", "unblocked_at"]
    actions = ["unblock_selected"]

    def fingerprint_short(self, obj):
        """Display shortened fingerprint."""
        return f"{obj.fingerprint[:16]}..." if len(obj.fingerprint) > 16 else obj.fingerprint

    fingerprint_short.short_description = "Fingerprint"

    def unblock_selected(self, request, queryset):
        """Unblock selected fingerprints."""
        count = 0
        for block in queryset.filter(is_active=True):
            block.unblock(user=request.user)
            count += 1
        self.message_user(request, f"Unblocked {count} fingerprint(s).")

    unblock_selected.short_description = "Unblock selected fingerprints"


@admin.register(FraudAlert)
class FraudAlertAdmin(admin.ModelAdmin):
    """Admin for FraudAlert."""

    list_display = ["vote", "poll", "user", "ip_address", "risk_score", "created_at"]
    list_filter = ["risk_score", "created_at"]
    search_fields = ["poll__title", "user__username", "ip_address"]
    readonly_fields = ["vote", "poll", "user", "ip_address", "reasons", "risk_score", "created_at"]
    date_hierarchy = "created_at"


@admin.register(IPReputation)
class IPReputationAdmin(admin.ModelAdmin):
    """Admin for IPReputation."""

    list_display = [
        "ip_address",
        "reputation_score",
        "violation_count",
        "successful_attempts",
        "failed_attempts",
        "last_seen",
    ]
    list_filter = ["reputation_score", "violation_count", "last_seen"]
    search_fields = ["ip_address"]
    readonly_fields = [
        "ip_address",
        "reputation_score",
        "violation_count",
        "successful_attempts",
        "failed_attempts",
        "first_seen",
        "last_seen",
        "last_violation_at",
    ]
    date_hierarchy = "last_seen"
    actions = ["block_selected_ips"]
    
    def get_queryset(self, request):
        """Optimize queryset."""
        return super().get_queryset(request).select_related()
    
    def block_selected_ips(self, request, queryset):
        """Block selected IPs based on reputation."""
        from core.utils.ip_reputation import block_ip
        
        count = 0
        for reputation in queryset:
            try:
                block_ip(
                    ip_address=reputation.ip_address,
                    reason=f"Manually blocked by admin (score: {reputation.reputation_score}, violations: {reputation.violation_count})",
                    is_manual=True,
                    blocked_by=request.user,
                )
                count += 1
            except Exception as e:
                self.message_user(request, f"Error blocking {reputation.ip_address}: {e}", level="error")
        
        self.message_user(request, f"Blocked {count} IP(s).")

    block_selected_ips.short_description = "Block selected IPs"


@admin.register(IPBlock)
class IPBlockAdmin(admin.ModelAdmin):
    """Admin for IPBlock."""

    list_display = [
        "ip_address",
        "reason_short",
        "is_manual",
        "is_active",
        "blocked_at",
        "blocked_by",
        "auto_unblock_at",
    ]
    list_filter = ["is_active", "is_manual", "blocked_at"]
    search_fields = ["ip_address", "reason"]
    readonly_fields = ["ip_address", "blocked_at", "unblocked_at"]
    actions = ["unblock_selected", "block_selected_manually"]
    
    fieldsets = (
        ("IP Information", {
            "fields": ("ip_address", "reason", "is_manual", "is_active")
        }),
        ("Blocking Information", {
            "fields": ("blocked_by", "blocked_at", "auto_unblock_at")
        }),
        ("Unblocking Information", {
            "fields": ("unblocked_by", "unblocked_at")
        }),
    )

    def reason_short(self, obj):
        """Display shortened reason."""
        if len(obj.reason) > 50:
            return f"{obj.reason[:50]}..."
        return obj.reason

    reason_short.short_description = "Reason"

    def unblock_selected(self, request, queryset):
        """Unblock selected IPs."""
        from core.utils.ip_reputation import unblock_ip
        
        count = 0
        for block in queryset.filter(is_active=True):
            if unblock_ip(block.ip_address, unblocked_by=request.user):
                count += 1
        self.message_user(request, f"Unblocked {count} IP(s).")

    unblock_selected.short_description = "Unblock selected IPs"

    def block_selected_manually(self, request, queryset):
        """Manually block selected IPs (if not already blocked)."""
        from core.utils.ip_reputation import block_ip
        
        count = 0
        for block in queryset:
            if not block.is_active:
                try:
                    block_ip(
                        ip_address=block.ip_address,
                        reason="Manually blocked by admin",
                        is_manual=True,
                        blocked_by=request.user,
                    )
                    count += 1
                except Exception as e:
                    self.message_user(request, f"Error blocking {block.ip_address}: {e}", level="error")
        
        self.message_user(request, f"Blocked {count} IP(s).")

    block_selected_manually.short_description = "Manually block selected IPs"


@admin.register(IPWhitelist)
class IPWhitelistAdmin(admin.ModelAdmin):
    """Admin for IPWhitelist."""

    list_display = ["ip_address", "reason_short", "is_active", "created_by", "created_at"]
    list_filter = ["is_active", "created_at"]
    search_fields = ["ip_address", "reason"]
    readonly_fields = ["created_at"]
    actions = ["remove_from_whitelist"]
    
    fieldsets = (
        ("IP Information", {
            "fields": ("ip_address", "reason", "is_active")
        }),
        ("Metadata", {
            "fields": ("created_by", "created_at")
        }),
    )

    def reason_short(self, obj):
        """Display shortened reason."""
        if len(obj.reason) > 50:
            return f"{obj.reason[:50]}..."
        return obj.reason

    reason_short.short_description = "Reason"

    def remove_from_whitelist(self, request, queryset):
        """Remove selected IPs from whitelist."""
        from core.utils.ip_reputation import remove_whitelist
        
        count = 0
        for whitelist in queryset.filter(is_active=True):
            if remove_whitelist(whitelist.ip_address):
                count += 1
        self.message_user(request, f"Removed {count} IP(s) from whitelist.")

    remove_from_whitelist.short_description = "Remove from whitelist"
