from cube_relay.experiments.benchmark import run_case, task_matrix


def test_task_matrix_has_required_fixed_cases() -> None:
    matrix = task_matrix()
    assert sum(task == "A" for task, _ in matrix) == 20
    assert sum(task == "B" for task, _ in matrix) == 10
    assert sum(task == "C" for task, _ in matrix) == 10


def test_both_baselines_succeed_without_disturbance() -> None:
    assert run_case("fixed-plan", "A", 2).success
    assert run_case("replan", "A", 2).success


def test_replan_recovers_and_fixed_plan_does_not() -> None:
    for task in ("B", "C"):
        fixed = run_case("fixed-plan", task, 3)
        replan = run_case("replan", task, 3)
        assert not fixed.success
        assert replan.success
        assert replan.replan_count == 1
        assert replan.mismatch_count == 1


def test_benchmark_is_reproducible_except_wall_clock() -> None:
    left = run_case("replan", "B", 9).as_dict()
    right = run_case("replan", "B", 9).as_dict()
    left.pop("runtime_ms"); right.pop("runtime_ms")
    assert left == right

