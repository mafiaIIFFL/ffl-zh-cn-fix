#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FFL 中文翻译及修复补丁

面向 Mafia II: Definitive Edition + Friends for Life 1.1。
只使用 Python 标准库，不分发游戏/模组原始资源。

核心工作：
1. 为 FFL content 补充 Chinesesimp 挂载（以及兼容性 MainMenuTdbFile）。
2. 将 FFL 英文 gui-main_dlc_zfl.sds 复制到 sds_sc/gui，并规范 ResourceInfo 顺序。
3. 将 77010001~77010018 合并进 pc/sds_sc/text/text_default.sds 的主 TextDatabase。
4. 自动备份、状态检查、恢复。
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import sys
import tempfile
import xml.etree.ElementTree as ET
import zlib

PROJECT_NAME = "FFL中文翻译及修复补丁"
VERSION = "1.0.3"

# FFL 1.1 在不同来源/历史版本中可能使用不同 DLC 文件夹名。
# 启动时会自动检测实际目录，不要求玩家重命名模组文件夹。
FFL_DIR_CANDIDATES = ("cnt_friendsforlife", "cnt_friends_for_life")
REL_CONTENT = Path("pc/dlcs/cnt_friendsforlife/content")
REL_ZFL_EN = Path("pc/dlcs/cnt_friendsforlife/sds_en/gui/gui-main_dlc_zfl.sds")
REL_ZFL_SC = Path("pc/dlcs/cnt_friendsforlife/sds_sc/gui/gui-main_dlc_zfl.sds")
REL_TEXT_DEFAULT = Path("pc/sds_sc/text/text_default.sds")
BACKUP_ROOT = Path("FFL_ZH_CN_BACKUP")

# 本项目实际验证时使用的文件哈希。不同发行渠道/更新版本可能不同，
# 因此默认只警告，不强制拒绝；SDS 结构校验仍会严格执行。
KNOWN_HASHES = {
    "text_default_epic_tested": "6b6ba43220997900fafe2c5fc765ea7d1dae8057017f3d3dbd7822c30c2c7efe",
    "zfl_en_tested": "d7c5980e8549acad6086de966ab6b4bdae0eafe494d866e54d8bf293014303a8",
    "text_default_patched_verified": "4260635d00c95ca9c12195f3b0e8a32b7275c4c09ded3ec65c3912ab96477543",
}


class PatchError(RuntimeError):
    pass


def app_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def load_translations() -> list[dict[str, str]]:
    p = app_dir() / "translations" / "zh-CN.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        raise PatchError(f"无法读取翻译表：{p}\n{e}") from e
    items = data.get("entries", [])
    if len(items) != 18:
        raise PatchError(f"翻译表应包含 18 条，实际为 {len(items)} 条。")
    return items


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fnv1(data: bytes) -> int:
    h = 0x811C9DC5
    for x in data:
        h = (h * 0x01000193) & 0xFFFFFFFF
        h ^= x
    return h


def safe_bytes(payload: bytes) -> bytes:
    return payload + struct.pack("<I", fnv1(payload))


