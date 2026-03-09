"""版本更新检查服务"""
import os
import urllib.request
import urllib.error
import json
import re
from typing import Optional, Dict, List, Tuple


# GitHub 仓库信息
GITHUB_REPO = "MuskCheng/ihomeguard"
RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases"


def get_local_version() -> str:
    """获取本地版本号"""
    version_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'VERSION')
    if os.path.exists(version_file):
        with open(version_file, 'r', encoding='utf-8') as f:
            return f.read().strip()
    return 'unknown'


def compare_versions(v1: str, v2: str) -> int:
    """比较版本号，返回 -1 (v1<v2), 0 (v1=v2), 1 (v1>v2)"""
    def parse_version(v):
        # 移除 v 前缀，提取数字部分
        v = v.lstrip('v')
        parts = re.findall(r'\d+', v)
        return [int(p) for p in parts] if parts else [0]
    
    p1, p2 = parse_version(v1), parse_version(v2)
    # 补齐长度
    max_len = max(len(p1), len(p2))
    p1.extend([0] * (max_len - len(p1)))
    p2.extend([0] * (max_len - len(p2)))
    
    for a, b in zip(p1, p2):
        if a < b:
            return -1
        elif a > b:
            return 1
    return 0


def fetch_releases(limit: int = 5) -> Tuple[bool, List[Dict], str]:
    """从 GitHub 获取最近 releases
    
    Returns:
        (success, releases, error_message)
    """
    try:
        url = f"{RELEASES_API}?per_page={limit}"
        req = urllib.request.Request(url)
        req.add_header('Accept', 'application/vnd.github.v3+json')
        req.add_header('User-Agent', 'iHomeGuard-UpdateChecker')
        
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            
        releases = []
        for release in data:
            releases.append({
                'version': release.get('tag_name', ''),
                'name': release.get('name', release.get('tag_name', '')),
                'published_at': release.get('published_at', ''),
                'body': release.get('body', ''),
                'html_url': release.get('html_url', '')
            })
        
        return True, releases, ''
    except urllib.error.URLError as e:
        return False, [], f"网络错误: {str(e)}"
    except json.JSONDecodeError:
        return False, [], "解析响应失败"
    except Exception as e:
        return False, [], f"未知错误: {str(e)}"


def check_update() -> Dict:
    """检查更新
    
    Returns:
        {
            'current_version': str,
            'latest_version': str,
            'has_update': bool,
            'releases': List[Dict],  # 最近5条更新日志
            'error': str  # 错误信息（如果有）
        }
    """
    local_version = get_local_version()
    
    success, releases, error = fetch_releases(limit=5)
    
    if not success:
        return {
            'current_version': local_version,
            'latest_version': local_version,
            'has_update': False,
            'releases': [],
            'error': error
        }
    
    latest_version = releases[0]['version'] if releases else local_version
    has_update = compare_versions(local_version, latest_version) < 0
    
    return {
        'current_version': local_version,
        'latest_version': latest_version,
        'has_update': has_update,
        'releases': releases,
        'error': ''
    }


def parse_changelog(limit: int = 5) -> List[Dict]:
    """解析本地 CHANGELOG.md
    
    Returns:
        [{'version': '1.2.1', 'date': '2026-03-07', 'content': '...'}, ...]
    """
    changelog_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'CHANGELOG.md')
    
    if not os.path.exists(changelog_file):
        return []
    
    with open(changelog_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 匹配版本块：## [version] - date ... ## [next]
    pattern = r'## \[([^\]]+)\]\s*-\s*(\d{4}-\d{2}-\d{2})(.*?)(?=## \[|$)'
    matches = re.findall(pattern, content, re.DOTALL)
    
    entries = []
    for version, date, body in matches[:limit]:
        entries.append({
            'version': version,
            'date': date,
            'content': body.strip()
        })
    
    return entries
