"""
PSDL Batch Runtime - Abstract interface for batch execution (RFC-0008).

Provides vendor-neutral base classes for batch scenario execution.
SQL-specific runtimes extend SQLBatchRuntime with dialect-specific
rendering.

Usage:
    from psdl.runtimes.batch import BatchRuntime, SQLBatchRuntime, BatchResult
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional, Set


@dataclass
class BatchResult:
    """Result from batch scenario execution."""

    patient_id: str
    triggered: bool
    triggered_logic: List[str] = field(default_factory=list)
    trend_values: Dict[str, float] = field(default_factory=dict)
    logic_results: Dict[str, bool] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class BatchRuntime(ABC):
    """Abstract interface for batch scenario execution (RFC-0008).

    Defines the contract for runtimes that execute scenarios
    over cohorts of patients.
    """

    @abstractmethod
    def compile(self, scenario: Any, dataset_spec: Any = None) -> Any:
        """Compile a scenario to backend-specific form.

        Args:
            scenario: Parsed PSDL scenario
            dataset_spec: Optional DatasetSpec for binding resolution

        Returns:
            Backend-specific compiled representation
        """
        pass

    @abstractmethod
    def execute(
        self,
        scenario: Any,
        dataset_spec: Any = None,
        patient_ids: Optional[List[str]] = None,
    ) -> Iterator[BatchResult]:
        """Execute a scenario and yield results.

        Args:
            scenario: Parsed PSDL scenario
            dataset_spec: Optional DatasetSpec for binding resolution
            patient_ids: Optional patient ID filter

        Yields:
            BatchResult for each patient
        """
        pass

    @property
    @abstractmethod
    def capabilities(self) -> Set[str]:
        """Declare runtime capabilities.

        Known capabilities:
        - "sql": generates SQL queries
        - "parallel": supports parallel execution
        - "streaming": supports streaming mode
        """
        pass


class SQLBatchRuntime(BatchRuntime):
    """Base class for SQL-specific batch runtimes (RFC-0008).

    Extends BatchRuntime with SQL dialect-specific rendering methods.
    Concrete implementations (e.g., PostgreSQL, SQL Server) override
    the rendering methods.
    """

    @abstractmethod
    def get_sql_dialect(self) -> str:
        """Return the SQL dialect name (e.g., 'postgresql', 'mssql')."""
        pass

    @abstractmethod
    def render_interval(self, seconds: int) -> str:
        """Render a time interval in dialect-specific SQL.

        Args:
            seconds: Duration in seconds

        Returns:
            SQL interval expression (e.g., "INTERVAL '3600 seconds'")
        """
        pass

    def render_operator_cte(
        self,
        operator: str,
        trend_name: str,
        binding: Any,
        window_seconds: int,
    ) -> str:
        """Render a CTE for a temporal operator.

        Default implementation raises NotImplementedError.
        Subclasses should override for their specific dialect.

        Args:
            operator: Operator name (e.g., "delta", "slope")
            trend_name: Name for the CTE
            binding: Resolved binding with table/field info
            window_seconds: Window duration in seconds

        Returns:
            SQL CTE string
        """
        raise NotImplementedError(
            f"render_operator_cte not implemented for {self.get_sql_dialect()}"
        )
