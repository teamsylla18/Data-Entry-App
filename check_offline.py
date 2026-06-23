"""
Verify no external/CDN URLs exist in templates or static files.
Must exit 0 before any module is considered done.
"""
import re
import sys
from pathlib import Path

BASE = Path(__file__).parent

TEMPLATE_CDN = re.compile(
    r'(src|href)\s*=\s*["\']https?://',
    re.IGNORECASE,
)
CSS_CDN = re.compile(
    r'url\s*\(\s*["\']?\s*https?://',
    re.IGNORECASE,
)

violations = []


def check_file(path, pattern):
    text = path.read_text(encoding='utf-8', errors='ignore')
    for i, line in enumerate(text.splitlines(), 1):
        if pattern.search(line):
            violations.append(f"  {path.relative_to(BASE)}:{i}  {line.strip()[:120]}")


for p in BASE.glob('app/templates/**/*.html'):
    check_file(p, TEMPLATE_CDN)

for p in BASE.glob('app/static/**/*.css'):
    check_file(p, CSS_CDN)

if violations:
    print("FAIL — external/CDN URL violations:")
    for v in violations:
        print(v)
    sys.exit(1)

print("PASS — all assets are local, no CDN URLs found.")
sys.exit(0)
