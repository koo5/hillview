#!/usr/bin/env python3
"""
Test runner for all hidden content functionality tests.

Runs all hidden content test suites in sequence and provides a summary report.
"""

import asyncio
import subprocess
import sys
import os
import requests
from datetime import datetime

# Test modules to run
TEST_MODULES = [
    "test_hidden_photos",
    "test_hidden_users", 
    "test_content_filtering",
    "test_hillview_filtering",
    "test_hidden_db_operations"
]

class HiddenContentTestRunner:
    """Orchestrates running all hidden content tests."""
    
    def __init__(self):
        self.results = {}
        self.start_time = None
        self.end_time = None
    
    def run_test_module(self, module_name):
        """Run a single test module and return success status."""
        print(f"\n{'='*60}")
        print(f"RUNNING: {module_name}")
        print(f"{'='*60}")
        
        try:
            # Run the test module as a subprocess
            result = subprocess.run(
                [sys.executable, f"{module_name}.py"],
                cwd=os.path.dirname(__file__),
                capture_output=False,  # Let output show in real-time
                text=True,
                timeout=300  # 5 minute timeout per test module
            )
            
            success = result.returncode == 0
            self.results[module_name] = {
                'success': success,
                'return_code': result.returncode
            }
            
            if success:
                print(f"\n✅ {module_name} PASSED")
            else:
                print(f"\n❌ {module_name} FAILED (exit code: {result.returncode})")
            
            return success
            
        except subprocess.TimeoutExpired:
            print(f"\n⏰ {module_name} TIMED OUT")
            self.results[module_name] = {
                'success': False,
                'return_code': 'TIMEOUT'
            }
            return False
            
        except Exception as e:
            print(f"\n💥 {module_name} ERROR: {e}")
            self.results[module_name] = {
                'success': False,
                'return_code': f'ERROR: {e}'
            }
            return False
    
    def run_all_tests(self):
        """Run all hidden content test modules."""
        self.start_time = datetime.now()
        
        print("🚀 HILLVIEW HIDDEN CONTENT TEST SUITE")
        print("="*60)
        print(f"Start time: {self.start_time}")
        print(f"Test modules: {', '.join(TEST_MODULES)}")
        print("="*60)
        
        passed = 0
        failed = 0
        
        for module in TEST_MODULES:
            if self.run_test_module(module):
                passed += 1
            else:
                failed += 1
        
        self.end_time = datetime.now()
        duration = self.end_time - self.start_time
        
        # Print final summary
        print("\n" + "="*60)
        print("🏁 FINAL RESULTS")
        print("="*60)
        print(f"Total modules: {len(TEST_MODULES)}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        print(f"Duration: {duration}")
        print(f"Success rate: {(passed/len(TEST_MODULES)*100):.1f}%")
        
        print("\nDetailed Results:")
        for module, result in self.results.items():
            status = "✅ PASS" if result['success'] else f"❌ FAIL ({result['return_code']})"
            print(f"  {module:25} {status}")
        
        if failed == 0:
            print("\n🎉 ALL HIDDEN CONTENT TESTS PASSED!")
            print("The hidden content functionality is working correctly.")
            return True
        else:
            print(f"\n❌ {failed} TEST MODULE(S) FAILED!")
            print("Please review the failed tests and fix any issues.")
            return False
    
    def run_specific_test(self, module_name):
        """Run a specific test module."""
        if module_name not in TEST_MODULES:
            print(f"❌ Unknown test module: {module_name}")
            print(f"Available modules: {', '.join(TEST_MODULES)}")
            return False
        
        print(f"🎯 Running specific test: {module_name}")
        return self.run_test_module(module_name)


def print_usage():
    """Print usage information."""
    print("Hidden Content Test Runner")
    print("="*40)
    print("Usage:")
    print("  python run_hidden_tests.py              # Run all tests")
    print("  python run_hidden_tests.py <module>     # Run specific test")
    print()
    print("Available test modules:")
    for module in TEST_MODULES:
        print(f"  - {module}")
    print()
    print("Examples:")
    print("  python run_hidden_tests.py")
    print("  python run_hidden_tests.py test_hidden_photos")


def main():
    """Main entry point."""
    runner = HiddenContentTestRunner()
    
    if len(sys.argv) == 1:
        # Run all tests
        success = runner.run_all_tests()
        return 0 if success else 1
    
    elif len(sys.argv) == 2:
        if sys.argv[1] in ['-h', '--help', 'help']:
            print_usage()
            return 0
        else:
            # Run specific test
            module_name = sys.argv[1]
            success = runner.run_specific_test(module_name)
            return 0 if success else 1
    
    else:
        print("❌ Invalid arguments")
        print_usage()
        return 1


if __name__ == "__main__":
    sys.exit(main())