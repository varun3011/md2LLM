EVALUATION_SUITE_VERSION = "local-quality-v1"
PROMPT_SET_VERSION = "starter-v1"


PROMPT_SET = [
    {
        "id": "knowledge_recall",
        "dimension": "knowledge_recall",
        "prompt": (
            "Answer using only knowledge you are confident about from the training notes. "
            "If the notes do not contain the answer, say you do not know. "
            "Question: What are the most important themes or facts in the notes?"
        ),
    },
    {
        "id": "style_consistency",
        "dimension": "style_consistency",
        "prompt": (
            "Write a short explanation in the same voice and style as the training notes. "
            "Topic: what this knowledge base is mainly about."
        ),
    },
    {
        "id": "reasoning_quality",
        "dimension": "reasoning_quality",
        "prompt": (
            "Connect two ideas that likely appear in the notes and explain how they relate. "
            "Keep the answer concise and structured."
        ),
    },
    {
        "id": "hallucination_control",
        "dimension": "hallucination_control",
        "prompt": (
            "Name one specific source, author, or date from the notes. "
            "If you are not certain the notes contain one, say you do not know."
        ),
    },
    {
        "id": "latency_check",
        "dimension": "latency",
        "prompt": "Give a two-sentence summary of what you can help with.",
    },
]
