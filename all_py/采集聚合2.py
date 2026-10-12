# -*- coding: utf-8 -*-
"""
================================================================
 Eternity影视 TVBox py站源 v1.0 (xr.bot1.ccwu.cc 聚合影视)
================================================================
 功能:
  - 30+ 精细节目分类(电影/连续剧/综艺/动漫/动作/喜剧/爱情/科幻...)
  - 站内搜索(支持分页)
  - 影片详情(多播放源/多集选集)
  - 智能解析:多资源站轮换,自动优选直链(m3u8/mp4),失败自动换源
  - 多 User-Agent 轮换
  - 本地缓存

 数据来源:苹果CMS资源站接口(20源智能轮换)
  依赖: requests  (pip install requests)
================================================================
"""

import json
import re
import os
import time
import random
import hashlib
import traceback
import tempfile
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


# ---------------- UA 池:多 User-Agent 轮换 ----------------
USER_AGENTS = [
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 11; TV) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (SMART-TV; Linux; Tizen 6.0) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/4.0 TV Safari/537.36",
]

# ---------------- 资源站接口(多源智能轮换,20源) ----------------
API_SOURCES = [
    # 原有3源
    "https://cj.ffzyapi.com/api.php/provide/vod/",      # 非凡
    "https://api.zuidapi.com/api.php/provide/vod/",     # 最大
    "https://api.ffzyapi.com/api.php/provide/vod/",     # 非凡备用
    # 新增17源
    "https://www.maoyanzy.com/api.php/provide/vod/",    # 猫眼
    "https://tyyszy.com/api.php/provide/vod/",           # 天涯影视
    "http://www.ffzy.tv/api.php/provide/vod/",          # 非凡资源
    "https://www.lzzy.tv/api.php/provide/vod/",         # 量子
    "https://niuniuzy6.com/api.php/provide/vod/",       # 牛牛
    "https://suonizy.cc/api.php/provide/vod/",          # 索尼
    "https://shandianzy.com/api.php/provide/vod/",      # 闪电
    "https://okzyw.cc/api.php/provide/vod/",            # OK
    "https://kuaichezy.com/api.php/provide/vod/",       # 快车
    "https://www.zuidazy.co/api.php/provide/vod/",      # 最大备用
    "https://dbzy.tv/api.php/provide/vod/",             # 豆瓣
    "http://www.haohuazy.com/api.php/provide/vod/",     # 豪华
    "http://dyttzyw.tv/api.php/provide/vod/",           # 电影
    "https://www.jisuzy.com/api.php/provide/vod/",      # 极速
    "https://www.subozy.com/api.php/provide/vod/",      # 速播
    "https://www.iqiyizy.cc/api.php/provide/vod/",      # 爱奇艺
    "https://www.ikunzy.cc/api.php/provide/vod/",       # 爱坤
]

# ---------------- 内置分类(接口拉取失败时的兜底,均为叶子分类ID) ----------------
BUILTIN_CATEGORIES = [
    {"type_id": "6", "type_name": "💥动作片"},
    {"type_id": "7", "type_name": "😂喜剧片"},
    {"type_id": "8", "type_name": "💕爱情片"},
    {"type_id": "9", "type_name": "🚀科幻片"},
    {"type_id": "10", "type_name": "👻恐怖片"},
    {"type_id": "11", "type_name": "🎭剧情片"},
    {"type_id": "12", "type_name": "⚔️战争片"},
    {"type_id": "13", "type_name": "🇨🇳国产剧"},
    {"type_id": "14", "type_name": "🇭🇰香港剧"},
    {"type_id": "15", "type_name": "🇰🇷韩国剧"},
    {"type_id": "16", "type_name": "🇺🇸欧美剧"},
    {"type_id": "22", "type_name": "🇯🇵日本剧"},
    {"type_id": "24", "type_name": "🇹🇭泰国剧"},
    {"type_id": "25", "type_name": "大陆综艺"},
    {"type_id": "28", "type_name": "欧美综艺"},
    {"type_id": "29", "type_name": "国产动漫"},
    {"type_id": "30", "type_name": "日韩动漫"},
    {"type_id": "31", "type_name": "欧美动漫"},
    {"type_id": "20", "type_name": "📹纪录片"},
]

