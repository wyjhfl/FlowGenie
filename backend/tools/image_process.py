"""C4: 图像处理工具

使用 Pillow 提供常用图像处理能力:
- resize: 调整尺寸(支持保持比例)
- convert: 格式转换(jpg/png/webp)
- thumbnail: 生成缩略图
- rotate: 旋转指定角度
- info: 获取图像元信息(尺寸/格式/色彩模式)

输入/输出:工作区文件系统(复用 file_write 的路径校验)。

安全:
- 路径遍历防护:复用 file_write._validate_workspace_path
- 输入图像大小上限:50MB(防止解码炸弹)
- 输出尺寸上限:10000x10000(防止内存爆炸)
- 仅支持常见格式:JPEG/PNG/WebP/GIF/BMP
"""
import os
import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

# 安全上限
_MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
_MAX_DIMENSION = 10000
_ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF", "BMP"}
# 格式别名映射(用户输入小写/简写 → Pillow 标准格式名)
_FORMAT_ALIASES = {
    "jpg": "JPEG",
    "jpeg": "JPEG",
    "png": "PNG",
    "webp": "WEBP",
    "gif": "GIF",
    "bmp": "BMP",
}


def _validate_workspace_path(path: str) -> str:
    """复用 file_write 的路径校验逻辑"""
    from tools.file_write import _validate_workspace_path as _validate
    return _validate(path)


def _normalize_format(fmt: str) -> str:
    """格式名规范化:小写/简写 → Pillow 标准格式名"""
    if not fmt:
        return ""
    normalized = _FORMAT_ALIASES.get(fmt.lower().strip())
    if not normalized:
        raise ValueError(f"不支持的图像格式: {fmt}(支持: {sorted(_FORMAT_ALIASES.keys())})")
    return normalized


def _open_image(path: str):
    """打开图像并校验大小"""
    from PIL import Image

    size = os.path.getsize(path)
    if size > _MAX_FILE_SIZE:
        raise ValueError(f"图像文件过大: {size} bytes(上限 {_MAX_FILE_SIZE} bytes)")

    img = Image.open(path)
    img.load()  # 立即加载,避免后续操作时延迟打开
    return img


def _resize_sync(input_path: str, output_path: str, width: int, height: int, keep_ratio: bool) -> dict:
    """同步 resize"""
    from PIL import Image

    img = _open_image(input_path)
    original_size = img.size  # (width, height)

    # 校验目标尺寸
    if width <= 0 or height <= 0:
        raise ValueError(f"width/height 必须为正数,当前: {width}x{height}")
    if width > _MAX_DIMENSION or height > _MAX_DIMENSION:
        raise ValueError(f"目标尺寸超过上限 {_MAX_DIMENSION}px,当前: {width}x{height}")

    if keep_ratio:
        # 保持比例:取较小缩放比
        ratio = min(width / original_size[0], height / original_size[1])
        new_size = (int(original_size[0] * ratio), int(original_size[1] * ratio))
    else:
        new_size = (width, height)

    # 使用 LANCZOS 高质量重采样
    resized = img.resize(new_size, Image.LANCZOS)
    resized.save(output_path)
    file_size = os.path.getsize(output_path)

    return {
        "success": True,
        "operation": "resize",
        "input_path": input_path,
        "output_path": output_path,
        "original_size": list(original_size),
        "new_size": list(new_size),
        "keep_ratio": keep_ratio,
        "size": file_size,
    }


def _convert_sync(input_path: str, output_path: str, target_format: str, quality: int) -> dict:
    """同步格式转换"""
    from PIL import Image

    img = _open_image(input_path)
    fmt = _normalize_format(target_format)

    # JPEG 不支持 alpha 通道,需转 RGB
    save_kwargs = {}
    if fmt == "JPEG":
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")
        save_kwargs["quality"] = quality
    elif fmt == "WEBP":
        save_kwargs["quality"] = quality
    elif fmt == "PNG":
        save_kwargs["optimize"] = True

    img.save(output_path, format=fmt, **save_kwargs)
    file_size = os.path.getsize(output_path)

    return {
        "success": True,
        "operation": "convert",
        "input_path": input_path,
        "output_path": output_path,
        "original_format": img.format or "",
        "new_format": fmt,
        "quality": quality if fmt in ("JPEG", "WEBP") else None,
        "size": file_size,
    }


