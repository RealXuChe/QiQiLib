# 祺祺图书馆
#
# 从wenku8.net自动爬取轻小说并生成电子书文件.献给Kindle中存了无数轻小说的ZSQ同学.
#
# Copyright 2021 XuChe <chrisxuche@gmail.com>
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

from subprocess import run, PIPE
from base64 import standard_b64encode as b64enc
from autoscraper import AutoScraper
from typing import List, Callable, Any, NamedTuple, Optional
from bs4 import BeautifulSoup
from requests.exceptions import *
import requests
from urllib.parse import urljoin
from pathlib import Path as p
from mimetypes import guess_type
from enum import Enum


class GenOpt(Enum):  # 可用的生成选项
    StandaloneMarkdown = 0,  # 单文件MD
    Mobi = 1,  # Mobi电子书(Kindle格式)
    Epub = 2,  # Epub电子书
    SepPicMarkdown = 3,  # 多文件MD(对阅读器性能友好)
    PlainText = 4  # 纯文本文档


# 由于技术限制,本程序生成的epub会占用阅读器大量处理资源,几乎不可能阅读,仅供图一乐
# (似乎你更应该怪阅读器.PC上就没有一个能用的阅读器.

# --- 配置项 ---
OUT_DIR: str = "./output"  # 输出目录
TRIM_BEG_SPACE: bool = False  # 是否删除段落开头缩进,默认False
PARAGRAPH_SPLIT: bool = False  # 段落是否使用空行分隔(否则段落之间紧贴),默认True
SEP_BOOK: bool = True  # 是否每本书单独成文件.默认True
FORBID_CHARS: str = r'/\:*?"<>|'  # 文件名中不能出现的字符(请不要乱改)
SERIES_NAME_BEFORE_TITLE: bool = True  # 书文件名前是否添加系列名称.只当设置SEP_BOOK时有意义.默认为True
FETCH_PIC: bool = True  # 是否抓取图片.如启用,生成的md文件会难以预览.生成的电子书文件没有此问题.默认为True
HTTP_PROXY_SERVER: Optional[str] = "localhost"  # 代理服务器地址(留空为None)
HTTP_PROXY_PORT: Optional[int] = 1082  # 代理服务器端口(留空为None)
COVER_IMG_PATH: Optional[str] = None  # 封面图片路径,无需加转义引号.(留空为None)
GEN_OPTION: GenOpt = GenOpt.Mobi  # 填入生成选项
PANDOC_PATH: str = "./bin/pandoc.exe"  # pandoc可执行文件路径(请不要乱改)
KINDLEGEN_PATH: str = "./bin/kindlegen.exe"  # kindlegen可执行文件路径(请不要乱改)
# --- 配置项 ---

proxies = {
    'http': 'http://' + HTTP_PROXY_SERVER + ':' + str(HTTP_PROXY_PORT),
    'https': 'http://' + HTTP_PROXY_SERVER + ':' + str(HTTP_PROXY_PORT),
}


# def method_retry_builder(func: Callable[..., Any]) -> Callable[..., Any]:
#     def r(inst, *args, **kwargs):
#         while True:
#             try:
#                 return func(inst, *args, **kwargs)
#             except ProxyError:
#                 continue
#             except SSLError:
#                 continue
#
#     return r


def func_retry_builder(func: Callable[..., Any]) -> Callable[..., Any]:
    def r(*args, **kwargs):
        while True:
            try:
                return func(*args, **kwargs)
            except ProxyError:
                continue
            except SSLError:
                continue

    return r


get = func_retry_builder(requests.get)


# def encode_param_builder(func: Callable[..., Any]) -> Callable[..., Any]:
#     def result(inst, encoding=None, url=None, html=None, *args, **kwargs):
#         # 如传入HTML,直接使用HTML.
#         # 指定encoding时,必须指定url.
#         if html:
#             return func(inst, url=url, html=html, *args, **kwargs)
#         elif url:
#             if encoding:
#                 r: requests.Response = get(url)
#                 r.encoding = encoding
#                 return func(inst, html=r.text, *args, **kwargs)
#             else:
#                 return func(inst, url=url, *args, **kwargs)
#         else:  # 调用错误,直接传下去引发错误
#             return func(inst, url=url, html=html, *args, **kwargs)
#
#     return result


# build = encode_param_builder(method_retry_builder(AutoScraper.build))
# get_result_similar = encode_param_builder(method_retry_builder(AutoScraper.get_result_similar))
# get_result_exact = encode_param_builder(method_retry_builder(AutoScraper.get_result_exact))


