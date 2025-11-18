"""
Translation configuration for Poll models using django-modeltranslation.
"""

from modeltranslation.translator import TranslationOptions, register

from .models import Poll, PollOption


@register(Poll)
class PollTranslationOptions(TranslationOptions):
    """Translation options for Poll model."""

    fields = ("title", "description")
    required_languages = ("en",)  # English is always required


@register(PollOption)
class PollOptionTranslationOptions(TranslationOptions):
    """Translation options for PollOption model."""

    fields = ("text",)
    required_languages = ("en",)  # English is always required