# 父分类ID(查不出数据,需过滤)
PARENT_TYPE_IDS = {"1", "2", "3", "4"}

PAGE_SIZE = 20
CACHE_TTL = 1800
CACHE_VERSION = "v1"

# 播放源名称美化
SOURCE_NAMES = {
    "ffm3u8": "非凡m3u8", "feifan": "非凡", "zuidam3u8": "最大m3u8",
    "zuida": "最大", "lzm3u8": "量子m3u8", "liangzi": "量子",
    "snm3u8": "索尼m3u8", "suoni": "索尼", "mym3u8": "猫眼m3u8",
    "okm3u8": "OKm3u8", "tianya": "天涯", "niuniu": "牛牛",
    "shandian": "闪电", "kuaiche": "快车", "dbm3u8": "豆瓣m3u8",
    "haohua": "豪华", "jisu": "极速", "subo": "速播",
    "iqiyi": "爱奇艺", "ikun": "爱坤", "jsm3u8": "极速m3u8",
    "hhm3u8": "豪华m3u8", "subm3u8": "速播m3u8", "dyttm3u8": "电影m3u8",
    "ikm3u8": "爱坤m3u8", "iqym3u8": "爱奇艺m3u8", "jsyun": "极速云",
    "tianyi": "天翼", "wjm3u8": "万佳m3u8",
}


