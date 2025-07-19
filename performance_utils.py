"""
Performance utilities for the AI Web Agent.
Includes caching, connection pooling, and optimization helpers.
"""
import asyncio
import hashlib
import time
import threading
import psutil
import gc
from typing import Dict, Any, Optional, Callable, List
from functools import wraps, lru_cache
from io import BytesIO
from PIL import Image
import json
from collections import OrderedDict
from threading import Lock
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import google.generativeai as genai
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service as ChromeService

from config import config_manager

class LRUCache:
    """Thread-safe LRU Cache implementation for vision responses."""
    
    def __init__(self, maxsize: int = 100):
        self.maxsize = maxsize
        self.cache = OrderedDict()
        self.lock = Lock()
    
    def get(self, key: str) -> Optional[Any]:
        with self.lock:
            if key in self.cache:
                # Move to end (most recently used)
                self.cache.move_to_end(key)
                return self.cache[key]
        return None
    
    def put(self, key: str, value: Any) -> None:
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
            else:
                self.cache[key] = value
                if len(self.cache) > self.maxsize:
                    # Remove least recently used
                    self.cache.popitem(last=False)
            self.cache[key] = value
    
    def clear(self) -> None:
        with self.lock:
            self.cache.clear()
    
    def size(self) -> int:
        with self.lock:
            return len(self.cache)

class PerformanceMonitor:
    """Monitor and track performance metrics."""
    
    def __init__(self):
        self.metrics = {
            'api_calls': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'browser_operations': 0,
            'memory_usage': [],
            'response_times': []
        }
        self.lock = Lock()
    
    def record_api_call(self, response_time: float):
        with self.lock:
            self.metrics['api_calls'] += 1
            self.metrics['response_times'].append(response_time)
    
    def record_cache_hit(self):
        with self.lock:
            self.metrics['cache_hits'] += 1
    
    def record_cache_miss(self):
        with self.lock:
            self.metrics['cache_misses'] += 1
    
    def record_browser_operation(self):
        with self.lock:
            self.metrics['browser_operations'] += 1
    
    def record_memory_usage(self):
        with self.lock:
            memory_info = psutil.virtual_memory()
            self.metrics['memory_usage'].append({
                'timestamp': time.time(),
                'used_percent': memory_info.percent,
                'available_gb': memory_info.available / (1024**3)
            })
    
    def get_stats(self) -> Dict[str, Any]:
        with self.lock:
            cache_total = self.metrics['cache_hits'] + self.metrics['cache_misses']
            cache_hit_rate = (self.metrics['cache_hits'] / cache_total * 100) if cache_total > 0 else 0
            
            avg_response_time = (
                sum(self.metrics['response_times']) / len(self.metrics['response_times'])
                if self.metrics['response_times'] else 0
            )
            
            return {
                'api_calls': self.metrics['api_calls'],
                'cache_hit_rate': f"{cache_hit_rate:.2f}%",
                'avg_response_time': f"{avg_response_time:.2f}s",
                'browser_operations': self.metrics['browser_operations'],
                'current_memory_usage': f"{psutil.virtual_memory().percent:.1f}%"
            }

class BrowserPool:
    """Manages a pool of browser instances for better resource utilization."""
    
    def __init__(self, pool_size: int = 3):
        self.pool_size = pool_size
        self.available_browsers = []
        self.in_use_browsers = set()
        self.lock = Lock()
        self.config = config_manager.get_config()
    
    def _create_browser(self) -> webdriver.Chrome:
        """Create a new optimized browser instance."""
        chrome_options = Options()
        for option in self.config.CHROME_OPTIONS:
            chrome_options.add_argument(option)
        
        # Additional performance optimizations
        chrome_options.add_experimental_option("useAutomationExtension", False)
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Use webdriver-manager for automatic driver management
        service = ChromeService(ChromeDriverManager().install())
        
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.implicitly_wait(self.config.IMPLICIT_WAIT)
        driver.set_page_load_timeout(self.config.PAGE_LOAD_TIMEOUT)
        
        return driver
    
    def get_browser(self) -> webdriver.Chrome:
        """Get an available browser from the pool."""
        with self.lock:
            if self.available_browsers:
                browser = self.available_browsers.pop()
                self.in_use_browsers.add(browser)
                return browser
            
            if len(self.in_use_browsers) < self.pool_size:
                browser = self._create_browser()
                self.in_use_browsers.add(browser)
                return browser
        
        # If pool is full, create a temporary browser
        return self._create_browser()
    
    def return_browser(self, browser: webdriver.Chrome):
        """Return a browser to the pool."""
        with self.lock:
            if browser in self.in_use_browsers:
                self.in_use_browsers.remove(browser)
                if len(self.available_browsers) < self.pool_size:
                    self.available_browsers.append(browser)
                else:
                    browser.quit()
    
    def cleanup(self):
        """Clean up all browsers in the pool."""
        with self.lock:
            for browser in self.available_browsers + list(self.in_use_browsers):
                try:
                    browser.quit()
                except:
                    pass
            self.available_browsers.clear()
            self.in_use_browsers.clear()