def parse_sds(path: Path) -> dict:
    b = path.read_bytes()
    if len(b) < 80:
        raise PatchError(f"SDS 文件过小或损坏：{path}")

    if fnv1(b[:12]) != struct.unpack_from("<I", b, 12)[0]:
        raise PatchError(f"SDS 顶层校验失败：{path}")

    magic = b[:4]
    if magic != b"SDS\x00":
        raise PatchError(f"不是受支持的 SDS 文件：{path}")

    version = struct.unpack_from("<I", b, 4)[0]
    if version not in (19, 20):
        raise PatchError(f"不支持的 SDS 版本 {version}：{path}")
    platform = b[8:12]

    hp = b[16:68]
    if fnv1(hp) != struct.unpack_from("<I", b, 68)[0]:
        raise PatchError(f"SDS 文件头校验失败：{path}")

    vals = struct.unpack("<8I16sI", hp)
    hdr = dict(zip(
        ["type_off", "block_off", "xml_off", "slotram", "slotvram",
         "otherram", "othervram", "flags", "unknown", "count"],
        vals,
    ))

    off = hdr["type_off"]
    n = struct.unpack_from("<I", b, off)[0]
    off += 4
    types = []
    for _ in range(n):
        rid = struct.unpack_from("<I", b, off)[0]
        off += 4
        ln = struct.unpack_from("<i", b, off)[0]
        off += 4
        if ln < 0 or off + ln > len(b):
            raise PatchError(f"SDS 资源类型表异常：{path}")
        nm = b[off:off + ln].decode("cp1252")
        off += ln
        parent = struct.unpack_from("<I", b, off)[0]
        off += 4
        types.append((rid, nm, parent))
    if off != hdr["block_off"]:
        raise PatchError(f"SDS 资源类型表与块表偏移不一致：{path}")

    boff = off
    magic2, align_raw = struct.unpack_from("<II", b, boff)
    flags2 = b[boff + 8]
    boff += 9
    if magic2 != 0x6C7A4555 or flags2 != 4:  # 'UEzl'
        raise PatchError(f"不支持的 SDS block 格式：{path}")

    virtual = bytearray()
    while True:
        if boff + 5 > len(b):
            raise PatchError(f"SDS block 表被截断：{path}")
        size = struct.unpack_from("<I", b, boff)[0]
        comp = b[boff + 4]
        boff += 5
        if size == 0:
            break
        if comp:
            if boff + 32 > len(b):
                raise PatchError(f"SDS 压缩块头被截断：{path}")
            u_size, hsize, chunk_size, chunk_count, unk, *chunks = struct.unpack_from(
                "<IIhhI8H", b, boff
            )
            boff += 32
            csize = sum(chunks)
            cdat = b[boff:boff + csize]
            boff += csize
            try:
                dat = zlib.decompress(cdat)
            except zlib.error as e:
                raise PatchError(f"SDS zlib 解压失败：{path}\n{e}") from e
            if len(dat) != u_size:
                raise PatchError(f"SDS 解压长度不匹配：{path}")
            virtual.extend(dat)
        else:
            dat = b[boff:boff + size]
            boff += size
            virtual.extend(dat)

    if boff != hdr["xml_off"]:
        raise PatchError(f"SDS XML 偏移异常：{path}")

    vo = 0
    resources = []
    header_size = 34 if version == 20 else 26
    safe_size = header_size + 4
    for _ in range(hdr["count"]):
        if vo + safe_size > len(virtual):
            raise PatchError(f"SDS 资源头被截断：{path}")
        rh = bytes(virtual[vo:vo + header_size])
        vo += header_size
        stored = struct.unpack_from("<I", virtual, vo)[0]
        vo += 4
        if fnv1(rh) != stored:
            raise PatchError(f"SDS 资源头校验失败：{path}")

        if version == 19:
            typeid, size, rv, slotram, slotvram, otherram, othervram = struct.unpack(
                "<IIHIIII", rh
            )
            dlen = size - 30
        else:
            # 本项目目标是 M2DE(version 19)。保留 version 20 解析错误提示，
            # 避免静默损坏其他游戏文件。
            raise PatchError("当前补丁仅支持 Mafia II / Mafia II Definitive Edition 的 SDS v19。")

        if dlen < 0 or vo + dlen > len(virtual):
            raise PatchError(f"SDS 资源长度异常：{path}")
        data = bytes(virtual[vo:vo + dlen])
        vo += dlen
        resources.append({
            "typeid": typeid,
            "size": size,
            "version": rv,
            "slotram": slotram,
            "slotvram": slotvram,
            "otherram": otherram,
            "othervram": othervram,
            "data": data,
        })

    if vo != len(virtual):
        raise PatchError(f"SDS 资源区存在未识别数据：{path}")

    xml = b[hdr["xml_off"]:]
    try:
        ET.fromstring(xml.decode("ascii"))
    except Exception as e:
        raise PatchError(f"SDS ResourceInfo XML 无法解析：{path}\n{e}") from e

    return {
        "raw": b,
        "magic": magic,
        "version": version,
        "platform": platform,
        "hdr": hdr,
        "types": types,
        "alignment": align_raw & 0xFFFFFF,
        "resources": resources,
        "xml": xml,
    }


def resource_virtual_bytes(resources: list[dict]) -> bytes:
    out = bytearray()
    for r in resources:
        size = 30 + len(r["data"])
        rh = struct.pack(
            "<IIHIIII",
            r["typeid"], size, r["version"], r["slotram"], r["slotvram"],
            r["otherram"], r["othervram"],
        )
        out.extend(safe_bytes(rh))
        out.extend(r["data"])
    return bytes(out)


