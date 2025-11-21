"""
Tests for API documentation generation and accuracy.
"""

import pytest
import yaml
from django.test import Client
from django.urls import reverse

from drf_spectacular.openapi import AutoSchema
from drf_spectacular.utils import extend_schema


class TestAPIDocumentation:
    """Test API documentation generation and accuracy."""
    
    def test_schema_generation_no_errors(self):
        """Test that schema can be generated without errors."""
        from drf_spectacular.generators import SchemaGenerator
        from django.urls import get_resolver
        
        generator = SchemaGenerator(
            patterns=get_resolver().url_patterns,
            api_version="1.0.0",
        )
        schema = generator.get_schema(request=None, public=True)
        
        assert schema is not None
        assert "openapi" in schema
        assert schema["openapi"].startswith("3.")
    
    def test_schema_endpoints_documented(self):
        """Test that all major endpoints are documented."""
        from drf_spectacular.generators import SchemaGenerator
        from django.urls import get_resolver
        
        generator = SchemaGenerator(
            patterns=get_resolver().url_patterns,
            api_version="1.0.0",
        )
        schema = generator.get_schema(request=None, public=True)
        
        paths = schema.get("paths", {})
        
        # Check that key endpoints are documented
        assert "/api/v1/polls/" in paths or any("/polls" in path for path in paths.keys())
        assert "/api/v1/votes/" in paths or any("/votes" in path for path in paths.keys())
        assert "/api/v1/users/" in paths or any("/users" in path for path in paths.keys())
        assert "/api/v1/analytics/" in paths or any("/analytics" in path for path in paths.keys())
    
    def test_vote_cast_endpoint_documented(self):
        """Test that vote cast endpoint is properly documented."""
        from drf_spectacular.generators import SchemaGenerator
        from django.urls import get_resolver
        
        generator = SchemaGenerator(
            patterns=get_resolver().url_patterns,
            api_version="1.0.0",
        )
        schema = generator.get_schema(request=None, public=True)
        
        paths = schema.get("paths", {})
        
        # Find vote cast endpoint
        vote_path = None
        for path in paths.keys():
            if "votes" in path and "cast" in path:
                vote_path = path
                break
        
        if vote_path:
            path_item = paths[vote_path]
            assert "post" in path_item
            post_op = path_item["post"]
            
            # Check that it has request body
            assert "requestBody" in post_op
            
            # Check that it has responses documented
            assert "responses" in post_op
            assert "201" in post_op["responses"]  # Created
            assert "200" in post_op["responses"]  # Idempotent retry
            assert "400" in post_op["responses"]  # Bad Request
            assert "409" in post_op["responses"]  # Conflict
    
    def test_poll_results_endpoint_documented(self):
        """Test that poll results endpoint is properly documented."""
        from drf_spectacular.generators import SchemaGenerator
        from django.urls import get_resolver
        
        generator = SchemaGenerator(
            patterns=get_resolver().url_patterns,
            api_version="1.0.0",
        )
        schema = generator.get_schema(request=None, public=True)
        
        paths = schema.get("paths", {})
        
        # Find poll results endpoint
        results_path = None
        for path in paths.keys():
            if "polls" in path and "results" in path:
                results_path = path
                break
        
        if results_path:
            path_item = paths[results_path]
            assert "get" in path_item
            get_op = path_item["get"]
            
            # Check that it has responses documented
            assert "responses" in get_op
            assert "200" in get_op["responses"]
    
    def test_schema_has_info(self):
        """Test that schema has proper info section."""
        from drf_spectacular.generators import SchemaGenerator
        from django.urls import get_resolver
        
        generator = SchemaGenerator(
            patterns=get_resolver().url_patterns,
            api_version="1.0.0",
        )
        schema = generator.get_schema(request=None, public=True)
        
        assert "info" in schema
        info = schema["info"]
        assert "title" in info
        assert "version" in info
        assert info["title"] == "Provote API"
        # Version may include additional info in parentheses
        assert info["version"].startswith("1.0.0")
    
    def test_schema_has_tags(self):
        """Test that schema has tags defined."""
        from drf_spectacular.generators import SchemaGenerator
        from django.urls import get_resolver
        
        generator = SchemaGenerator(
            patterns=get_resolver().url_patterns,
            api_version="1.0.0",
        )
        schema = generator.get_schema(request=None, public=True)
        
        assert "tags" in schema
        tags = schema["tags"]
        tag_names = [tag["name"] for tag in tags]
        
        # Check that key tags are present
        assert "Polls" in tag_names
        assert "Votes" in tag_names
    
    def test_api_docs_endpoint_accessible(self, client):
        """Test that API docs endpoint is accessible."""
        # Test Swagger UI
        response = client.get("/api/docs/")
        assert response.status_code in [200, 302]  # 302 if redirect to login
        
        # Test ReDoc
        response = client.get("/api/redoc/")
        assert response.status_code in [200, 302]  # 302 if redirect to login
        
        # Test schema endpoint
        response = client.get("/api/schema/")
        assert response.status_code in [200, 302]  # 302 if redirect to login
    
    def test_schema_yaml_format(self):
        """Test that schema can be exported as YAML."""
        from drf_spectacular.generators import SchemaGenerator
        from django.urls import get_resolver
        
        generator = SchemaGenerator(
            patterns=get_resolver().url_patterns,
            api_version="1.0.0",
        )
        schema = generator.get_schema(request=None, public=True)
        
        # Convert to YAML
        yaml_str = yaml.dump(schema, default_flow_style=False)
        
        assert yaml_str is not None
        assert "openapi" in yaml_str.lower()
        assert "provote" in yaml_str.lower()
    
    def test_idempotency_documented(self):
        """Test that idempotency behavior is documented in vote endpoint."""
        from drf_spectacular.generators import SchemaGenerator
        from django.urls import get_resolver
        
        generator = SchemaGenerator(
            patterns=get_resolver().url_patterns,
            api_version="1.0.0",
        )
        schema = generator.get_schema(request=None, public=True)
        
        paths = schema.get("paths", {})
        
        # Find vote cast endpoint
        vote_path = None
        for path in paths.keys():
            if "votes" in path and "cast" in path:
                vote_path = path
                break
        
        if vote_path:
            path_item = paths[vote_path]
            post_op = path_item.get("post", {})
            
            # Check that description mentions idempotency
            description = post_op.get("description", "")
            assert "idempotency" in description.lower() or "idempotent" in description.lower()
            
            # Check that 200 response exists (for idempotent retry)
            responses = post_op.get("responses", {})
            assert "200" in responses
    
    def test_rate_limits_documented(self):
        """Test that rate limits are mentioned in endpoint documentation."""
        from drf_spectacular.generators import SchemaGenerator
        from django.urls import get_resolver
        
        generator = SchemaGenerator(
            patterns=get_resolver().url_patterns,
            api_version="1.0.0",
        )
        schema = generator.get_schema(request=None, public=True)
        
        paths = schema.get("paths", {})
        
        # Check vote cast endpoint
        vote_path = None
        for path in paths.keys():
            if "votes" in path and "cast" in path:
                vote_path = path
                break
        
        if vote_path:
            path_item = paths[vote_path]
            post_op = path_item.get("post", {})
            description = post_op.get("description", "")
            
            # Check that rate limits are mentioned
            assert "rate" in description.lower() or "limit" in description.lower()
        
        # Check poll create endpoint
        poll_path = None
        for path in paths.keys():
            if "polls" in path and path.endswith("/"):
                poll_path = path
                break
        
        if poll_path:
            path_item = paths[poll_path]
            post_op = path_item.get("post", {})
            if post_op:
                description = post_op.get("description", "")
                # Check that rate limits are mentioned
                assert "rate" in description.lower() or "limit" in description.lower()

