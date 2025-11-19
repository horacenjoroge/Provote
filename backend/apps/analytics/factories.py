"""
Factory Boy factories for Analytics models.
"""

import factory
from faker import Faker

from apps.polls.factories import PollFactory, UserFactory
from apps.polls.models import Poll
from django.contrib.auth.models import User

from .models import (
    AuditLog,
    FingerprintBlock,
    FraudAlert,
    IPBlock,
    IPReputation,
    IPWhitelist,
    PollAnalytics,
)

fake = Faker()


class PollAnalyticsFactory(factory.django.DjangoModelFactory):
    """Factory for PollAnalytics model."""

    class Meta:
        model = PollAnalytics

    poll = factory.SubFactory(PollFactory)
    total_votes = 0
    unique_voters = 0


class AuditLogFactory(factory.django.DjangoModelFactory):
    """Factory for AuditLog model."""

    class Meta:
        model = AuditLog

    user = factory.SubFactory(UserFactory)
    method = "GET"
    path = factory.Faker("uri_path")
    query_params = None
    request_body = None
    status_code = 200
    ip_address = factory.Faker("ipv4")
    user_agent = factory.Faker("user_agent")
    request_id = factory.Faker("uuid4")
    response_time = factory.Faker("pyfloat", positive=True, max_value=1.0)


class FingerprintBlockFactory(factory.django.DjangoModelFactory):
    """Factory for FingerprintBlock model."""

    class Meta:
        model = FingerprintBlock

    fingerprint = factory.Faker("sha256")
    reason = factory.Faker("sentence")
    blocked_by = factory.SubFactory(UserFactory)
    is_active = True
    unblocked_at = None
    unblocked_by = None


class IPReputationFactory(factory.django.DjangoModelFactory):
    """Factory for IPReputation model."""

    class Meta:
        model = IPReputation

    ip_address = factory.Faker("ipv4")
    reputation_score = 50
    violation_count = 0
    successful_attempts = 0
    failed_attempts = 0
    last_violation_at = None


class IPBlockFactory(factory.django.DjangoModelFactory):
    """Factory for IPBlock model."""

    class Meta:
        model = IPBlock

    ip_address = factory.Faker("ipv4")
    reason = factory.Faker("sentence")
    is_active = True
    is_manual = False
    blocked_by = None
    auto_unblock_at = None


class IPWhitelistFactory(factory.django.DjangoModelFactory):
    """Factory for IPWhitelist model."""

    class Meta:
        model = IPWhitelist

    ip_address = factory.Faker("ipv4")
    reason = factory.Faker("sentence")
    is_active = True
    created_by = factory.SubFactory(UserFactory)


class FraudAlertFactory(factory.django.DjangoModelFactory):
    """Factory for FraudAlert model."""

    class Meta:
        model = FraudAlert

    vote = factory.SubFactory("apps.votes.factories.VoteFactory")
    poll = factory.LazyAttribute(lambda obj: obj.vote.poll)
    user = factory.LazyAttribute(lambda obj: obj.vote.user)
    reasons = factory.Faker("sentence")
    risk_score = factory.Faker("random_int", min=0, max=100)
    ip_address = factory.LazyAttribute(lambda obj: obj.vote.ip_address)

