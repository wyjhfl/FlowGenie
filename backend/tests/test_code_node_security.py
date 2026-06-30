"""code_node 沙箱安全测试套件

覆盖 15+ 绕过尝试 + 正常用例,确保沙箱不可逃逸。
"""
import pytest
from tools.code_node import execute


@pytest.mark.asyncio
async def test_normal_code_execution():
    """正常代码:简单数学运算"""
    result = await execute({"code": "result = 1 + 2 + 3"})
    assert result["success"] is True
    assert result["result"] == 6


@pytest.mark.asyncio
async def test_normal_code_with_input():
    """正常代码:使用 input 变量"""
    result = await execute({"code": "result = input * 2", "input": 21})
    assert result["success"] is True
    assert result["result"] == 42


@pytest.mark.asyncio
async def test_normal_code_with_json():
    """正常代码:json 处理"""
    code = 'result = json.loads(\'{"a": 1, "b": 2}\')'
    result = await execute({"code": code})
    assert result["success"] is True
    assert result["result"] == {"a": 1, "b": 2}


@pytest.mark.asyncio
async def test_normal_code_with_re():
    """正常代码:正则表达式"""
    code = 'import re\nresult = re.findall(r"\\d+", "a1b22c333")'
    result = await execute({"code": code})
    assert result["success"] is True
    assert result["result"] == ["1", "22", "333"]


@pytest.mark.asyncio
async def test_normal_code_with_math():
    """正常代码:数学模块"""
    code = 'import math\nresult = math.sqrt(16)'
    result = await execute({"code": code})
    assert result["success"] is True
    assert result["result"] == 4.0


# ===== 绕过尝试:网络访问 =====

@pytest.mark.asyncio
async def test_block_urllib_request():
    """绕过尝试:urllib.request 发起网络请求"""
    code = "import urllib.request\nresult = urllib.request.urlopen('http://evil.com')"
    result = await execute({"code": code})
    assert result["success"] is False
    assert "urllib" in result["error"]


@pytest.mark.asyncio
async def test_block_urllib_submodule():
    """绕过尝试:urllib.request 子模块"""
    code = "from urllib.request import urlopen\nresult = urlopen('http://evil.com')"
    result = await execute({"code": code})
    assert result["success"] is False
    assert "urllib" in result["error"]


@pytest.mark.asyncio
async def test_block_socket_direct():
    """绕过尝试:直接 socket 连接"""
    code = "import socket\ns = socket.socket()\ns.connect(('evil.com', 80))"
    result = await execute({"code": code})
    assert result["success"] is False
    assert "socket" in result["error"]


@pytest.mark.asyncio
async def test_block_http_client():
    """绕过尝试:http.client 模块"""
    code = "import http.client\nconn = http.client.HTTPSConnection('evil.com')"
    result = await execute({"code": code})
    assert result["success"] is False
    assert "http" in result["error"]


# ===== 绕过尝试:反序列化 =====

@pytest.mark.asyncio
async def test_block_pickle():
    """绕过尝试:pickle 反序列化攻击"""
    code = "import pickle\nresult = pickle.loads(b'abc')"
    result = await execute({"code": code})
    assert result["success"] is False
    assert "pickle" in result["error"]


# ===== 绕过尝试:命令执行 =====

@pytest.mark.asyncio
async def test_block_subprocess():
    """绕过尝试:subprocess 执行命令"""
    code = "import subprocess\nresult = subprocess.run(['id'], capture_output=True)"
    result = await execute({"code": code})
    assert result["success"] is False
    assert "subprocess" in result["error"]


@pytest.mark.asyncio
async def test_block_os_system():
    """绕过尝试:os.system 执行命令"""
    code = "import os\nos.system('whoami')"
    result = await execute({"code": code})
    assert result["success"] is False
    assert "os" in result["error"]


@pytest.mark.asyncio
async def test_block_os_path():
    """绕过尝试:os.path 子模块"""
    code = "import os.path\nresult = os.path.exists('/etc/passwd')"
    result = await execute({"code": code})
    assert result["success"] is False
    assert "os" in result["error"]


# ===== 绕过尝试:AST 动态代码 =====

@pytest.mark.asyncio
async def test_block_ast_module():
    """绕过尝试:ast 模块动态构造代码"""
    code = "import ast\nresult = ast.literal_eval('1+1')"
    result = await execute({"code": code})
    assert result["success"] is False
    assert "ast" in result["error"]


# ===== 绕过尝试:属性链逃逸 =====

@pytest.mark.asyncio
async def test_block_dunder_class_access():
    """绕过尝试:通过 __class__ 获取类型链"""
    code = 'result = "".__class__.__bases__[0].__subclasses__()'
    result = await execute({"code": code})
    assert result["success"] is False
    assert "危险属性" in result["error"]


@pytest.mark.asyncio
async def test_block_globals_access():
    """绕过尝试:通过 __globals__ 获取全局命名空间"""
    code = "def f(): pass\nresult = f.__globals__"
    result = await execute({"code": code})
    assert result["success"] is False
    assert "危险属性" in result["error"]


