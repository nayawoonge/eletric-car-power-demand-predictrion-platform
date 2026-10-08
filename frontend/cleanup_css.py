#!/usr/bin/env python3
"""
사용하지 않는 CSS 선택자 제거 스크립트
"""
import re
import sys

def remove_unused_css_blocks(file_path, unused_selectors):
    """파일에서 사용하지 않는 CSS 블록 제거"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    original_content = content

    for selector in unused_selectors:
        # 선택자 escape
        escaped_selector = re.escape(selector)

        # CSS 블록 패턴: 선택자 { ... }
        # 중첩 가능성 고려
        pattern = rf'^\s*{escaped_selector}\s*{{[^}}]*}}'

        # multiline으로 검색하여 제거
        content = re.sub(pattern, '', content, flags=re.MULTILINE)

    # 빈 줄 정리 (연속된 빈 줄을 최대 2개로 제한)
    content = re.sub(r'\n\n\n+', '\n\n', content)

    if content != original_content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False


# dashboard/[stationId]/+page.svelte
dashboard_page_unused = [
    '.nav-link',
    '.btn-back',
    '.btn-back:hover',
    '.title-icon',
    '.status-indicator',
    '.status-dot',
    '.info-banner',
    '.banner-icon',
    '.banner-icon svg',
    '.banner-content',
    '.banner-title',
    '.banner-stats',
    '.stat-item',
    '.stat-label',
    '.stat-value',
    '.stat-divider',
    '.control-panel',
    '.button-group',
    '.btn',
    '.info-banner .banner-stats .stat-divider',
    '.info-banner .banner-stats',
]

print("Cleaning dashboard/[stationId]/+page.svelte...")
if remove_unused_css_blocks(
    r'src\routes\dashboard\[stationId]\+page.svelte',
    dashboard_page_unused
):
    print("✓ Cleaned dashboard page")
else:
    print("- No changes needed")

print("\nDone!")
