"""
Language utility functions for multi-language support.
"""

from django.conf import settings
from django.utils import translation


def get_request_language(request):
    """
    Get the language from request query parameter, header, or default.
    
    Args:
        request: Django request object
        
    Returns:
        str: Language code (e.g., 'en', 'es', 'fr', 'de')
    """
    # Check query parameter first (highest priority)
    lang = request.query_params.get("lang") or request.GET.get("lang")
    
    if lang:
        # Validate language code
        if lang in dict(settings.LANGUAGES):
            return lang
    
    # Check Accept-Language header
    if hasattr(request, "META") and "HTTP_ACCEPT_LANGUAGE" in request.META:
        accept_language = request.META.get("HTTP_ACCEPT_LANGUAGE", "")
        # Parse Accept-Language header (simple parsing)
        for lang_code, _ in settings.LANGUAGES:
            if lang_code in accept_language.lower():
                return lang_code
    
    # Use Django's current language
    current_lang = translation.get_language()
    if current_lang:
        # Extract base language code (e.g., 'en-us' -> 'en')
        base_lang = current_lang.split("-")[0]
        if base_lang in dict(settings.LANGUAGES):
            return base_lang
    
    # Fallback to default language
    return settings.MODELTRANSLATION_DEFAULT_LANGUAGE


def activate_language(language_code):
    """
    Activate a language for the current thread.
    
    Args:
        language_code: Language code to activate
    """
    translation.activate(language_code)


def deactivate_language():
    """Deactivate the current language and restore default."""
    translation.deactivate()


def get_translated_field(instance, field_name, language_code=None):
    """
    Get a translated field value for a model instance.
    
    Args:
        instance: Model instance with translations
        field_name: Name of the field to get
        language_code: Language code (defaults to current language)
        
    Returns:
        str: Translated value or fallback to default language
    """
    if language_code is None:
        language_code = translation.get_language() or settings.MODELTRANSLATION_DEFAULT_LANGUAGE
    
    # Extract base language code
    base_lang = language_code.split("-")[0]
    
    # Check if language is supported
    if base_lang not in dict(settings.LANGUAGES):
        base_lang = settings.MODELTRANSLATION_DEFAULT_LANGUAGE
    
    # Try to get translated field
    translated_field = f"{field_name}_{base_lang}"
    if hasattr(instance, translated_field):
        value = getattr(instance, translated_field)
        if value:  # Return translated value if available
            return value
    
    # Fallback to default language
    default_field = f"{field_name}_{settings.MODELTRANSLATION_DEFAULT_LANGUAGE}"
    if hasattr(instance, default_field):
        return getattr(instance, default_field)
    
    # Final fallback to original field
    return getattr(instance, field_name, "")

