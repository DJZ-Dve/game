"""fetch_*.py 共用的下载：只用 Python 标准库。
先下到 .part，完整下完再改名（断线不会留下半截文件）；.part 还在就按 Range 接着下（网慢时一次下不完，再跑一遍接上）；失败重试。
代理：proxy 参数（各脚本的 --proxy），或者环境变量 HTTPS_PROXY / HTTP_PROXY（urllib 自己会读）。
超时是“多久没收到数据”，不是整个文件的总时长，网慢但一直在下的不会被掐断。
"""
import http.client
import json
import os
import shutil
import sys
import urllib.error
import urllib.request

UA = "Guixu-tools/1.0"  # Poly Haven 的 API 要求带一个能认出是谁的 User-Agent

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    except (AttributeError, ValueError):
        pass


def _open(url, proxy=None, timeout=120, headers=None):
    handlers = [urllib.request.ProxyHandler({"http": proxy, "https": proxy})] if proxy else []
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    return urllib.request.build_opener(*handlers).open(req, timeout=timeout)


def get_json(url, proxy=None, tries=3):
    for i in range(tries):
        try:
            with _open(url, proxy) as r:
                return json.load(r)
        except (OSError, http.client.HTTPException, ValueError) as e:
            if i == tries - 1:
                raise SystemExit(f"下载失败: {url}: {e}")
            print(f"retry {i + 1} {url}: {e}")


def download(url, dest, proxy=None, tries=3, timeout=120):
    """下载到 dest（已经有了就跳过），返回是否成功"""
    if os.path.exists(dest) and os.path.getsize(dest):
        return True
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    part = dest + ".part"
    for i in range(tries):
        have = os.path.getsize(part) if os.path.exists(part) else 0
        try:
            with _open(url, proxy, timeout, {"Range": f"bytes={have}-"} if have else None) as r:
                if have and r.status != 206:
                    have = 0  # 服务器不支持续传，从头下
                with open(part, "ab" if have else "wb") as f:
                    shutil.copyfileobj(r, f, 1 << 16)
            os.replace(part, dest)
            return True
        except urllib.error.HTTPError as e:
            if e.code == 416 and os.path.exists(part):  # .part 有问题（比远端还长），丢掉重下
                os.remove(part)
            print(f"retry {i + 1} {url}: {e}")
        except (OSError, http.client.HTTPException) as e:
            print(f"retry {i + 1} {url}: {e}")
    return False
