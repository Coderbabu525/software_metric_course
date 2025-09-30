#!/usr/bin/env python3
"""
measurement-instruments.py

A from-scratch implementation of measurement instruments for:
- Physical LOC
- Logical LOC (heuristic)
- McCabe Cyclomatic Complexity (heuristic)
- Fan-in and Fan-out (call graph heuristic)

Supports C, Java, TypeScript/JavaScript, and Python files. No external analysis tools required.

Usage:
    python3 measurement-instruments.py --repo /path/to/repo --out results.json

Outputs JSON with:
- Repo-wide totals
- Per-module summary

Notes/Limitations:
- This is an approximate, language-heuristic analyzer. It does not build perfect ASTs.
- Cyclomatic complexity is estimated using decision tokens.
- Fan-in/out uses simple function name matching; name collisions may reduce accuracy.
"""

import argparse
import json
import os
import re
from collections import defaultdict, Counter
from pathlib import Path
from typing import List

# -------------------------
# Supported file extensions
# -------------------------
LANG_EXTENSIONS = {
    'c': ['.c', '.C', '.h', '.H'],
    'java': ['.java'],
    'ts': ['.ts', '.tsx', '.js', '.jsx'],
    'py': ['.py'],
}

DECISION_TOKENS = {
    'c': [r'\bif\b', r'\bfor\b', r'\bwhile\b', r'\bcase\b', r'\bcatch\b', r'\belse if\b', r'\?\s*', r'&&', r'\|\|'],
    'java': [r'\bif\b', r'\bfor\b', r'\bwhile\b', r'\bcase\b', r'\bcatch\b', r'\belse if\b', r'\?\s*', r'&&', r'\|\|'],
    'ts': [r'\bif\b', r'\bfor\b', r'\bwhile\b', r'\bcase\b', r'\bcatch\b', r'\belse if\b', r'\?\s*', r'&&', r'\|\|'],
    'py': [r'\bif\b', r'\belif\b', r'\bfor\b', r'\bwhile\b', r'\bexcept\b', r'\band\b', r'\bor\b']
}

FUNC_DEF_PATTERNS = {
    'c': re.compile(r'^[\w\s\*]+\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\([^;]*\)\s*\{', re.MULTILINE),
    'java': re.compile(r'(public|protected|private|static|\s)+[\<\>\w\[\]]+\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\([^\)]*\)\s*\{', re.MULTILINE),
    'ts': re.compile(r'(^|\s)(function\s+)?([a-zA-Z_][a-zA-Z0-9_]*)\s*\([^\)]*\)\s*\{', re.MULTILINE),
    'py': re.compile(r'^\s*def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', re.MULTILINE),
}

