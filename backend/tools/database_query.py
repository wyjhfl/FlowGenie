"""数据库查询工具 - SQLAlchemy

安全策略:
1. 白名单:仅允许 SELECT / WITH 开头的语句
2. 黑名单:拒绝 INSERT/UPDATE/DELETE/DROP/ALTER/INTO/COPY/ATTACH/PRAGMA/CREATE/TRUNCATE/REPLACE/MERGE/GRANT/REVOKE
3. 注释绕过防护:校验前去除 /* */ 块注释和 -- 行注释
4. 参数化查询:支持 params 字典,用 :param 占位符绑定,防止 SQL 注入
"""
import os
import re
from sqlalchemy import create_engine, text

# 查询白名单:仅允许 SELECT / WITH 开头的语句(大小写不敏感)
_SELECT_WHITELIST_RE = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)

# 显式拒绝的危险关键词(大小写不敏感,词边界匹配)
# 新增 INTO(防 SELECT ... INTO 建表)、COPY(PostgreSQL 批量导出)、GRANT/REVOKE(权限)
_FORBIDDEN_KEYWORDS_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|INTO|COPY|ATTACH|DETACH|PRAGMA|"
    r"CREATE|TRUNCATE|REPLACE|MERGE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)

# 注释模式:块注释 /* */ 和行注释 --
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT_RE = re.compile(r"--[^\n]*")


def _strip_comments(query: str) -> str:
    """去除 SQL 注释,防止通过注释绕过关键词校验"""
    query = _BLOCK_COMMENT_RE.sub(" ", query)
    query = _LINE_COMMENT_RE.sub(" ", query)
    return query


def _validate_query(query: str) -> str | None:
    """SQL 语句白名单 + 黑名单校验,返回错误信息或 None"""
    # 先去除注释,防止 /* INSERT */ SELECT 这种绕过
    stripped = _strip_comments(query)
    if not _SELECT_WHITELIST_RE.match(stripped):
        return "仅允许 SELECT/WITH 查询"
    if _FORBIDDEN_KEYWORDS_RE.search(stripped):
        return "不允许的 SQL 操作"
    return None


async def execute(params: dict, context) -> dict:
    """
    执行 SQL 查询
    :param params: { query, params? }
        - query: SQL 字符串,支持 :param 占位符参数化绑定
        - params: 可选,dict,与 query 中的 :param 占位符对应,防止 SQL 注入
    :return: { rows, count, columns, message } 或 { error }
    """
    query = params.get("query", "")
    query_params = params.get("params")

    if not query:
        raise ValueError("query 参数不能为空")

    # 顶部先做白名单+黑名单校验,通过后再执行
    err = _validate_query(query)
    if err:
        raise ValueError(err)

    # 参数化查询:params 必须是 dict,绑定到 :param 占位符
    if query_params is not None and not isinstance(query_params, dict):
        raise ValueError("params 必须是字典类型")

    # 不再从工作流参数读取 connection,统一从环境变量配置读取
    connection = os.getenv("DATABASE_URL", "sqlite:///./flowgenie.db")

    # SQLAlchemy 同步引擎(在 async 函数中同步调用,个人版可接受)
    engine = create_engine(connection)
    try:
        with engine.connect() as conn:
            # 参数化绑定:有 params 则用 text(query).bindparams,否则直接 text(query)
            stmt = text(query)
            if query_params:
                stmt = stmt.bindparams(**query_params)
            result = conn.execute(stmt)

            # 先判断是否返回行,再提取数据(避免迭代耗尽问题)
            if result.returns_rows:
                columns = list(result.keys())
                rows = [dict(zip(columns, row)) for row in result.fetchall()]
                return {
                    "rows": rows,
                    "count": len(rows),
                    "columns": columns,
                    "message": f"查询成功,返回 {len(rows)} 行",
                }
            else:
                # SELECT 通常 returns_rows=True;此处兜底
                conn.commit()
                return {"rows": [], "count": 0, "columns": [], "message": "执行成功(无返回行)"}
    finally:
        engine.dispose()
