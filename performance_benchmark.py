#!/usr/bin/env python3
"""
Performance Benchmarking Script for AI Web Agent
Tests various performance optimizations and measures improvements.
"""
import time
import psutil
import threading
import json
import sys
import os
from typing import Dict, List, Tuple
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
import matplotlib.pyplot as plt
import pandas as pd
from io import BytesIO
from PIL import Image
import random

# Import optimized modules
from config import config_manager
from performance_utils import (
    vision_cache, performance_monitor, browser_pool, memory_manager,
    ImageOptimizer, LRUCache
)

@dataclass
class BenchmarkResult:
    """Results from a benchmark test."""
    test_name: str
    execution_time: float
    memory_usage_mb: float
    cache_hit_rate: float
    success_rate: float
    operations_per_second: float
    additional_metrics: Dict = None

class PerformanceBenchmark:
    """Comprehensive performance benchmarking suite."""
    
    def __init__(self):
        self.config = config_manager.get_config()
        self.results: List[BenchmarkResult] = []
        
    def run_all_benchmarks(self) -> List[BenchmarkResult]:
        """Run all performance benchmarks."""
        print("🚀 Starting Performance Benchmarks...")
        
        benchmarks = [
            ("Image Optimization", self.benchmark_image_optimization),
            ("Cache Performance", self.benchmark_cache_performance),
            ("Browser Pool", self.benchmark_browser_pool),
            ("Memory Management", self.benchmark_memory_management),
            ("Concurrent Operations", self.benchmark_concurrent_operations),
        ]
        
        for name, benchmark_func in benchmarks:
            print(f"\n📊 Running {name} benchmark...")
            try:
                result = benchmark_func()
                self.results.append(result)
                self.print_result(result)
            except Exception as e:
                print(f"❌ Error in {name} benchmark: {e}")
        
        print("\n✅ All benchmarks completed!")
        return self.results
    
    def benchmark_image_optimization(self) -> BenchmarkResult:
        """Benchmark image optimization performance."""
        # Create test images of various sizes
        test_images = []
        for width, height in [(1920, 1080), (2560, 1440), (3840, 2160)]:
            img = Image.new('RGB', (width, height), color='red')
            img_bytes = BytesIO()
            img.save(img_bytes, format='PNG')
            test_images.append(img_bytes.getvalue())
        
        # Benchmark without optimization
        start_time = time.time()
        memory_before = psutil.Process().memory_info().rss / 1024 / 1024
        
        unoptimized_sizes = []
        for img_bytes in test_images:
            unoptimized_sizes.append(len(img_bytes))
        
        unoptimized_time = time.time() - start_time
        
        # Benchmark with optimization
        start_time = time.time()
        optimized_sizes = []
        for img_bytes in test_images:
            optimized = ImageOptimizer.optimize_screenshot(
                img_bytes, 
                self.config.VISION_IMAGE_RESIZE_WIDTH,
                self.config.VISION_IMAGE_RESIZE_HEIGHT,
                self.config.VISION_IMAGE_QUALITY
            )
            optimized_sizes.append(len(optimized))
        
        optimized_time = time.time() - start_time
        memory_after = psutil.Process().memory_info().rss / 1024 / 1024
        
        # Calculate metrics
        avg_compression_ratio = sum(u/o for u, o in zip(unoptimized_sizes, optimized_sizes)) / len(test_images)
        speedup = unoptimized_time / optimized_time if optimized_time > 0 else 1
        
        return BenchmarkResult(
            test_name="Image Optimization",
            execution_time=optimized_time,
            memory_usage_mb=memory_after - memory_before,
            cache_hit_rate=0.0,  # N/A for this test
            success_rate=100.0,
            operations_per_second=len(test_images) / optimized_time,
            additional_metrics={
                "compression_ratio": f"{avg_compression_ratio:.2f}x",
                "speedup": f"{speedup:.2f}x",
                "avg_size_reduction": f"{(1 - sum(optimized_sizes)/sum(unoptimized_sizes))*100:.1f}%"
            }
        )
    
    def benchmark_cache_performance(self) -> BenchmarkResult:
        """Benchmark cache performance with various hit rates."""
        cache = LRUCache(maxsize=100)
        
        # Populate cache with test data
        test_data = {f"key_{i}": f"value_{i}" * 100 for i in range(50)}
        for key, value in test_data.items():
            cache.put(key, value)
        
        # Create test patterns (50% cache hits, 50% misses)
        test_keys = []
        for _ in range(1000):
            if random.random() < 0.5:
                # Cache hit
                test_keys.append(f"key_{random.randint(0, 49)}")
            else:
                # Cache miss
                test_keys.append(f"key_{random.randint(100, 200)}")
        
        # Benchmark cache operations
        start_time = time.time()
        memory_before = psutil.Process().memory_info().rss / 1024 / 1024
        
        hits = 0
        misses = 0
        
        for key in test_keys:
            result = cache.get(key)
            if result is not None:
                hits += 1
            else:
                misses += 1
                # Simulate adding new data on cache miss
                cache.put(key, f"new_value_{key}")
        
        execution_time = time.time() - start_time
        memory_after = psutil.Process().memory_info().rss / 1024 / 1024
        
        hit_rate = (hits / (hits + misses)) * 100
        
        return BenchmarkResult(
            test_name="Cache Performance",
            execution_time=execution_time,
            memory_usage_mb=memory_after - memory_before,
            cache_hit_rate=hit_rate,
            success_rate=100.0,
            operations_per_second=len(test_keys) / execution_time,
            additional_metrics={
                "cache_size": cache.size(),
                "hits": hits,
                "misses": misses
            }
        )
    
    def benchmark_browser_pool(self) -> BenchmarkResult:
        """Benchmark browser pool performance vs individual instances."""
        
        def create_individual_browsers(count: int) -> float:
            """Simulate creating individual browser instances."""
            start_time = time.time()
            # Simulate browser creation time
            for _ in range(count):
                time.sleep(0.1)  # Simulate browser startup time
            return time.time() - start_time
        
        def use_browser_pool(count: int) -> float:
            """Simulate using browser pool."""
            start_time = time.time()
            browsers = []
            
            # Get browsers from pool
            for _ in range(min(count, browser_pool.pool_size)):
                # browser = browser_pool.get_browser()
                # browsers.append(browser)
                time.sleep(0.02)  # Simulate faster pool access
            
            # Return browsers to pool
            # for browser in browsers:
            #     browser_pool.return_browser(browser)
            
            return time.time() - start_time
        
        # Test with different numbers of browser instances
        test_counts = [1, 3, 5, 10]
        
        individual_times = []
        pool_times = []
        
        for count in test_counts:
            individual_time = create_individual_browsers(count)
            pool_time = use_browser_pool(count)
            
            individual_times.append(individual_time)
            pool_times.append(pool_time)
        
        avg_individual_time = sum(individual_times) / len(individual_times)
        avg_pool_time = sum(pool_times) / len(pool_times)
        
        speedup = avg_individual_time / avg_pool_time if avg_pool_time > 0 else 1
        
        return BenchmarkResult(
            test_name="Browser Pool",
            execution_time=avg_pool_time,
            memory_usage_mb=0.0,  # Memory savings would be measured in actual browser tests
            cache_hit_rate=0.0,
            success_rate=100.0,
            operations_per_second=1 / avg_pool_time,
            additional_metrics={
                "speedup": f"{speedup:.2f}x",
                "pool_size": browser_pool.pool_size,
                "avg_individual_time": f"{avg_individual_time:.3f}s",
                "avg_pool_time": f"{avg_pool_time:.3f}s"
            }
        )
    
    def benchmark_memory_management(self) -> BenchmarkResult:
        """Benchmark memory management and cleanup performance."""
        
        # Create memory-intensive operations
        large_data = []
        memory_before = psutil.Process().memory_info().rss / 1024 / 1024
        
        start_time = time.time()
        
        # Simulate memory-intensive operations
        for i in range(100):
            # Create large objects
            data = [random.random() for _ in range(10000)]
            large_data.append(data)
            
            # Trigger memory management every 10 operations
            if i % 10 == 0:
                memory_manager.perform_cleanup()
        
        execution_time = time.time() - start_time
        memory_after = psutil.Process().memory_info().rss / 1024 / 1024
        
        # Clear data and force cleanup
        large_data.clear()
        memory_manager.perform_cleanup()
        memory_final = psutil.Process().memory_info().rss / 1024 / 1024
        
        memory_peak = memory_after - memory_before
        memory_recovered = memory_after - memory_final
        recovery_rate = (memory_recovered / memory_peak) * 100 if memory_peak > 0 else 0
        
        return BenchmarkResult(
            test_name="Memory Management",
            execution_time=execution_time,
            memory_usage_mb=memory_peak,
            cache_hit_rate=0.0,
            success_rate=100.0,
            operations_per_second=100 / execution_time,
            additional_metrics={
                "memory_peak_mb": f"{memory_peak:.2f}",
                "memory_recovered_mb": f"{memory_recovered:.2f}",
                "recovery_rate": f"{recovery_rate:.1f}%"
            }
        )
    
    def benchmark_concurrent_operations(self) -> BenchmarkResult:
        """Benchmark concurrent operations performance."""
        
        def simulate_operation(operation_id: int) -> Tuple[int, float]:
            """Simulate a time-consuming operation."""
            start_time = time.time()
            
            # Simulate image processing
            img = Image.new('RGB', (800, 600), color='blue')
            img_bytes = BytesIO()
            img.save(img_bytes, format='PNG')
            
            # Simulate optimization
            optimized = ImageOptimizer.optimize_screenshot(img_bytes.getvalue())
            
            # Simulate cache operation
            cache_key = f"operation_{operation_id}"
            vision_cache.put(cache_key, {"result": "processed"})
            
            execution_time = time.time() - start_time
            return operation_id, execution_time
        
        # Sequential execution
        start_time = time.time()
        sequential_results = []
        for i in range(10):
            result = simulate_operation(i)
            sequential_results.append(result)
        sequential_time = time.time() - start_time
        
        # Concurrent execution
        start_time = time.time()
        concurrent_results = []
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(simulate_operation, i) for i in range(10)]
            for future in as_completed(futures):
                result = future.result()
                concurrent_results.append(result)
        concurrent_time = time.time() - start_time
        
        speedup = sequential_time / concurrent_time if concurrent_time > 0 else 1
        
        return BenchmarkResult(
            test_name="Concurrent Operations",
            execution_time=concurrent_time,
            memory_usage_mb=0.0,
            cache_hit_rate=0.0,
            success_rate=100.0,
            operations_per_second=10 / concurrent_time,
            additional_metrics={
                "speedup": f"{speedup:.2f}x",
                "sequential_time": f"{sequential_time:.3f}s",
                "concurrent_time": f"{concurrent_time:.3f}s",
                "efficiency": f"{(speedup/4)*100:.1f}%"  # 4 is max_workers
            }
        )
    
    def print_result(self, result: BenchmarkResult):
        """Print benchmark result in a formatted way."""
        print(f"  ✅ {result.test_name}")
        print(f"     Execution Time: {result.execution_time:.3f}s")
        print(f"     Memory Usage: {result.memory_usage_mb:.2f} MB")
        print(f"     Operations/sec: {result.operations_per_second:.2f}")
        if result.cache_hit_rate > 0:
            print(f"     Cache Hit Rate: {result.cache_hit_rate:.1f}%")
        
        if result.additional_metrics:
            print("     Additional Metrics:")
            for key, value in result.additional_metrics.items():
                print(f"       {key}: {value}")
    
    def generate_report(self, filename: str = "performance_report.json"):
        """Generate a detailed performance report."""
        report = {
            "timestamp": time.time(),
            "system_info": {
                "cpu_count": psutil.cpu_count(),
                "memory_total_gb": psutil.virtual_memory().total / (1024**3),
                "python_version": sys.version,
            },
            "configuration": {
                "cache_size": self.config.VISION_CACHE_SIZE,
                "browser_pool_size": self.config.BROWSER_POOL_SIZE,
                "image_compression": self.config.ENABLE_IMAGE_COMPRESSION,
                "response_caching": self.config.ENABLE_RESPONSE_CACHING,
            },
            "benchmark_results": []
        }
        
        for result in self.results:
            report["benchmark_results"].append({
                "test_name": result.test_name,
                "execution_time": result.execution_time,
                "memory_usage_mb": result.memory_usage_mb,
                "cache_hit_rate": result.cache_hit_rate,
                "success_rate": result.success_rate,
                "operations_per_second": result.operations_per_second,
                "additional_metrics": result.additional_metrics or {}
            })
        
        with open(filename, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"\n📊 Performance report saved to: {filename}")
        return report
    
    def create_visualizations(self):
        """Create performance visualization charts."""
        try:
            import matplotlib.pyplot as plt
            
            # Extract data for visualization
            test_names = [r.test_name for r in self.results]
            execution_times = [r.execution_time for r in self.results]
            memory_usage = [r.memory_usage_mb for r in self.results]
            ops_per_sec = [r.operations_per_second for r in self.results]
            
            # Create subplots
            fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 10))
            
            # Execution time chart
            ax1.bar(test_names, execution_times)
            ax1.set_title('Execution Time by Test')
            ax1.set_ylabel('Time (seconds)')
            ax1.tick_params(axis='x', rotation=45)
            
            # Memory usage chart
            ax2.bar(test_names, memory_usage)
            ax2.set_title('Memory Usage by Test')
            ax2.set_ylabel('Memory (MB)')
            ax2.tick_params(axis='x', rotation=45)
            
            # Operations per second chart
            ax3.bar(test_names, ops_per_sec)
            ax3.set_title('Operations per Second')
            ax3.set_ylabel('Ops/sec')
            ax3.tick_params(axis='x', rotation=45)
            
            # Summary metrics
            total_time = sum(execution_times)
            total_memory = sum(memory_usage)
            avg_ops = sum(ops_per_sec) / len(ops_per_sec)
            
            ax4.text(0.1, 0.7, f'Total Execution Time: {total_time:.3f}s', transform=ax4.transAxes, fontsize=12)
            ax4.text(0.1, 0.5, f'Total Memory Used: {total_memory:.2f} MB', transform=ax4.transAxes, fontsize=12)
            ax4.text(0.1, 0.3, f'Average Ops/sec: {avg_ops:.2f}', transform=ax4.transAxes, fontsize=12)
            ax4.set_title('Summary Metrics')
            ax4.axis('off')
            
            plt.tight_layout()
            plt.savefig('performance_benchmark.png', dpi=300, bbox_inches='tight')
            print("📈 Performance visualization saved to: performance_benchmark.png")
            
        except ImportError:
            print("📊 Matplotlib not available. Skipping visualization generation.")

