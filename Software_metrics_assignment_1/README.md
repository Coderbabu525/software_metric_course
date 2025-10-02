# software_metric_assignment_1: Measurement Instruments

What is the measurement-instruments.py? What does it do?

A from-scratch implementation of software measurement instruments for:
- Physical LOC
- Logical LOC (heuristic)
- McCabe Cyclomatic Complexity (heuristic)
- Fan-in and Fan-out (call graph heuristic)

Supports C, Java, TypeScript/JavaScript, and Python files. No external analysis tools required.

Command:
    python3 measurement-instruments.py --repo /path/to/repo --out results.json

Outputs JSON with:
- Repo-wide totals
- Per-module summary

Notes/Limitations:
- This is an approximate, language-heuristic analyzer. It does not build perfect ASTs.
- Cyclomatic complexity is estimated using decision tokens.
- Fan-in/out uses simple function name matching; name collisions may reduce accuracy.