def serialize_sds(parsed: dict, resources: list[dict] | None = None,
                  xml: bytes | None = None) -> bytes:
    resources = resources if resources is not None else parsed["resources"]
    xml = xml if xml is not None else parsed["xml"]

    out = bytearray()
    first = parsed["magic"] + struct.pack("<I", parsed["version"]) + parsed["platform"]
    out.extend(safe_bytes(first))
    header_pos = len(out)
    out.extend(b"\0" * 56)

    type_off = len(out)
    out.extend(struct.pack("<I", len(parsed["types"])))
    for rid, nm, parent in parsed["types"]:
        nb = nm.encode("cp1252")
        out.extend(struct.pack("<Ii", rid, len(nb)))
        out.extend(nb)
        out.extend(struct.pack("<I", parent))

    block_off = len(out)
    align = parsed["alignment"]
    out.extend(struct.pack("<II", 0x6C7A4555, align))
    out.append(4)

    virtual = resource_virtual_bytes(resources)
    for pos in range(0, len(virtual), align):
        block = virtual[pos:pos + align]
        c = zlib.compress(block, 9)
        if len(c) < len(block):
            out.extend(struct.pack("<I", 32 + len(c)))
            out.append(1)
            chunks = [len(c)] + [0] * 7
            out.extend(struct.pack(
                "<IIhhI8H", len(block), 32, align, 1, 135200769, *chunks
            ))
            out.extend(c)
        else:
            out.extend(struct.pack("<I", len(block)))
            out.append(0)
            out.extend(block)

    out.extend(struct.pack("<I", 0))
    out.append(0)
    xml_off = len(out)
    out.extend(xml)

    hdr = parsed["hdr"]
    hp = struct.pack(
        "<8I16sI",
        type_off,
        block_off,
        xml_off,
        sum(r["slotram"] for r in resources),
        sum(r["slotvram"] for r in resources),
        sum(r["otherram"] for r in resources),
        sum(r["othervram"] for r in resources),
        1,
        hdr["unknown"],
        len(resources),
    )
    out[header_pos:header_pos + 56] = safe_bytes(hp)
    return bytes(out)


def parse_memfile(data: bytes) -> tuple[bytes, int, bytes]:
    if len(data) < 16:
        raise PatchError("MemFile 资源过短。")
    nlen = struct.unpack_from("<I", data, 0)[0]
    if 4 + nlen + 8 > len(data):
        raise PatchError("MemFile 文件名长度异常。")
    name = data[4:4 + nlen]
    pos = 4 + nlen
    unk1 = struct.unpack_from("<I", data, pos)[0]
    pos += 4
    ln = struct.unpack_from("<I", data, pos)[0]
    pos += 4
    payload = data[pos:pos + ln]
    if len(payload) != ln:
        raise PatchError("MemFile 数据长度异常。")
    return name, unk1, payload


def build_memfile(name: bytes, unk1: int, payload: bytes) -> bytes:
    return (
        struct.pack("<I", len(name)) + name +
        struct.pack("<II", unk1, len(payload)) + payload
    )


