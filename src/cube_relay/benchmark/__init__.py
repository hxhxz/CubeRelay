"""CubeRelay M4-D Task Agent Capability Benchmark package."""

from .attribution import attribute_closed_loop_episode, attribute_replay_decision
from .cases import build_closed_loop_scenarios, build_m4d_replay_cases
from .exporter import (
    BenchmarkExporter,
    discover_benchmark_runs,
    load_benchmark_run,
    verify_benchmark_zip_integrity,
)
from .m4c_importer import discover_m4c_bundles, extract_m4c_replay_slice
from .metrics import compute_scorecard, summarize_vlm_ablation, wilson_ci
from .oracle import (
    EvaluationOracle,
    assert_no_future_leakage,
    assert_no_oracle_in_prompt,
    normalize_decision_kind,
)
from .runners import ClosedLoopBenchmarkRunner, DecisionReplayRunner, assemble_benchmark_run
from .schema import (
    BENCHMARK_VERSION,
    AgentScorecard,
    BenchmarkAgentInput,
    BenchmarkCase,
    BenchmarkRunResult,
    BenchmarkSourceType,
    CapabilityDimension,
    ClosedLoopEpisodeResult,
    DecisionRecord,
    DecisionRuleSpec,
    DimensionScoreSummary,
    ExecutionSourceLabel,
    FailureAttributionCategory,
    FailureAttributionResult,
    MetricValue,
    OracleEvaluationResult,
    PlannerGroup,
    PromptGuideMode,
    SafetyValidationResult,
    VLMAblationCondition,
)

__all__ = [
    "BENCHMARK_VERSION",
    "AgentScorecard",
    "BenchmarkAgentInput",
    "BenchmarkCase",
    "BenchmarkExporter",
    "BenchmarkRunResult",
    "BenchmarkSourceType",
    "CapabilityDimension",
    "ClosedLoopBenchmarkRunner",
    "ClosedLoopEpisodeResult",
    "DecisionRecord",
    "DecisionReplayRunner",
    "DecisionRuleSpec",
    "DimensionScoreSummary",
    "EvaluationOracle",
    "ExecutionSourceLabel",
    "FailureAttributionCategory",
    "FailureAttributionResult",
    "MetricValue",
    "OracleEvaluationResult",
    "PlannerGroup",
    "PromptGuideMode",
    "SafetyValidationResult",
    "VLMAblationCondition",
    "assert_no_future_leakage",
    "assert_no_oracle_in_prompt",
    "assemble_benchmark_run",
    "attribute_closed_loop_episode",
    "attribute_replay_decision",
    "build_closed_loop_scenarios",
    "build_m4d_replay_cases",
    "compute_scorecard",
    "discover_benchmark_runs",
    "discover_m4c_bundles",
    "extract_m4c_replay_slice",
    "load_benchmark_run",
    "normalize_decision_kind",
    "summarize_vlm_ablation",
    "verify_benchmark_zip_integrity",
    "wilson_ci",
]
