#!/usr/bin/env python3
"""
Standalone test script for WhiteboxTools functionality
Run this script to verify WhiteboxTools is working properly
"""

import sys
import os
import tempfile
import numpy as np

def test_whitebox_installation():
    """Test WhiteboxTools installation and basic functionality."""
    print("=" * 60)
    print("TESTING WHITEBOXTOOLS INSTALLATION")
    print("=" * 60)
    
    # Test 1: Import WhiteboxTools
    print("\n1. Testing WhiteboxTools import...")
    try:
        import whitebox
        print("✓ WhiteboxTools imported successfully")
    except ImportError as e:
        print(f"✗ Failed to import WhiteboxTools: {e}")
        return False
    
    # Test 2: Initialize WhiteboxTools
    print("\n2. Initializing WhiteboxTools...")
    try:
        wbt = whitebox.WhiteboxTools()
        print("✓ WhiteboxTools initialized successfully")
        print(f"  - Executable path: {wbt.exe_path}")
        print(f"  - Working directory: {wbt.work_dir}")
    except Exception as e:
        print(f"✗ Failed to initialize WhiteboxTools: {e}")
        return False
    
    # Test 3: Check executable exists
    print("\n3. Checking executable...")
    if wbt.exe_path and os.path.exists(wbt.exe_path):
        print(f"✓ Executable found at: {wbt.exe_path}")
        # Check if executable is actually executable
        if os.access(wbt.exe_path, os.X_OK):
            print("✓ Executable has execute permissions")
        else:
            print("✗ Executable lacks execute permissions")
            return False
    else:
        print(f"✗ Executable not found at: {wbt.exe_path}")
        return False
    
    # Test 4: Get version
    print("\n4. Getting WhiteboxTools version...")
    try:
        version = wbt.version()
        print(f"✓ WhiteboxTools version: {version}")
    except Exception as e:
        print(f"✗ Failed to get version: {e}")
        return False
    
    # Test 5: List available tools
    print("\n5. Checking available tools...")
    try:
        tools = wbt.list_tools()
        print(f"✓ Found {len(tools)} available tools")
        
        # Check for essential tools
        essential_tools = ['slope', 'aspect', 'd8_pointer', 'd8_flow_accumulation']
        missing_tools = []
        
        for tool in essential_tools:
            if hasattr(wbt, tool):
                print(f"  ✓ {tool}")
            else:
                print(f"  ✗ {tool} (missing)")
                missing_tools.append(tool)
        
        if missing_tools:
            print(f"✗ Missing essential tools: {missing_tools}")
            return False
            
    except Exception as e:
        print(f"✗ Failed to list tools: {e}")
        return False
    
    # Test 6: Test rasterio dependency
    print("\n6. Testing rasterio dependency...")
    try:
        import rasterio
        from rasterio.transform import from_bounds
        print("✓ Rasterio imported successfully")
    except ImportError as e:
        print(f"✗ Failed to import rasterio: {e}")
        return False
    
    # Test 7: Create test data and run actual WhiteboxTools operations
    print("\n7. Testing actual WhiteboxTools operations...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            # Create synthetic DEM data
            width, height = 50, 50
            bounds = (-1, -1, 1, 1)
            transform = from_bounds(*bounds, width, height)
            
            # Create a simple hill
            x = np.linspace(-1, 1, width)
            y = np.linspace(-1, 1, height)
            X, Y = np.meshgrid(x, y)
            elevation = 100 * np.exp(-(X**2 + Y**2))
            
            # Write test DEM
            dem_path = os.path.join(temp_dir, "test_dem.tif")
            slope_path = os.path.join(temp_dir, "test_slope.tif")
            
            with rasterio.open(
                dem_path, 'w',
                driver='GTiff',
                height=height, width=width, count=1,
                dtype=rasterio.float32,
                crs='EPSG:4326',
                transform=transform
            ) as dst:
                dst.write(elevation.astype(rasterio.float32), 1)
            
            print(f"  ✓ Created test DEM: {dem_path}")
            
            # Test slope calculation
            print("  - Testing slope calculation...")
            result = wbt.slope(dem_path, slope_path, units="degrees")
            
            if result == 0 and os.path.exists(slope_path):
                print("  ✓ Slope calculation successful")
                
                # Verify the output contains valid data
                with rasterio.open(slope_path) as src:
                    slope_data = src.read(1)
                    if not np.all(np.isnan(slope_data)):
                        print(f"  ✓ Slope data is valid (min: {np.nanmin(slope_data):.2f}°, max: {np.nanmax(slope_data):.2f}°)")
                    else:
                        print("  ✗ Slope data contains only NaN values")
                        return False
            else:
                print(f"  ✗ Slope calculation failed (return code: {result})")
                return False
            
            # Test aspect calculation
            print("  - Testing aspect calculation...")
            aspect_path = os.path.join(temp_dir, "test_aspect.tif")
            result = wbt.aspect(dem_path, aspect_path)
            
            if result == 0 and os.path.exists(aspect_path):
                print("  ✓ Aspect calculation successful")
            else:
                print(f"  ✗ Aspect calculation failed (return code: {result})")
                return False
                
        except Exception as e:
            print(f"  ✗ Error during operations test: {e}")
            return False
    
    print("\n" + "=" * 60)
    print("✓ ALL TESTS PASSED - WHITEBOXTOOLS IS WORKING CORRECTLY!")
    print("=" * 60)
    return True


def test_environment():
    """Test the overall environment setup."""
    print("\n" + "=" * 60)
    print("ENVIRONMENT INFORMATION")
    print("=" * 60)
    
    print(f"Python version: {sys.version}")
    print(f"Python executable: {sys.executable}")
    print(f"Current working directory: {os.getcwd()}")
    
    # Check for environment variables
    env_vars = ['OPENTOPO_API_KEY', 'GEMINI_API_KEY']
    print("\nEnvironment variables:")
    for var in env_vars:
        value = os.environ.get(var, 'Not set')
        if value != 'Not set':
            print(f"  {var}: {'*' * min(len(value), 20)} (length: {len(value)})")
        else:
            print(f"  {var}: Not set")


if __name__ == "__main__":
    print("WhiteboxTools Installation Test")
    print("This script will test if WhiteboxTools is properly installed and functional.")
    
    test_environment()
    
    if test_whitebox_installation():
        sys.exit(0)  # Success
    else:
        print("\n" + "!" * 60)
        print("TESTS FAILED - WHITEBOXTOOLS IS NOT WORKING PROPERLY!")
        print("!" * 60)
        sys.exit(1)  # Failure