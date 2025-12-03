#!/usr/bin/env python3
"""
Test script to verify critical bug fixes in AirFlan
Tests:
1. Tasks without context parameter execute correctly (indentation fix)
2. Parallel execution with thread safety
3. Timeout handling (no duplicate handlers)
4. All code paths return TaskResult
"""

import time
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

# Import from new modular package
from airflan import WorkflowOrchestrator, WorkflowContext, TaskStatus


def test_1_task_without_context():
    """Test that tasks without context parameter execute (Bug #1 fix)"""
    print("\n" + "="*70)
    print("TEST 1: Task without context parameter")
    print("="*70)
    
    wf = WorkflowOrchestrator(name="test_no_context", enable_cache=False)
    
    @wf.task(name="task_no_context")
    def simple_task():
        """This task doesn't accept context - should still execute"""
        print("  → Executing task without context parameter")
        return "Success without context!"
    
    results = wf.run(parallel=False, enable_ui=False)
    
    assert "task_no_context" in results, "Task not found in results"
    assert results["task_no_context"].status == TaskStatus.COMPLETED, \
        f"Expected COMPLETED, got {results['task_no_context'].status}"
    assert results["task_no_context"].output == "Success without context!", \
        "Task output incorrect"
    
    print("✓ TEST 1 PASSED: Tasks without context execute correctly")
    return True


def test_2_task_with_context():
    """Test that tasks WITH context parameter still work"""
    print("\n" + "="*70)
    print("TEST 2: Task with context parameter")
    print("="*70)
    
    wf = WorkflowOrchestrator(name="test_with_context", enable_cache=False)
    
    @wf.task(name="task_with_context")
    def context_task(context: WorkflowContext):
        """This task uses context - should execute"""
        print("  → Executing task with context parameter")
        context.set("test_key", "test_value")
        return "Success with context!"
    
    results = wf.run(parallel=False, enable_ui=False)
    
    assert results["task_with_context"].status == TaskStatus.COMPLETED
    assert wf.context.get("test_key") == "test_value"
    
    print("✓ TEST 2 PASSED: Tasks with context execute correctly")
    return True


def test_3_parallel_execution_thread_safety():
    """Test parallel execution with thread safety (Bug #3 fix)"""
    print("\n" + "="*70)
    print("TEST 3: Parallel execution with thread safety")
    print("="*70)
    
    wf = WorkflowOrchestrator(name="test_parallel", max_parallel=5, enable_cache=False)
    
    # Create 10 parallel tasks that execute simultaneously
    for i in range(10):
        @wf.task(name=f"parallel_task_{i}")
        def parallel_task(task_id=i):
            print(f"  → Task {task_id} running")
            time.sleep(0.1)  # Simulate work
            return f"Result from task {task_id}"
        
    results = wf.run(parallel=True, enable_ui=False)
    
    # Verify all tasks completed
    assert len(results) == 10, f"Expected 10 results, got {len(results)}"
    for i in range(10):
        task_name = f"parallel_task_{i}"
        assert task_name in results, f"Missing task: {task_name}"
        assert results[task_name].status == TaskStatus.COMPLETED, \
            f"Task {task_name} not completed: {results[task_name].status}"
    
    print("✓ TEST 3 PASSED: Parallel execution is thread-safe")
    return True


def test_4_timeout_handling():
    """Test timeout handling (Bug #2 fix - no duplicate handlers)"""
    print("\n" + "="*70)
    print("TEST 4: Timeout handling")
    print("="*70)
    
    wf = WorkflowOrchestrator(name="test_timeout", enable_cache=False)
    
    @wf.task(name="timeout_task", timeout=0.5)
    def slow_task():
        """This task will timeout"""
        print("  → Starting slow task...")
        time.sleep(2)  # Exceeds 0.5s timeout
        return "Should not reach here"
    
    results = wf.run(parallel=False, enable_ui=False)
    
    assert results["timeout_task"].status == TaskStatus.TIMEOUT, \
        f"Expected TIMEOUT, got {results['timeout_task'].status}"
    
    print("✓ TEST 4 PASSED: Timeout handling works correctly")
    return True


def test_5_error_handling():
    """Test that failed tasks return TaskResult (Bug #4 fix)"""
    print("\n" + "="*70)
    print("TEST 5: Error handling and TaskResult return")
    print("="*70)
    
    wf = WorkflowOrchestrator(name="test_errors", enable_cache=False)
    
    @wf.task(name="failing_task", skip_on_failure=True)
    def failing_task():
        """This task will fail"""
        print("  → Executing failing task...")
        raise ValueError("Intentional error for testing")
    
    results = wf.run(parallel=False, enable_ui=False)
    
    assert results["failing_task"].status == TaskStatus.FAILED
    assert results["failing_task"].error is not None
    assert isinstance(results["failing_task"].error, ValueError)
    
    print("✓ TEST 5 PASSED: Failed tasks return proper TaskResult")
    return True


def test_6_dependency_chain():
    """Test dependency chain with mixed context usage"""
    print("\n" + "="*70)
    print("TEST 6: Dependency chain with mixed context usage")
    print("="*70)
    
    wf = WorkflowOrchestrator(name="test_deps", enable_cache=False)
    
    @wf.task(name="task_a")
    def task_a():
        print("  → Task A (no context)")
        return "A"
    
    @wf.task(name="task_b", depends_on=["task_a"])
    def task_b(context: WorkflowContext):
        print("  → Task B (with context)")
        result_a = context.get("result_task_a")
        return f"B-{result_a}"
    
    @wf.task(name="task_c", depends_on=["task_b"])
    def task_c():
        print("  → Task C (no context)")
        return "C"
    
    results = wf.run(parallel=False, enable_ui=False)
    
    assert all(results[name].status == TaskStatus.COMPLETED 
               for name in ["task_a", "task_b", "task_c"])
    assert results["task_b"].output == "B-A"
    
    print("✓ TEST 6 PASSED: Dependency chain works with mixed context usage")
    return True


def run_all_tests():
    """Run all verification tests"""
    print("\n" + "#"*70)
    print("# AIRFLAN BUG FIX VERIFICATION SUITE")
    print("#"*70)
    
    tests = [
        test_1_task_without_context,
        test_2_task_with_context,
        test_3_parallel_execution_thread_safety,
        test_4_timeout_handling,
        test_5_error_handling,
        test_6_dependency_chain,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            failed += 1
            print(f"✗ {test.__name__} FAILED: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "="*70)
    print(f"RESULTS: {passed}/{len(tests)} tests passed")
    if failed == 0:
        print("✓ ALL TESTS PASSED - Bug fixes verified!")
    else:
        print(f"✗ {failed} tests failed - review errors above")
    print("="*70 + "\n")
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
