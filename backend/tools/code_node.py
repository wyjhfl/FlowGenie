"""Python 代码节点 - 在安全沙箱中执行用户代码

沙箱策略(白名单优先):
1. AST 静态检查:禁止访问危险属性(__class__/__bases__/__subclasses__/__globals__ 等)
2. 导入白名单:仅允许安全的标准库模块(math/json/re/datetime 等),其他一律拒绝
3. 运行时 _safe_import:双重防护,白名单外模块拒绝
4. 受限 builtins:移除 eval/exec/open/__import__ 等危险函数
5. 超时保护:10 秒限制,通过 asyncio.to_thread 避免阻塞事件循环
"""
import ast
import asyncio
import json
from datetime import datetime, timedelta

# 保存真实 __import__ 引用,供沙箱内 datetime 等模块内部使用
_real_import = __import__


# ===== 沙箱白名单:仅这些模块允许导入 =====
ALLOWED_IMPORTS = {
    # 基础数据结构
    "json", "re", "math", "decimal", "fractions", "statistics",
    "collections", "itertools", "functools", "heapq", "bisect", "array",
    "copy",
    # 时间日期
    "datetime", "time", "calendar",
    # 字符串/文本
    "string", "textwrap",
    # 类型/工具
    "typing", "uuid",
    # 安全的哈希/随机(不涉及加密密钥管理)
    "hashlib", "hmac", "secrets", "random",
}

# ===== 黑名单(冗余防护,即使白名单漏判也拦截) =====
FORBIDDEN_IMPORTS = {
    # 网络
    "os", "sys", "subprocess", "socket", "socketserver", "ssl",
    "http", "urllib", "urllib3", "requests", "ftplib", "telnetlib",
    "smtplib", "imaplib", "poplib", "nntplib", "webbrowser", "asyncio",
    # 序列化/反序列化(可执行任意代码)
    "pickle", "shelve", "marshal", "copyreg",
    # 动态代码/AST
    "ast", "code", "codeop", "compile", "compileall",
    # 解释器/进程/线程
    "multiprocessing", "threading", "concurrent", "forkpy",
    "ctypes", "cffi",
    # 文件系统
    "pathlib", "shutil", "tempfile", "fileinput", "glob",
    "distutils", "pkgutil", "importlib", "builtins",
    # 内省/逃逸
    "gc", "inspect", "traceback", "types", "warnings",
    # 其他危险
    "platform", "sysconfig", "sitecustomize", "usercustomize",
}


def _check_code_safety(code: str) -> str | None:
    """AST 静态检查:禁止访问危险属性

    返回错误信息字符串(拒绝)或 None(通过)。
    """
    DANGEROUS_ATTRS = {
        # 类型内省逃逸
        "__class__", "__bases__", "__subclasses__", "__mro__",
        "__subclasshook__",
        # 命名空间逃逸
        "__globals__", "__builtins__", "__dict__", "__module__",
        # 导入/代码对象
        "__import__", "__loader__", "__spec__", "__code__",
        # 函数/方法绑定
        "__init__", "__self__", "__getattribute__", "__func__", "__wrapped__",
        # 序列化绕过
        "__reduce__", "__reduce_ex__",
        # traceback / frame(获取调用栈逃逸)
        "__traceback__", "tb_frame", "tb_lineno", "tb_next",
        "f_globals", "f_locals", "f_builtins", "f_code", "f_back",
        # generator / coroutine 帧
        "gi_frame", "gi_code", "cr_frame", "cr_code",
    }
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f"语法错误: {e}"

    dangerous_found = []
    for node in ast.walk(tree):
        # 检查属性访问 x.__class__ 等
        if isinstance(node, ast.Attribute):
            if node.attr in DANGEROUS_ATTRS and node.attr not in dangerous_found:
                dangerous_found.append(node.attr)

    if dangerous_found:
        return f"禁止访问危险属性: {', '.join(dangerous_found)}"

    return None


