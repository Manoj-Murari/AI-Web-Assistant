#!/usr/bin/env python3
"""
Setup script for AI Web Agent Performance Optimizations
"""
import os
import sys
import subprocess
import shutil
from pathlib import Path

def run_command(cmd, description):
    """Run a command and handle errors."""
    print(f"🔧 {description}...")
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error in {description}: {e}")
        print(f"Output: {e.stdout}")
        print(f"Error: {e.stderr}")
        return False

def check_python_version():
    """Check if Python version is compatible."""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print("❌ Python 3.8 or higher is required")
        return False
    print(f"✅ Python {version.major}.{version.minor}.{version.micro} detected")
    return True

def install_dependencies():
    """Install required dependencies."""
    print("📦 Installing dependencies...")
    
    # Check if requirements.txt exists
    if not os.path.exists("requirements.txt"):
        print("❌ requirements.txt not found")
        return False
    
    # Install requirements
    return run_command(
        f"{sys.executable} -m pip install -r requirements.txt",
        "Installing Python packages"
    )

def setup_api_key():
    """Setup API key configuration."""
    print("🔑 Setting up API key configuration...")
    
    # Check if apikey.py already exists
    if os.path.exists("apikey.py"):
        print("⚠️  apikey.py already exists. Skipping...")
        return True
    
    # Copy template
    if os.path.exists("apikey_template.py"):
        try:
            shutil.copy("apikey_template.py", "apikey.py")
            print("✅ Created apikey.py from template")
            print("📝 Please edit apikey.py and add your Gemini API key")
            print("   Get your key from: https://aistudio.google.com/app/apikey")
            return True
        except Exception as e:
            print(f"❌ Error copying template: {e}")
            return False
    else:
        print("❌ apikey_template.py not found")
        return False

def check_chrome_driver():
    """Check if Chrome and ChromeDriver are available."""
    print("🌐 Checking Chrome browser availability...")
    
    # Check if Chrome is installed
    chrome_paths = [
        "/usr/bin/google-chrome",
        "/usr/bin/chromium-browser",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
        "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe"
    ]
    
    chrome_found = False
    for path in chrome_paths:
        if os.path.exists(path):
            print(f"✅ Chrome found at: {path}")
            chrome_found = True
            break
    
    if not chrome_found:
        print("⚠️  Chrome browser not found in standard locations")
        print("   Please install Google Chrome for full functionality")
    
    return chrome_found

def create_directories():
    """Create necessary directories."""
    print("📁 Creating directories...")
    
    directories = ["logs", "cache", "screenshots"]
    
    for directory in directories:
        try:
            Path(directory).mkdir(exist_ok=True)
            print(f"✅ Created directory: {directory}")
        except Exception as e:
            print(f"❌ Error creating directory {directory}: {e}")
            return False
    
    return True

def run_basic_test():
    """Run a basic test to verify setup."""
    print("🧪 Running basic functionality test...")
    
    try:
        # Test imports
        import google.generativeai
        print("✅ Google Generative AI imported successfully")
        
        import selenium
        print("✅ Selenium imported successfully")
        
        from PIL import Image
        print("✅ PIL imported successfully")
        
        import psutil
        print("✅ psutil imported successfully")
        
        # Test local imports
        from config import config_manager
        print("✅ Configuration module imported successfully")
        
        from performance_utils import vision_cache, performance_monitor
        print("✅ Performance utilities imported successfully")
        
        print("✅ All basic tests passed!")
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("   Try running: pip install -r requirements.txt")
        return False
    except Exception as e:
        print(f"❌ Test error: {e}")
        return False

def show_next_steps():
    """Show next steps to the user."""
    print("\n🎉 Setup completed successfully!")
    print("\n📋 Next Steps:")
    print("1. Edit apikey.py and add your Gemini API key")
    print("2. Run the optimized application:")
    print("   python main_optimized.py")
    print("3. Or run performance benchmarks:")
    print("   python performance_benchmark.py")
    print("4. Type 'stats' in the application to see performance metrics")
    print("\n📖 For more information, see PERFORMANCE_OPTIMIZATION_README.md")

def main():
    """Main setup function."""
    print("🚀 AI Web Agent Performance Optimization Setup")
    print("=" * 50)
    
    # Track setup success
    setup_steps = [
        ("Python Version Check", check_python_version),
        ("Install Dependencies", install_dependencies),
        ("Setup API Key", setup_api_key),
        ("Check Chrome Driver", check_chrome_driver),
        ("Create Directories", create_directories),
        ("Run Basic Test", run_basic_test),
    ]
    
    failed_steps = []
    
    for step_name, step_function in setup_steps:
        print(f"\n{'='*20} {step_name} {'='*20}")
        if not step_function():
            failed_steps.append(step_name)
    
    print(f"\n{'='*50}")
    
    if failed_steps:
        print("⚠️  Setup completed with some issues:")
        for step in failed_steps:
            print(f"   ❌ {step}")
        print("\nPlease resolve the above issues before proceeding.")
    else:
        show_next_steps()
    
    return len(failed_steps) == 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)