def patch_text_default(path: Path, entries: list[dict[str, str]]) -> None:
    parsed = parse_sds(path)

    # 在 ResourceInfo XML 中定位主 /tables/TextDatabase.dat。
    xml_text = parsed["xml"].decode("ascii")
    root = ET.fromstring(xml_text)
    infos = root.findall("ResourceInfo")
    target_idx = None
    for idx, ri in enumerate(infos):
        if ri.findtext("SourceDataDescription") == "/tables/TextDatabase.dat":
            target_idx = idx
            break
    if target_idx is None or target_idx >= len(parsed["resources"]):
        raise PatchError("未在 text_default.sds 中找到 /tables/TextDatabase.dat。")

    resources = [dict(r) for r in parsed["resources"]]
    r = resources[target_idx]
    name, unk1, payload = parse_memfile(r["data"])
    if payload[:3] != b"\xef\xbb\xbf":
        raise PatchError("主 TextDatabase.dat 不是预期的 UTF-8 BOM 文本格式。")

    text = payload.decode("utf-8-sig")
    # 保持主库原有 CRLF 风格。
    line_ending = "\r\n" if "\r\n" in text else "\n"

    # 先替换已存在的 FFL ID，避免重复安装。
    missing: list[dict[str, str]] = []
    for item in entries:
        key = item["key"]
        zh = item["zh_cn"]
        pattern = re.compile(rf"(?m)^{re.escape(key)}:.*$")
        replacement = f"{key}:{zh}"
        if pattern.search(text):
            text = pattern.sub(replacement, text, count=1)
        else:
            missing.append(item)

    if missing:
        insert_text = "".join(
            f"{item['key']}:{item['zh_cn']}{line_ending}" for item in missing
        )
        marker = "00_77_04_0001:"
        if marker in text:
            text = text.replace(marker, insert_text + marker, 1)
        else:
            if text and not text.endswith(("\n", "\r")):
                text += line_ending
            text += insert_text

    new_payload = b"\xef\xbb\xbf" + text.encode("utf-8")
    r["data"] = build_memfile(name, unk1, new_payload)
    r["slotram"] = len(new_payload)
    resources[target_idx] = r

    # 同步 ResourceInfo 中对应资源的 SlotRamRequired。
    pat = re.compile(
        r"(<SourceDataDescription>/tables/TextDatabase\.dat</SourceDataDescription>"
        r".*?<SlotRamRequired __type=['\"]Int['\"]>)(\d+)(</SlotRamRequired>)",
        re.S,
    )
    m = pat.search(xml_text)
    if not m:
        raise PatchError("无法更新 TextDatabase.dat 的 ResourceInfo 内存大小。")
    new_xml_text = xml_text[:m.start(2)] + str(len(new_payload)) + xml_text[m.end(2):]
    new_xml = new_xml_text.encode("ascii")

    candidate = serialize_sds(parsed, resources, new_xml)

    # 写入前在内存里严格自检。
    tmp = path.with_name(path.name + ".ffl_tmp")
    tmp.write_bytes(candidate)
    try:
        check = parse_sds(tmp)
        # 除主文本资源外，其他资源必须保持逐字节一致。
        for idx, (old_r, new_r) in enumerate(zip(parsed["resources"], check["resources"])):
            if idx != target_idx and old_r["data"] != new_r["data"]:
                raise PatchError(f"安全检查失败：资源 {idx} 被意外修改。")

        c_name, _, c_payload = parse_memfile(check["resources"][target_idx]["data"])
        c_text = c_payload.decode("utf-8-sig")
        for item in entries:
            expected = f"{item['key']}:{item['zh_cn']}"
            if expected not in c_text:
                raise PatchError(f"安全检查失败：未写入 {item['key']}。")

        # 再序列化一次必须字节级一致，证明结构稳定。
        if serialize_sds(check) != candidate:
            raise PatchError("安全检查失败：SDS 无法稳定 round-trip。")
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass

    path.write_bytes(candidate)


def normalize_zfl_resourceinfo(src: Path, dst: Path) -> None:
    """复制 ZFL SDS，并复现最终验证环境中的 ResourceInfo 规范化。

    该调整本身不是 770100xx 的根因，但最终成功环境包含它；v1.0 为了
    最大程度复现已验证状态保留此兼容性处理。只重排 XML 元数据，不改资源体。
    """
    b = src.read_bytes()
    parsed = parse_sds(src)
    xml_off = parsed["hdr"]["xml_off"]
    xml_text = b[xml_off:].decode("ascii")

    pattern = re.compile(r"(\s*<ResourceInfo>.*?</ResourceInfo>)", re.S)
    blocks = pattern.findall(xml_text)
    if len(blocks) < 9:
        # 非已知 FFL 结构时不冒险修改，只复制。
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return

    def desc(block: str) -> str:
        m = re.search(r"<SourceDataDescription>(.*?)</SourceDataDescription>", block, re.S)
        return m.group(1) if m else ""

    tail = [desc(x) for x in blocks[-3:]]
    known_bad = [
        "/tables/TextDatabase_MainMenu_ZFL.dat",
        "/config/gui/dlcs/ZaharForLife/Screens/MainMenu/DLC_ZFL_Loading",
        "/config/gui/dlcs/ZaharForLife/Screens/MainMenu/DLC_ZFL_SaveSlot",
    ]
    known_good = [
        "/config/gui/dlcs/ZaharForLife/Screens/MainMenu/DLC_ZFL_Loading",
        "/config/gui/dlcs/ZaharForLife/Screens/MainMenu/DLC_ZFL_SaveSlot",
        "/tables/TextDatabase_MainMenu_ZFL.dat",
    ]

    if tail == known_bad:
        new_blocks = blocks.copy()
        new_blocks[-3], new_blocks[-2], new_blocks[-1] = blocks[-2], blocks[-1], blocks[-3]
        it = iter(new_blocks)
        new_xml_text = pattern.sub(lambda _m: next(it), xml_text)
        new_xml = new_xml_text.encode("ascii")
        if len(new_xml) != len(b[xml_off:]):
            raise PatchError("ZFL ResourceInfo 规范化导致 XML 长度变化，已中止。")
        out = b[:xml_off] + new_xml
    elif tail == known_good:
        out = b
    else:
        # 未知版本：不做这个非必要规范化，但仍复制到 sds_sc。
        out = b

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(out)
    # 确保复制后的 SDS 仍能完整解析。
    parse_sds(dst)


