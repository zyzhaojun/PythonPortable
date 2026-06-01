便携 Python 教学运行台（U 盘版）
================================

适用对象：高中信息技术课堂。课堂电脑无需预装 Python 或任何第三方库。

使用步骤
--------
1. 把整个 PythonPortable 文件夹复制到 U 盘（或本地任意目录）。
2. 双击 Start-PythonTeaching.bat。
3. 浏览器会自动打开教学网页。用右上角的「Python 3.7 / Python 3.12」按钮选择运行版本。
4. 在左边写代码，点「运行」（或按 Ctrl+Enter）。右边显示标准输出、input 提示、报错、表格和图像。
5. 当代码用到 input() 时，直接在右边输出区里输入并按回车。
6. 使用过程中请保持那个黑色命令行窗口开着，用完直接关闭即可。

编辑器小功能
------------
- 代码语法高亮（关键字、字符串、注释、数字、函数名分色），左侧带行号，报错行号可直接对照。
- 代码会自动保存在本浏览器里（localStorage），误关网页后重新打开仍在；点「清空」会同时清除草稿。
- 「打开」：把电脑上的 .py 文件载入编辑器。「保存」：把当前代码下载为 lesson.py。
- 「数据」：选择本地 .xlsx / .csv 数据文件载入程序目录，载入后即可在代码里读取，例如：
      import pandas as pd
      df = pd.read_csv("你的文件.csv")      # Excel 用 pd.read_excel("你的文件.xlsx")
  （页面会提示你该用哪一行读取代码。）

内置两套运行时
--------------
- runtimes\python37 ：Python 3.7.9
    numpy 1.21.6 / pandas 1.3.5 / matplotlib 3.5.3 / openpyxl 3.0.10 / Pillow 9.5.0
- runtimes\python312：Python 3.12.10
    numpy 2.4.6 / pandas 3.0.3 / matplotlib 3.10.9 / openpyxl 3.1.5 / Pillow 12.2.0

说明
----
- 网页服务由 Python 3.7 启动，以兼容较老的机房 Windows；运行学生代码时再按所选版本调用。
- 较老的 Windows（低于 Windows 8.1）不支持 Python 3.12，选到 3.12 时网页会提示改用 3.7。
- data.xlsx 就在本文件夹里，代码可直接用 pd.read_excel("data.xlsx")。读 Excel 依赖已内置的 openpyxl。
- matplotlib 已配置中文字体，图表中文不会乱码。
- 每次运行产生的临时文件放在 run_outputs\ 下，会在会话结束和下次启动时自动清理，不会越积越多。

加载速度（老机器很重要）
------------------------
- 不用绘图的代码（print、input、循环、字符串、列表等）现在不会加载 pandas / matplotlib，
  在老机器和慢速 U 盘上也能秒级运行。只有真正用到 matplotlib / pandas 的代码才会加载对应库。
- 第一次画图时 matplotlib 需要建立字体缓存（较慢，仅一次）。本程序在启动后会自动在后台预热，
  趁老师讲解时把缓存建好，让课堂上第一张图也不卡。缓存保存在 matplotlib_cache\，下次直接复用。
  ——日常上课什么都不用做，双击 Start-PythonTeaching.bat 即可，预热是全自动的。
- （可选，日常上课不需要）制作 U 盘母盘时，可先在一台电脑上预热一次，把字体缓存随 U 盘一起带走，
  让换到新电脑后的首次画图也最快：
      runtimes\python37\python.exe teaching_shell.py --warmup
  这条命令会建好缓存后自动退出，不会启动网页。

机房部署提示（杀毒 / SmartScreen）
----------------------------------
- 部分机房安全软件或 Windows SmartScreen 会拦截「从 U 盘运行的 .bat 调起 python.exe」。
  若被拦截：右键 .bat →「以管理员身份运行」，或在安全软件里把 PythonPortable 文件夹加入信任 / 白名单。
- 本程序只在本机 127.0.0.1 上提供网页服务，不联网、不对外开放端口。