@pytest.mark.asyncio
async def test_block_builtins_access():
    """绕过尝试:通过 __builtins__ 获取内建命名空间"""
    code = "result = __builtins__"
    result = await execute({"code": code})
    # __builtins__ 在沙箱内已被替换为受限 dict,但 AST 不会拦截变量名访问
    # 这里验证它不能拿到真实 builtins
    assert result["success"] is True
    # 沙箱内 __builtins__ 是受限 dict,不应包含 eval/exec
    builtins_dict = result["result"]
    assert "eval" not in builtins_dict
    assert "exec" not in builtins_dict
    assert "open" not in builtins_dict


@pytest.mark.asyncio
async def test_block_subclasses_chain():
    """绕过尝试:通过 __subclasses__ 找到危险类"""
    code = 'result = object.__subclasses__()'
    result = await execute({"code": code})
    assert result["success"] is False
    assert "危险属性" in result["error"]


# ===== 绕过尝试:eval/exec 直接调用 =====

@pytest.mark.asyncio
async def test_block_eval_call():
    """绕过尝试:eval 执行字符串代码"""
    code = 'result = eval("__import__(\'os\').system(\'id\')")'
    result = await execute({"code": code})
    # eval 未在沙箱 builtins 中,应 NameError
    assert result["success"] is False
    assert "NameError" in result["error"] or "eval" in result["error"].lower()


@pytest.mark.asyncio
async def test_block_exec_call():
    """绕过尝试:exec 执行字符串代码"""
    code = 'exec("import os")'
    result = await execute({"code": code})
    assert result["success"] is False
    assert "NameError" in result["error"] or "exec" in result["error"].lower()


@pytest.mark.asyncio
async def test_block_open_call():
    """绕过尝试:open 读取文件"""
    code = 'result = open("/etc/passwd").read()'
    result = await execute({"code": code})
    assert result["success"] is False
    assert "NameError" in result["error"] or "open" in result["error"].lower()


# ===== 绕过尝试:其他危险模块 =====

@pytest.mark.asyncio
async def test_block_ctypes():
    """绕过尝试:ctypes 调用 C 库"""
    code = "import ctypes\nresult = ctypes.CDLL(None)"
    result = await execute({"code": code})
    assert result["success"] is False
    assert "ctypes" in result["error"]


@pytest.mark.asyncio
async def test_block_multiprocessing():
    """绕过尝试:multiprocessing 启动进程"""
    code = "import multiprocessing\np = multiprocessing.Process(target=print)"
    result = await execute({"code": code})
    assert result["success"] is False
    assert "multiprocessing" in result["error"]


@pytest.mark.asyncio
async def test_block_threading():
    """绕过尝试:threading 启动线程"""
    code = "import threading\nt = threading.Thread(target=print)"
    result = await execute({"code": code})
    assert result["success"] is False
    assert "threading" in result["error"]


@pytest.mark.asyncio
async def test_block_pathlib():
    """绕过尝试:pathlib 遍历文件系统"""
    code = "from pathlib import Path\nresult = Path('/').iterdir()"
    result = await execute({"code": code})
    assert result["success"] is False
    assert "pathlib" in result["error"]


@pytest.mark.asyncio
async def test_block_unknown_module_rejected():
    """白名单策略:未在白名单的未知模块默认拒绝"""
    code = "import some_unknown_module\nresult = some_unknown_module.x"
    result = await execute({"code": code})
    assert result["success"] is False
    # 运行时会尝试 _safe_import,被拒绝
    assert "白名单" in result["error"] or "some_unknown_module" in result["error"]


# ===== 超时保护 =====

@pytest.mark.asyncio
async def test_timeout_protection():
    """超时保护:死循环应在 10 秒内被中断"""
    code = "while True:\n    pass"
    result = await execute({"code": code})
    assert result["success"] is False
    assert "超时" in result["error"]


# ===== 沙箱内安全模块仍可用 =====

@pytest.mark.asyncio
async def test_allowed_collections():
    """白名单模块:collections 可用"""
    code = "from collections import Counter\nresult = Counter('abracadabra')"
    result = await execute({"code": code})
    assert result["success"] is True


@pytest.mark.asyncio
async def test_allowed_itertools():
    """白名单模块:itertools 可用"""
    code = "import itertools\nresult = list(itertools.chain([1,2], [3,4]))"
    result = await execute({"code": code})
    assert result["success"] is True
    assert result["result"] == [1, 2, 3, 4]


@pytest.mark.asyncio
async def test_allowed_datetime():
    """白名单模块:datetime 可用"""
    code = "from datetime import datetime, timedelta\nresult = (datetime(2026,1,1) + timedelta(days=1)).isoformat()"
    result = await execute({"code": code})
    assert result["success"] is True
    assert result["result"] == "2026-01-02T00:00:00"