CALL_PATTERN = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)\s*\(')

# -------------------------
# Helpers
# -------------------------
def remove_comments_and_strings_c_style(code: str) -> str:
    string_re = r'(\"\"\".*?\"\"\"|\'\'\'.*?\'\'\'|\".*?\"|\'.*?\')'
    code = re.sub(string_re, '""', code, flags=re.DOTALL)
    code = re.sub(r'//.*', '', code)
    code = re.sub(r'#.*', '', code)
    code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
    return code

def physical_loc(lines: List[str], lang='c'):
    total = len(lines)
    blanks = sum(1 for l in lines if l.strip() == '')
    if lang == 'py':
        comments = sum(1 for l in lines if l.strip().startswith('#'))
    else:
        comments = sum(1 for l in lines if l.strip().startswith('//') or
                       l.strip().startswith('/*') or l.strip().endswith('*/') or
                       l.strip().startswith('*'))
    return total, blanks, comments

def logical_loc_from_code(code: str, lang: str) -> int:
    clean = remove_comments_and_strings_c_style(code)
    code_lines = [l for l in clean.splitlines() if l.strip()]
    if lang == 'py':
        stmt_lines = sum(1 for l in code_lines if l.strip().endswith(':') or '=' in l)
        return max(stmt_lines, len(code_lines)//2)
    else:
        semis = clean.count(';')
        returns = len(re.findall(r'\breturn\b', clean))
        return int(0.5*semis + 0.3*returns + 0.2*len(code_lines))

def find_functions_and_bodies(code: str, lang: str):
    pattern = FUNC_DEF_PATTERNS.get(lang)
    if not pattern: return []
    matches = []
    for m in pattern.finditer(code):
        if lang=='py':
            name = m.group(1)
            lines = code.splitlines()
            start_line = code[:m.start()].count('\n')
            indent = len(lines[start_line]) - len(lines[start_line].lstrip())
            body_lines = []
            for line in lines[start_line+1:]:
                if len(line)-len(line.lstrip()) <= indent and line.strip():
                    break
                body_lines.append(line)
            body = '\n'.join(body_lines)
        else:
            name = m.group(1) if lang=='c' else m.group(2) if lang=='java' else m.group(3)
            brace_pos = code.find('{', m.end()-1)
            if brace_pos == -1: continue
            depth=0; i=brace_pos; end=None
            while i<len(code):
                if code[i]=='{': depth+=1
                elif code[i]=='}': depth-=1
                if depth==0: end=i; break
                i+=1
            if end is None: continue
            body = code[brace_pos:end+1]
        matches.append((name, body))
    return matches

def complexity_of_body(body:str, lang='c') -> int:
    clean = remove_comments_and_strings_c_style(body)
    tokens = DECISION_TOKENS.get(lang, [])
    return 1 + sum(len(re.findall(tok, clean)) for tok in tokens)

def extract_function_names(code:str, lang:str) -> List[str]:
    funcs = []
    pattern = FUNC_DEF_PATTERNS.get(lang)
    if not pattern: return funcs
    for m in pattern.finditer(code):
        funcs.append(m.group(1) if lang=='py' else m.group(1) if lang=='c' else m.group(2) if lang=='java' else m.group(3))
    return funcs

def extract_calls(code:str) -> List[str]:
    clean = remove_comments_and_strings_c_style(code)
    calls = [m.group(1) for m in CALL_PATTERN.finditer(clean)]
    junk = set(['if','for','while','switch','return','catch','function','new','typeof','elif','except','print','len','range'])
    return [c for c in calls if c not in junk]

# -------------------------
# File collection
# -------------------------
def collect_files(repo_path:str):
    files_collected=[]
    for root,_,files in os.walk(repo_path, followlinks=True):
        for file in files:
            ext = Path(file).suffix.lower()
            for lang, exts in LANG_EXTENSIONS.items():
                if ext in [e.lower() for e in exts]:
                    files_collected.append((lang, os.path.join(root,file)))
    return files_collected

# -------------------------
# File-level measurement
# -------------------------
def measure_files(files):
    results = {}
    for lang, file_path in files:
        try:
            with open(file_path,'r',encoding='utf-8',errors='ignore') as f:
                code = f.read()
        except:
            continue
        lines = code.splitlines()
        total, blanks, comments = physical_loc(lines, lang)
        logical = logical_loc_from_code(code, lang)
        funcs = extract_function_names(code, lang)
        complexity = [complexity_of_body(body, lang) for name,body in find_functions_and_bodies(code, lang)]
        calls = extract_calls(code)
        results[file_path] = {
            "physical_loc":[total,blanks,comments],
            "logical_loc":logical,
            "num_functions":len(funcs),
            "cyclomatic_complexity":complexity,
            "fan_out":len(calls),
            "fan_in":len(funcs)  # approximation
        }
    return results

# -------------------------
# Module & repo aggregation
# -------------------------
def aggregate_summary(results:dict):
    modules = defaultdict(lambda: {
        "physical_loc":[0,0,0],
        "logical_loc":0,
        "num_functions":0,
        "cyclomatic_complexity":0,
        "fan_in":0,
        "fan_out":0
    })
    repo_totals = {
        "physical_loc":[0,0,0],
        "logical_loc":0,
        "num_functions":0,
        "cyclomatic_complexity":0,
        "fan_in":0,
        "fan_out":0
    }
    for f,data in results.items():
        module = os.path.dirname(f)
        for i in range(3):
            modules[module]["physical_loc"][i] += data["physical_loc"][i]
            repo_totals["physical_loc"][i] += data["physical_loc"][i]
        modules[module]["logical_loc"] += data["logical_loc"]
        modules[module]["num_functions"] += data["num_functions"]
        modules[module]["cyclomatic_complexity"] += sum(data["cyclomatic_complexity"])
        modules[module]["fan_in"] += data["fan_in"]
        modules[module]["fan_out"] += data["fan_out"]

        repo_totals["logical_loc"] += data["logical_loc"]
        repo_totals["num_functions"] += data["num_functions"]
        repo_totals["cyclomatic_complexity"] += sum(data["cyclomatic_complexity"])
        repo_totals["fan_in"] += data["fan_in"]
        repo_totals["fan_out"] += data["fan_out"]

    return dict(modules), repo_totals

# -------------------------
# CLI
# -------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()

    files = collect_files(args.repo)
    lang_counts = Counter(lang for lang,_ in files)
    print(f"📊 Found {len(files)} source files:")
    for lang,count in lang_counts.items():
        print(f"  {lang}: {count} files")

    results = measure_files(files)
    modules, repo_totals = aggregate_summary(results)

    output = {
        "repo_totals": repo_totals,
        "modules": modules
    }

    with open(args.out,'w',encoding='utf-8') as f:
        json.dump(output,f,indent=2)

    print(f"\n✅ Analysis complete. Results saved to {args.out}")

if __name__=="__main__":
    main()
