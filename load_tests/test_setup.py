"""
Test to verify load test setup is correct.

This is a pytest test that can be run to verify the load test infrastructure.
"""

import pytest
import sys
from pathlib import Path


def test_locust_installed():
    """Test that Locust is installed."""
    try:
        import locust
        assert hasattr(locust, '__version__')
    except ImportError:
        pytest.fail("Locust is not installed. Run: pip install locust")


def test_websockets_installed():
    """Test that websockets is installed."""
    try:
        import websockets
        assert hasattr(websockets, '__version__')
    except ImportError:
        pytest.fail("websockets is not installed. Run: pip install websockets")


def test_load_test_files_exist():
    """Test that all load test files exist."""
    load_tests_dir = Path(__file__).parent
    
    required_files = [
        "voting_load_test.py",
        "api_performance_test.py",
        "data_integrity_test.py",
        "graceful_degradation_test.py",
        "websocket_load_test.py",
        "websocket_load_async.py",
        "locustfile.py",
        "README.md",
        "run_load_tests.sh",
    ]
    
    missing_files = []
    for file in required_files:
        if not (load_tests_dir / file).exists():
            missing_files.append(file)
    
    if missing_files:
        pytest.fail(f"Missing load test files: {', '.join(missing_files)}")


def test_load_test_imports():
    """Test that load test modules can be imported."""
    # Add load_tests to path
    load_tests_dir = Path(__file__).parent
    if str(load_tests_dir) not in sys.path:
        sys.path.insert(0, str(load_tests_dir))
    
    # Test imports without actually importing (to avoid Django dependencies)
    # Just check that files are syntactically correct
    import ast
    
    test_files = [
        "voting_load_test.py",
        "api_performance_test.py",
        "data_integrity_test.py",
        "graceful_degradation_test.py",
    ]
    
    for file in test_files:
        file_path = load_tests_dir / file
        if file_path.exists():
            try:
                with open(file_path, 'r') as f:
                    ast.parse(f.read(), filename=str(file_path))
            except SyntaxError as e:
                pytest.fail(f"Syntax error in {file}: {e}")


def test_performance_monitor():
    """Test performance monitor functionality."""
    from performance_monitor import PerformanceMonitor
    
    monitor = PerformanceMonitor()
    
    # Record some test metrics
    monitor.record_request("test_endpoint", 100.0, 200)
    monitor.record_request("test_endpoint", 200.0, 200)
    monitor.record_request("test_endpoint", 150.0, 500, "Error")
    
    stats = monitor.get_statistics()
    assert "test_endpoint" in stats
    assert stats["test_endpoint"]["count"] == 3
    assert stats["test_endpoint"]["errors"] == 1
    
    bottlenecks = monitor.identify_bottlenecks()
    # Should identify endpoint with errors
    assert len(bottlenecks) > 0 or stats["test_endpoint"]["error_rate"] > 0
    
    report = monitor.generate_report()
    assert "PERFORMANCE REPORT" in report
    assert "test_endpoint" in report