def _check_imports(code: str) -> str | None:
    """AST 级导入检查:白名单优先,黑名单兜底

    返回错误信息字符串(拒绝)或 None(通过)。
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f"语法错误: {e}"

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                err = _check_single_import(alias.name)
                if err:
                    return err
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            err = _check_single_import(mod)
            if err:
                return err
            # 检查 from 导入的具体名称(防止 `from os import system`)
            for alias in node.names:
                # name 是导入的符号,无法直接判断是否危险,
                # 但若 module 已通过白名单校验,符号默认允许
                # (如 `from datetime import timedelta` 是合法的)
                pass

    return None


def _check_single_import(module_name: str) -> str | None:
    """检查单个模块名是否允许导入

    策略:取顶级模块名,白名单内允许;否则拒绝。
    """
    if not module_name:
        return None
    top = module_name.split(".")[0]
    if top in ALLOWED_IMPORTS:
        return None
    if top in FORBIDDEN_IMPORTS:
        return f"禁止导入 {module_name} 模块(黑名单)"
    # 既不在白名单也不在黑名单:默认拒绝(白名单策略)
    return f"禁止导入 {module_name} 模块(不在白名单)"


async def execute(params, context=None):
    """Python 代码节点 - 在安全沙箱中执行用户代码

    :param params: { code, input }
    :return: { result, success, error }
    """
    code = params.get("code", "")
    input_data = params.get("input", None)

    if not code or not code.strip():
        raise ValueError("code 参数不能为空")

    # 1. AST 安全检查:禁止危险属性访问
    safety_error = _check_code_safety(code)
    if safety_error:
        return {"result": None, "success": False, "error": safety_error}

    # 2. AST 导入检查:白名单优先
    import_error = _check_imports(code)
    if import_error:
        return {"result": None, "success": False, "error": import_error}

    # 运行时 _safe_import:双重防护,与静态检查一致
    def _safe_import(name, *args, **kwargs):
        err = _check_single_import(name)
        if err:
            raise ImportError(err)
        return _real_import(name, *args, **kwargs)

    # 受限全局命名空间
    safe_globals = {
        "__builtins__": {
            # 基础类型
            "print": print,
            "len": len,
            "str": str, "int": int, "float": float, "bool": bool,
            "list": list, "dict": dict, "set": set, "tuple": tuple,
            "bytes": bytes, "bytearray": bytearray,
            # 迭代/序列
            "range": range, "enumerate": enumerate, "zip": zip,
            "map": map, "filter": filter,
            "sorted": sorted, "reversed": reversed,
            "iter": iter, "next": next,
            "slice": slice,
            # 数学
            "min": min, "max": max, "sum": sum,
            "abs": abs, "round": round, "pow": pow, "divmod": divmod,
            "all": all, "any": any,
            # 类型检查
            "isinstance": isinstance, "issubclass": issubclass,
            "type": type,  # type() 构造允许,但 __class__ 访问已被 AST 拦截
            "id": id,
            # 字典/集合操作
            "keys": lambda d: d.keys(),
            "values": lambda d: d.values(),
            "items": lambda d: d.items(),
            # 模块
            "json": json,
            # 异常类型(允许 try/except)
            "TypeError": TypeError, "ValueError": ValueError,
            "KeyError": KeyError, "IndexError": IndexError,
            "AttributeError": AttributeError, "StopIteration": StopIteration,
            "ZeroDivisionError": ZeroDivisionError, "Exception": Exception,
            # 受控导入
            "__import__": _safe_import,
            # 显式移除危险函数
            # eval / exec / open / compile / input / __build_class__ 不在此处
        },
        "input": input_data,
        "result": None,
        "datetime": datetime,
        "timedelta": timedelta,
    }

    try:
        await asyncio.wait_for(
            asyncio.to_thread(exec, code, safe_globals),
            timeout=10
        )
        result = safe_globals.get("result")
        return {"result": result, "success": True, "error": None}
    except asyncio.TimeoutError:
        return {"result": None, "success": False, "error": "代码执行超时(10秒限制)"}
    except Exception as e:
        return {"result": None, "success": False, "error": f"{type(e).__name__}: {str(e)}"}
