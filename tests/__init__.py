"""One package per test. Each exposes the same five functions so eval.py and
grade.py can treat them alike:

    cases()              -> list of case dicts, each with a unique "id"
    run(case, chat)      -> output dict saved to results/ (chat sends one request)
    estimate(case)       -> [(input_tokens, output_tokens), ...] one pair per request
    grade(case, output)  -> {"passed": True/False, or None when a person grades it, ...}
    DESCRIPTION          -> one line shown in reports
"""
