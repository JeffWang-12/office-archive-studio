from __future__ import annotations

import configparser
import json
import os
import re
import shutil
import sys
import tempfile
import uuid
import zipfile
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from docxtpl import DocxTemplate, InlineImage
from docx.shared import Cm
from jinja2.sandbox import SandboxedEnvironment

from .font_embedder import apply_global_font, embed_fonts, scan_fonts
from .summary_builder import build_summary
from .plan_builder import build_plan
from .photo_guard import prepare_photos, validate_photos
from .template_guard import check_template


AUTO_FONT = "严格按团内格式规范"


class UserInputError(ValueError):
    pass


@dataclass
class GenerationResult:
    output_path: Path
    font_report: dict
    warnings: list[str]


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def load_config(root: Path) -> configparser.ConfigParser:
    config = configparser.ConfigParser()
    path = root / "config.ini"
    if path.exists():
        try:
            config.read(path, encoding="utf-8-sig")
        except (OSError, configparser.Error):
            config = configparser.ConfigParser()
    if "general" not in config:
        config["general"] = {}
    config["general"].setdefault("default_template", "年度工作总结")
    config["general"].setdefault("selected_font", AUTO_FONT)
    config["general"].setdefault("output_folder", "输出文档")
    config["general"].setdefault("embed_fonts", "true")
    if "privacy" not in config:
        config["privacy"] = {}
    config["privacy"].setdefault("auto_save_drafts", "true")
    return config


def save_config(root: Path, config: configparser.ConfigParser) -> None:
    temporary = root / "config.ini.tmp"
    with temporary.open("w", encoding="utf-8-sig") as handle:
        config.write(handle)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, root / "config.ini")


def font_choices(root: Path) -> tuple[list[str], list[str]]:
    choices = [AUTO_FONT]
    warnings = []
    for font in scan_fonts(root / "fonts"):
        if font.restricted:
            warnings.append(f"{font.family}：字体授权位禁止嵌入，未列入可选字体。")
        # 发布文档的字体由格式规范决定，不允许界面整体替换字体。
    return list(dict.fromkeys(choices)), warnings


def _extract_placeholders(template_path: Path) -> set[str]:
    try:
        template = DocxTemplate(template_path)
        return set(template.get_undeclared_template_variables())
    except Exception:
        return set()


def _infer_field(name: str) -> dict:
    lowered = name.lower()
    label = name.replace("_", " ")
    if name == "project_name":
        return {"name": name, "label": "项目/档案名称（用于文件名）", "type": "text", "required": True, "max_chars": 60}
    if any(key in lowered for key in ("date", "日期")):
        field_type = "date"
    elif any(key in lowered for key in ("amount", "money", "金额", "人数", "count", "year", "month")):
        field_type = "number"
    elif any(key in lowered for key in ("body", "content", "summary", "description", "正文", "内容", "说明")):
        field_type = "multiline"
    else:
        field_type = "text"
    return {"name": name, "label": label, "type": field_type, "required": True, "max_chars": 4000 if field_type == "multiline" else 200}


def _merge_template_fields(spec: dict, template_path: Path) -> dict:
    result = deepcopy(spec)
    known = {field["name"] for field in result.get("fields", [])}
    ignored = {
        "date_cn",
        "title_char1",
        "title_char2",
        "title_char3",
        "title_char4",
        *{f"photo{i}" for i in range(1, 4)},
        *{f"toc{i}_{key}" for i in range(1, 7) for key in ("name", "page")},
        *{f"event{i}_{key}" for i in range(1, 8) for key in ("name", "time", "location", "organizer", "guest")},
        *{f"activity2_{key}" for key in ("purpose", "time", "location", "publicity", "preparation", "scope", "participants", "process", "impact")},
    }
    missing = sorted(_extract_placeholders(template_path) - known - ignored)
    result.setdefault("fields", []).extend(_infer_field(name) for name in missing)
    return result


