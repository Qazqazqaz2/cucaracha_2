#!/usr/bin/env python3
"""
Script to install TON libraries for the crypto exchange bot
"""

import subprocess
import sys

def install_package(package):
    """Install a Python package using pip"""
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])
        print(f"Successfully installed {package}")
    except subprocess.CalledProcessError as e:
        print(f"Failed to install {package}: {e}")
        return False
    return True

def main():
    """Main installation function"""
    print("Installing TON libraries for crypto exchange bot...")
    
    # List of packages to install
    packages = [
        "pytonlib>=0.0.19"
    ]
    
    # Install each package
    for package in packages:
        print(f"Installing {package}...")
        if not install_package(package):
            print(f"Failed to install {package}")
            sys.exit(1)
    
    print("All TON libraries installed successfully!")

if __name__ == "__main__":
    main()