class ImageOptimizer:
    """Optimizes images for faster processing and reduced memory usage."""
    
    @staticmethod
    def optimize_screenshot(image_bytes: bytes, max_width: int = 1024, max_height: int = 768, quality: int = 85) -> bytes:
        """Optimize screenshot for vision API processing."""
        img = Image.open(BytesIO(image_bytes))
        
        # Resize if necessary
        if img.width > max_width or img.height > max_height:
            img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
        
        # Convert to RGB if necessary
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Compress
        output = BytesIO()
        img.save(output, format='JPEG', quality=quality, optimize=True)
        return output.getvalue()
    
    @staticmethod
    def generate_image_hash(image_bytes: bytes) -> str:
        """Generate a hash for image deduplication."""
        return hashlib.md5(image_bytes).hexdigest()

def retry_with_backoff(func: Callable) -> Callable:
    """Decorator for API calls with exponential backoff retry."""
    config = config_manager.get_config()
    
    @retry(
        stop=stop_after_attempt(config.API_RETRY_ATTEMPTS),
        wait=wait_exponential(multiplier=config.API_RETRY_DELAY, max=60),
        retry=retry_if_exception_type((ConnectionError, TimeoutError))
    )
    @wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    
    return wrapper

def timed_operation(operation_name: str = "operation"):
    """Decorator to time operations and record metrics."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                performance_monitor.record_api_call(duration)
                print(f"DEBUG: {operation_name} took {duration:.2f}s")
        return wrapper
    return decorator

class MemoryManager:
    """Manages memory usage and performs cleanup operations."""
    
    def __init__(self):
        self.last_cleanup = time.time()
        self.config = config_manager.get_config()
    
    def should_cleanup(self) -> bool:
        """Check if cleanup should be performed."""
        return time.time() - self.last_cleanup > self.config.CLEANUP_INTERVAL
    
    def perform_cleanup(self):
        """Perform memory cleanup operations."""
        if self.should_cleanup():
            gc.collect()
            self.last_cleanup = time.time()
            performance_monitor.record_memory_usage()
            print("DEBUG: Performed memory cleanup")
    
    def get_memory_usage(self) -> Dict[str, float]:
        """Get current memory usage statistics."""
        memory = psutil.virtual_memory()
        return {
            'total_gb': memory.total / (1024**3),
            'available_gb': memory.available / (1024**3),
            'used_percent': memory.percent,
            'free_gb': memory.free / (1024**3)
        }

# Global instances
vision_cache = LRUCache(maxsize=config_manager.get_config().VISION_CACHE_SIZE)
performance_monitor = PerformanceMonitor()
browser_pool = BrowserPool(config_manager.get_config().BROWSER_POOL_SIZE)
memory_manager = MemoryManager()

# Utility functions
def cache_key_from_prompt_and_image(prompt: str, image_bytes: bytes) -> str:
    """Generate cache key from prompt and image."""
    image_hash = ImageOptimizer.generate_image_hash(image_bytes)
    prompt_hash = hashlib.md5(prompt.encode()).hexdigest()
    return f"{prompt_hash}_{image_hash}"

def cleanup_on_exit():
    """Cleanup function to be called on exit."""
    browser_pool.cleanup()
    vision_cache.clear()
    print("DEBUG: Cleanup completed")