def load_template_catalog(root: Path) -> dict[str, dict]:
    manifest_path = root / "templates.json"
    catalog: dict[str, dict] = {}
    if manifest_path.exists():
        data = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        for display_name, raw in data.items():
            template_path = root / "templates" / raw["file"]
            spec = _merge_template_fields(raw, template_path) if template_path.exists() else deepcopy(raw)
            spec["path"] = template_path
            catalog[display_name] = spec
    known_paths = {spec["path"].resolve() for spec in catalog.values() if spec["path"].exists()}
    for template_path in sorted((root / "templates").glob("*.docx")) if (root / "templates").exists() else []:
        if template_path.resolve() in known_paths:
            continue
        name = f"外部模板：{template_path.stem}"
        fields = [_infer_field("project_name")]
        fields.extend(_infer_field(item) for item in sorted(_extract_placeholders(template_path)) if item != "project_name")
        catalog[name] = {"file": template_path.name, "path": template_path, "description": "自动识别的外部模板。", "fields": fields}
    root_template = root / "模板.docx"
    if root_template.exists():
        fields = [_infer_field("project_name")]
        fields.extend(_infer_field(item) for item in sorted(_extract_placeholders(root_template)) if item != "project_name")
        catalog["自定义模板（根目录模板.docx）"] = {
            "file": root_template.name,
            "path": root_template,
            "description": "可直接覆盖根目录的模板.docx；界面会自动识别其中的 {{占位符}}。",
            "fields": fields,
        }
    return catalog


def default_value(field: dict) -> str:
    if "default" in field:
        return str(field["default"])
    today = date.today()
    name = field["name"]
    if field.get("type") == "date":
        return today.strftime("%Y-%m-%d")
    if name in {"year", "school_year_start"}:
        academic_start = today.year if today.month >= 8 else today.year - 1
        return str(academic_start if name == "school_year_start" else today.year)
    if name == "school_year_end":
        academic_start = today.year if today.month >= 8 else today.year - 1
        return str(academic_start + 1)
    if name == "month":
        return str(today.month)
    return ""


def _visible_length(value: str) -> int:
    return len(re.sub(r"\s+", "", value))


def _parse_date(value: str, label: str) -> tuple[str, str]:
    try:
        parsed = datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except ValueError as exc:
        raise UserInputError(f"“{label}”格式不正确，请按 YYYY-MM-DD 填写。") from exc
    return parsed.strftime("%Y-%m-%d"), f"{parsed.year}年{parsed.month}月{parsed.day}日"


def _validate_number(value: str, field: dict) -> str:
    label = field["label"]
    cleaned = value.replace(",", "").strip()
    if not re.fullmatch(r"\d+", cleaned):
        raise UserInputError(f"“{label}”只能输入数字。")
    if field.get("digits") and len(cleaned) != int(field["digits"]):
        raise UserInputError(f"“{label}”必须是 {field['digits']} 位数字。")
    number = int(cleaned)
    if "min" in field and number < int(field["min"]):
        raise UserInputError(f"“{label}”不能小于 {field['min']}。")
    if "max" in field and number > int(field["max"]):
        raise UserInputError(f"“{label}”不能大于 {field['max']}。")
    if any(key in field["name"].lower() for key in ("amount", "money")) or "金额" in label:
        return f"{number:,}"
    return str(number)