def _decode_text_preserve(raw: bytes) -> tuple[str, bytes]:
    bom = b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b""
    payload = raw[len(bom):]
    try:
        return payload.decode("utf-8"), bom
    except UnicodeDecodeError as e:
        raise PatchError("FFL content 不是预期的 UTF-8 文本。") from e


def patch_content(path: Path) -> None:
    raw = path.read_bytes()
    text, bom = _decode_text_preserve(raw)
    nl = "\r\n" if "\r\n" in text else "\n"

    # Chinesesimp GameLine 挂载。
    if 'TriggerId="GameLine_3_Chinesesimp"' not in text:
        pat = re.compile(
            r'(?P<indent>^[ \t]*)<Mount TriggerId="GameLine_3_English">.*?'
            r'(?P=indent)</Mount>',
            re.M | re.S,
        )
        m = pat.search(text)
        if not m:
            raise PatchError("content 中找不到 GameLine_3_English Mount。")
        ind = m.group("indent")
        child = ind + "\t"
        block = nl.join([
            f'{ind}<Mount TriggerId="GameLine_3_Chinesesimp">',
            f'{child}<Src>/sds_sc</Src>',
            f'{child}<Dst>/sds</Dst>',
            f'{child}<Files>',
            f'{child}\t<File Name="/gui/gui-main_dlc_zfl.sds" />',
            f'{child}</Files>',
            f'{ind}</Mount>',
        ])
        text = text[:m.end()] + nl + block + text[m.end():]

    # 语言级 Chinesesimp 挂载。
    if 'TriggerId="Chinesesimp"' not in text:
        pat = re.compile(
            r'(?P<indent>^[ \t]*)<Mount TriggerId="English">.*?'
            r'(?P=indent)</Mount>',
            re.M | re.S,
        )
        m = pat.search(text)
        if not m:
            raise PatchError("content 中找不到 English Mount。")
        ind = m.group("indent")
        child = ind + "\t"
        block = nl.join([
            f'{ind}<Mount TriggerId="Chinesesimp">',
            f'{child}<Src>/sds_sc/gui</Src>',
            f'{child}<Dst>/sds/gui</Dst>',
            f'{child}<Files>',
            f'{child}\t<File Name="/gui-main_dlc_zfl.sds" />',
            f'{child}</Files>',
            f'{ind}</Mount>',
        ])
        text = text[:m.end()] + nl + block + text[m.end():]

    # 最终成功环境中保留的显式注册参数；不是根因，但用于复现实测状态。
    if "MainMenuTdbFile" not in text:
        line_pat = re.compile(
            r'(?m)^(?P<indent>[ \t]*)<Param Name="GuiSDS">/sds/gui/gui-main_dlc_zfl</Param>\s*$'
        )
        m = line_pat.search(text)
        if not m:
            raise PatchError("content 中找不到 FFL GuiSDS 参数。")
        ind = m.group("indent")
        add = f'{ind}<Param Name="MainMenuTdbFile">/tables/TextDatabase_MainMenu_ZFL.dat</Param>'
        text = text[:m.end()] + nl + add + text[m.end():]

    path.write_bytes(bom + text.encode("utf-8"))


def detect_ffl_dir(game_dir: Path) -> str:
    """检测当前游戏实际使用的 Friends for Life DLC 文件夹。"""
    dlcs = game_dir / "pc" / "dlcs"
    if not dlcs.is_dir():
        raise PatchError(f"游戏目录中找不到 pc\\dlcs：{dlcs}")

    def looks_like_ffl(base: Path) -> bool:
        return (
            (base / "content").is_file()
            and (base / "sds_en" / "gui" / "gui-main_dlc_zfl.sds").is_file()
        )

    # 先尝试已知的两个常见目录名。
    for name in FFL_DIR_CANDIDATES:
        if looks_like_ffl(dlcs / name):
            return name

    # 再扫描 dlcs 下其它目录，避免第三方打包改名。
    for base in dlcs.iterdir():
        if base.is_dir() and looks_like_ffl(base):
            return base.name

    found_dirs = sorted(p.name for p in dlcs.iterdir() if p.is_dir())
    listing = "\n".join(f"  - {x}" for x in found_dirs) if found_dirs else "  （未发现任何 DLC 子目录）"
    raise PatchError(
        "未检测到 Friends for Life 1.1。\n"
        "安装器已扫描 pc\\dlcs 下的所有 DLC 文件夹，但没有找到同时包含：\n"
        "- content\n"
        "- sds_en\\gui\\gui-main_dlc_zfl.sds\n\n"
        "实际扫描到的 DLC 目录：\n" + listing + "\n\n"
        "请确认 FFL 1.1 已安装到当前游戏目录。"
    )


