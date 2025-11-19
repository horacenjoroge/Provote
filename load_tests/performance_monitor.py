"""
Performance monitoring utilities for load tests.

Tracks:
- Database query performance
- Cache hit rates
- Response time distributions
- System resource usage
"""

import time
import statistics
from collections import defaultdict
from typing import Dict, List


class PerformanceMonitor:
    """Monitor performance metrics during load tests."""
    
    def __init__(self):
        self.metrics = defaultdict(list)
        self.start_time = time.time()
        self.request_times = defaultdict(list)
        self.error_counts = defaultdict(int)
        self.slow_requests = []
    
    def record_request(self, endpoint: str, response_time: float, status_code: int, error: str = None):
        """Record a request metric."""
        self.request_times[endpoint].append(response_time)
        self.metrics[endpoint].append({
            "response_time": response_time,
            "status_code": status_code,
            "error": error,
            "timestamp": time.time(),
        })
        
        if error or status_code >= 500:
            self.error_counts[endpoint] += 1
        
        if response_time > 5000:  # >5 seconds
            self.slow_requests.append({
                "endpoint": endpoint,
                "response_time": response_time,
                "timestamp": time.time(),
            })
    
    def get_statistics(self) -> Dict:
        """Get performance statistics."""
        stats = {}
        
        for endpoint, times in self.request_times.items():
            if times:
                stats[endpoint] = {
                    "count": len(times),
                    "min": min(times),
                    "max": max(times),
                    "avg": statistics.mean(times),
                    "median": statistics.median(times),
                    "p95": self._percentile(times, 95),
                    "p99": self._percentile(times, 99),
                    "errors": self.error_counts[endpoint],
                    "error_rate": (self.error_counts[endpoint] / len(times)) * 100,
                }
        
        return stats
    
    def _percentile(self, data: List[float], percentile: int) -> float:
        """Calculate percentile."""
        if not data:
            return 0.0
        sorted_data = sorted(data)
        index = int(len(sorted_data) * (percentile / 100))
        return sorted_data[min(index, len(sorted_data) - 1)]
    
    def identify_bottlenecks(self) -> List[Dict]:
        """Identify performance bottlenecks."""
        bottlenecks = []
        stats = self.get_statistics()
        
        for endpoint, stat in stats.items():
            if stat["count"] < 10:  # Skip low-traffic endpoints
                continue
            
            issues = []
            
            # Check p95 response time
            if stat["p95"] > 1000:
                issues.append(f"High p95: {stat['p95']:.2f}ms")
            
            # Check error rate
            if stat["error_rate"] > 5:
                issues.append(f"High error rate: {stat['error_rate']:.2f}%")
            
            # Check average response time
            if stat["avg"] > 500:
                issues.append(f"High average: {stat['avg']:.2f}ms")
            
            if issues:
                bottlenecks.append({
                    "endpoint": endpoint,
                    "issues": issues,
                    "statistics": stat,
                })
        
        return sorted(bottlenecks, key=lambda x: x["statistics"]["p95"], reverse=True)
    
    def generate_report(self) -> str:
        """Generate performance report."""
        stats = self.get_statistics()
        bottlenecks = self.identify_bottlenecks()
        
        report = []
        report.append("=" * 80)
        report.append("PERFORMANCE REPORT")
        report.append("=" * 80)
        report.append(f"Test Duration: {time.time() - self.start_time:.2f}s")
        report.append("")
        
        report.append("Endpoint Statistics:")
        report.append("-" * 80)
        for endpoint, stat in sorted(stats.items(), key=lambda x: x[1]["p95"], reverse=True):
            report.append(f"\n{endpoint}:")
            report.append(f"  Requests: {stat['count']}")
            report.append(f"  Avg: {stat['avg']:.2f}ms")
            report.append(f"  P95: {stat['p95']:.2f}ms")
            report.append(f"  P99: {stat['p99']:.2f}ms")
            report.append(f"  Errors: {stat['errors']} ({stat['error_rate']:.2f}%)")
        
        if bottlenecks:
            report.append("\n" + "=" * 80)
            report.append("BOTTLENECKS IDENTIFIED")
            report.append("=" * 80)
            for bottleneck in bottlenecks:
                report.append(f"\n{bottleneck['endpoint']}:")
                for issue in bottleneck['issues']:
                    report.append(f"  - {issue}")
        
        if self.slow_requests:
            report.append("\n" + "=" * 80)
            report.append(f"SLOW REQUESTS (>5s): {len(self.slow_requests)}")
            report.append("=" * 80)
            for req in self.slow_requests[:10]:  # Show first 10
                report.append(f"  {req['endpoint']}: {req['response_time']:.2f}ms")
        
        return "\n".join(report)


# Global monitor instance
monitor = PerformanceMonitor()