def validate_values(spec: dict, raw_values: dict) -> dict:
    values = {}
    for field in spec.get("fields", []):
        name = field["name"]
        field_type = field.get("type", "text")
        value = raw_values.get(name, [] if field_type in {"photos", "points", "task_groups"} else "")
        if field_type == "photos":
            paths = [str(item).strip() for item in value if str(item).strip()]
            if field.get("required") and len(paths) < 2:
                raise UserInputError("工作总结必须选择2—3张活动照片。")
            if len(paths) > 3:
                raise UserInputError("活动照片最多选择3张。")
            for item in paths:
                path = Path(item)
                if not path.exists() or not path.is_file():
                    raise UserInputError(f"照片不存在：{item}")
                if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp"}:
                    raise UserInputError(f"不支持的照片格式：{path.name}")
            try:
                validate_photos(paths)
            except ValueError as exc:
                raise UserInputError(str(exc)) from exc
            values[name] = paths
            continue
        if field_type == "points":
            items = value if isinstance(value, list) else [line for line in str(value).splitlines()]
            items = [str(item).strip() for item in items if str(item).strip()]
            items = [re.sub(r"^(?:[（(]\d+[）)]|\d+[.、．])\s*", "", item).strip() for item in items]
            items = [item for item in items if item]
            if field.get("required") and not items:
                raise UserInputError(f"请填写“{field['label']}”的至少一条内容。")
            if len(items) > int(field.get("max_items", 12)):
                raise UserInputError(f"“{field['label']}”最多填写 {field.get('max_items', 12)} 条。")
            if sum(_visible_length(item) for item in items) > int(field.get("max_chars", 12000)):
                raise UserInputError(f"“{field['label']}”内容过长。")
            values[name] = items
            continue
        if field_type == "task_groups":
            if not isinstance(value, list):
                raise UserInputError(f"“{field['label']}”的任务内容格式不正确。")
            tasks = []
            for index, item in enumerate(value, 1):
                if not isinstance(item, dict):
                    raise UserInputError(f"第 {index} 个任务格式不正确。")
                description = re.sub(r"\s+", " ", str(item.get("description", ""))).strip()
                goals = [re.sub(r"\s+", " ", str(point)).strip() for point in item.get("goals", [])]
                measures = [re.sub(r"\s+", " ", str(point)).strip() for point in item.get("measures", [])]
                goals = [re.sub(r"^(?:[（(]\d+[）)]|\d+[.、．])\s*", "", point) for point in goals if point]
                measures = [re.sub(r"^(?:[（(]\d+[）)]|\d+[.、．])\s*", "", point) for point in measures if point]
                if not description and not goals and not measures:
                    continue
                if not description:
                    raise UserInputError(f"请填写第 {index} 个任务的“任务内容”。")
                if not goals and not measures:
                    raise UserInputError(f"第 {index} 个任务请至少填写一条目标或具体措施。")
                tasks.append({"description": description, "goals": goals, "measures": measures})
            if field.get("required") and not tasks:
                raise UserInputError(f"请至少填写一个“{field['label']}”任务。")
            if len(tasks) > int(field.get("max_tasks", 12)):
                raise UserInputError(f"“{field['label']}”最多填写 {field.get('max_tasks', 12)} 个任务。")
            if sum(_visible_length(part) for task in tasks for part in [task["description"], *task["goals"], *task["measures"]]) > int(field.get("max_chars", 12000)):
                raise UserInputError(f"“{field['label']}”内容过长。")
            values[name] = tasks
            continue
        text = str(value).strip()
        if field.get("required") and not text:
            raise UserInputError(f"请填写“{field['label']}”。")
        if not text:
            values[name] = ""
            continue
        length = _visible_length(text)
        if "min_chars" in field and length < int(field["min_chars"]):
            raise UserInputError(f"“{field['label']}”内容过短，至少填写 {field['min_chars']} 个有效字符。")
        if "max_chars" in field and length > int(field["max_chars"]):
            raise UserInputError(f"“{field['label']}”内容过长，最多 {field['max_chars']} 个有效字符。")
        if field_type == "number":
            text = _validate_number(text, field)
        elif field_type == "choice":
            if text not in field.get("choices", []):
                raise UserInputError(f"“{field['label']}”请选择提供的选项")
        elif field_type == "date":
            text, _date_cn = _parse_date(text, field["label"])
        elif field_type == "events":
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            if field.get("required") and not lines:
                raise UserInputError("请至少填写1条活动明细。")
            if len(lines) > int(field.get("max_rows", 7)):
                raise UserInputError(f"活动明细最多填写 {field.get('max_rows', 7)} 行。")
            for index, line in enumerate(lines, 1):
                if len([item for item in line.split("|")]) != 5:
                    raise UserInputError(f"活动明细第 {index} 行应包含5项，并用半角竖线 | 分隔。")
        elif field_type == "toc":
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            if len(lines) > 6:
                raise UserInputError("目录条目最多填写6行。")
            for index, line in enumerate(lines, 1):
                if len(line.split("|")) != 2:
                    raise UserInputError(f"目录第 {index} 行应为“名称|页码”。")
        values[name] = text
    return values


def _doc_multiline(value: str) -> str:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    return normalized.replace("\n", "\a")


