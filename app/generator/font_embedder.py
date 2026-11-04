from __future__ import annotations

import io
import logging
import os
import re
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from lxml import etree


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
NS = {"w": W_NS, "r": R_NS}
EMBED_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/font"
ODTTF_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.obfuscatedFont"


@dataclass(frozen=True)
class FontInfo:
    path: Path
    family: str
    aliases: tuple[str, ...]
    fs_type: int

    @property
    def restricted(self) -> bool:
        # Outline embedding cannot satisfy bitmap-only permissions.
        return bool(self.fs_type & (0x0002 | 0x0200))

    @property
    def no_subsetting(self) -> bool:
        return bool(self.fs_type & 0x0100)


def _decode_name(record) -> str:
    try:
        return record.toUnicode().strip()
    except Exception:
        return ""


def _preferred_family(names: list[str], fallback: str) -> str:
    for value in names:
        if any("\u4e00" <= char <= "\u9fff" for char in value):
            return value
    return names[0] if names else fallback


def inspect_font(path: Path) -> FontInfo:
    font = TTFont(path, lazy=True)
    names: list[str] = []
    for record in font["name"].names:
        if record.nameID in {1, 4, 6}:
            value = _decode_name(record)
            if value and value not in names:
                names.append(value)
    fs_type = int(getattr(font.get("OS/2"), "fsType", 0))
    font.close()
    family = _preferred_family(names, path.stem)
    aliases = tuple(dict.fromkeys([family, path.stem, *names]))
    return FontInfo(path=path, family=family, aliases=aliases, fs_type=fs_type)


def scan_fonts(fonts_dir: Path) -> list[FontInfo]:
    if not fonts_dir.exists():
        return []
    fonts = []
    for path in sorted(fonts_dir.iterdir()):
        if path.is_file() and path.suffix.lower() in {".ttf", ".otf"}:
            try:
                fonts.append(inspect_font(path))
            except Exception:
                logging.exception("无法读取字体：%s", path)
    return fonts


def _norm(value: str) -> str:
    return re.sub(r"[\s_-]+", "", value).casefold()


