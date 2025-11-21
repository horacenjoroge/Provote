"""
URL configuration for Provote project.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from rest_framework.decorators import api_view, permission_classes, renderer_classes
from rest_framework.permissions import AllowAny
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([AllowAny])
@renderer_classes([JSONRenderer])  # Only use JSONRenderer to avoid BrowsableAPIRenderer template issues
def api_root(request):
    """API root endpoint that lists available endpoints."""
    data = {
        "message": "Welcome to Provote API",
        "version": "1.0.0",
        "documentation": {
            "swagger_ui": "/api/docs/",
            "redoc": "/api/redoc/",
            "schema": "/api/schema/",
            "schema_viewer": "/api/schema/view/",
        },
        "endpoints": {
            "polls": "/api/v1/polls/",
            "votes": "/api/v1/votes/",
            "users": "/api/v1/users/",
            "analytics": "/api/v1/analytics/",
            "notifications": "/api/v1/notifications/",
            "categories": "/api/v1/categories/",
            "tags": "/api/v1/tags/",
        },
        "info": "For detailed API documentation, visit /api/docs/ or /api/redoc/",
    }
    
    return Response(data)


def schema_viewer(request):
    """Display schema in browser-friendly format with links to interactive docs."""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Provote API - Schema</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 1200px; margin: 50px auto; padding: 20px; }
            .header { background: #f5f5f5; padding: 20px; border-radius: 5px; margin-bottom: 20px; }
            .links { margin: 20px 0; }
            .links a { display: inline-block; margin-right: 15px; padding: 10px 20px; 
                       background: #007bff; color: white; text-decoration: none; border-radius: 3px; }
            .links a:hover { background: #0056b3; }
            .info { background: #e7f3ff; padding: 15px; border-left: 4px solid #007bff; margin: 20px 0; }
            .download-links { margin-top: 20px; }
            .download-links a { color: #007bff; text-decoration: none; margin-right: 15px; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Provote API Documentation</h1>
            <p>OpenAPI 3.0 Schema</p>
        </div>
        
        <div class="info">
            <strong>📖 Interactive Documentation:</strong> Use the links below to explore and test the API interactively.
        </div>
        
        <div class="links">
            <a href="/api/docs/" target="_blank">📘 Swagger UI (Interactive Explorer)</a>
            <a href="/api/redoc/" target="_blank">📕 ReDoc (Alternative Documentation)</a>
        </div>
        
        <div class="download-links">
            <h3>Download Schema Files:</h3>
            <a href="/api/schema/?format=json" download="schema.json">📄 Download JSON Schema</a>
            <a href="/api/schema/?format=yaml" download="schema.yaml">📄 Download YAML Schema</a>
        </div>
        
        <div style="margin-top: 30px;">
            <h3>About the Schema Endpoints:</h3>
            <p>The schema endpoints return raw OpenAPI specification files (JSON/YAML) which are designed for:</p>
            <ul>
                <li>API client code generation</li>
                <li>Importing into API testing tools (Postman, Insomnia, etc.)</li>
                <li>Integration with CI/CD pipelines</li>
                <li>Programmatic API consumption</li>
            </ul>
            <p><strong>For interactive exploration and testing, use Swagger UI or ReDoc above.</strong></p>
        </div>
    </body>
    </html>
    """
    return HttpResponse(html_content, content_type="text/html")


urlpatterns = [
    path("admin/", admin.site.urls),
    # API Root - accessible without authentication
    path("api/v1/", api_root, name="api-root"),
    path("api/v1/", include("apps.polls.urls")),
    path("api/v1/", include("apps.votes.urls")),
    path("api/v1/", include("apps.users.urls")),
    path("api/v1/", include("apps.analytics.urls")),
    path("api/v1/", include("apps.notifications.urls")),
    # API Documentation
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/schema/view/", schema_viewer, name="schema-viewer"),  # Browser-friendly schema page
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