def _prepare_context(template: DocxTemplate, spec: dict, values: dict) -> dict:
    context = dict(values)
    if "college_name" in context:
        context["college_name"] = re.sub(r"学院$", "", context["college_name"].strip())
    kind = context.get("document_kind", "工作总结")
    if kind:
        if len(kind) != 4:
            raise UserInputError("封面文档类别必须为4个汉字，例如“工作总结”或“工作计划”。")
        for index, char in enumerate(kind, 1):
            context[f"title_char{index}"] = char
    if context.get("date"):
        _iso, context["date_cn"] = _parse_date(context["date"], "成文日期")
        context["date"] = context["date_cn"]
    else:
        today = date.today()
        context["date_cn"] = f"{today.year}年{today.month}月{today.day}日"
    if not context.get("signature_unit"):
        if context.get("college_name"):
            if spec.get("file") == "文化导航申报表.docx":
                context["signature_unit"] = f"中北大学{context['college_name']}学院"
            else:
                context["signature_unit"] = f"{context['college_name']}学院学生会"
        elif context.get("department_name"):
            context["signature_unit"] = context["department_name"]
        else:
            context["signature_unit"] = ""
    for field in spec.get("fields", []):
        if field.get("type") == "multiline" and context.get(field["name"]):
            context[field["name"]] = _doc_multiline(context[field["name"]])
    for index in range(1, 7):
        context[f"toc{index}_name"] = ""
        context[f"toc{index}_page"] = ""
    for index, line in enumerate([line for line in context.get("toc", "").splitlines() if line.strip()][:6], 1):
        name, page = [item.strip() for item in line.split("|", 1)]
        context[f"toc{index}_name"] = name
        context[f"toc{index}_page"] = page
    event_keys = ("name", "time", "location", "organizer", "guest")
    for index in range(1, 8):
        for key in event_keys:
            context[f"event{index}_{key}"] = ""
    for index, line in enumerate([line for line in context.get("events", "").splitlines() if line.strip()][:7], 1):
        for key, value in zip(event_keys, [item.strip() for item in line.split("|")]):
            context[f"event{index}_{key}"] = value
    activity_keys = ("purpose", "time", "location", "publicity", "preparation", "scope", "participants", "process", "impact", "summary")
    for key in activity_keys:
        context.setdefault(f"activity2_{key}", "")
    photos = context.pop("photo_paths", [])
    for index in range(1, 4):
        if index <= len(photos):
            context[f"photo{index}"] = InlineImage(template, photos[index - 1], width=Cm(4), height=Cm(5.34))
        else:
            context[f"photo{index}"] = ""
    return context


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[<>:\"/\\|?*\x00-\x1F]", "_", value)
    cleaned = re.sub(r"\s+", "_", cleaned).strip(" ._")
    return (cleaned or "标准化文档")[:80]


def _output_path(root: Path, config: configparser.ConfigParser, project_name: str) -> Path:
    folder_name = config.get("general", "output_folder", fallback="输出文档").strip() or "输出文档"
    folder = Path(folder_name)
    if folder.is_absolute() or len(folder.parts) != 1 or folder_name in {".", ".."}:
        raise UserInputError("输出目录只能填写本程序文件夹内的单层文件夹名称。")
    output_dir = root / folder_name
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = f"{stamp}_{_safe_filename(project_name)}"
    candidate = output_dir / f"{base}.docx"
    counter = 2
    while candidate.exists():
        candidate = output_dir / f"{base}_{counter}.docx"
        counter += 1
    return candidate


def _preflight_output(folder: Path, photos: list[str]) -> None:
    try:
        required = max(20 * 1024 * 1024, 4 * sum(Path(path).stat().st_size for path in photos))
        if shutil.disk_usage(folder).free < required:
            raise UserInputError("输出磁盘剩余空间不足，请清理空间或将整个程序文件夹移到其他位置。")
        with tempfile.NamedTemporaryFile(prefix=".写入检查_", dir=folder, delete=True) as stream:
            stream.write(b"ok")
            stream.flush()
            os.fsync(stream.fileno())
    except UserInputError:
        raise
    except OSError as exc:
        raise UserInputError(f"输出文件夹无法写入，请检查U盘连接、只读状态和磁盘空间：{exc}") from exc


