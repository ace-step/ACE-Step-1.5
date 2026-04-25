"""Task-type helpers for Gradio generation events."""


def resolve_no_fsq_task_type(task_type: str, no_fsq: bool) -> str:
    """Resolve the Remix ``no_fsq`` checkbox into the backend task type.

    Args:
        task_type: Current hidden Gradio task type.
        no_fsq: Whether Remix should skip FSQ-quantized source conditioning.

    Returns:
        ``cover-nofsq`` only for Remix/cover with the checkbox enabled;
        otherwise the original task type.
    """
    if task_type == "cover" and no_fsq:
        return "cover-nofsq"
    return task_type