def _thumbnail_sync(input_path: str, output_path: str, max_size: int) -> dict:
    """同步生成缩略图"""
    from PIL import Image

    img = _open_image(input_path)
    original_size = img.size

    if max_size <= 0 or max_size > _MAX_DIMENSION:
        raise ValueError(f"max_size 必须为 1-{_MAX_DIMENSION},当前: {max_size}")

    # thumbnail 会保持比例,原地修改
    img.thumbnail((max_size, max_size), Image.LANCZOS)
    # 保留原格式
    original_format = img.format or "PNG"
    img.save(output_path, format=original_format)
    file_size = os.path.getsize(output_path)

    return {
        "success": True,
        "operation": "thumbnail",
        "input_path": input_path,
        "output_path": output_path,
        "original_size": list(original_size),
        "new_size": list(img.size),
        "max_size": max_size,
        "size": file_size,
    }


def _rotate_sync(input_path: str, output_path: str, angle: int) -> dict:
    """同步旋转"""
    from PIL import Image

    img = _open_image(input_path)
    original_size = img.size

    # rotate 逆时针;expand=True 扩展画布以容纳旋转后的完整图像
    rotated = img.rotate(-angle, expand=True, fillcolor=(255, 255, 255, 0) if img.mode == "RGBA" else (255, 255, 255))
    original_format = img.format or "PNG"
    rotated.save(output_path, format=original_format)
    file_size = os.path.getsize(output_path)

    return {
        "success": True,
        "operation": "rotate",
        "input_path": input_path,
        "output_path": output_path,
        "angle": angle,
        "original_size": list(original_size),
        "new_size": list(rotated.size),
        "size": file_size,
    }


def _info_sync(input_path: str) -> dict:
    """同步获取图像信息"""
    img = _open_image(input_path)
    info = {
        "success": True,
        "operation": "info",
        "path": input_path,
        "format": img.format or "",
        "mode": img.mode,
        "size": list(img.size),
        "width": img.size[0],
        "height": img.size[1],
        "file_size": os.path.getsize(input_path),
    }
    img.close()
    return info


# ===== 异步执行器 =====

async def execute(params: dict, context: Any) -> dict:
    """图像处理工具统一入口(按 action 分派)

    :param params: {action: "resize"|"convert"|"thumbnail"|"rotate"|"info", ...}
    :return: 操作结果 dict
    """
    action = params.get("action", "")
    if action == "resize":
        return await execute_resize(params, context)
    if action == "convert":
        return await execute_convert(params, context)
    if action == "thumbnail":
        return await execute_thumbnail(params, context)
    if action == "rotate":
        return await execute_rotate(params, context)
    if action == "info":
        return await execute_info(params, context)
    return {
        "success": False,
        "warning": f"未知 action: {action}(支持 resize / convert / thumbnail / rotate / info)",
    }


async def execute_resize(params: dict, context: Any) -> dict:
    """image_resize: 调整图像尺寸"""
    input_path = params.get("input_path", "")
    output_path = params.get("output_path", "")
    try:
        width = int(params.get("width", 0))
        height = int(params.get("height", 0))
    except (TypeError, ValueError):
        return {"success": False, "warning": "width/height 必须为整数"}
    keep_ratio = params.get("keep_ratio", True)

    if not input_path or not output_path:
        return {"success": False, "warning": "input_path 和 output_path 不能为空"}

    try:
        abs_input = _validate_workspace_path(input_path)
        abs_output = _validate_workspace_path(output_path)
    except ValueError as e:
        return {"success": False, "warning": str(e)}

    if not os.path.exists(abs_input):
        return {"success": False, "warning": f"输入文件不存在: {input_path}"}

    try:
        return await asyncio.to_thread(_resize_sync, abs_input, abs_output, width, height, keep_ratio)
    except Exception as e:
        logger.error(f"image_resize 失败: {e}")
        return {"success": False, "warning": f"图像 resize 失败: {e}"}


