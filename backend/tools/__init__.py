"""tools 包初始化 - 真实工具执行实现"""
from tools.http_request import execute as http_request
from tools.llm_summary import execute as llm_summary
from tools.llm_analysis import execute as llm_analysis
from tools.llm_review import execute as llm_review
from tools.send_email import execute as send_email
from tools.send_wechat import execute as send_wechat
from tools.send_slack import execute as send_slack
from tools.web_scraper import execute as web_scraper
from tools.database_query import execute as database_query
from tools.file_write import execute as file_write
from tools.file_read import execute as file_read_execute
from tools.data_transform import execute as data_transform_execute
from tools.chart_generator import execute as chart_generator_execute
from tools.llm_generate import execute as llm_generate_execute
from tools.rss_reader import execute as rss_reader_execute
from tools.github_api import execute as github_api_execute
from tools.send_dingtalk import execute as send_dingtalk_execute
from tools.send_telegram import execute as send_telegram_execute
from tools.code_node import execute as code_node_execute
from tools.if_else import execute as if_else_execute
from tools.llm_translate import execute as llm_translate_execute
from tools.llm_classify import execute as llm_classify_execute
from tools.llm_extract import execute as llm_extract_execute
from tools.wait_delay import execute as wait_delay_execute
from tools.switch_branch import execute as switch_branch_execute
from tools.text_template import execute as text_template_execute
from tools.notion_api import execute as notion_api_execute
from tools.feishu_api import execute as feishu_api_execute
from tools.json_path import execute as json_path_execute
from tools.regex_extract import execute as regex_extract_execute
from tools.date_format import execute as date_format_execute
from tools.array_ops import execute as array_ops_execute
from tools.math_calculate import execute as math_calculate_execute
from tools.function_call import execute as function_call_execute
from tools.conversation import (
    execute_start as conversation_start_execute,
    execute_continue as conversation_continue_execute,
    execute_list as conversation_list_execute,
)
from tools.object_storage import (
    execute_upload as object_storage_upload_execute,
    execute_download as object_storage_download_execute,
    execute_delete as object_storage_delete_execute,
    execute_list as object_storage_list_execute,
)
from tools.pdf_generator import execute as pdf_generator_execute
from tools.excel_io import (
    execute_write as excel_write_execute,
    execute_read as excel_read_execute,
)
from tools.image_process import (
    execute_resize as image_resize_execute,
    execute_convert as image_convert_execute,
    execute_thumbnail as image_thumbnail_execute,
    execute_info as image_info_execute,
)
from tools.embedding import execute as embedding_execute
from tools.vector_store import (
    execute_upsert as vector_store_upsert_execute,
    execute_search as vector_store_search_execute,
    execute_delete as vector_store_delete_execute,
)
# A1: 审批节点占位执行器(实际由 executor 拦截,抛出 PauseExecution 暂停工作流)
from tools.approve_node import execute as approve_node_execute
# A2: 子流程调用占位执行器(实际由 executor 拦截,从 DB 加载目标工作流递归执行)
from tools.subworkflow import execute as subworkflow_execute

# 工具执行器映射表
# 注: loop 工具由 executor 内部特殊处理(子流程遍历),不在此注册
# 注: approve_node 由 executor 内部拦截(抛出 PauseExecution),此注册仅为保持映射表完整
# 注: subworkflow 由 executor 内部拦截(递归调用 _execute_internal),此注册仅为保持映射表完整
TOOL_EXECUTORS = {
    "http_request": http_request,
    "llm_summary": llm_summary,
    "llm_analysis": llm_analysis,
    "llm_review": llm_review,
    "send_email": send_email,
    "send_wechat": send_wechat,
    "send_slack": send_slack,
    "web_scraper": web_scraper,
    "database_query": database_query,
    "file_write": file_write,
    "file_read": file_read_execute,
    "data_transform": data_transform_execute,
    "chart_generator": chart_generator_execute,
    "llm_generate": llm_generate_execute,
    "rss_reader": rss_reader_execute,
    "github_api": github_api_execute,
    "send_dingtalk": send_dingtalk_execute,
    "send_telegram": send_telegram_execute,
    "code_node": code_node_execute,
    "if_else": if_else_execute,
    "llm_translate": llm_translate_execute,
    "llm_classify": llm_classify_execute,
    "llm_extract": llm_extract_execute,
    "wait_delay": wait_delay_execute,
    "switch_branch": switch_branch_execute,
    "text_template": text_template_execute,
    "notion_api": notion_api_execute,
    "feishu_api": feishu_api_execute,
    "json_path": json_path_execute,
    "regex_extract": regex_extract_execute,
    "date_format": date_format_execute,
    "array_ops": array_ops_execute,
    "math_calculate": math_calculate_execute,
    "function_call": function_call_execute,
    "conversation_start": conversation_start_execute,
    "conversation_continue": conversation_continue_execute,
    "conversation_list": conversation_list_execute,
    "object_storage_upload": object_storage_upload_execute,
    "object_storage_download": object_storage_download_execute,
    "object_storage_delete": object_storage_delete_execute,
    "object_storage_list": object_storage_list_execute,
    "pdf_generator": pdf_generator_execute,
    "excel_write": excel_write_execute,
    "excel_read": excel_read_execute,
    "image_resize": image_resize_execute,
    "image_convert": image_convert_execute,
    "image_thumbnail": image_thumbnail_execute,
    "image_info": image_info_execute,
    "embedding": embedding_execute,
    "vector_store_upsert": vector_store_upsert_execute,
    "vector_store_search": vector_store_search_execute,
    "vector_store_delete": vector_store_delete_execute,
    "approve_node": approve_node_execute,
    "subworkflow": subworkflow_execute,
}