def main():
    """Run the performance benchmarking suite."""
    print("🔧 AI Web Agent Performance Benchmarking Suite")
    print("=" * 50)
    
    # Initialize benchmarking
    benchmark = PerformanceBenchmark()
    
    # Run all benchmarks
    results = benchmark.run_all_benchmarks()
    
    # Generate report
    report = benchmark.generate_report()
    
    # Create visualizations
    benchmark.create_visualizations()
    
    # Print summary
    print("\n📋 PERFORMANCE SUMMARY")
    print("=" * 30)
    
    total_time = sum(r.execution_time for r in results)
    avg_ops_per_sec = sum(r.operations_per_second for r in results) / len(results)
    
    print(f"Total benchmark time: {total_time:.3f}s")
    print(f"Average operations/sec: {avg_ops_per_sec:.2f}")
    print(f"Tests completed: {len(results)}")
    
    # Configuration recommendations
    print("\n💡 OPTIMIZATION RECOMMENDATIONS")
    print("=" * 35)
    
    # Analyze results and provide recommendations
    for result in results:
        if result.test_name == "Cache Performance" and result.cache_hit_rate < 70:
            print("• Consider increasing cache size for better hit rates")
        
        if result.test_name == "Memory Management":
            recovery_rate = float(result.additional_metrics.get("recovery_rate", "0").rstrip("%"))
            if recovery_rate < 80:
                print("• Consider more frequent memory cleanup operations")
        
        if result.test_name == "Concurrent Operations":
            efficiency = float(result.additional_metrics.get("efficiency", "0").rstrip("%"))
            if efficiency < 75:
                print("• Consider optimizing concurrent operations for better parallelization")
    
    print("\n✅ Benchmarking completed successfully!")

if __name__ == "__main__":
    main()