def configure_ffl_paths(game_dir: Path) -> str:
    global REL_CONTENT, REL_ZFL_EN, REL_ZFL_SC
    name = detect_ffl_dir(game_dir)
    base = Path("pc/dlcs") / name
    REL_CONTENT = base / "content"
    REL_ZFL_EN = base / "sds_en/gui/gui-main_dlc_zfl.sds"
    REL_ZFL_SC = base / "sds_sc/gui/gui-main_dlc_zfl.sds"
    return name


def validate_game_dir(game_dir: Path) -> None:
    ffl_name = configure_ffl_paths(game_dir)
    missing = []
    for rel in (REL_CONTENT, REL_ZFL_EN, REL_TEXT_DEFAULT):
        if not (game_dir / rel).is_file():
            missing.append(str(rel))
    if missing:
        raise PatchError(
            "游戏目录不完整。缺少：\n- " + "\n- ".join(missing)
        )
    print(f"[OK] 已检测到 Friends for Life：pc\\dlcs\\{ffl_name}")


def backup_files(game_dir: Path) -> Path:
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = game_dir / BACKUP_ROOT / stamp
    backup_dir.mkdir(parents=True, exist_ok=False)

    manifest = {
        "project": PROJECT_NAME,
        "version": VERSION,
        "created_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "files": [],
    }
    for rel in (REL_CONTENT, REL_ZFL_SC, REL_TEXT_DEFAULT):
        src = game_dir / rel
        existed = src.exists()
        item = {"path": rel.as_posix(), "existed": existed}
        if existed:
            dst = backup_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            item["sha256"] = sha256_file(src)
        manifest["files"].append(item)

    (backup_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return backup_dir


def find_latest_backup(game_dir: Path) -> Path:
    root = game_dir / BACKUP_ROOT
    if not root.is_dir():
        raise PatchError("没有找到自动备份。")
    candidates = sorted(
        (p for p in root.iterdir() if p.is_dir() and (p / "manifest.json").is_file()),
        reverse=True,
    )
    if not candidates:
        raise PatchError("没有找到可用备份。")
    return candidates[0]


def restore_backup(game_dir: Path, backup_dir: Path) -> None:
    manifest = json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))
    for item in manifest["files"]:
        rel = Path(item["path"])
        target = game_dir / rel
        if item["existed"]:
            src = backup_dir / rel
            if not src.is_file():
                raise PatchError(f"备份文件缺失：{src}")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
        else:
            if target.exists():
                target.unlink()


def textdb_has_ffl(path: Path, entries: list[dict[str, str]]) -> bool:
    try:
        parsed = parse_sds(path)
        root = ET.fromstring(parsed["xml"].decode("ascii"))
        infos = root.findall("ResourceInfo")
        idx = next(
            i for i, ri in enumerate(infos)
            if ri.findtext("SourceDataDescription") == "/tables/TextDatabase.dat"
        )
        _, _, payload = parse_memfile(parsed["resources"][idx]["data"])
        text = payload.decode("utf-8-sig")
        return all(f"{x['key']}:{x['zh_cn']}" in text for x in entries)
    except Exception:
        return False



def textdb_ffl_details(path: Path, entries: list[dict[str, str]]) -> tuple[list[str], list[str]]:
    """Return (present keys, missing keys) from the active Simplified Chinese main TextDatabase."""
    parsed = parse_sds(path)
    root = ET.fromstring(parsed["xml"].decode("ascii"))
    infos = root.findall("ResourceInfo")
    idx = next(
        i for i, ri in enumerate(infos)
        if ri.findtext("SourceDataDescription") == "/tables/TextDatabase.dat"
    )
    _, _, payload = parse_memfile(parsed["resources"][idx]["data"])
    text = payload.decode("utf-8-sig")
    present, missing = [], []
    for x in entries:
        expected = f"{x['key']}:{x['zh_cn']}"
        (present if expected in text else missing).append(x["key"])
    return present, missing


