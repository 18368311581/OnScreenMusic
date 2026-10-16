"""Local HTML guide rendered by Qt Widgets; no browser engine is required."""

HELP_HTML = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><style>
body {font-family:'Microsoft YaHei UI';font-size:14px;color:#263247;background:white;margin:22px;}
h1 {font-size:28px;color:#182a43;margin-bottom:8px;} h2 {font-size:19px;color:#245cca;margin-top:26px;}
p,li {line-height:1.65;} .muted {color:#738198;} a {color:#326ce5;text-decoration:none;}
table {border-collapse:collapse;width:100%;} td {padding:14px;background:#f3f7fe;}
</style></head><body>
<p class="muted">ON SCREEN MUSIC · 音乐管理</p><h1>整理音乐，从这里开始</h1>
<p class="muted">管理歌曲、处理歌词与整理歌单，都在一个窗口中完成。</p>
<table cellspacing="0" cellpadding="14"><tr><td>
<b>先准备工具，再开始处理</b><br>在参数设置中为各项工具选择文件、自动查找，或点击下载。
下载会打开独立命令行窗口，完成后按回车关闭。large-v3 模型约 3.1 GB，已有文件会直接复用。
</td></tr></table>
<p><a href="#library">歌曲资料</a>　·　<a href="#processing">处理歌曲</a>　·　
<a href="#playlists">歌单管理</a>　·　<a href="#tasks">任务记录</a>　·　<a href="#settings">参数设置</a></p>
<h2 id="library">01　歌曲资料</h2>
<p>资料库仅列出 music 文件夹第一层的 MP3，可按歌名搜索；歌单引用在歌单管理中单独维护。</p>
<p>点击每行的<b>编辑歌词</b>打开同名 LRC。直接编辑，内容改变后保存按钮启用，恢复原内容后置灰。
保存会备份原歌词；原文件被其他程序改动时会阻止覆盖。关闭或按 Esc 时会提醒未保存修改。</p>
<p>窗口内可播放、暂停、拖动进度条与调节音量。打开不自动播放，关闭即停止。
整体时间偏移和纯音乐标记也可以撤销；修改后点击保存生效。</p>
<h2 id="processing">02　处理歌曲</h2>
<p>通过添加文件、添加文件夹或选择现有歌曲加入列表，再逐行设置：</p>
<ul><li><b>格式响度</b>：新素材转成统一 MP3，现有歌曲保留原音频。</li>
<li><b>识别歌词</b>：本地识别，不上传音频。</li>
<li><b>AI 校对</b>：先通过本行的参考歌词按钮填写完整原词；在线校对仅发送歌词文本。</li>
<li><b>允许重复</b>：本地识别时，确认大量重复确属原词后勾选。</li></ul>
<p>选中歌曲后开始处理。条件不满足时按钮置灰，悬停可查看原因。
同时识别和校对时，AI 使用本次识别的新草稿。整项成功后，最终歌词自动写入 lyrics 中的对应 LRC，覆盖前保留旧版备份；失败或终止不更新原歌词。转换音频仍保存在工作目录。</p>
<p>行末 × 仅移除处理条目；移除全部会保留排队和正在处理的任务。</p>
<h2 id="playlists">03　歌单管理</h2>
<p>选择歌单后自动载入并检查。有错误时可自动修复，移除错误行后保存才生效。
正常重复行代表权重，不算错误。每行可修改整数权重及歌词开关，末行 ＋ 添加歌曲。</p>
<p>删除歌单需要确认，原 TXT 会备份；歌曲和歌词文件不会删除。
修改歌单或歌词后，在桌面播放器点击<b>刷新</b>读取新内容。</p>
<h2 id="tasks">04　任务记录</h2>
<p>每行显示一个任务的阶段与进度。进行中点击 ×，确认后仅终止该任务；未完成结果不提交，其他任务继续。
完成、失败和终止记录保留到手动删除；删除记录不会删除音乐或已保存结果。</p>
<h2 id="settings">05　参数设置</h2>
<p>FFmpeg、本地识别程序和模型分别管理。选择已有文件后单独保存；自动查找会复用本机文件并保存该项。
下载窗口会校验并安装到软件旁的 tools 文件夹，完成后自动保存对应路径；不会修改系统 PATH。</p>
<p>接口密钥也单独保存，仅保存在本机。软件与资料一起移动时，同目录下的相对路径会随之移动。</p>
<p>清理临时文件可查看占用并选择清理范围。默认保留任务结果和历史备份；下载缓存及备份可分别选择，确认后才删除。处理或下载期间暂不清理。</p>
<table cellspacing="0" cellpadding="14"><tr><td><b>资料位置</b><br>
music：歌曲　·　lyrics：歌词　·　playlists：歌单<br>
MusicWorkshopWork：处理结果与备份<br><span class="muted">真实识别质量、歌词版本及时间仍需试听确认。</span></td></tr></table>
<p class="muted">音乐管理与桌面播放器独立运行，由同目录的 OnScreenMusic.ini 保存各自设置。</p>
</body></html>"""
