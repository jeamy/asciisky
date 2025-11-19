
import sys
import os
# Add the api directory to the path to allow for imports
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from api.computation import compute_sunpath_year

def run_test():
    """
    Directly tests the compute_sunpath_year function with the problematic
    coordinates to get a traceback.
    """
    print("Starting sunpath computation test...")
    try:
        result = compute_sunpath_year(
            lat=60.1666204,
            lon=24.9435408,
            elevation=0,
            year=2025
        )
        print("Test completed successfully.")
        # print(result)  # Optionally print the full result
    except Exception as e:
        print("An error occurred during the test.")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_test()