def is_installed(game_dir: Path, entries: list[dict[str, str]]) -> bool:
    try:
        content = (game_dir / REL_CONTENT).read_bytes().decode("utf-8-sig", errors="replace")
        return (
            'TriggerId="GameLine_3_Chinesesimp"' in content
            and 'TriggerId="Chinesesimp"' in content
            and (game_dir / REL_ZFL_SC).is_file()
            and textdb_has_ffl(game_dir / REL_TEXT_DEFAULT, entries)
        )
    except Exception:
        return False

def install(game_dir: Path) -> None:
    validate_game_dir(game_dir)
    entries = load_translations()

    print(f"[{PROJECT_NAME} v{VERSION}]")
    print("正在检查文件……")
    if is_installed(game_dir, entries):
        print("检测到补丁已经完整安装：18/18 条简中 ID 均存在。")
        print("未重复修改，也未创建新的备份。")
        return

    text_hash_before = sha256_file(game_dir / REL_TEXT_DEFAULT)
    zfl_hash = sha256_file(game_dir / REL_ZFL_EN)
    print(f"原始 text_default SHA256: {text_hash_before}")
    print(f"FFL ZFL English SHA256:   {zfl_hash}")
    if text_hash_before != KNOWN_HASHES["text_default_epic_tested"]:
        print("[警告] 当前 text_default.sds 与实测干净 Epic 样本哈希不同。")
        print("       将继续依靠 SDS 结构校验，但建议确认游戏文件是否为原版。")
    if zfl_hash != KNOWN_HASHES["zfl_en_tested"]:
        print("[警告] 当前 FFL ZFL SDS 与实测 FFL 1.1 样本哈希不同。")

    # 在触碰游戏文件之前先解析原文件。
    parse_sds(game_dir / REL_TEXT_DEFAULT)
    parse_sds(game_dir / REL_ZFL_EN)

    backup_dir = backup_files(game_dir)
    print(f"自动备份：{backup_dir}")

    try:
        # 先在独立临时目录中生成全部候选文件。全部通过后才写回游戏。
        with tempfile.TemporaryDirectory(prefix="ffl_zh_cn_") as td:
            stage = Path(td)
            staged_content = stage / "content"
            staged_zfl = stage / "gui-main_dlc_zfl.sds"
            staged_text = stage / "text_default.sds"

            shutil.copy2(game_dir / REL_CONTENT, staged_content)
            shutil.copy2(game_dir / REL_TEXT_DEFAULT, staged_text)

            print("[1/3] 生成简中 FFL content……")
            patch_content(staged_content)
            print("[2/3] 生成简中 GUI SDS……")
            normalize_zfl_resourceinfo(game_dir / REL_ZFL_EN, staged_zfl)
            print("[3/3] 合并 77010001~77010018 到简中主文本库……")
            patch_text_default(staged_text, entries)

            present, missing = textdb_ffl_details(staged_text, entries)
            if missing:
                raise PatchError(
                    f"候选文本库验证失败：仅写入 {len(present)}/18 条；缺失："
                    + ", ".join(missing)
                )

            staged_hash = sha256_file(staged_text)
            print(f"候选 text_default SHA256: {staged_hash}")
            if text_hash_before == KNOWN_HASHES["text_default_epic_tested"]:
                expected = KNOWN_HASHES["text_default_patched_verified"]
                if staged_hash != expected:
                    raise PatchError(
                        "已知干净 Epic 样本生成结果与实机成功样本哈希不一致，已中止。\n"
                        f"期望：{expected}\n实际：{staged_hash}"
                    )
                print("[OK] 与此前实机成功的 text_default.sds 哈希完全一致。")

            # 候选文件全部通过，才开始应用。
            print("候选文件全部验证通过，开始应用……")
            (game_dir / REL_ZFL_SC).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(staged_content, game_dir / REL_CONTENT)
            shutil.copy2(staged_zfl, game_dir / REL_ZFL_SC)
            shutil.copy2(staged_text, game_dir / REL_TEXT_DEFAULT)

        # 对真正写入游戏目录的结果再次验证。
        present, missing = textdb_ffl_details(game_dir / REL_TEXT_DEFAULT, entries)
        if missing:
            raise PatchError("写入后验证失败，缺失：" + ", ".join(missing))
        if not is_installed(game_dir, entries):
            raise PatchError("写入后综合验证失败。")

    except Exception:
        print("安装过程中发生错误，正在自动回滚……")
        restore_backup(game_dir, backup_dir)
        print("[OK] 已恢复到本次安装前状态。")
        raise

    print("\n安装成功：18/18 条 FFL 简中文本已验证。")
    print(f"最终 text_default SHA256: {sha256_file(game_dir / REL_TEXT_DEFAULT)}")
    print("请将游戏语言设置为【简体中文】，进入：附加内容 → 一生挚友。")