class Spider:
    def __init__(self):
        self.cache_dir = os.path.join(tempfile.gettempdir(), "xrys_cache")
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
        except Exception:
            pass
        self.proxy = None
        self.timeout = 20
        self._session = None
        self._api_idx = 0

    # ============ 基础 ============
    def getName(self):
        return "Eternity影视"

    def init(self, extend=""):
        if not extend:
            return
        try:
            cfg = json.loads(extend) if isinstance(extend, str) else extend
            self.proxy = cfg.get("proxy")
            self.timeout = int(cfg.get("timeout", 20))
        except Exception:
            pass

    def isVideoFormat(self, url):
        """智能识别视频格式:m3u8/mp4/mkv/flv/ts 等直链"""
        u = (url or "").lower()
        path = u.split("?")[0].split("#")[0]
        if path.endswith((".m3u8", ".mp4", ".mkv", ".flv", ".ts",
                          ".m4v", ".webm", ".mov", ".avi")):
            return True
        # 路径中带格式关键字但不是 share 中转页
        if "share" not in u and ("/m3u8" in u or ".m3u8" in u or ".mp4" in u):
            return True
        return False

    def manualVideoCheck(self):
        return True

    # ============ 内部工具 ============
    def _session_get(self):
        if self._session is None:
            self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })
        return self._session

    def _api_get(self, params, require_list=False):
        """
        智能多源轮换:主源失败自动切备用源。
        require_list=True 时,空列表视为未命中,继续试下一个源(用于详情查ID)。
        返回 (data, api_url) 或 (None, None)。
        """
        if not HAS_REQUESTS:
            return None, None
        s = self._session_get()
        proxies = {"http": self.proxy, "https": self.proxy} if self.proxy else None
        # 轮换顺序:从上次成功的位置开始
        order = API_SOURCES[self._api_idx:] + API_SOURCES[:self._api_idx]
        for i, api in enumerate(order):
            try:
                r = s.get(api, params=params, timeout=self.timeout,
                          proxies=proxies)
                r.raise_for_status()
                d = r.json()
                if d.get("code") == 1 or "list" in d:
                    # 详情查ID时空列表=没命中,继续下一个源
                    if require_list and not (d.get("list") or []):
                        continue
                    # 记录成功位置,下次优先
                    self._api_idx = API_SOURCES.index(api)
                    return d, api
            except Exception:
                traceback.print_exc()
                continue
        return None, None

    def _cache_path(self, key):
        return os.path.join(self.cache_dir, CACHE_VERSION + "_" +
                            hashlib.md5(key.encode("utf-8")).hexdigest() + ".json")

    def _cache_get(self, key):
        try:
            p = self._cache_path(key)
            if not os.path.exists(p):
                return None
            if time.time() - os.path.getmtime(p) > CACHE_TTL:
                return None
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _cache_set(self, key, data):
        try:
            with open(self._cache_path(key), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception:
            pass

    def _pretty_source(self, name):
        name = (name or "").strip()
        return SOURCE_NAMES.get(name.lower(), name or "默认")

    # ============ 数据层 ============
    def _get_categories(self):
        cached = self._cache_get("categories")
        if cached:
            return cached
        d, _ = self._api_get({"ac": "list"})
        cats = []
        try:
            for c in (d or {}).get("class") or []:
                tid = str(c.get("type_id"))
                tname = c.get("type_name") or ""
                # 过滤父分类(查不出数据)和伦理片
                if tid in PARENT_TYPE_IDS or tid == "34" or "伦理" in tname:
                    continue
                cats.append({"type_id": tid, "type_name": tname})
        except Exception:
            pass
        if not cats:
            cats = BUILTIN_CATEGORIES
        # 只缓存有效结果
        if cats:
            self._cache_set("categories", cats)
        return cats

    def _fetch_list(self, params, cache_key):
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        d, _ = self._api_get(params)
        result = {"list": [], "page": 1, "pagecount": 1, "total": 0}
        try:
            if d:
                result = {
                    "list": d.get("list") or [],
                    "page": int(d.get("page") or 1),
                    "pagecount": int(d.get("pagecount") or 1),
                    "total": int(d.get("total") or 0),
                }
        except Exception:
            pass
        # 只缓存有效结果
        if result["list"]:
            self._cache_set(cache_key, result)
        return result

    def _to_vod(self, v):
        return {
            "vod_id": str(v.get("vod_id")),
            "vod_name": v.get("vod_name") or "未知",
            "vod_pic": v.get("vod_pic") or "",
            "vod_remarks": (v.get("vod_remarks") or v.get("vod_year") or "").strip(),
        }

    def _search_one_api(self, api, title):
        """在单个源按片名搜索,返回最佳匹配的影片数据或 None"""
        try:
            s = self._session_get()
            proxies = {"http": self.proxy, "https": self.proxy} if self.proxy else None
            r = s.get(api, params={"ac": "videolist", "wd": title, "pg": 1},
                      timeout=8, proxies=proxies,
                      headers={"User-Agent": random.choice(USER_AGENTS)})
            r.raise_for_status()
            d = r.json()
            if d.get("code") != 1:
                return None
            for v in d.get("list") or []:
                vn = (v.get("vod_name") or "").strip()
                # 标题精确匹配或包含
                if vn == title or (title in vn or vn in title):
                    if v.get("vod_play_url"):
                        return v
            return None
        except Exception:
            return None

    def _aggregate_sources(self, title, exclude_api=None):
        """
        全源聚合:按片名并行搜索所有资源站,合并播放源。
        返回 [(源名, [(集名, url), ...]), ...]
        """
        if not title:
            return []
        apis = [a for a in API_SOURCES if a != exclude_api]
        merged = []
        seen_urls = set()
        with ThreadPoolExecutor(max_workers=10) as ex:
            futs = {ex.submit(self._search_one_api, api, title): api
                    for api in apis}
            for fut in as_completed(futs):
                v = fut.result()
                if not v:
                    continue
                for sname, eps in self._parse_play_data(v):
                    # 去重:同一源名只保留一次,URL去重
                    if any(s[0] == sname for s in merged):
                        continue
                    filtered = [(n, u) for n, u in eps if u not in seen_urls]
                    if not filtered:
                        continue
                    for _, u in filtered:
                        seen_urls.add(u)
                    merged.append((sname, filtered))
        # 直链优先排序
        def score(src):
            _, eps = src
            for _, u in eps[:3]:
                if self.isVideoFormat(u):
                    return 0
            return 1
        merged.sort(key=score)
        return merged

    def _parse_play_data(self, v):
        """
        解析播放数据,返回 [(源名, [(集名, url), ...]), ...]
        智能排序:直链(m3u8/mp4)优先。
        """
        froms = (v.get("vod_play_from") or "").split("$$$")
        urls = (v.get("vod_play_url") or "").split("$$$")
        sources = []
        for i, fr in enumerate(froms):
            if i >= len(urls):
                continue
            eps = []
            for ep in urls[i].split("#"):
                if "$" not in ep:
                    continue
                name, url = ep.split("$", 1)
                name, url = name.strip(), url.strip()
                if not url:
                    continue
                eps.append((name, url))
            if eps:
                sources.append((self._pretty_source(fr), eps))
        # 直链优先:把含 m3u8/mp4 直链的源排前面
        def score(src):
            _, eps = src
            for _, u in eps[:3]:
                if self.isVideoFormat(u):
                    return 0
            return 1
        sources.sort(key=score)
        return sources

    # ============ TVBox 接口 ============
    def homeContent(self, filter):
        cats = self._get_categories()
        return {"class": cats, "filters": {}}

    def homeVideoContent(self):
        """首页:最新更新"""
        if not HAS_REQUESTS:
            return {"list": [{"vod_id": "__diag__", "vod_name": "⚠️缺少 requests 依赖",
                              "vod_pic": "", "vod_remarks": "点我看详情"}]}
        r = self._fetch_list({"ac": "videolist", "pg": 1, "h": 24}, "home_new")
        return {"list": [self._to_vod(v) for v in r["list"][:20]]}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = max(int(pg), 1)
        except Exception:
            pg = 1
        if not HAS_REQUESTS:
            return {"list": [{"vod_id": "__diag__", "vod_name": "⚠️缺少 requests 依赖",
                              "vod_pic": "", "vod_remarks": ""}],
                    "page": 1, "pagecount": 1, "limit": PAGE_SIZE, "total": 1}
        r = self._fetch_list({"ac": "videolist", "t": tid, "pg": pg},
                             "cat:{}:{}".format(tid, pg))
        items = [self._to_vod(v) for v in r["list"][:PAGE_SIZE]]
        return {"list": items, "page": r["page"], "pagecount": r["pagecount"],
                "limit": PAGE_SIZE, "total": r["total"]}

    def detailContent(self, ids):
        vod_id = ids[0] if ids else ""
        if vod_id == "__diag__" or not HAS_REQUESTS:
            return {"list": [{
                "vod_id": "__diag__", "vod_name": "⚠️缺少 requests 依赖",
                "vod_pic": "", "type_name": "系统诊断",
                "vod_content": "请在 TVBox 的 Python 环境中执行: pip install requests",
                "vod_play_from": "说明", "vod_play_url": "确定$__diag__"}]}
        d, _ = self._api_get({"ac": "detail", "ids": vod_id}, require_list=True)
        v = None
        try:
            v = (d.get("list") or [])[0]
        except Exception:
            pass
        if not v:
            # 换 videolist 接口再试一次
            d, _ = self._api_get({"ac": "videolist", "ids": vod_id},
                                 require_list=True)
            try:
                v = (d.get("list") or [])[0]
            except Exception:
                pass
        if not v:
            return {"list": []}
        title = (v.get("vod_name") or "").strip()
        # 本源播放源
        sources = self._parse_play_data(v)
        # 全源聚合:按片名并行搜索其他资源站,合并更多播放源
        primary_api = API_SOURCES[self._api_idx]
        extra = self._aggregate_sources(title, exclude_api=primary_api)
        # 合并去重(源名不重复)
        have = {s[0] for s in sources}
        for sname, eps in extra:
            if sname not in have:
                sources.append((sname, eps))
                have.add(sname)
        # 直链优先
        def _score(src):
            _, eps = src
            for _, u in eps[:3]:
                if self.isVideoFormat(u):
                    return 0
            return 1
        sources.sort(key=_score)
        play_from, play_urls = [], []
        for sname, eps in sources:
            play_from.append(sname)
            play_urls.append("#".join("{}${}".format(n, u) for n, u in eps))
        vod = {
            "vod_id": str(v.get("vod_id")),
            "vod_name": v.get("vod_name") or "",
            "vod_pic": v.get("vod_pic") or "",
            "type_name": v.get("type_name") or "",
            "vod_year": str(v.get("vod_year") or ""),
            "vod_area": v.get("vod_area") or "",
            "vod_remarks": v.get("vod_remarks") or "",
            "vod_actor": v.get("vod_actor") or "",
            "vod_director": v.get("vod_director") or "",
            "vod_content": (v.get("vod_content") or "").strip(),
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_urls),
        }
        return {"list": [vod]}

    def searchContent(self, key, quick, pg="1"):
        key = (key or "").strip()
        if not key:
            return {"list": []}
        if not HAS_REQUESTS:
            return {"list": [{"vod_id": "__diag__", "vod_name": "⚠️缺少 requests 依赖",
                              "vod_pic": "", "vod_remarks": ""}]}
        try:
            pg = max(int(pg), 1)
        except Exception:
            pg = 1
        if quick:
            r = self._fetch_list({"ac": "videolist", "wd": key, "pg": 1},
                                 "search:{}:1".format(key))
            return {"list": [self._to_vod(v) for v in r["list"][:10]]}
        r = self._fetch_list({"ac": "videolist", "wd": key, "pg": pg},
                             "search:{}:{}".format(key, pg))
        items = [self._to_vod(v) for v in r["list"][:PAGE_SIZE]]
        return {"list": items, "page": r["page"], "pagecount": r["pagecount"],
                "limit": PAGE_SIZE, "total": r["total"]}

    def playerContent(self, flag, id, vipFlags):
        """
        智能解析:
         1. m3u8/mp4 直链 -> 直接播放(parse:0);
         2. share 中转页 -> 尝试抓取真实地址,失败则交 TVBox 解析(parse:1);
         3. 返回标准 header(UA 轮换 + Referer)。
        """
        if not HAS_REQUESTS or not id or id == "__diag__":
            return {"parse": 0, "url": ""}
        url = id.strip()
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Referer": "https://xr.bot1.ccwu.cc/",
            "Origin": "https://xr.bot1.ccwu.cc",
        }
        # share 中转页优先处理:尝试抓取真实 m3u8
        if "share" in url:
            try:
                s = self._session_get()
                proxies = ({"http": self.proxy, "https": self.proxy}
                           if self.proxy else None)
                r = s.get(url, headers=headers, timeout=15, proxies=proxies)
                m = re.search(r'https?://[^"\'\s<>]+\.m3u8[^"\'\s<>]*', r.text)
                if m:
                    return {"parse": 0, "playUrl": "", "url": m.group(0),
                            "header": headers}
            except Exception:
                traceback.print_exc()
            # 抓不到则交 TVBox 解析
            return {"parse": 1, "url": url, "header": headers}
        # 直链直接播
        if self.isVideoFormat(url):
            return {"parse": 0, "playUrl": "", "url": url, "header": headers}
        # 兜底:交 TVBox 解析
        return {"parse": 1, "url": url, "header": headers}


if __name__ == "__main__":
    sp = Spider()
    sp.init("")
    print("站名:", sp.getName())
    print("分类数:", len(sp.homeContent(None)["class"]))
    r = sp.searchContent("哪吒", True)
    print("搜索 哪吒:", len(r["list"]), "条")
    if r["list"]:
        print("首条:", r["list"][0]["vod_name"])
