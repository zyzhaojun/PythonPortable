# PythonPortable — 便携 Python 教学运行台

面向**高中信息技术教学**的免安装 U 盘工具。双击一个 `.bat` 即可在课堂电脑上打开一个浏览器版
Python 运行台：左边写代码、右边看输出（文本、`input()` 交互、pandas 表格、matplotlib 图像），
**课堂电脑无需预装 Python 或任何第三方库**。

## 工作原理

```
双击 Start-PythonTeaching.bat
        │
        ▼
runtimes\python37\python.exe teaching_shell.py   ← 用 3.7 启动，兼容老机房
        │  启动一个只监听 127.0.0.1 的本地 HTTP 服务，并自动打开浏览器
        ▼
浏览器中的教学网页（单页 HTML，内嵌在 teaching_shell.py 的 HTML_PAGE 里）
        │  学生点「运行」→ POST /run/interactive/start
        ▼
teaching_shell.py 按所选版本调起 runner.py 子进程执行学生代码
        │  runner.py 负责：捕获 stdout/stderr、支持 input()、
        │  把 DataFrame 渲染成 HTML 表格、把 matplotlib 图存成 PNG
        ▼
网页轮询 /run/interactive/status 显示结果
```

仅监听本机回环地址、不联网、不对外开放端口。

## 编辑器与文件功能

- **语法高亮**：零依赖、纯前端实现——透明 `<textarea>` 叠加一层着色 `<pre>`，配一个小巧的
  Python 着色器（关键字/字符串/注释/数字/函数名/内置名分色），完全离线，不引入任何外部库。
- **行号 + 草稿自动保存**：左侧行号与报错对照；代码用 `localStorage` 自动保存。
- **打开 / 保存 .py**：纯前端 `FileReader` 打开、`Blob` 下载保存。
- **打开数据文件（.xlsx/.csv）**：前端把文件经 `POST /upload`（base64）传到本地服务，
  由 `save_uploaded_data` 校验扩展名/大小、basename 防穿越后写入程序目录，
  学生即可用 `pd.read_csv("名字.csv")` / `pd.read_excel("名字.xlsx")` 读取。

## 目录结构

```
PythonPortable/
├─ Start-PythonTeaching.bat   启动器
├─ teaching_shell.py          本地 Web 服务 + 教学网页（核心）
├─ runner.py                  在子进程中执行学生代码的执行层
├─ README-USB.txt             给老师/学生的使用说明（随 U 盘分发）
├─ data.xlsx                  教学样例数据
└─ runtimes/                  两套嵌入式 Python（二进制，不纳入 Git，见下）
   ├─ python37/   Python 3.7.9   + numpy/pandas/matplotlib/openpyxl/Pillow
   │  └─ python37._pth         嵌入式解释器路径配置
   └─ python312/  Python 3.12.10 + numpy/pandas/matplotlib/openpyxl/Pillow
      └─ python312._pth
```

## 内置库版本

| 库 | Python 3.7 | Python 3.12 |
|---|---|---|
| numpy | 1.21.6 | 2.4.6 |
| pandas | 1.3.5 | 3.0.3 |
| matplotlib | 3.5.3 | 3.10.9 |
| openpyxl | 3.0.10 | 3.1.5 |
| Pillow | 9.5.0 | 12.2.0 |

双运行时：3.7 兼容较老的机房 Windows（含 Win7），3.12 用于较新电脑；低于 Win8.1 选 3.12 时网页会提示改用 3.7。

## 版本管理说明

本仓库只纳入**文本源码**（`teaching_shell.py`、`runner.py`、`Start-PythonTeaching.bat`、
`README-USB.txt`、`*._pth`）。两套嵌入式 Python 运行时与第三方库属二进制大文件，
通过 `.gitignore` 排除，发布时随 U 盘 / 离线包分发。要得到可运行的 U 盘，
需把 `runtimes/python37`、`runtimes/python312` 下的解释器与 `Lib/site-packages` 补齐。

## 性能 / 启动速度

为解决老机房电脑首次运行卡顿（曾长达 5 分钟）的问题：

- **重型库懒加载**：`runner.py` 不再每次运行都加载 matplotlib/pandas。只有代码里出现
  `matplotlib`/`pylab`/`seaborn` 时才配置字体；pandas/matplotlib 仅在学生代码自己导入后，
  才在 `display()` 与图像收集里通过 `sys.modules` 引用。print/input/循环等课程因此秒开。
- **后台预热**：`teaching_shell.py` 启动后在后台对各运行时预建 matplotlib 字体缓存
  （`warmup_runtimes_in_background`），把一次性的慢操作放到老师讲解阶段完成，使第一张图也不卡；
  缓存持久化在 `matplotlib_cache/`，跨会话/同版本复用。可用 `--no-warmup` 关闭。
- **制作 U 盘时预热一次**：`teaching_shell.py --warmup` 会建好字体缓存后退出，随 U 盘带走。

## 本地自检

在已装好运行时的目录下：

```bat
runtimes\python37\python.exe teaching_shell.py --self-test
```

会用两套运行时各跑一段导入 pandas 的代码，输出 OK / FAILED。

预热（制作 U 盘时跑一次，让课堂首次画图最快）：

```bat
runtimes\python37\python.exe teaching_shell.py --warmup
```