def uninstall(game_dir: Path, backup: Path | None = None) -> None:
    backup = backup or find_latest_backup(game_dir)
    restore_backup(game_dir, backup)
    print(f"已恢复备份：{backup}")


def status(game_dir: Path) -> None:
    print(f"[{PROJECT_NAME} v{VERSION}] 状态检查")
    try:
        validate_game_dir(game_dir)
        print("[OK] 游戏目录与 FFL 1.1 关键文件存在")
    except PatchError as e:
        print(f"[X] {e}")
        return

    entries = load_translations()
    content = (game_dir / REL_CONTENT).read_bytes().decode("utf-8-sig", errors="replace")
    print("[{}] Chinesesimp GameLine Mount".format(
        "OK" if 'GameLine_3_Chinesesimp' in content else "--"
    ))
    print("[{}] Chinesesimp GUI Mount".format(
        "OK" if 'TriggerId="Chinesesimp"' in content else "--"
    ))
    print("[{}] sds_sc/gui/gui-main_dlc_zfl.sds".format(
        "OK" if (game_dir / REL_ZFL_SC).is_file() else "--"
    ))
    try:
        present, missing = textdb_ffl_details(game_dir / REL_TEXT_DEFAULT, entries)
        print(f"[{'OK' if not missing else '--'}] FFL 简中文本：{len(present)}/18")
        if missing:
            print("缺失 ID：" + ", ".join(missing))
    except Exception as e:
        print(f"[X] 无法读取简中主文本库：{e}")
    h = sha256_file(game_dir / REL_TEXT_DEFAULT)
    print(f"text_default SHA256: {h}")
    if h == KNOWN_HASHES["text_default_epic_tested"]:
        print("哈希状态：已知干净 Epic 简中原版")
    elif h == KNOWN_HASHES["text_default_patched_verified"]:
        print("哈希状态：已知实机成功 FFL 简中补丁版")
    else:
        print("哈希状态：未知/其他版本")

def guess_game_dir(value: str | None) -> Path:
    if value:
        p = Path(value.strip().strip('"')).expanduser().resolve()
        return p

    # 从当前目录尝试。
    here = Path.cwd()
    if (here / "pc").is_dir():
        return here

    print("请输入《Mafia II: Definitive Edition》游戏根目录（该目录内应有 pc 文件夹）：")
    raw = input("> ").strip().strip('"')
    if not raw:
        raise PatchError("未输入游戏目录。")
    return Path(raw).expanduser().resolve()


def main(argv: list[str] | None = None) -> int:
    print(f"[{PROJECT_NAME} v{VERSION}]")
    print("[启动] 自动检测 Friends for Life DLC 目录已启用")

    actual_argv = list(sys.argv[1:] if argv is None else argv)
    interactive_menu = len(actual_argv) == 0

    if interactive_menu:
        print("\n请选择操作：")
        print("  [1] 安装 / 修复补丁")
        print("  [2] 检查补丁状态")
        print("  [3] 卸载补丁并恢复最近一次自动备份")
        print("  [0] 退出")
        choice = input("> ").strip()
        mapping = {"1": "install", "2": "status", "3": "uninstall", "0": "exit"}
        command = mapping.get(choice)
        if command is None:
            print("无效选项。")
            input("\n按回车键退出……")
            return 2
        if command == "exit":
            return 0
        actual_argv = [command]

    parser = argparse.ArgumentParser(description=PROJECT_NAME)
    parser.add_argument("command", choices=["install", "uninstall", "status"])
    parser.add_argument("--game-dir", help="Mafia II Definitive Edition 游戏根目录")
    parser.add_argument("--backup", help="uninstall 时指定备份目录")
    args = parser.parse_args(actual_argv)

    rc = 0
    try:
        game_dir = guess_game_dir(args.game_dir)
        if args.command == "install":
            install(game_dir)
        elif args.command == "uninstall":
            # 卸载前也需要识别实际 FFL 目录，使 manifest 路径与当前安装一致。
            configure_ffl_paths(game_dir)
            b = Path(args.backup).resolve() if args.backup else None
            uninstall(game_dir, b)
        else:
            status(game_dir)
    except PatchError as e:
        print(f"\n[错误] {e}", file=sys.stderr)
        rc = 2
    except KeyboardInterrupt:
        print("\n已取消。")
        rc = 130

    if interactive_menu:
        input("\n按回车键退出……")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
