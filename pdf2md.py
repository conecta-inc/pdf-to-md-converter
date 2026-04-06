import os
import sys
import re
import threading
import tkinter as tk
from tkinter import filedialog, ttk
from pathlib import Path
from io import BytesIO
import base64

import fitz


def resource_path(relative_path: str) -> str:
    if getattr(sys, "_MEIPASS", None):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath(os.path.dirname(__file__)), relative_path)


def _detect_heading_level(font_size: float, base_size: float) -> int | None:
    if base_size <= 0:
        return None
    ratio = font_size / base_size
    if ratio >= 2.0:
        return 1
    if ratio >= 1.6:
        return 2
    if ratio >= 1.3:
        return 3
    if ratio >= 1.15:
        return 4
    return None


def _is_bold(flags: int) -> bool:
    return bool(flags & 2**4)


def _is_italic(flags: int) -> bool:
    return bool(flags & 2**1)


def _format_span_text(text: str, flags: int) -> str:
    text = text.strip()
    if not text:
        return ""
    bold = _is_bold(flags)
    italic = _is_italic(flags)
    if bold and italic:
        return f"***{text}***"
    if bold:
        return f"**{text}**"
    if italic:
        return f"*{text}*"
    return text


def _extract_tables_from_page(page: fitz.Page) -> list[dict]:
    tables_data = []
    try:
        tabs = page.find_tables()
        for table in tabs:
            table_rect = fitz.Rect(table.bbox)
            rows = table.extract()
            if rows:
                tables_data.append({"rect": table_rect, "rows": rows})
    except Exception:
        pass
    return tables_data


