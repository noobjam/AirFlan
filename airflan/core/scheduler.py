"""
AirFlan Core Module - Workflow Scheduler

This module handles dependency resolution and execution planning
for workflow tasks using topological sorting.
"""

from typing import Dict, List, Set
from .task import Task


class WorkflowScheduler:
    """
    Scheduler for resolving task dependencies and building execution plan
    
    The scheduler analyzes the task dependency graph (DAG) and produces
    execution levels where tasks in the same level can run in parallel.
    """
    
    def __init__(self, tasks: Dict[str, Task]):
        """
        Initialize scheduler with tasks
        
        Args:
            tasks: Dictionary mapping task names to Task objects
        """
        self.tasks = tasks
    
    def build_execution_graph(self) -> List[Set[str]]:
        """
        Build execution graph using topological sort
        
        Returns a list of sets, where each set contains task names
        that can be executed in parallel (same dependency level).
        
        Returns:
            List of sets of task names, ordered by dependency level
            
        Raises:
            ValueError: If circular dependency is detected
        """
        # Calculate in-degree for each task
        in_degree = {
            name: len(task.depends_on) 
            for name, task in self.tasks.items()
        }
        
        levels: List[Set[str]] = []
        remaining = set(self.tasks.keys())
        
        while remaining:
            # Find tasks with no unsatisfied dependencies
            level = {
                name for name in remaining
                if all(dep not in remaining for dep in self.tasks[name].depends_on)
            }
            
            if not level:
                # No tasks can be executed - circular dependency
                raise ValueError(
                    f"Circular dependency detected in tasks: {remaining}"
                )
            
            levels.append(level)
            remaining -= level
        
        return levels
    
    def validate_dependencies(self) -> List[str]:
        """
        Validate that all task dependencies exist
        
        Returns:
            List of error messages (empty if valid)
        """
        errors = []
        
        for task_name, task in self.tasks.items():
            for dep in task.depends_on:
                if dep not in self.tasks:
                    errors.append(
                        f"Task '{task_name}' depends on non-existent task '{dep}'"
                    )
        
        return errors
    
    def get_execution_order(self) -> List[str]:
        """
        Get flat list of task names in execution order
        
        Tasks within same level are sorted by priority (desc) then order (asc)
        
        Returns:
            Ordered list of task names
        """
        levels = self.build_execution_graph()
        execution_order = []
        
        for level in levels:
            # Sort tasks within level by priority (high first) and order (low first)
            sorted_tasks = sorted(
                level,
                key=lambda name: (-self.tasks[name].priority, self.tasks[name].order)
            )
            execution_order.extend(sorted_tasks)
        
        return execution_order
    
    def get_task_depth(self, task_name: str) -> int:
        """
        Get the dependency depth of a task (level in execution graph)
        
        Args:
            task_name: Name of task
            
        Returns:
            Depth level (0 for tasks with no dependencies)
        """
        levels = self.build_execution_graph()
        
        for depth, level in enumerate(levels):
            if task_name in level:
                return depth
        
        return -1  # Task not found
    
    def get_dependencies_recursive(self, task_name: str) -> Set[str]:
        """
        Get all dependencies (transitive) for a task
        
        Args:
            task_name: Name of task
            
        Returns:
            Set of all task names this task depends on (directly or indirectly)
        """
        if task_name not in self.tasks:
            return set()
        
        all_deps = set()
        to_process = list(self.tasks[task_name].depends_on)
        
        while to_process:
            dep = to_process.pop()
            if dep not in all_deps:
                all_deps.add(dep)
                if dep in self.tasks:
                    to_process.extend(self.tasks[dep].depends_on)
        
        return all_deps
