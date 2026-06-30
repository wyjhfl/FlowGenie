"""C4: 图像处理工具单元测试

验证:
- image_resize: 调整尺寸 / 保持比例 / 强制尺寸 / 非法尺寸兜底
- image_convert: 格式转换 / JPEG 处理 alpha / 非法格式兜底 / 质量参数
- image_thumbnail: 缩略图生成 / 保持比例
- image_info: 读取元信息
- 路径遍历防护 / 文件不存在兜底
- executor 路由 + tool_registry 注册
"""
import os
import pytest


@pytest.fixture
def workspace_tmp(monkeypatch, tmp_path):
    """将 WORKSPACE_DIR 指向临时目录,并生成一个测试 PNG"""
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path))
    # 生成 100x80 的测试 PNG
    from PIL import Image
    img = Image.new("RGB", (100, 80), color=(255, 0, 0))
    img_path = tmp_path / "input.png"
    img.save(img_path, format="PNG")
    img.close()
    yield tmp_path


# ============ image_resize 测试 ============

@pytest.mark.asyncio
async def test_resize_force_dimensions(workspace_tmp):
    """强制尺寸(keep_ratio=False):输出精确尺寸"""
    from tools.image_process import execute_resize

    result = await execute_resize(
        {"input_path": "input.png", "output_path": "out.png", "width": 50, "height": 40, "keep_ratio": False},
        context=None,
    )

    assert result["success"] is True
    assert result["operation"] == "resize"
    assert result["original_size"] == [100, 80]
    assert result["new_size"] == [50, 40]
    assert result["keep_ratio"] is False
    assert (workspace_tmp / "out.png").exists()


@pytest.mark.asyncio
async def test_resize_keep_ratio(workspace_tmp):
    """保持比例:输出按较小缩放比缩放"""
    from tools.image_process import execute_resize

    # 100x80 缩放到 200x200,保持比例 → 200x160(取较小比 2.0)
    result = await execute_resize(
        {"input_path": "input.png", "output_path": "out_ratio.png", "width": 200, "height": 200, "keep_ratio": True},
        context=None,
    )

    assert result["success"] is True
    assert result["keep_ratio"] is True
    # 100→200 比例 2.0,80→160 比例 2.0,两者相等取 2.0
    assert result["new_size"] == [200, 160]


@pytest.mark.asyncio
async def test_resize_keep_ratio_is_min_ratio(workspace_tmp):
    """保持比例:取较小缩放比(避免超出目标)"""
    from tools.image_process import execute_resize

    # 100x80 缩放到 50x200,比例 0.5 和 2.5,取较小 0.5 → 50x40
    result = await execute_resize(
        {"input_path": "input.png", "output_path": "out_min.png", "width": 50, "height": 200, "keep_ratio": True},
        context=None,
    )
    assert result["success"] is True
    assert result["new_size"] == [50, 40]


@pytest.mark.asyncio
async def test_resize_invalid_dimensions_returns_warning(workspace_tmp):
    """非法 width/height 返回 warning"""
    from tools.image_process import execute_resize

    result = await execute_resize(
        {"input_path": "input.png", "output_path": "out.png", "width": 0, "height": 40},
        context=None,
    )
    assert result["success"] is False
    assert "warning" in result


@pytest.mark.asyncio
async def test_resize_dimension_exceeds_max_returns_warning(workspace_tmp):
    """目标尺寸超过上限返回 warning"""
    from tools.image_process import execute_resize, _MAX_DIMENSION

    result = await execute_resize(
        {"input_path": "input.png", "output_path": "out.png", "width": _MAX_DIMENSION + 1, "height": 100},
        context=None,
    )
    assert result["success"] is False
    assert "warning" in result


@pytest.mark.asyncio
async def test_resize_nonexistent_input_returns_warning(workspace_tmp):
    """输入文件不存在返回 warning"""
    from tools.image_process import execute_resize

    result = await execute_resize(
        {"input_path": "missing.png", "output_path": "out.png", "width": 50, "height": 50},
        context=None,
    )
    assert result["success"] is False
    assert "不存在" in result["warning"]


# ============ image_convert 测试 ============

@pytest.mark.asyncio
async def test_convert_png_to_jpeg(workspace_tmp):
    """PNG → JPEG 转换(自动转 RGB)"""
    from tools.image_process import execute_convert

    result = await execute_convert(
        {"input_path": "input.png", "output_path": "out.jpg", "target_format": "JPEG", "quality": 90},
        context=None,
    )

    assert result["success"] is True
    assert result["operation"] == "convert"
    assert result["new_format"] == "JPEG"
    assert result["quality"] == 90
    assert (workspace_tmp / "out.jpg").exists()


@pytest.mark.asyncio
async def test_convert_format_aliases(workspace_tmp):
    """格式别名支持(jpg/jpeg/png/webp 大小写)"""
    from tools.image_process import execute_convert, _normalize_format

    # 小写别名
    assert _normalize_format("jpg") == "JPEG"
    assert _normalize_format("PNG") == "PNG"
    assert _normalize_format("webp") == "WEBP"

    # 实际转换:用小写 jpg
    result = await execute_convert(
        {"input_path": "input.png", "output_path": "alias.jpg", "target_format": "jpg"},
        context=None,
    )
    assert result["success"] is True


@pytest.mark.asyncio
async def test_convert_unsupported_format_returns_warning(workspace_tmp):
    """不支持的格式返回 warning"""
    from tools.image_process import execute_convert

    result = await execute_convert(
        {"input_path": "input.png", "output_path": "out.tiff", "target_format": "TIFF"},
        context=None,
    )
    assert result["success"] is False
    assert "不支持" in result["warning"] or "格式" in result["warning"]