async def execute_convert(params: dict, context: Any) -> dict:
    """image_convert: 格式转换"""
    input_path = params.get("input_path", "")
    output_path = params.get("output_path", "")
    target_format = params.get("target_format", "")
    try:
        quality = int(params.get("quality", 85))
    except (TypeError, ValueError):
        quality = 85

    if not input_path or not output_path:
        return {"success": False, "warning": "input_path 和 output_path 不能为空"}
    if not target_format:
        return {"success": False, "warning": "target_format 不能为空"}

    # 预校验格式名(避免线程内才报错)
    try:
        _normalize_format(target_format)
    except ValueError as e:
        return {"success": False, "warning": str(e)}

    try:
        abs_input = _validate_workspace_path(input_path)
        abs_output = _validate_workspace_path(output_path)
    except ValueError as e:
        return {"success": False, "warning": str(e)}

    if not os.path.exists(abs_input):
        return {"success": False, "warning": f"输入文件不存在: {input_path}"}

    try:
        return await asyncio.to_thread(_convert_sync, abs_input, abs_output, target_format, quality)
    except Exception as e:
        logger.error(f"image_convert 失败: {e}")
        return {"success": False, "warning": f"图像转换失败: {e}"}


async def execute_thumbnail(params: dict, context: Any) -> dict:
    """image_thumbnail: 生成缩略图"""
    input_path = params.get("input_path", "")
    output_path = params.get("output_path", "")
    try:
        max_size = int(params.get("max_size", 200))
    except (TypeError, ValueError):
        return {"success": False, "warning": "max_size 必须为整数"}

    if not input_path or not output_path:
        return {"success": False, "warning": "input_path 和 output_path 不能为空"}

    try:
        abs_input = _validate_workspace_path(input_path)
        abs_output = _validate_workspace_path(output_path)
    except ValueError as e:
        return {"success": False, "warning": str(e)}

    if not os.path.exists(abs_input):
        return {"success": False, "warning": f"输入文件不存在: {input_path}"}

    try:
        return await asyncio.to_thread(_thumbnail_sync, abs_input, abs_output, max_size)
    except Exception as e:
        logger.error(f"image_thumbnail 失败: {e}")
        return {"success": False, "warning": f"缩略图生成失败: {e}"}


async def execute_rotate(params: dict, context: Any) -> dict:
    """image_rotate: 旋转图像"""
    input_path = params.get("input_path", "")
    output_path = params.get("output_path", "")
    try:
        angle = int(params.get("angle", 0))
    except (TypeError, ValueError):
        return {"success": False, "warning": "angle 必须为整数"}

    if not input_path or not output_path:
        return {"success": False, "warning": "input_path 和 output_path 不能为空"}

    try:
        abs_input = _validate_workspace_path(input_path)
        abs_output = _validate_workspace_path(output_path)
    except ValueError as e:
        return {"success": False, "warning": str(e)}

    if not os.path.exists(abs_input):
        return {"success": False, "warning": f"输入文件不存在: {input_path}"}

    try:
        return await asyncio.to_thread(_rotate_sync, abs_input, abs_output, angle)
    except Exception as e:
        logger.error(f"image_rotate 失败: {e}")
        return {"success": False, "warning": f"图像旋转失败: {e}"}


async def execute_info(params: dict, context: Any) -> dict:
    """image_info: 获取图像元信息"""
    input_path = params.get("input_path", "")
    if not input_path:
        return {"success": False, "warning": "input_path 不能为空"}

    try:
        abs_input = _validate_workspace_path(input_path)
    except ValueError as e:
        return {"success": False, "warning": str(e)}

    if not os.path.exists(abs_input):
        return {"success": False, "warning": f"输入文件不存在: {input_path}"}

    try:
        return await asyncio.to_thread(_info_sync, abs_input)
    except Exception as e:
        logger.error(f"image_info 失败: {e}")
        return {"success": False, "warning": f"图像信息读取失败: {e}"}