# def get_toc_url(book_url: str) -> str:
#     url = "https://www.wenku8.net/book/2231.htm"
#     wl = ["https://www.wenku8.net/novel/2/2231/index.htm"]
#     s = AutoScraper()
#     build(s, url, wl, request_args={"proxies": proxies})
#     return get_result_exact(s, book_url)[0]


class ChaptInfo(NamedTuple):
    title: str
    url: str


class BookInfo(NamedTuple):
    title: str
    chapt_infos: List[ChaptInfo]


class ChaptText(NamedTuple):
    title: str
    text: str


class BookText(NamedTuple):
    title: str
    chapt_texts: List[ChaptText]


def remove_char(arg: str, chars: str) -> str:
    for c in chars:
        arg = arg.replace(c, "")
    return arg


def get_tree(url: str) -> BeautifulSoup:
    encodings = ["gb18030", "utf_8", "gbk", "gb2312", "cp950", "big5", "hz"]
    r: requests.Response = get(url)
    txt: Optional[str] = None
    for e in encodings:
        try:
            txt = r.content.decode(e)
        except UnicodeDecodeError:
            continue
    if txt is None:
        raise UnicodeDecodeError("All tried", b'', 0, 1, "不能解码网页")
    return BeautifulSoup(txt, "html.parser")


def mdttl(ttl_lvl: int):
    if ttl_lvl <= 0 or ttl_lvl >= 7:
        raise ValueError("Md doesn't support level {} title.".format(ttl_lvl))
    return "#" * ttl_lvl + " "


METADATA_TEMPLATE = r'''<dc:title>{}</dc:title>
<dc:creator>{}</dc:creator>
<dc:rights>请给RealXuche的生成工具点star!</dc:rights>
<dc:language>zh-CN</dc:language>'''


def make(url) -> ():
    if (GEN_OPTION is GenOpt.SepPicMarkdown) or (GEN_OPTION is GenOpt.PlainText):
        raise NotImplementedError("暂时不支持的生成格式.欢迎PR.")
    (book_inf, author, series_ttl) = fetch_bookinf(url)
    book_txt = fetch_text(book_inf)
    #
    mdfile_list = write_md(book_txt, series_ttl)
    if GEN_OPTION is GenOpt.StandaloneMarkdown:
        return
    #
    epub_list = gen_epub(mdfile_list, author)
    remove_files(mdfile_list)
    if GEN_OPTION is GenOpt.Epub:
        return
    #
    if GEN_OPTION is GenOpt.Mobi:
        gen_mobi(epub_list)
        remove_files(epub_list)
        return
    else:
        raise NotImplementedError("未知的生成格式.")


def remove_files(f: List[str]) -> ():
    for file in f:
        (p(OUT_DIR) / file).unlink(missing_ok=True)
    return


def gen_mobi(file_list: List[str]) -> ():
    for file in file_list:
        cmd = r'"{}" "{}"'.format(str(p(KINDLEGEN_PATH)), str(p(OUT_DIR) / file))
        run(cmd, shell=True)
    return


def main():
    p(OUT_DIR).mkdir(exist_ok=True)
    url = "https://www.wenku8.net/novel/2/2231/index.htm"
    make(url)


def gen_epub(file_list: List[str], author: str) -> List[str]:
    epub_cmdt: str
    epub_list = []
    pp = '"{}"'.format(str(p(PANDOC_PATH)))  # pandoc path
    if COVER_IMG_PATH is None:
        epub_cmdt = pp + r' -s "{}.md" -t epub -o "{}.epub" --epub-metadata metadata.xml --toc'
    else:
        epub_cmdt = pp + r' -s "{}.md" -t epub -o "{}.epub" --epub-metadata metadata.xml --epub-cover-image "{}" --toc'
    for fname in file_list:
        cmd: str
        ttl = fname.removesuffix(".md")
        epub_list.append(ttl + ".epub")
        fstem = str(p(OUT_DIR) / ttl)
        with open("metadata.xml", "w", encoding="utf_8") as f:
            f.write(METADATA_TEMPLATE.format(ttl, author))
        #
        if COVER_IMG_PATH is None:
            cmd = epub_cmdt.format(fstem, fstem)
        else:
            cmd = epub_cmdt.format(fstem, fstem, COVER_IMG_PATH)
        run(cmd, shell=True, stderr=PIPE, check=True)
    p("metadata.xml").unlink(missing_ok=True)
    return epub_list


