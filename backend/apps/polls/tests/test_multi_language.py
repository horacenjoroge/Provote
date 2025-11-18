"""
Tests for multi-language support in polls.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.polls.models import Poll, PollOption


@pytest.fixture
def user():
    """Create a test user."""
    return User.objects.create_user(username="testuser", password="testpass123")


@pytest.fixture
def api_client():
    """Create an API client."""
    return APIClient()


@pytest.fixture
def authenticated_client(api_client, user):
    """Create an authenticated API client."""
    api_client.force_authenticate(user=user)
    return api_client


@pytest.mark.django_db
class TestMultiLanguagePollCreation:
    """Test creating polls with multiple languages."""

    def test_create_poll_with_english_only(self, authenticated_client, user):
        """Test creating a poll with only English (default language)."""
        url = reverse("poll-list")
        data = {
            "title": "Test Poll",
            "description": "This is a test poll",
            "options": [
                {"text": "Option 1"},
                {"text": "Option 2"},
            ],
        }
        response = authenticated_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["title"] == "Test Poll"
        assert response.data["description"] == "This is a test poll"

    def test_create_poll_with_multiple_languages(self, authenticated_client, user):
        """Test creating a poll with translations in multiple languages."""
        url = reverse("poll-list")
        data = {
            "title": "Test Poll",
            "title_es": "Encuesta de Prueba",
            "title_fr": "Sondage de Test",
            "title_de": "Test-Umfrage",
            "description": "This is a test poll",
            "description_es": "Esta es una encuesta de prueba",
            "description_fr": "Ceci est un sondage de test",
            "description_de": "Dies ist eine Testumfrage",
            "options": [
                {"text": "Option 1", "text_es": "Opción 1", "text_fr": "Option 1", "text_de": "Option 1"},
                {"text": "Option 2", "text_es": "Opción 2", "text_fr": "Option 2", "text_de": "Option 2"},
            ],
        }
        response = authenticated_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        
        # Check that poll was created
        poll = Poll.objects.get(id=response.data["id"])
        assert poll.title == "Test Poll"
        assert poll.title_es == "Encuesta de Prueba"
        assert poll.title_fr == "Sondage de Test"
        assert poll.title_de == "Test-Umfrage"
        
        # Check options translations
        options = poll.options.all()
        assert options[0].text == "Option 1"
        assert options[0].text_es == "Opción 1"
        assert options[1].text == "Option 2"
        assert options[1].text_es == "Opción 2"

    def test_create_poll_with_swahili_translation(self, authenticated_client, user):
        """Test creating a poll with Swahili translation."""
        url = reverse("poll-list")
        data = {
            "title": "Test Poll",
            "title_sw": "Uchaguzi wa Jaribio",
            "description": "This is a test poll",
            "description_sw": "Hii ni uchaguzi wa jaribio",
            "options": [
                {"text": "Option 1", "text_sw": "Chaguo 1"},
                {"text": "Option 2", "text_sw": "Chaguo 2"},
            ],
        }
        response = authenticated_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        
        # Check that poll was created with Swahili translation
        poll = Poll.objects.get(id=response.data["id"])
        assert poll.title == "Test Poll"
        assert poll.title_sw == "Uchaguzi wa Jaribio"
        assert poll.description_sw == "Hii ni uchaguzi wa jaribio"
        
        # Check options translations
        options = poll.options.all()
        assert options[0].text_sw == "Chaguo 1"
        assert options[1].text_sw == "Chaguo 2"


@pytest.mark.django_db
class TestAPILanguageParameter:
    """Test API language parameter handling."""

    def test_api_returns_english_by_default(self, authenticated_client, user):
        """Test that API returns English by default when no language specified."""
        # Create poll with translations
        poll = Poll.objects.create(
            title="Test Poll",
            title_es="Encuesta de Prueba",
            title_fr="Sondage de Test",
            created_by=user,
        )
        PollOption.objects.create(poll=poll, text="Option 1", text_es="Opción 1")
        
        url = reverse("poll-detail", kwargs={"pk": poll.id})
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data["title"] == "Test Poll"
        assert response.data["options"][0]["text"] == "Option 1"

    def test_api_returns_spanish_with_lang_parameter(self, authenticated_client, user):
        """Test that API returns Spanish when lang=es parameter is provided."""
        # Create poll with translations
        poll = Poll.objects.create(
            title="Test Poll",
            title_es="Encuesta de Prueba",
            created_by=user,
        )
        PollOption.objects.create(poll=poll, text="Option 1", text_es="Opción 1")
        
        url = reverse("poll-detail", kwargs={"pk": poll.id})
        response = authenticated_client.get(url, {"lang": "es"})
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data["title"] == "Encuesta de Prueba"
        assert response.data["options"][0]["text"] == "Opción 1"

    def test_api_returns_french_with_lang_parameter(self, authenticated_client, user):
        """Test that API returns French when lang=fr parameter is provided."""
        # Create poll with translations
        poll = Poll.objects.create(
            title="Test Poll",
            title_fr="Sondage de Test",
            created_by=user,
        )
        PollOption.objects.create(poll=poll, text="Option 1", text_fr="Option 1 (FR)")
        
        url = reverse("poll-detail", kwargs={"pk": poll.id})
        response = authenticated_client.get(url, {"lang": "fr"})
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data["title"] == "Sondage de Test"
        assert response.data["options"][0]["text"] == "Option 1 (FR)"

    def test_api_returns_german_with_lang_parameter(self, authenticated_client, user):
        """Test that API returns German when lang=de parameter is provided."""
        # Create poll with translations
        poll = Poll.objects.create(
            title="Test Poll",
            title_de="Test-Umfrage",
            created_by=user,
        )
        PollOption.objects.create(poll=poll, text="Option 1", text_de="Option 1 (DE)")
        
        url = reverse("poll-detail", kwargs={"pk": poll.id})
        response = authenticated_client.get(url, {"lang": "de"})
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data["title"] == "Test-Umfrage"
        assert response.data["options"][0]["text"] == "Option 1 (DE)"

    def test_api_returns_swahili_with_lang_parameter(self, authenticated_client, user):
        """Test that API returns Swahili when lang=sw parameter is provided."""
        # Create poll with translations
        poll = Poll.objects.create(
            title="Test Poll",
            title_sw="Uchaguzi wa Jaribio",
            created_by=user,
        )
        PollOption.objects.create(poll=poll, text="Option 1", text_sw="Chaguo 1")
        
        url = reverse("poll-detail", kwargs={"pk": poll.id})
        response = authenticated_client.get(url, {"lang": "sw"})
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data["title"] == "Uchaguzi wa Jaribio"
        assert response.data["options"][0]["text"] == "Chaguo 1"

    def test_api_falls_back_to_english_when_translation_missing(self, authenticated_client, user):
        """Test that API falls back to English when requested translation is missing."""
        # Create poll with only English
        poll = Poll.objects.create(
            title="Test Poll",
            created_by=user,
        )
        PollOption.objects.create(poll=poll, text="Option 1")
        
        url = reverse("poll-detail", kwargs={"pk": poll.id})
        response = authenticated_client.get(url, {"lang": "es"})
        
        assert response.status_code == status.HTTP_200_OK
        # Should fallback to English
        assert response.data["title"] == "Test Poll"
        assert response.data["options"][0]["text"] == "Option 1"

    def test_api_falls_back_to_english_for_invalid_language(self, authenticated_client, user):
        """Test that API falls back to English for invalid language code."""
        poll = Poll.objects.create(
            title="Test Poll",
            created_by=user,
        )
        PollOption.objects.create(poll=poll, text="Option 1")
        
        url = reverse("poll-detail", kwargs={"pk": poll.id})
        response = authenticated_client.get(url, {"lang": "invalid"})
        
        assert response.status_code == status.HTTP_200_OK
        # Should fallback to English
        assert response.data["title"] == "Test Poll"


@pytest.mark.django_db
class TestLanguageSwitching:
    """Test language switching functionality."""

    def test_switch_language_in_list_endpoint(self, authenticated_client, user):
        """Test switching language in list endpoint."""
        # Create polls with translations
        poll1 = Poll.objects.create(
            title="Poll 1",
            title_es="Encuesta 1",
            created_by=user,
        )
        poll2 = Poll.objects.create(
            title="Poll 2",
            title_es="Encuesta 2",
            created_by=user,
        )
        
        url = reverse("poll-list")
        response = authenticated_client.get(url, {"lang": "es"})
        
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"] if "results" in response.data else response.data
        assert len(results) >= 2
        # Check that both polls return Spanish titles
        poll_titles = [p["title"] for p in results if p["id"] in [poll1.id, poll2.id]]
        assert "Encuesta 1" in poll_titles
        assert "Encuesta 2" in poll_titles

    def test_switch_language_in_detail_endpoint(self, authenticated_client, user):
        """Test switching language in detail endpoint."""
        poll = Poll.objects.create(
            title="Test Poll",
            title_es="Encuesta de Prueba",
            title_fr="Sondage de Test",
            description="English description",
            description_es="Descripción en español",
            description_fr="Description en français",
            created_by=user,
        )
        PollOption.objects.create(
            poll=poll,
            text="Option 1",
            text_es="Opción 1",
            text_fr="Option 1 (FR)",
        )
        
        url = reverse("poll-detail", kwargs={"pk": poll.id})
        
        # Test English
        response = authenticated_client.get(url, {"lang": "en"})
        assert response.status_code == status.HTTP_200_OK
        assert response.data["title"] == "Test Poll"
        assert response.data["description"] == "English description"
        assert response.data["options"][0]["text"] == "Option 1"
        
        # Test Spanish
        response = authenticated_client.get(url, {"lang": "es"})
        assert response.status_code == status.HTTP_200_OK
        assert response.data["title"] == "Encuesta de Prueba"
        assert response.data["description"] == "Descripción en español"
        assert response.data["options"][0]["text"] == "Opción 1"
        
        # Test French
        response = authenticated_client.get(url, {"lang": "fr"})
        assert response.status_code == status.HTTP_200_OK
        assert response.data["title"] == "Sondage de Test"
        assert response.data["description"] == "Description en français"
        assert response.data["options"][0]["text"] == "Option 1 (FR)"


@pytest.mark.django_db
class TestPartialTranslations:
    """Test handling of partial translations."""

    def test_partial_translation_falls_back_to_english(self, authenticated_client, user):
        """Test that partial translations fall back to English for missing fields."""
        # Create poll with only Spanish title, but English description
        poll = Poll.objects.create(
            title="Test Poll",
            title_es="Encuesta de Prueba",
            description="English description only",
            created_by=user,
        )
        # Option with only Spanish text
        PollOption.objects.create(
            poll=poll,
            text="Option 1",
            text_es="Opción 1",
        )
        
        url = reverse("poll-detail", kwargs={"pk": poll.id})
        response = authenticated_client.get(url, {"lang": "es"})
        
        assert response.status_code == status.HTTP_200_OK
        # Title should be Spanish
        assert response.data["title"] == "Encuesta de Prueba"
        # Description should fallback to English
        assert response.data["description"] == "English description only"
        # Option text should be Spanish
        assert response.data["options"][0]["text"] == "Opción 1"

    def test_mixed_translations_in_options(self, authenticated_client, user):
        """Test handling of mixed translations in options."""
        poll = Poll.objects.create(
            title="Test Poll",
            created_by=user,
        )
        # Option 1: Full translations
        PollOption.objects.create(
            poll=poll,
            text="Option 1",
            text_es="Opción 1",
            text_fr="Option 1 (FR)",
        )
        # Option 2: Only English
        PollOption.objects.create(
            poll=poll,
            text="Option 2",
        )
        
        url = reverse("poll-detail", kwargs={"pk": poll.id})
        response = authenticated_client.get(url, {"lang": "es"})
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["options"]) == 2
        # Option 1 should be Spanish
        assert response.data["options"][0]["text"] == "Opción 1"
        # Option 2 should fallback to English
        assert response.data["options"][1]["text"] == "Option 2"