def generate_document(root: Path, spec: dict, raw_values: dict, selected_font: str, config: configparser.ConfigParser) -> GenerationResult:
    template_path = Path(spec["path"])
    try:
        check_template(root, template_path)
    except ValueError as exc:
        raise UserInputError(str(exc)) from exc
    values = validate_values(spec, raw_values)
    project_name = values.get("project_name") or template_path.stem
    try:
        output_path = _output_path(root, config, project_name)
    except OSError as exc:
        raise UserInputError(f"无法创建输出文件夹，请检查U盘连接、只读状态和磁盘空间：{exc}") from exc
    _preflight_output(output_path.parent, values.get("photo_paths", []))
    working_path = output_path.with_name(f".{output_path.stem}.{uuid.uuid4().hex}.part.docx")
    try:
        if spec.get("summary") and template_path.name in {"年度工作总结.docx", "月份工作总结.docx"}:
            summary_values = dict(values)
            summary_values["photo_paths"] = prepare_photos(values.get("photo_paths", []))
            summary_values["college_name"] = re.sub(r"学院$", "", summary_values.get("college_name", "").strip())
            if not summary_values.get("signature_unit"):
                summary_values["signature_unit"] = (
                    summary_values.get("department_name")
                    or f'{summary_values.get("college_name", "")}学院学生会'
                )
            _iso, summary_values["date_cn"] = _parse_date(summary_values["date"], "成文日期")
            build_summary(template_path, working_path, summary_values, template_path.name.startswith("月份"))
        elif template_path.name in {"年度工作计划.docx", "月份工作计划.docx"} and spec.get("guided_plan"):
            plan_values = dict(values)
            plan_values["college_name"] = re.sub(r"学院$", "", plan_values.get("college_name", "").strip())
            if not plan_values.get("signature_unit"):
                plan_values["signature_unit"] = (
                    plan_values.get("department_name")
                    or f'{plan_values.get("college_name", "")}学院学生会'
                )
            _iso, plan_values["date_cn"] = _parse_date(plan_values["date"], "成文日期")
            build_plan(template_path, working_path, plan_values, template_path.name.startswith("月份"))
        else:
            template = DocxTemplate(template_path)
            context = _prepare_context(template, spec, values)
            template.render(context, jinja_env=SandboxedEnvironment(autoescape=True), autoescape=True)
            template.save(working_path)
    except Exception as exc:
        try:
            working_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise UserInputError(f"模板渲染失败：{exc}") from exc
    try:
        warnings = []
        font_family = None
        installed_fonts = scan_fonts(root / "fonts")
        fallback_to_songti = False
        if not installed_fonts:
            warnings.append("未随附可嵌入字体，已保留模板字体名称，请在 Word / WPS 中检查所需字体是否安装")
        if selected_font and selected_font != AUTO_FONT:
            available = {font.family: font for font in installed_fonts}
            font = available.get(selected_font)
            if font is None:
                warnings.append(f"未找到所选字体“{selected_font}”，已回退使用系统“宋体”。")
                fallback_to_songti = True
            elif font.restricted:
                warnings.append(f"字体“{selected_font}”的授权位禁止嵌入，已回退使用系统“宋体”。")
                fallback_to_songti = True
            else:
                apply_global_font(working_path, selected_font)
                font_family = selected_font
        if fallback_to_songti:
            apply_global_font(working_path, "宋体")
            if not installed_fonts:
                warnings.append("fonts 文件夹中没有可读取字体，已回退使用系统“宋体”。")
        font_report = {"embedded": [], "skipped": []}
        if config.getboolean("general", "embed_fonts", fallback=True):
            font_report = embed_fonts(working_path, root / "fonts", selected_family=font_family)
            for skipped in font_report.get("skipped", []):
                warnings.append(f"{skipped['font']}：{skipped['reason']}")
            if not font_report.get("embedded"):
                warnings.append("未找到可嵌入且在文档中使用的字体，接收方电脑可能发生字体替换。")
        with zipfile.ZipFile(working_path) as archive:
            if archive.testzip() is not None:
                raise UserInputError("生成文件校验失败，未保留不完整文档。")
        os.replace(working_path, output_path)
    except Exception as exc:
        try:
            working_path.unlink(missing_ok=True)
        except OSError:
            pass
        if isinstance(exc, UserInputError):
            raise
        raise UserInputError(f"写入或校验文档失败，请检查U盘连接、只读状态和磁盘空间：{exc}") from exc
    return GenerationResult(output_path=output_path, font_report=font_report, warnings=warnings)