def write_md(book_txt: List[BookText], series_ttl: str) -> List[str]:
    # 这坨逻辑密度过高,估计维护难度很成问题
    file_list = []
    if not SEP_BOOK:  # 移除已经存在的文件
        (p(OUT_DIR) / remove_char(series_ttl + ".md", FORBID_CHARS)).unlink(missing_ok=True)
    for (idx, book) in enumerate(book_txt):
        if SEP_BOOK:
            if SERIES_NAME_BEFORE_TITLE:
                fnam = remove_char(series_ttl + " " + book.title, FORBID_CHARS) + ".md"
            else:
                fnam = remove_char(book.title, FORBID_CHARS) + ".md"
            (p(OUT_DIR) / fnam).unlink(missing_ok=True)
        else:
            fnam = remove_char(series_ttl, FORBID_CHARS) + ".md"
        with open(str(p(OUT_DIR) / fnam), "a", encoding="utf_8") as f:
            file_list.append(fnam)
            # ttlvl:基础标题等级,如果要写入单文件,系列名就会占据最高级标题,这种时候基础值加一就能让卷名和章节名标题等级都加一.
            ttlvl: int = 1 if GEN_OPTION is GenOpt.StandaloneMarkdown else 0
            if not SEP_BOOK:  # 如果是系列合集
                if idx == 0 and GEN_OPTION is GenOpt.StandaloneMarkdown:
                    f.write(mdttl(ttlvl) + series_ttl + "\n")
                ttlvl = 2 if GEN_OPTION is GenOpt.StandaloneMarkdown else 1
                f.write("\n" + mdttl(ttlvl) + book.title + "\n")
            elif GEN_OPTION is GenOpt.StandaloneMarkdown:
                # 如果不是系列合集,就只应当在输出MD时用大标题写卷名,因为电子书格式会自动写卷名，就不用特地重复写一遍了.
                f.write(mdttl(ttlvl) + book.title + "\n")
            for chapt in book.chapt_texts:
                f.write("\n" + mdttl(ttlvl + 1) + chapt.title + "\n")
                f.write(chapt.text + "\n")
    return file_list
    pass


def fetch_bookinf(tocurl: str) -> (List[BookInfo], str, str):
    book_inf: List[BookInfo] = []
    tocurl = tocurl.strip()
    tree = get_tree(tocurl)
    for node in tree.select("table")[0]:  # 选中并遍历目录
        if node.name != "tr":
            continue
        #
        if ttl := node.select('tr td[colspan="4"]'):
            book_title = str(ttl[0].string)
            book_inf.append(BookInfo(book_title, []))
        else:
            entries = node.select("td a")
            for chapter in entries:
                chapt_ttl = str(chapter.string)
                book_inf[-1].chapt_infos.append(
                    ChaptInfo(chapt_ttl,
                              urljoin(tocurl, chapter["href"]))
                )
    author = tree.select("div#info")[0].string.removeprefix(r"作者：").strip()
    series_ttl = tree.select("div#title")[0].string.strip()
    return book_inf, author, series_ttl


def fetch_text(book_inf: List[BookInfo]) -> List[BookText]:
    bk_txt: List[BookText] = []
    for book in book_inf:
        bk_txt.append(BookText(book.title, []))
        for chapt in book.chapt_infos:
            inner_txt = ""
            url = chapt.url
            content = get_tree(url).select("div#content")[0]
            for node in content:
                if node.name == "ul":  # 出处链接,忽略
                    continue
                elif node.name == "div" and node["class"] == ["divimage"] and FETCH_PIC:  # 插图处理
                    purl = node.contents[0]["href"]
                    # 获取类型
                    (typ, _) = guess_type(purl)
                    if typ is None:
                        raise TypeError("Cannot guess type for picture '{}'.".format(purl))
                    r = get(purl)  # 获取图片
                    # 生成内嵌代码
                    inner_txt = inner_txt + "![](data:{};base64,{})\n".format(typ, b64enc(r.content).decode())
                elif node.name == "br":  # 换行符
                    if PARAGRAPH_SPLIT:
                        inner_txt = inner_txt + "\n"
                    else:
                        inner_txt = inner_txt if inner_txt.endswith("  \n") else (inner_txt + "  \n")
                else:  # 小说文本
                    node = node.string.strip("\r\n")  # br才是决定显示效果的换行,忽略文本中的\r\n
                    if TRIM_BEG_SPACE:
                        node = node.strip()
                    inner_txt = inner_txt + node
            inner_txt = inner_txt.rstrip()
            inner_txt = inner_txt.lstrip("\r\n")
            bk_txt[-1].chapt_texts.append(
                ChaptText(
                    chapt.title,
                    inner_txt
                ))
    return bk_txt


if __name__ == '__main__':
    main()
