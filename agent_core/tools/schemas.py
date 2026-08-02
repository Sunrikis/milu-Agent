"""集中定义提供给模型的工具 schema。
Define all model-facing tool schemas in one place.
"""

from __future__ import annotations


TOOL_DEFINITIONS = [
    {
        "name": "run_command",
        "description": (
            "在项目目录执行 shell 命令并返回退出码、标准输出和错误输出。"
            "shell=auto 时 Windows 使用 PowerShell；不要写 Bash 语法。"
            "读取目录、文本或 docx 时优先使用 list_directory/read_file，"
            "避免命令行转义和中文编码问题"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的 shell 命令"
                },
                "shell": {
                    "type": "string",
                    "enum": ["auto", "powershell", "cmd", "sh", "bash"],
                    "description": "自动选择或明确指定 shell；Windows 推荐 powershell",
                },
            },
            "required": ["command", "shell"],
            "additionalProperties": False,
        },
    },
    {
        "name": "run_python_script",
        "description": (
            "使用 Agent 当前 Python 解释器安全运行项目目录内的 .py 脚本。"
            "参数通过独立数组传递，不要拼接 shell 命令；运行项目 Python 脚本时"
            "优先于 run_command"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "script_path": {
                    "type": "string",
                    "description": "项目相对路径或项目内绝对路径",
                },
                "args": {
                    "type": "array",
                    "maxItems": 100,
                    "items": {
                        "type": "string"
                    },
                    "description": "按顺序传给脚本的参数，不包含 Python 命令",
                },
            },
            "required": ["script_path", "args"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_directory",
        "description": (
            "直接列出本地目录，原生支持 Windows 中文路径。"
            "优先于用 run_command 调用 ls/dir"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "绝对或项目相对目录"
                },
                "pattern": {
                    "type": "string",
                    "description": "glob 模式，例如 * 或 *.docx",
                },
                "recursive": {
                    "type": "boolean",
                    "description": "是否递归"
                },
                "max_entries": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 1000,
                },
            },
            "required": ["path", "pattern", "recursive", "max_entries"],
            "additionalProperties": False,
        },
    },
    {
        "name": "read_file",
        "description": (
            "直接读取本地文本或 .docx，自动处理 UTF-8/GBK 与中文路径。"
            "统一返回 source、total_chars、range 和 has_more，"
            "可用 start_char 分段继续读取"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "绝对或项目相对文件"
                },
                "start_char": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "从第几个字符开始；首次读取传 0",
                },
                "max_chars": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 50000,
                    "description": "本次最多读取的正文字符数",
                },
            },
            "required": ["path", "start_char", "max_chars"],
            "additionalProperties": False,
        },
    },
    {
        "name": "read_files",
        "description": (
            "一次批量读取最多 10 个本地文本或 .docx。"
            "适合独立章节或多个小文件，可显著减少工具调用轮数"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "files": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 10,
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string"
                            },
                            "start_char": {
                                "type": "integer",
                                "minimum": 0
                            },
                            "max_chars": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 50000,
                            },
                        },
                        "required": ["path", "start_char", "max_chars"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["files"],
            "additionalProperties": False,
        },
    },
    {
        "name": "read_daily_memory",
        "description": (
            "按单日或日期范围读取 memory/YYYY-MM-DD.md 情景记忆。"
            "用户询问某天、前天、N天前、最近N天或明确日期区间时调用。"
            "query_type=date 时使用 date 或 days_ago；query_type=range 时使用"
            "start_date/end_date 或 recent_days。相对日期由工具按当前本地日期计算"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query_type": {
                    "type": "string",
                    "enum": ["date", "range"],
                    "description": "单日用 date，连续日期范围用 range",
                },
                "date": {
                    "type": "string",
                    "description": "明确单日，格式 YYYY-MM-DD",
                },
                "days_ago": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 36500,
                    "description": "相对单日：今天为0、昨天为1、前天为2",
                },
                "start_date": {
                    "type": "string",
                    "description": "明确范围起始日，格式 YYYY-MM-DD，包含当天",
                },
                "end_date": {
                    "type": "string",
                    "description": "明确范围结束日，格式 YYYY-MM-DD，包含当天",
                },
                "recent_days": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 31,
                    "description": "最近N天，包含今天，例如3表示今天及之前2天",
                },
                "max_chars": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 50000,
                    "description": "本次最多读取的记忆字符数",
                },
            },
            "required": ["query_type", "max_chars"],
            "additionalProperties": False,
        },
    },
    {
        "name": "web_fetch",
        "description": (
            "获取并在当前进程缓存完整的 HTTP/HTTPS 网页，支持纯文本或原始 HTML。"
            "返回 source、total_chars、range 和 has_more；若 has_more 为 true，"
            "把 range 的结束位置作为下一次 start_char，直至完整读取"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "完整的 HTTP/HTTPS URL"
                },
                "extract_mode": {
                    "type": "string",
                    "enum": ["text", "raw"],
                    "description": "提取正文用 text，读取原始 HTML 用 raw",
                },
                "start_char": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "从第几个字符开始；首次读取传 0",
                },
                "max_chars": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 50000,
                    "description": "本次最多读取的正文字符数",
                },
            },
            "required": ["url", "extract_mode", "start_char", "max_chars"],
            "additionalProperties": False,
        },
    },
    {
        "name": "load_skill",
        "description": (
            "加载指定技能的详细知识内容和 source_path，在回答相关问题前调用；"
            "source_path 的父目录就是该技能目录"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "系统提示中列出的技能名称",
                }
            },
            "required": ["skill_name"],
            "additionalProperties": False,
        },
    },
]
