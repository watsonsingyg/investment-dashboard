#!/usr/bin/env python3
"""
generate_dashboard.py
读取周报 Excel，生成动态 Pipeline 看板 HTML。
用法: python3 generate_dashboard.py [Excel文件路径]
     不传路径时自动取同目录下最新的 .xlsx 文件
"""

import os
import sys

from reporter.dashboard_api import load_dashboard_payload
from reporter.dashboard_data import find_excel, parse_excel
from reporter.shadow_store import sync_dashboard_data


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if len(sys.argv) > 1:
        excel_path = sys.argv[1]
    else:
        excel_path = find_excel(script_dir)

    print(f'读取：{excel_path}')
    data = parse_excel(excel_path)
    print(f'解析完成：{len(data["projects"])} 个项目，{len(data["week_cols"])} 个周报列')

    payload = load_dashboard_payload(script_dir)
    sync_dashboard_data(script_dir, payload)
    tpl_path = os.path.join(script_dir, 'reporter', 'templates', 'dashboard.html')
    with open(tpl_path, 'r', encoding='utf-8') as f:
        html = f.read()

    out_path = os.path.join(script_dir, 'dashboard.html')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f'已生成：{out_path}')
    print(f'本周活跃：{sum(1 for p in data["projects"] if p["is_active"])}')
    print(f'近8周新增：{sum(1 for p in data["projects"] if p["is_new"])}')


if __name__ == '__main__':
    main()