def _read_package(docx_path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(docx_path, "r") as package:
        return {item.filename: package.read(item.filename) for item in package.infolist()}


def _xml(data: bytes):
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('不支持含 DTD 或实体声明的模板')
    return etree.fromstring(data, parser=etree.XMLParser(remove_blank_text=False, recover=False, resolve_entities=False, no_network=True))


def _serialize(root) -> bytes:
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _story_parts(parts: dict[str, bytes]):
    for name, data in parts.items():
        if not name.startswith("word/") or not name.endswith(".xml"):
            continue
        if name in {"word/settings.xml", "word/fontTable.xml"}:
            continue
        yield name, data


def collect_document_text(parts: dict[str, bytes]) -> str:
    chunks: list[str] = []
    for _name, data in _story_parts(parts):
        try:
            root = _xml(data)
        except Exception:
            continue
        chunks.extend(node.text or "" for node in root.xpath(".//w:t", namespaces=NS))
    return "".join(chunks) + " 0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz—（）。，、；：！？《》·"


def collect_used_fonts(parts: dict[str, bytes]) -> set[str]:
    result: set[str] = set()
    for _name, data in _story_parts(parts):
        try:
            root = _xml(data)
        except Exception:
            continue
        for node in root.xpath(".//w:rFonts", namespaces=NS):
            for key in ("ascii", "hAnsi", "eastAsia", "cs"):
                value = node.get(f"{{{W_NS}}}{key}")
                if value:
                    result.add(value)
    return result


def apply_global_font(docx_path: Path, family: str) -> None:
    parts = _read_package(docx_path)
    targets = list(_story_parts(parts))
    for name, data in targets:
        try:
            root = _xml(data)
        except Exception:
            continue
        for run in root.xpath(".//w:r", namespaces=NS):
            r_pr = run.find(f"{{{W_NS}}}rPr")
            if r_pr is None:
                r_pr = etree.Element(f"{{{W_NS}}}rPr")
                run.insert(0, r_pr)
            r_fonts = r_pr.find(f"{{{W_NS}}}rFonts")
            if r_fonts is None:
                r_fonts = etree.Element(f"{{{W_NS}}}rFonts")
                r_pr.insert(0, r_fonts)
            for key in ("ascii", "hAnsi", "eastAsia", "cs"):
                r_fonts.set(f"{{{W_NS}}}{key}", family)
        for r_fonts in root.xpath(".//w:rPrDefault//w:rFonts | .//w:style//w:rFonts", namespaces=NS):
            for key in ("ascii", "hAnsi", "eastAsia", "cs"):
                r_fonts.set(f"{{{W_NS}}}{key}", family)
        parts[name] = _serialize(root)
    _write_package(docx_path, parts)


def _subset_font(font_info: FontInfo, text: str) -> bytes:
    if font_info.no_subsetting:
        return font_info.path.read_bytes()
    font = TTFont(font_info.path, recalcTimestamp=False)
    options = subset.Options()
    options.recalc_timestamp = False
    options.name_IDs = [0, 1, 2, 3, 4, 5, 6]
    options.name_legacy = True
    options.name_languages = ["*"]
    options.notdef_glyph = True
    options.notdef_outline = True
    options.recommended_glyphs = True
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(text=text)
    subsetter.subset(font)
    buffer = io.BytesIO()
    font.save(buffer)
    font.close()
    return buffer.getvalue()


def _obfuscate(font_bytes: bytes, key: uuid.UUID) -> bytes:
    data = bytearray(font_bytes)
    # ECMA-376 17.8.1: reverse the complete GUID byte sequence, not GUID's
    # mixed-endian Windows memory representation. Word uses this same key.
    key_bytes = key.bytes[::-1]
    for index in range(min(32, len(data))):
        data[index] ^= key_bytes[index % 16]
    return bytes(data)


def _ensure_settings(parts: dict[str, bytes]):
    name = "word/settings.xml"
    if name in parts:
        root = _xml(parts[name])
    else:
        root = etree.Element(f"{{{W_NS}}}settings", nsmap={"w": W_NS})
    for tag in ("embedTrueTypeFonts", "saveSubsetFonts"):
        if root.find(f"{{{W_NS}}}{tag}") is None:
            root.append(etree.Element(f"{{{W_NS}}}{tag}"))
    parts[name] = _serialize(root)


def _ensure_content_type(parts: dict[str, bytes]):
    root = _xml(parts["[Content_Types].xml"])
    exists = root.xpath("./ct:Default[@Extension='odttf']", namespaces={"ct": CT_NS})
    if not exists:
        node = etree.Element(f"{{{CT_NS}}}Default")
        node.set("Extension", "odttf")
        node.set("ContentType", ODTTF_CONTENT_TYPE)
        root.append(node)
    parts["[Content_Types].xml"] = _serialize(root)


def _font_table(parts: dict[str, bytes]):
    if "word/fontTable.xml" in parts:
        return _xml(parts["word/fontTable.xml"])
    return etree.Element(f"{{{W_NS}}}fonts", nsmap={"w": W_NS, "r": R_NS})


def _font_relationships(parts: dict[str, bytes]):
    name = "word/_rels/fontTable.xml.rels"
    if name in parts:
        return _xml(parts[name])
    return etree.Element(f"{{{PKG_REL_NS}}}Relationships")


def _next_rid(rel_root) -> str:
    used = {node.get("Id") for node in rel_root}
    index = 1
    while f"rId{index}" in used:
        index += 1
    return f"rId{index}"


def _set_font_entry(font_root, rel_root, family: str, target: str, key: uuid.UUID, subsetted=True):
    entries = font_root.xpath("./w:font[@w:name=$name]", namespaces=NS, name=family)
    entry = entries[0] if entries else etree.SubElement(font_root, f"{{{W_NS}}}font")
    entry.set(f"{{{W_NS}}}name", family)
    for old in entry.findall(f"{{{W_NS}}}embedRegular"):
        entry.remove(old)
    rid = _next_rid(rel_root)
    embed = etree.SubElement(entry, f"{{{W_NS}}}embedRegular")
    embed.set(f"{{{R_NS}}}id", rid)
    embed.set(f"{{{W_NS}}}fontKey", "{" + str(key).upper() + "}")
    embed.set(f"{{{W_NS}}}subsetted", "1" if subsetted else "0")
    relationship = etree.SubElement(rel_root, f"{{{PKG_REL_NS}}}Relationship")
    relationship.set("Id", rid)
    relationship.set("Type", EMBED_REL_TYPE)
    relationship.set("Target", target)


def _write_package(docx_path: Path, parts: dict[str, bytes]):
    temp_path = docx_path.with_name(docx_path.name + ".tmp")
    with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as package:
        for name, data in parts.items():
            package.writestr(name, data)
    os.replace(temp_path, docx_path)


def embed_fonts(docx_path: Path, fonts_dir: Path, selected_family: str | None = None) -> dict:
    fonts = scan_fonts(fonts_dir)
    parts = _read_package(docx_path)
    used = collect_used_fonts(parts)
    used_norm = {_norm(value) for value in used}
    selected_norm = _norm(selected_family) if selected_family else ""
    text = collect_document_text(parts)
    report = {"embedded": [], "skipped": [], "used_fonts": sorted(used)}
    candidates: list[FontInfo] = []
    for font in fonts:
        alias_norms = {_norm(alias) for alias in font.aliases}
        needed = bool(alias_norms & used_norm) or (selected_norm and selected_norm in alias_norms)
        if not needed:
            continue
        if font.restricted:
            report["skipped"].append({"font": font.family, "reason": "字体授权位禁止嵌入"})
            continue
        candidates.append(font)
    if not candidates:
        return report
    font_root = _font_table(parts)
    rel_root = _font_relationships(parts)
    for index, font in enumerate(candidates, start=1):
        subset_bytes = _subset_font(font, text)
        key = uuid.uuid4()
        part_name = f"word/fonts/embedded_{index}.odttf"
        target = f"fonts/embedded_{index}.odttf"
        parts[part_name] = _obfuscate(subset_bytes, key)
        matched_names = [name for name in used if _norm(name) in {_norm(a) for a in font.aliases}]
        family_names = matched_names or [font.family]
        for family in dict.fromkeys(family_names):
            _set_font_entry(font_root, rel_root, family, target, key, not font.no_subsetting)
        report["embedded"].append(
            {
                "font": font.family,
                "source_bytes": font.path.stat().st_size,
                "subset_bytes": len(subset_bytes),
                "part": part_name,
            }
        )
    parts["word/fontTable.xml"] = _serialize(font_root)
    parts["word/_rels/fontTable.xml.rels"] = _serialize(rel_root)
    _ensure_settings(parts)
    _ensure_content_type(parts)
    _write_package(docx_path, parts)
    validation = validate_embedded_fonts(docx_path)
    if not validation["valid"]:
        raise ValueError("字体封装校验失败：" + "；".join(validation["errors"]))
    report["validation"] = validation
    return report


def validate_embedded_fonts(docx_path: Path) -> dict:
    parts = _read_package(docx_path)
    errors = []
    checked_parts = []
    odttf = sorted(name for name in parts if name.startswith("word/fonts/") and name.endswith(".odttf"))
    if not odttf:
        errors.append("未发现 .odttf 字体部件")
    try:
        settings = _xml(parts["word/settings.xml"])
        for tag in ("embedTrueTypeFonts", "saveSubsetFonts"):
            if settings.find(f"{{{W_NS}}}{tag}") is None:
                errors.append(f"settings.xml 缺少 {tag}")
    except Exception:
        errors.append("settings.xml 无法读取")
    embeds = []
    try:
        font_table = _xml(parts["word/fontTable.xml"])
        embeds = font_table.xpath(".//w:embedRegular", namespaces=NS)
        if len(embeds) < len(odttf):
            errors.append("fontTable.xml 的嵌入引用数量不足")
    except Exception:
        errors.append("fontTable.xml 无法读取")
    try:
        rels = _xml(parts["word/_rels/fontTable.xml.rels"])
        relationships = {
            node.get("Id"): node.get("Target")
            for node in rels
            if node.get("Type") == EMBED_REL_TYPE
        }
        targets = {
            node.get("Target")
            for node in rels
            if node.get("Type") == EMBED_REL_TYPE
        }
        for part in odttf:
            if part.replace("word/", "") not in targets:
                errors.append(f"字体部件缺少关系：{part}")
        for embed in embeds:
            rid = embed.get(f"{{{R_NS}}}id")
            key_text = embed.get(f"{{{W_NS}}}fontKey", "").strip("{}")
            target = relationships.get(rid)
            if not target or not key_text:
                errors.append(f"字体引用缺少关系或密钥：{rid or '未知引用'}")
                continue
            part_name = "word/" + target.lstrip("/")
            if part_name not in parts:
                errors.append(f"字体引用指向不存在的部件：{part_name}")
                continue
            if part_name in checked_parts:
                continue
            try:
                clear_bytes = _obfuscate(parts[part_name], uuid.UUID(key_text))
                font = TTFont(io.BytesIO(clear_bytes), lazy=True)
                if not font.getGlyphOrder():
                    errors.append(f"嵌入字体没有字形：{part_name}")
                font.close()
                checked_parts.append(part_name)
            except Exception as exc:
                errors.append(f"嵌入字体无法反解或解析：{part_name}（{exc}）")
    except Exception:
        errors.append("fontTable.xml.rels 无法读取")
    return {"valid": not errors, "errors": errors, "parts": odttf, "parsed_parts": checked_parts}
