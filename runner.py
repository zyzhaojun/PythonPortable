from __future__ import annotations

import ast
import html
import json
import os
import sys
import time
import traceback
from pathlib import Path

import matplotlib

matplotlib.use("Agg")


def configure_standard_streams() -> None:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(
                    encoding="utf-8",
                    errors="replace",
                    line_buffering=True,
                    write_through=True,
                )
            except TypeError:
                stream.reconfigure(encoding="utf-8", errors="replace")


def configure_chinese_fonts() -> None:
    from matplotlib import font_manager
    from matplotlib import rcParams

    font_candidates = [
        ("Microsoft YaHei", r"C:\Windows\Fonts\msyh.ttc"),
        ("Microsoft YaHei", r"C:\Windows\Fonts\msyh.ttf"),
        ("SimHei", r"C:\Windows\Fonts\simhei.ttf"),
        ("SimSun", r"C:\Windows\Fonts\simsun.ttc"),
        ("DengXian", r"C:\Windows\Fonts\Deng.ttf"),
        ("KaiTi", r"C:\Windows\Fonts\simkai.ttf"),
    ]

    available_names: list[str] = []
    for font_name, font_path in font_candidates:
        if os.path.exists(font_path):
            try:
                font_manager.fontManager.addfont(font_path)
                available_names.append(font_name)
            except Exception:
                pass

    rcParams["font.family"] = "sans-serif"
    rcParams["font.sans-serif"] = [*available_names, "DejaVu Sans"]
    rcParams["axes.unicode_minus"] = False


def main(argv: list[str] | None = None) -> int:
    configure_standard_streams()

    args = argv if argv is not None else sys.argv[1:]
    code_path = Path(args[0])
    output_dir = Path(args[1])
    result_path = Path(args[2])
    source = code_path.read_text(encoding="utf-8-sig")
    outputs: list[dict[str, str]] = []
    saved_figures: set[int] = set()
    input_counter = 0
    interactive_state_path = os.environ.get("PYTHONTEACHING_INTERACTIVE_STATE")
    echo_interactive_input = os.environ.get("PYTHONTEACHING_ECHO_INPUT") == "1"
    configure_chinese_fonts()

    def write_interactive_state(waiting: bool, prompt: str = "", request_id: str = "") -> None:
        if not interactive_state_path:
            return

        state_path = Path(interactive_state_path)
        state_path.write_text(
            json.dumps(
                {
                    "waiting": waiting,
                    "prompt": prompt,
                    "request_id": request_id,
                    "updated_at": time.time(),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    write_interactive_state(False)

    def save_figure(fig) -> None:
        number = getattr(fig, "number", len(saved_figures) + 1)
        if number in saved_figures:
            return
        saved_figures.add(number)
        image_name = f"figure_{len(saved_figures)}.png"
        image_path = output_dir / image_name
        fig.savefig(image_path, dpi=150, bbox_inches="tight", facecolor="white")
        outputs.append({"type": "image", "src": f"/run_outputs/{output_dir.name}/{image_name}"})

    def display(value=None) -> None:
        if value is None:
            return

        try:
            import pandas as pd

            if isinstance(value, (pd.DataFrame, pd.Series)):
                outputs.append(
                    {
                        "type": "html",
                        "html": value.to_html(
                            border=0,
                            classes="data-frame",
                            max_rows=40,
                            max_cols=12,
                            notebook=False,
                        ),
                    }
                )
                return
        except Exception:
            pass

        try:
            from matplotlib.figure import Figure
            from matplotlib.artist import Artist

            if isinstance(value, Figure):
                save_figure(value)
                return
            if isinstance(value, Artist):
                return
        except Exception:
            pass

        outputs.append({"type": "text", "text": html.escape(repr(value))})

    def teaching_input(prompt="") -> str:
        nonlocal input_counter

        prompt_text = str(prompt)
        if prompt_text:
            sys.stdout.write(prompt_text)
        sys.stdout.flush()

        input_counter += 1
        request_id = str(input_counter)
        write_interactive_state(True, prompt_text, request_id)
        line = sys.stdin.readline()
        write_interactive_state(False, "", request_id)

        if line == "":
            raise EOFError("EOF when reading a line")
        if echo_interactive_input:
            sys.stdout.write(line)
            sys.stdout.flush()
        return line.rstrip("\n").rstrip("\r")

    namespace = {
        "__name__": "__main__",
        "__file__": str(code_path),
        "display": display,
        "input": teaching_input,
        "raw_input": teaching_input,
    }

    try:
        tree = ast.parse(source, filename=str(code_path))
        if tree.body and isinstance(tree.body[-1], ast.Expr):
            last_expr = ast.Expression(tree.body[-1].value)
            ast.fix_missing_locations(last_expr)
            tree.body = tree.body[:-1]
            exec(compile(tree, str(code_path), "exec"), namespace)
            value = eval(compile(last_expr, str(code_path), "eval"), namespace)
            display(value)
        else:
            exec(compile(tree, str(code_path), "exec"), namespace)

        try:
            import matplotlib.pyplot as plt

            for number in plt.get_fignums():
                save_figure(plt.figure(number))
        except Exception:
            pass

        result_path.write_text(json.dumps({"outputs": outputs}, ensure_ascii=False), encoding="utf-8")
        return 0
    except Exception:
        result_path.write_text(json.dumps({"outputs": outputs}, ensure_ascii=False), encoding="utf-8")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