def _table_to_markdown(rows: list[list]) -> str:
    if not rows:
        return ""
    cleaned = []
    for row in rows:
        cleaned.append([cell.strip() if cell else "" for cell in row])

    col_count = max(len(r) for r in cleaned)
    for r in cleaned:
        while len(r) < col_count:
            r.append("")

    lines = []
    header = "| " + " | ".join(cleaned[0]) + " |"
    separator = "| " + " | ".join(["---"] * col_count) + " |"
    lines.append(header)
    lines.append(separator)
    for row in cleaned[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _point_in_any_rect(x: float, y: float, rects: list[fitz.Rect]) -> bool:
    for r in rects:
        if r.x0 - 2 <= x <= r.x1 + 2 and r.y0 - 2 <= y <= r.y1 + 2:
            return True
    return False


def _detect_list_prefix(text: str) -> tuple[str, str]:
    m = re.match(r'^[\u2022\u2023\u25E6\u2043\u2219\u25CF\u25CB\u25AA\u25AB•·\-–—]\s*', text)
    if m:
        return "- ", text[m.end():]
    m = re.match(r'^(\d{1,3})[.)]\s*', text)
    if m:
        return f"{m.group(1)}. ", text[m.end():]
    m = re.match(r'^([a-zA-Z])[.)]\s*', text)
    if m:
        return f"{m.group(1)}. ", text[m.end():]
    return "", text


def convert_pdf_to_md(pdf_path: str, output_path: str, extract_images: bool = True) -> None:
    doc = fitz.open(pdf_path)
    md_lines: list[str] = []
    output_dir = os.path.dirname(output_path)
    stem = Path(output_path).stem
    images_dir = os.path.join(output_dir, f"{stem}_images")
    image_counter = 0

    font_sizes: dict[float, int] = {}
    for page in doc:
        blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
        for block in blocks:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    sz = round(span["size"], 1)
                    font_sizes[sz] = font_sizes.get(sz, 0) + len(span["text"].strip())

    base_size = max(font_sizes, key=font_sizes.get) if font_sizes else 12.0

    for page_num, page in enumerate(doc):
        if page_num > 0:
            md_lines.append("\n---\n")

        tables = _extract_tables_from_page(page)
        table_rects = [t["rect"] for t in tables]
        tables_inserted: set[int] = set()

        if extract_images:
            for img_index, img in enumerate(page.get_images(full=True)):
                try:
                    xref = img[0]
                    pix = fitz.Pixmap(doc, xref)
                    if pix.n > 4:
                        pix = fitz.Pixmap(fitz.csRGB, pix)
                    if not os.path.exists(images_dir):
                        os.makedirs(images_dir, exist_ok=True)
                    image_counter += 1
                    img_filename = f"img_{page_num + 1}_{image_counter}.png"
                    img_path = os.path.join(images_dir, img_filename)
                    pix.save(img_path)
                    rel_path = f"{stem}_images/{img_filename}"
                    md_lines.append(f"\n![image]({rel_path})\n")
                except Exception:
                    pass

        link_map: dict[tuple, str] = {}
        for link in page.get_links():
            if link.get("uri"):
                rect = fitz.Rect(link["from"])
                link_map[(round(rect.x0), round(rect.y0), round(rect.x1), round(rect.y1))] = link["uri"]

        blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
        prev_block_was_heading = False

        for block in blocks:
            if block["type"] != 0:
                continue

            block_rect = fitz.Rect(block["bbox"])

            bx = (block_rect.x0 + block_rect.x1) / 2
            by = (block_rect.y0 + block_rect.y1) / 2
            in_table_idx = None
            for ti, tr in enumerate(table_rects):
                if tr.x0 - 2 <= bx <= tr.x1 + 2 and tr.y0 - 2 <= by <= tr.y1 + 2:
                    in_table_idx = ti
                    break

            if in_table_idx is not None:
                if in_table_idx not in tables_inserted:
                    tables_inserted.add(in_table_idx)
                    md_lines.append("\n" + _table_to_markdown(tables[in_table_idx]["rows"]) + "\n")
                continue

            block_text_parts: list[str] = []
            block_heading_level: int | None = None

            for line in block["lines"]:
                line_text = ""
                line_heading = None

                for span in line["spans"]:
                    text = span["text"]
                    if not text.strip():
                        if text and line_text:
                            line_text += " "
                        continue

                    font_size = span["size"]
                    flags = span["flags"]

                    hl = _detect_heading_level(font_size, base_size)
                    if hl is not None and len(text.strip()) < 200:
                        line_heading = hl

                    span_rect = fitz.Rect(span["bbox"])
                    sr_key = (round(span_rect.x0), round(span_rect.y0),
                              round(span_rect.x1), round(span_rect.y1))
                    link_url = None
                    for lk, lv in link_map.items():
                        if (abs(lk[0] - sr_key[0]) < 5 and abs(lk[1] - sr_key[1]) < 5):
                            link_url = lv
                            break

                    formatted = _format_span_text(text, flags)
                    if link_url and formatted:
                        formatted = f"[{formatted}]({link_url})"

                    if formatted:
                        line_text += formatted + " "

                line_text = line_text.strip()
                if not line_text:
                    continue

                if line_heading is not None:
                    block_heading_level = line_heading

                block_text_parts.append(line_text)

            full_text = " ".join(block_text_parts).strip()
            if not full_text:
                continue

            list_prefix, remaining = _detect_list_prefix(full_text)

            if block_heading_level is not None:
                prefix = "#" * block_heading_level + " "
                md_lines.append(f"\n{prefix}{full_text}\n")
                prev_block_was_heading = True
            elif list_prefix:
                md_lines.append(f"{list_prefix}{remaining}")
                prev_block_was_heading = False
            else:
                if not prev_block_was_heading:
                    md_lines.append("")
                md_lines.append(full_text)
                prev_block_was_heading = False

        for ti, table in enumerate(tables):
            if ti not in tables_inserted:
                md_lines.append("\n" + _table_to_markdown(table["rows"]) + "\n")

    doc.close()

    result = "\n".join(md_lines)
    result = re.sub(r'\n{4,}', '\n\n\n', result)
    result = result.strip() + "\n"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(result)


COLOR_BLUE = "#0F3BFE"
COLOR_GREEN = "#C0F58B"
COLOR_GRAY = "#646B6B"
COLOR_BG_DARK = "#1E1E2E"
COLOR_BG_CARD = "#2A2A3C"
COLOR_TEXT = "#FFFFFF"
COLOR_TEXT_SECONDARY = "#B0B0B0"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Conecta .md Converter")
        self.geometry("720x620")
        self.minsize(620, 520)
        self.configure(bg=COLOR_BG_DARK)
        self.resizable(True, True)

        try:
            logo_path = resource_path("logo a ser utilizado.png")
            logo_img = tk.PhotoImage(file=logo_path)
            self.iconphoto(True, logo_img)
            self._logo_img = logo_img
        except Exception:
            self._logo_img = None

        self.pdf_files: list[str] = []
        self.output_dir: str = ""

        self._setup_styles()
        self._build_ui()

    def _setup_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure("Card.TFrame", background=COLOR_BG_CARD)
        style.configure("Dark.TFrame", background=COLOR_BG_DARK)

        style.configure("Title.TLabel",
                        background=COLOR_BG_DARK,
                        foreground=COLOR_GREEN,
                        font=("Segoe UI", 18, "bold"))

        style.configure("Subtitle.TLabel",
                        background=COLOR_BG_DARK,
                        foreground=COLOR_TEXT_SECONDARY,
                        font=("Segoe UI", 10))

        style.configure("Section.TLabel",
                        background=COLOR_BG_CARD,
                        foreground=COLOR_TEXT,
                        font=("Segoe UI", 11, "bold"))

        style.configure("Info.TLabel",
                        background=COLOR_BG_CARD,
                        foreground=COLOR_TEXT_SECONDARY,
                        font=("Segoe UI", 9))

        style.configure("Green.TButton",
                        background=COLOR_GREEN,
                        foreground="#1a1a1a",
                        font=("Segoe UI", 10, "bold"),
                        borderwidth=0,
                        focuscolor=COLOR_GREEN,
                        padding=(16, 8))
        style.map("Green.TButton",
                  background=[("active", "#A8E070"), ("disabled", COLOR_GRAY)])

        style.configure("Blue.TButton",
                        background=COLOR_BLUE,
                        foreground=COLOR_TEXT,
                        font=("Segoe UI", 10),
                        borderwidth=0,
                        focuscolor=COLOR_BLUE,
                        padding=(12, 6))
        style.map("Blue.TButton",
                  background=[("active", "#0D2FCC"), ("disabled", COLOR_GRAY)])

        style.configure("Gray.TButton",
                        background=COLOR_GRAY,
                        foreground=COLOR_TEXT,
                        font=("Segoe UI", 9),
                        borderwidth=0,
                        padding=(10, 5))
        style.map("Gray.TButton",
                  background=[("active", "#7a8282")])

        style.configure("green.Horizontal.TProgressbar",
                        troughcolor=COLOR_BG_CARD,
                        background=COLOR_GREEN,
                        borderwidth=0,
                        thickness=8)

    def _build_ui(self):
        main = ttk.Frame(self, style="Dark.TFrame")
        main.pack(fill="both", expand=True, padx=24, pady=16)

        header = ttk.Frame(main, style="Dark.TFrame")
        header.pack(fill="x", pady=(0, 12))

        if self._logo_img:
            logo_label = ttk.Label(header, image=self._logo_img, background=COLOR_BG_DARK)
            logo_label.pack(side="left", padx=(0, 12))

        title_frame = ttk.Frame(header, style="Dark.TFrame")
        title_frame.pack(side="left", fill="y")
        ttk.Label(title_frame, text="Converta seus arquivos .PDF para .MD",
                  style="Title.TLabel").pack(anchor="w")

        file_card = ttk.Frame(main, style="Card.TFrame")
        file_card.pack(fill="both", expand=True, pady=(0, 10))
        file_card.pack_propagate(False)

        file_header = ttk.Frame(file_card, style="Card.TFrame")
        file_header.pack(fill="x", padx=16, pady=(12, 4))

        ttk.Label(file_header, text="Arquivos PDF", style="Section.TLabel").pack(side="left")
        self.file_count_label = ttk.Label(file_header, text="Nenhum arquivo selecionado",
                                          style="Info.TLabel")
        self.file_count_label.pack(side="right")

        list_frame = ttk.Frame(file_card, style="Card.TFrame")
        list_frame.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        self.file_listbox = tk.Listbox(
            list_frame,
            bg="#353548",
            fg=COLOR_TEXT,
            selectbackground=COLOR_BLUE,
            selectforeground=COLOR_TEXT,
            font=("Consolas", 9),
            borderwidth=0,
            highlightthickness=1,
            highlightcolor=COLOR_BLUE,
            highlightbackground="#444460",
            activestyle="none"
        )
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.file_listbox.yview)
        self.file_listbox.configure(yscrollcommand=scrollbar.set)
        self.file_listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        btn_frame = ttk.Frame(file_card, style="Card.TFrame")
        btn_frame.pack(fill="x", padx=16, pady=(0, 12))
        ttk.Button(btn_frame, text="Selecionar PDFs", style="Blue.TButton",
                   command=self._select_files).pack(side="left", padx=(0, 8))
        ttk.Button(btn_frame, text="Limpar", style="Gray.TButton",
                   command=self._clear_files).pack(side="left")

        dest_card = ttk.Frame(main, style="Card.TFrame")
        dest_card.pack(fill="x", pady=(0, 10))

        dest_inner = ttk.Frame(dest_card, style="Card.TFrame")
        dest_inner.pack(fill="x", padx=16, pady=12)

        ttk.Label(dest_inner, text="Pasta de destino", style="Section.TLabel").pack(anchor="w")

        dest_row = ttk.Frame(dest_inner, style="Card.TFrame")
        dest_row.pack(fill="x", pady=(6, 0))

        self.dest_var = tk.StringVar(value="(mesma pasta dos PDFs)")
        self.dest_entry = tk.Entry(
            dest_row,
            textvariable=self.dest_var,
            bg="#353548",
            fg=COLOR_TEXT_SECONDARY,
            insertbackground=COLOR_TEXT,
            font=("Segoe UI", 9),
            borderwidth=0,
            highlightthickness=1,
            highlightcolor=COLOR_BLUE,
            highlightbackground="#444460",
            state="readonly"
        )
        self.dest_entry.pack(side="left", fill="x", expand=True, ipady=4)
        ttk.Button(dest_row, text="Alterar", style="Gray.TButton",
                   command=self._select_dest).pack(side="right", padx=(8, 0))

        bottom = ttk.Frame(main, style="Dark.TFrame")
        bottom.pack(fill="x", pady=(4, 0))

        self.progress = ttk.Progressbar(bottom, style="green.Horizontal.TProgressbar",
                                        mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=(0, 8))

        self.status_var = tk.StringVar(value="Pronto")
        self.status_label = ttk.Label(bottom, textvariable=self.status_var,
                                      background=COLOR_BG_DARK,
                                      foreground=COLOR_TEXT_SECONDARY,
                                      font=("Segoe UI", 9))
        self.status_label.pack(side="left")

        self.convert_btn = ttk.Button(bottom, text="Converter", style="Green.TButton",
                                      command=self._start_conversion)
        self.convert_btn.pack(side="right")

    def _select_files(self):
        files = filedialog.askopenfilenames(
            title="Selecionar arquivos PDF",
            filetypes=[("PDF", "*.pdf")],
            parent=self
        )
        if files:
            self.pdf_files = list(files)
            self.file_listbox.delete(0, tk.END)
            for f in self.pdf_files:
                self.file_listbox.insert(tk.END, f"  {os.path.basename(f)}")
            self.file_count_label.config(
                text=f"{len(self.pdf_files)} arquivo(s) selecionado(s)")
            if not self.output_dir:
                self.output_dir = os.path.dirname(self.pdf_files[0])
                self.dest_var.set(self.output_dir)

    def _clear_files(self):
        self.pdf_files.clear()
        self.file_listbox.delete(0, tk.END)
        self.file_count_label.config(text="Nenhum arquivo selecionado")
        self.output_dir = ""
        self.dest_var.set("(mesma pasta dos PDFs)")
        self.progress["value"] = 0
        self.status_var.set("Pronto")

    def _select_dest(self):
        initial = self.output_dir if self.output_dir else None
        folder = filedialog.askdirectory(
            title="Selecionar pasta de destino",
            initialdir=initial,
            parent=self
        )
        if folder:
            self.output_dir = folder
            self.dest_var.set(folder)

    def _start_conversion(self):
        if not self.pdf_files:
            self.status_var.set("Selecione pelo menos um arquivo PDF.")
            return

        self.convert_btn.configure(state="disabled")
        self.progress["value"] = 0
        threading.Thread(target=self._convert_all, daemon=True).start()

    def _convert_all(self):
        total = len(self.pdf_files)
        errors: list[str] = []

        for i, pdf_path in enumerate(self.pdf_files):
            name = os.path.basename(pdf_path)
            self._set_status(f"Convertendo {name}... ({i + 1}/{total})")

            out_dir = self.output_dir if self.output_dir else os.path.dirname(pdf_path)
            md_name = Path(pdf_path).stem + ".md"
            md_path = os.path.join(out_dir, md_name)

            try:
                convert_pdf_to_md(pdf_path, md_path)
            except Exception as e:
                errors.append(f"{name}: {e}")

            self._set_progress((i + 1) / total * 100)

        if errors:
            self._set_status(f"Concluído com {len(errors)} erro(s): {'; '.join(errors)}")
        else:
            self._set_status(f"Concluído! {total} arquivo(s) convertido(s) com sucesso.")

        self.after(0, lambda: self.convert_btn.configure(state="normal"))

        final_dir = self.output_dir if self.output_dir else os.path.dirname(self.pdf_files[0])
        self.after(0, lambda: self._show_done_popup(final_dir))

    def _show_done_popup(self, output_dir: str):
        popup = tk.Toplevel(self)
        popup.title("Conecta .md Converter")
        popup.configure(bg=COLOR_BG_DARK)
        popup.resizable(False, False)
        popup.grab_set()

        popup.update_idletasks()
        pw, ph = 420, 180
        x = self.winfo_x() + (self.winfo_width() - pw) // 2
        y = self.winfo_y() + (self.winfo_height() - ph) // 2
        popup.geometry(f"{pw}x{ph}+{x}+{y}")

        tk.Label(
            popup, text="Trabalho concluído!",
            bg=COLOR_BG_DARK, fg=COLOR_GREEN,
            font=("Segoe UI", 16, "bold")
        ).pack(pady=(28, 24))

        btn_frame = tk.Frame(popup, bg=COLOR_BG_DARK)
        btn_frame.pack()

        def close_and_open():
            popup.destroy()
            os.startfile(output_dir)
            self.destroy()

        def continue_using():
            popup.destroy()

        style = ttk.Style(popup)
        style.configure("PopupGreen.TButton",
                        background=COLOR_GREEN, foreground="#1a1a1a",
                        font=("Segoe UI", 9, "bold"), borderwidth=0,
                        focuscolor=COLOR_GREEN, padding=(14, 8))
        style.map("PopupGreen.TButton",
                  background=[("active", "#A8E070")])
        style.configure("PopupBlue.TButton",
                        background=COLOR_BLUE, foreground=COLOR_TEXT,
                        font=("Segoe UI", 9, "bold"), borderwidth=0,
                        focuscolor=COLOR_BLUE, padding=(14, 8))
        style.map("PopupBlue.TButton",
                  background=[("active", "#0D2FCC")])

        ttk.Button(btn_frame, text="Voltar para o conversor",
                   style="PopupBlue.TButton",
                   command=continue_using).pack(side="left", padx=(0, 10))
        ttk.Button(btn_frame, text="Encerrar programa e abrir diretório",
                   style="PopupGreen.TButton",
                   command=close_and_open).pack(side="left")

    def _set_status(self, text: str):
        self.after(0, lambda: self.status_var.set(text))

    def _set_progress(self, value: float):
        self.after(0, lambda: self.progress.configure(value=value))


if __name__ == "__main__":
    app = App()
    app.mainloop()
