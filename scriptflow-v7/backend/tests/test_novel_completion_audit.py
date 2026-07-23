from scriptflow_v7.novel.completion_audit import CompletionGate, completion_status


def test_completion_requires_every_gate_to_pass():
    assert completion_status([CompletionGate("one", True, "ok")]) == "complete"
    assert (
        completion_status(
            [CompletionGate("one", True, "ok"), CompletionGate("two", False, "missing")]
        )
        == "incomplete"
    )
    assert completion_status([]) == "incomplete"
