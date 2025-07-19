"""
Performance-optimized configuration management for the AI Web Agent.
"""
import os
from typing import Dict, Any
from dataclasses import dataclass

@dataclass
class PerformanceConfig:
    """Configuration class for performance optimizations."""
    
    # Vision Model Settings
    VISION_IMAGE_RESIZE_WIDTH: int = 1024
    VISION_IMAGE_RESIZE_HEIGHT: int = 768
    VISION_IMAGE_QUALITY: int = 85  # JPEG quality for compression
    VISION_CACHE_SIZE: int = 100  # Number of vision responses to cache
    
    # Browser Settings
    BROWSER_POOL_SIZE: int = 3  # Maximum concurrent browser instances
    BROWSER_TIMEOUT: int = 30  # Browser operation timeout in seconds
    PAGE_LOAD_TIMEOUT: int = 20  # Page load timeout in seconds
    IMPLICIT_WAIT: int = 10  # Implicit wait time for elements
    
    # API Settings
    API_TIMEOUT: int = 30  # API call timeout in seconds
    API_RETRY_ATTEMPTS: int = 3  # Number of retry attempts
    API_RETRY_DELAY: float = 1.0  # Initial retry delay in seconds
    API_BACKOFF_FACTOR: float = 2.0  # Exponential backoff factor
    
    # Memory Management
    MAX_SCREENSHOT_CACHE: int = 10  # Maximum screenshots to keep in memory
    MAX_CONTEXT_SIZE: int = 1000  # Maximum context entries
    CLEANUP_INTERVAL: int = 300  # Cleanup interval in seconds
    
    # Performance Features
    ENABLE_IMAGE_COMPRESSION: bool = True
    ENABLE_RESPONSE_CACHING: bool = True
    ENABLE_LAZY_LOADING: bool = True
    ENABLE_CONNECTION_POOLING: bool = True
    ENABLE_ASYNC_OPERATIONS: bool = True
    
    # Chrome Options for Performance
    CHROME_OPTIONS: list = None
    
    def __post_init__(self):
        if self.CHROME_OPTIONS is None:
            self.CHROME_OPTIONS = [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
                "--disable-features=TranslateUI",
                "--disable-ipc-flooding-protection",
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-default-apps",
                "--disable-popup-blocking",
                "--disable-extensions",
                "--start-maximized",
                "--enable-automation",
                "--disable-web-security",
                "--allow-running-insecure-content",
                # Memory optimizations
                "--memory-pressure-off",
                "--max_old_space_size=4096",
                # Performance optimizations
                "--aggressive-cache-discard",
                "--enable-precise-memory-info",
                "--enable-memory-coordinator"
            ]

class ConfigManager:
    """Manages configuration and environment settings."""
    
    def __init__(self):
        self.config = PerformanceConfig()
        self._load_environment_overrides()
    
    def _load_environment_overrides(self):
        """Load configuration overrides from environment variables."""
        # Override config values from environment variables
        for key in dir(self.config):
            if not key.startswith('_') and key.isupper():
                env_value = os.getenv(f"AGENT_{key}")
                if env_value:
                    current_value = getattr(self.config, key)
                    if isinstance(current_value, bool):
                        setattr(self.config, key, env_value.lower() in ('true', '1', 'yes'))
                    elif isinstance(current_value, int):
                        setattr(self.config, key, int(env_value))
                    elif isinstance(current_value, float):
                        setattr(self.config, key, float(env_value))
                    else:
                        setattr(self.config, key, env_value)
    
    def get_config(self) -> PerformanceConfig:
        """Get the current configuration."""
        return self.config
    
    def update_config(self, **kwargs):
        """Update configuration values."""
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)

# Global configuration instance
config_manager = ConfigManager()