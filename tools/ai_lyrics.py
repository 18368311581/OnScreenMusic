"""Shared text-only AI lyric repair used by the independent music tools."""
from __future__ import annotations

import json
import os
import re
from urllib import error, request

DEEPSEEK_ENDPOINT = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-v4-pro"
TIMED_LRC_PATTERN = re.compile(r"^\[(\d+):([0-5]\d)(?:\.(\d{1,3}))?\](.*)$")
LRC_LINE_PATTERN = re.compile(r"^(?:\[[^\]\r\n]+\])+")

class AiRepairError(RuntimeError):
    pass

def build_ai_messages(song_name: str, draft_lrc: str, reference_lyrics: str) -> list[dict]:
    system_prompt = (
        "你是专业的中文 LRC 歌词校对工具。只返回最终的标准 LRC 文本，不要解释，"
        "不要使用 Markdown 代码块。识别草稿中的时间戳是时间定位依据，参考歌词是"
        "文字、顺序和完整性依据。修正错别字和漏字，按歌曲顺序拆分参考歌词并匹配到"
        "合理时间；必要时可在相邻时间之间补充时间戳。不得添加作词、作曲、字幕组、"
        "水印或参考内容中不存在的歌词。时间戳必须递增。"
    )
    user_prompt = (
        f"歌曲名：{song_name}\n\n"
        "<带时间戳的识别草稿>\n"
        f"{draft_lrc}\n"
        "</带时间戳的识别草稿>\n\n"
        "<无时间戳的完整参考歌词>\n"
        f"{reference_lyrics}\n"
        "</无时间戳的完整参考歌词>"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def request_ai_repair(
    song_name: str,
    draft_lrc: str,
    reference_lyrics: str,
    api_key: str,
) -> str:
    payload = json.dumps(
        {
            "model": DEEPSEEK_MODEL,
            "messages": build_ai_messages(song_name, draft_lrc, reference_lyrics),
            "temperature": 0.1,
            "stream": False,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    api_request = request.Request(
        DEEPSEEK_ENDPOINT,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    os.environ["NO_PROXY"] = "api.deepseek.com"
    opener = request.build_opener()
    try:
        with opener.open(api_request, timeout=180) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        try:
            error_data = json.loads(exc.read().decode("utf-8", errors="replace"))
            detail = error_data.get("error", {}).get("message", str(exc))
        except (ValueError, AttributeError):
            detail = str(exc)
        raise AiRepairError(f"DeepSeek 接口返回错误：{detail}") from exc
    except (error.URLError, TimeoutError, OSError) as exc:
        raise AiRepairError(f"无法连接 DeepSeek：{exc}") from exc
    except (UnicodeError, ValueError) as exc:
        raise AiRepairError(f"DeepSeek 返回内容无法解析：{exc}") from exc

    try:
        content = response_data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AiRepairError("DeepSeek 返回结果中没有歌词内容。") from exc
    if not isinstance(content, str) or not content.strip():
        raise AiRepairError("DeepSeek 返回了空歌词。")
    return content


def normalize_ai_lrc(content: str) -> str:
    text = content.strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]).strip()

    output_lines = []
    timestamps = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if not LRC_LINE_PATTERN.match(line):
            raise AiRepairError(f"AI 返回了非 LRC 内容：{line[:60]}")
        output_lines.append(line)
        match = TIMED_LRC_PATTERN.match(line)
        if match:
            fraction = (match.group(3) or "0").ljust(3, "0")[:3]
            timestamp = (int(match.group(1)) * 60_000) + (int(match.group(2)) * 1_000)
            timestamp += int(fraction)
            timestamps.append(timestamp)

    if not timestamps:
        raise AiRepairError("AI 返回结果中没有有效的时间戳歌词。")
    if timestamps != sorted(timestamps):
        raise AiRepairError("AI 返回的歌词时间戳顺序错误，未覆盖原文件。")
    return "\n".join(output_lines) + "\n"