@pytest.mark.asyncio
async def test_convert_rgba_to_jpeg(workspace_tmp):
    """RGBA 图像转 JPEG 自动转 RGB"""
    from PIL import Image
    from tools.image_process import execute_convert

    # 生成 RGBA 图像
    rgba_img = Image.new("RGBA", (50, 50), color=(255, 0, 0, 128))
    rgba_img.save(workspace_tmp / "rgba.png", format="PNG")
    rgba_img.close()

    result = await execute_convert(
        {"input_path": "rgba.png", "output_path": "rgba.jpg", "target_format": "JPEG"},
        context=None,
    )
    assert result["success"] is True


# ============ image_thumbnail 测试 ============

@pytest.mark.asyncio
async def test_thumbnail_basic(workspace_tmp):
    """缩略图生成:输出尺寸不超过 max_size"""
    from tools.image_process import execute_thumbnail

    # 100x80 → max_size=40,缩略图应 ≤ 40x32(保持比例)
    result = await execute_thumbnail(
        {"input_path": "input.png", "output_path": "thumb.png", "max_size": 40},
        context=None,
    )

    assert result["success"] is True
    assert result["operation"] == "thumbnail"
    assert max(result["new_size"]) <= 40
    assert (workspace_tmp / "thumb.png").exists()


@pytest.mark.asyncio
async def test_thumbnail_smaller_than_max(workspace_tmp):
    """原图小于 max_size:尺寸不变"""
    from tools.image_process import execute_thumbnail

    # 100x80,max_size=200 → 不放大
    result = await execute_thumbnail(
        {"input_path": "input.png", "output_path": "thumb_big.png", "max_size": 200},
        context=None,
    )
    assert result["success"] is True
    assert result["new_size"] == [100, 80]


@pytest.mark.asyncio
async def test_thumbnail_invalid_max_size_returns_warning(workspace_tmp):
    """非法 max_size 返回 warning"""
    from tools.image_process import execute_thumbnail

    result = await execute_thumbnail(
        {"input_path": "input.png", "output_path": "thumb.png", "max_size": 0},
        context=None,
    )
    assert result["success"] is False
    assert "warning" in result


# ============ image_info 测试 ============

@pytest.mark.asyncio
async def test_info_basic(workspace_tmp):
    """读取图像元信息"""
    from tools.image_process import execute_info

    result = await execute_info({"input_path": "input.png"}, context=None)

    assert result["success"] is True
    assert result["operation"] == "info"
    assert result["format"] == "PNG"
    assert result["mode"] in ("RGB", "RGBA")
    assert result["width"] == 100
    assert result["height"] == 80
    assert result["size"] == [100, 80]
    assert result["file_size"] > 0


@pytest.mark.asyncio
async def test_info_nonexistent_file_returns_warning(workspace_tmp):
    """不存在的文件返回 warning"""
    from tools.image_process import execute_info

    result = await execute_info({"input_path": "missing.png"}, context=None)
    assert result["success"] is False
    assert "不存在" in result["warning"]


# ============ execute 统一入口测试 ============

@pytest.mark.asyncio
async def test_execute_unknown_action_returns_warning(workspace_tmp):
    """未知 action 返回 warning"""
    from tools.image_process import execute

    result = await execute({"action": "unknown"}, context=None)
    assert result["success"] is False
    assert "未知 action" in result["warning"]


# ============ 路径遍历防护测试 ============

@pytest.mark.asyncio
async def test_path_traversal_rejected(workspace_tmp):
    """路径遍历被拒绝"""
    from tools.image_process import execute_resize

    result = await execute_resize(
        {"input_path": "../../../etc/passwd", "output_path": "out.png", "width": 50, "height": 50},
        context=None,
    )
    assert result["success"] is False
    assert "warning" in result


# ============ executor 路由测试 ============

def test_tool_executors_registered():
    """TOOL_EXECUTORS 应包含 4 个图像工具"""
    from tools import TOOL_EXECUTORS

    assert "image_resize" in TOOL_EXECUTORS
    assert "image_convert" in TOOL_EXECUTORS
    assert "image_thumbnail" in TOOL_EXECUTORS
    assert "image_info" in TOOL_EXECUTORS


@pytest.mark.asyncio
async def test_executor_routes_image_info(workspace_tmp):
    """TOOL_EXECUTORS 路由 image_info → execute_info"""
    from tools import TOOL_EXECUTORS

    executor = TOOL_EXECUTORS["image_info"]
    result = await executor({"input_path": "input.png"}, context=None)
    assert result["success"] is True
    assert result["operation"] == "info"


# ============ tool_registry 注册验证 ============

def test_registry_has_image_tools():
    """tool_registry 注册了 4 个图像工具"""
    from core.tool_registry import get_tool

    assert get_tool("image_resize") is not None
    assert get_tool("image_convert") is not None
    assert get_tool("image_thumbnail") is not None
    assert get_tool("image_info") is not None


def test_registry_tool_metadata():
    """工具元数据正确"""
    from core.tool_registry import get_tool

    resize = get_tool("image_resize")
    assert resize.category == "数据存储"
    assert resize.icon == "🖼️"
    assert "input_path" in resize.required
    assert "output_path" in resize.required
    assert "width" in resize.required
    assert "height" in resize.required

    info = get_tool("image_info")
    assert "input_path" in info.required
    assert "output_path" not in info.required


def test_registry_get_tool_schema():
    """get_tool_schema 生成 OpenAI function schema"""
    from core.tool_registry import get_tool_schema

    schema = get_tool_schema("image_resize")
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "image_resize"
    assert "input_path" in schema["function"]["parameters"]["properties"]
    assert "width" in schema["function"]["parameters"]["properties"]
    assert "input_path" in schema["function"]["parameters"]["required"]
