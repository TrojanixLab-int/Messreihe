import tkinter as tk
from tkinter import messagebox, filedialog, Toplevel, ttk
import sounddevice as sd
import numpy as np
from datetime import datetime
import math
import time
import os
import subprocess

BG = "#000"
FG_W, FG_Y, FG_R, FG_O, FG_B, FG_G = "#fff", "#ff0", "#f00", "#f60", "#36f", "#0f0"
FG_DR, FG_GR = "#800000", "#777"
GRAY_FOC = "#3f3f3f"
FG_DG = "#006400"

class MessreiheApp:
    def __init__(self, root):
        self.root = root
        self.root.title("СерияМес - Программа для измерения радиации - М. Троян")
        try:
            if os.path.exists("Messreihe.ico"):
                self.root.iconbitmap("Messreihe.ico")
        except: pass
        self.root.state('zoomed')
        self.root.configure(bg=BG)
        self.thresh_idx = 10
        self.cpm_pro_sv = 1000
        self.filter_mm = 0.50
        self.alpha_eff = 40
        self.debounce_ms = 50
        self.last_hit_time = 0
        self.keys = ["odl", "alpha", "beta", "gamma"]
        self.data = {k: {"s": 0, "z": 0, "run": False, "p": False, "cpm": 0} for k in self.keys}
        self.manual_mode = False
        self.manual_entries = {}
        self.rows = {}
        self.odl_start_time = "--:--:--"
        self.gamma_stop_time = "--:--:--"
        self.hold_job = None
        self.hold_start_time = 0
        self.setup_ui()
        self.start_audio()
        self.update_loop()

    def format_val(self, val):
        return f"{val:.3f} мк".replace(".", ",")

    def setup_ui(self):
        self.footer = tk.Frame(self.root, bg="#0a0a0a", bd=1, relief="raised")
        self.footer.pack(side="bottom", fill="x", ipady=5)
        self.btn_manual = tk.Button(self.footer, text="Ручной режим", bg="#222", fg=FG_W, font=("Arial", 9), padx=10, command=self.toggle_manual_mode)
        self.btn_manual.pack(side="left", padx=5, pady=5)
        tk.Button(self.footer, text="Новый журнал", bg="#222", fg=FG_W, font=("Arial", 9), padx=10, command=self.neues_protokoll).pack(side="left", padx=5, pady=5)
        tk.Button(self.footer, text="Печать журнала", bg="#222", fg=FG_W, font=("Arial", 9), padx=10, command=self.show_print_window).pack(side="left", padx=5, pady=5)
        tk.Button(self.footer, text="Библиотека изотопов", bg="#222", fg=FG_W, font=("Arial", 9), padx=10, command=self.open_isotopes_table).pack(side="left", padx=5, pady=5)
        tk.Button(self.footer, text="Данные нуклидов", bg="#222", fg=FG_W, font=("Arial", 9), padx=10, command=self.run_nuklid_exe).pack(side="left", padx=5, pady=5)
        tk.Button(self.footer, text="Руководство пользователя", bg="#222", fg=FG_W, font=("Arial", 9), padx=10, command=self.show_anleitung).pack(side="left", padx=5, pady=5)
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=20, pady=10)
        try:
            if os.path.exists("Messreihe.png"):
                self.logo_full = tk.PhotoImage(file="Messreihe.png")
                self.logo_img = self.logo_full.subsample(2, 2)
                tk.Label(header, image=self.logo_img, bg=BG).pack(side="left", padx=(0, 20))
        except: pass
        tk.Label(header, text="СерияМес", fg=FG_W, bg=BG, font=("Arial", 60, "bold")).pack(side="left")
        self.clock_lbl = tk.Label(header, text="", fg=FG_B, bg=BG, font=("Arial", 30))
        self.clock_lbl.pack(side="left", padx=30)
        tot_f = tk.Frame(header, bg=BG)
        tot_f.pack(side="right")
        tk.Label(tot_f, text="Итого (αβγ)", fg=FG_W, bg=BG).pack()
        self.lbl_total_val = tk.Label(tot_f, text="0,000 мк", fg=FG_R, bg=BG, font=("Arial", 45, "bold"))
        self.lbl_total_val.pack()
        tk.Label(tot_f, text="Зв/ч", fg=FG_R, bg=BG, font=("Arial", 10, "bold")).pack()
        main = tk.Frame(self.root, bg=BG)
        main.pack(fill="both", expand=True, padx=20)
        left = tk.Frame(main, bg=BG); left.pack(side="left", fill="both", expand=True)
        right = tk.Frame(main, bg=BG, width=300); right.pack(side="right", fill="y", padx=10)
        self.v_lbls = {}
        self.action_btns = {}
        confs = [
            ("odl", "МАЭД - Мощность амбиентного эквивалента дозы", "Σ", ["Время (с)", "импульсы", "отсч/мин", "%", "Зв/ч (МАЭД)"]),
            ("alpha", "Альфа-нуклиды", "α", ["Время (с)", "импульсы", "отсч/мин", "%", "Гр/ч (α+β+γ)", "Гр/ч (α)"]),
            ("beta", "Бета-частицы", "β", ["Время (с)", "импульсы", "отсч/мин", "%", "Гр/ч (β+γ)", "Гр/ч (β)"]),
            ("gamma", "Гамма-излучение", "γ", ["Время (с)", "импульсы", "отсч/мин", "%", "Гр/ч ((β)+γ)", "Гр/ч (γ)"])
        ]
        for k, name, sym, units in confs:
            f = tk.Frame(left, bg=BG, bd=1, relief="flat", highlightbackground="#333", highlightthickness=1)
            f.pack(fill="x", pady=5); self.rows[k] = f
            tk.Label(f, text=sym, fg=FG_Y, bg=BG, font=("Arial", 70, "bold"), width=2).pack(side="left", padx=10)
            bf = tk.Frame(f, bg=BG); bf.pack(side="left", padx=10)
            b_start = tk.Button(bf, text="ПУСК", width=8, command=lambda x=k: self.press_start(x))
            b_start.grid(row=0, column=0, padx=1, pady=1)
            b_pause = tk.Button(bf, text="ПАУЗА", width=8, command=lambda x=k: self.press_pause(x))
            b_pause.grid(row=0, column=1, padx=1, pady=1)
            b_stopp = tk.Button(bf, text="СТОП", width=8, command=lambda x=k: self.press_stopp(x))
            b_stopp.grid(row=1, column=0, padx=1, pady=1)
            b_reset = tk.Button(bf, text="СБРОС", width=8, command=lambda x=k: self.press_reset(x))
            b_reset.grid(row=1, column=1, padx=1, pady=1)
            self.action_btns[k] = (b_start, b_pause, b_stopp, b_reset)
            vf = tk.Frame(f, bg=BG); vf.pack(side="left", fill="x", expand=True, padx=20)
            tk.Label(vf, text=name, fg=FG_W, bg=BG, font=("Arial", 12, "bold")).grid(row=0, column=0, columnspan=6, sticky="w")
            self.v_lbls[k] = []
            self.manual_entries[k] = {}
            for i in range(len(units)):
                c = tk.Frame(vf, bg=BG); c.grid(row=1, column=i, sticky="nsew", padx=15)
                if i == 0 or i == 1:
                    e = tk.Entry(c, width=6, font=("Arial", 10), justify="center")
                    self.manual_entries[k][i] = e 
                
                col = [FG_R, FG_R, FG_R, FG_Y, FG_DR, FG_O][i]
                l = tk.Label(c, text="0" if i<4 else "0,000 мк", fg=col, bg=BG, font=("Arial", 30, "bold"))
                l.pack(side="bottom")
                tk.Label(c, text=units[i], fg=FG_GR, bg=BG, font=("Arial", 9)).pack(side="bottom")
                self.v_lbls[k].append(l)
        self.setup_sidebar(right)

    def setup_sidebar(self, parent):
        configs = [("cpm", "Δ зонда 1 мкЗв/ч ≙", FG_B, 1), ("eff", "Δ α-эффективность зонда", FG_O, 1), ("fil", "Δ αβ-фильтр (Алюминий)", FG_B, 0.05), ("sig", "аудиовходной сигнал", FG_G, 1), ("deb", "настройка времени блокировки", FG_DG, 5)]
        for t, txt, col, d in configs:
            fr = tk.LabelFrame(parent, text=txt, fg=col, bg=BG, bd=1, relief="solid")
            fr.pack(fill="x", pady=5, ipady=5)
            if t == "cpm":
                self.res_sonde = tk.Label(fr, text=str(self.cpm_pro_sv), fg=col, bg=BG, font=("Arial", 25, "bold")); self.res_sonde.pack()
                tk.Label(fr, text="отсч/мин", fg=col, bg=BG).pack()
            elif t == "eff":
                self.res_eff = tk.Label(fr, text=f"{self.alpha_eff} %", fg=col, bg=BG, font=("Arial", 25, "bold")); self.res_eff.pack()
            elif t == "fil":
                self.res_fil = tk.Label(fr, text=f"{self.filter_mm:.2f} мм".replace(".", ","), fg=col, bg=BG, font=("Arial", 25, "bold")); self.res_fil.pack()
            elif t == "sig":
                self.canv = tk.Canvas(fr, width=120, height=35, bg=BG, highlightthickness=0); self.canv.pack()
                self.l_grn = self.canv.create_oval(35, 5, 55, 25, fill="#030"); self.l_red = self.canv.create_oval(65, 5, 85, 25, fill="#300")
                pf = tk.Frame(fr, bg=BG); pf.pack(); tk.Label(pf, text="Уровень:", fg=col, bg=BG).pack(side="left")
                self.lbl_p_val = tk.Label(pf, text=f"{self.thresh_idx*5}%", fg=FG_W, bg="#222"); self.lbl_p_val.pack(side="left", padx=5)
            elif t == "deb":
                self.res_deb = tk.Label(fr, text=f"{self.debounce_ms} мс", fg=col, bg=BG, font=("Arial", 25, "bold")); self.res_deb.pack()
            sb = tk.Frame(fr, bg=BG); sb.pack()
            bm = tk.Button(sb, text="-", width=10); bm.pack(side="left", padx=2)
            bp = tk.Button(sb, text="+", width=10); bp.pack(side="left", padx=2)
            if t not in ["sig", "deb"]:
                bm.bind("<ButtonPress-1>", lambda e, x=t, y=-d: self.start_hold(x, y))
                bm.bind("<ButtonRelease-1>", lambda e: self.stop_hold())
                bp.bind("<ButtonPress-1>", lambda e, x=t, y=d: self.start_hold(x, y))
                bp.bind("<ButtonRelease-1>", lambda e: self.stop_hold())
            elif t == "deb":
                bm.config(command=lambda: self.adj("deb", -5))
                bp.config(command=lambda: self.adj("deb", 5))
            else:
                bm.config(command=lambda: self.adj("sig", -1)); bp.config(command=lambda: self.adj("sig", 1))

    def toggle_manual_mode(self):
        self.manual_mode = not self.manual_mode
        self.btn_manual.config(text="Режим измер." if self.manual_mode else "Ручной режим")
        if not self.manual_mode: self.neues_protokoll()
        for k in self.keys:
            btns = self.action_btns[k]
            btns[0].config(text="УСТАНОВИТЬ" if self.manual_mode else "ПУСК")
            for b in [btns[1], btns[2]]: b.config(state="disabled" if self.manual_mode else "normal")
            for i in [0, 1]:
                if self.manual_mode: self.manual_entries[k][i].pack(side="top", pady=2)
                else: self.manual_entries[k][i].pack_forget()

    def press_start(self, k):
        if self.manual_mode:
            try:
                s = int(self.manual_entries[k][0].get() or 0)
                z = int(self.manual_entries[k][1].get() or 0)
                cpm = z / (s / 60) if s > 0 else 0
                self.data[k].update({"s": s, "z": z, "cpm": cpm})
                self.v_lbls[k][0].config(text=str(s)); self.v_lbls[k][1].config(text=str(z))
                self.v_lbls[k][2].config(text=str(int(cpm))); self.v_lbls[k][4].config(text=self.format_val(cpm / self.cpm_pro_sv))
                if k == "odl": self.odl_start_time = "Вручную"
                if k == "gamma": self.gamma_stop_time = "Вручную"; self.calculate_results()
            except: messagebox.showerror("Ошибка", "Пожалуйста, вводите только числа.")
        else:
            self.data[k]["run"], self.data[k]["p"] = True, False
            self.rows[k].config(bg=GRAY_FOC)
            if k == "odl": self.odl_start_time = datetime.now().strftime("%H:%M:%S")

    def press_reset(self, k):
        self.data[k].update({"s": 0, "z": 0, "run": False, "p": False})
        if self.manual_mode:
            for i in [0, 1]: self.manual_entries[k][i].delete(0, tk.END)
        self.rows[k].config(bg=BG)
        for i in range(4): self.v_lbls[k][i].config(text="0")
        self.v_lbls[k][4].config(text="0,000 мк")
        if len(self.v_lbls[k]) > 5: self.v_lbls[k][5].config(text="0,000 мк")

    def start_hold(self, t, d):
        self.hold_start_time = time.time(); self.adj_continuous(t, d)

    def stop_hold(self):
        if self.hold_job: self.root.after_cancel(self.hold_job); self.hold_job = None

    def adj_continuous(self, t, d):
        delta = d
        if t == "cpm" and (time.time() - self.hold_start_time) > 3.0: delta = 10 if d > 0 else -10
        elif t == "fil": delta = 0.05 if d > 0 else -0.05
        self.adj(t, delta)
        self.hold_job = self.root.after(100, lambda: self.adj_continuous(t, d))

    def adj(self, t, d):
        if t=="cpm": self.cpm_pro_sv = max(1, self.cpm_pro_sv + d); self.res_sonde.config(text=str(self.cpm_pro_sv))
        if t=="eff": self.alpha_eff = max(1, min(100, self.alpha_eff + d)); self.res_eff.config(text=f"{self.alpha_eff} %")
        if t=="sig": self.thresh_idx = max(1, min(20, self.thresh_idx + d)); self.lbl_p_val.config(text=f"{self.thresh_idx*5}%")
        if t=="fil": self.filter_mm = max(0.01, self.filter_mm + d); self.res_fil.config(text=f"{self.filter_mm:.2f} мм")
        if t=="deb": self.debounce_ms = max(0, self.debounce_ms + d); self.res_deb.config(text=f"{self.debounce_ms} мс")

    def start_audio(self):
        def cb(i, f, t, s):
            if np.max(np.abs(i)) >= (self.thresh_idx * 0.05):
                now = time.time() * 1000
                if now - self.last_hit_time >= self.debounce_ms:
                    self.last_hit_time = now
                    self.root.after(0, self.hit)
        try:
            self.stream = sd.InputStream(callback=cb, channels=1); self.stream.start()
            self.canv.itemconfig(self.l_grn, fill=FG_G)
        except: pass

    def hit(self):
        self.canv.itemconfig(self.l_grn, fill="#030"); self.canv.itemconfig(self.l_red, fill=FG_R); self.root.after(50, self.reset_leds)
        for k in self.keys:
            if self.data[k]["run"] and not self.data[k]["p"]: self.data[k]["z"] += 1

    def reset_leds(self): self.canv.itemconfig(self.l_red, fill="#300"); self.canv.itemconfig(self.l_grn, fill=FG_G)

    def press_stopp(self, k):
        self.data[k]["run"] = False; self.rows[k].config(bg=BG)
        if k == "gamma": self.gamma_stop_time = datetime.now().strftime("%H:%M:%S")

    def press_pause(self, k):
        if not self.data[k]["run"]: return
        self.data[k]["p"] = not self.data[k]["p"]
        if self.data[k]["p"]: self.blink_row(k)
        else: self.rows[k].config(bg=GRAY_FOC)

    def blink_row(self, k):
        if self.data[k]["run"] and self.data[k]["p"]:
            c = self.rows[k].cget("bg"); self.rows[k].config(bg=BG if c == GRAY_FOC else GRAY_FOC)
            self.root.after(500, lambda: self.blink_row(k))

    def neues_protokoll(self):
        if messagebox.askyesno("Серия измерений", "Удалить все результаты и начать новое измерение?"):
            for k in self.keys: self.press_reset(k)
            self.lbl_total_val.config(text="0,000 мк"); self.odl_start_time = "--:--:--"; self.gamma_stop_time = "--:--:--"

    def open_isotopes_table(self):
        win = tk.Toplevel(self.root); win.geometry("950x600"); win.title("Справочные значения радиоактивных изотопов"); win.configure(bg=BG)
        tk.Label(win, text="Изотопные отпечатки (Топ-50, отсортировано по частоте)", fg=FG_Y, bg=BG, font=("Arial", 20, "bold")).pack(pady=10)
        frame = tk.Frame(win, bg=BG); frame.pack(fill="both", expand=True, padx=20, pady=10)
        scrollbar = tk.Scrollbar(frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")
        style = ttk.Style(); style.theme_use("clam")
        style.configure("Treeview", background="#1a1a1a", foreground="white", fieldbackground="#1a1a1a", rowheight=25)
        style.configure("Treeview.Heading", background="#333", foreground="white", font=("Arial", 10, "bold"))
        tree = ttk.Treeview(frame, columns=("name", "dom", "alpha", "beta", "gamma"), show="headings")
        headings = [("name", "Продукт / Материал", 300), ("dom", "Доминанта", 150), ("alpha", "α %", 70), ("beta", "β %", 70), ("gamma", "γ %", 70)]
        for col, txt, w in headings:
            tree.heading(col, text=txt); tree.column(col, width=w, anchor="center" if col != "name" else "w")
        scrollbar.config(command=tree.yview)
        data = [
    ("Гранит (стройматериал)", "Гамма/Бета", "5", "45", "50"),
    ("Калийное удобрение (поташ)", "Бета", "0", "90", "10"),
    ("Урановое стекло (антиквариат)", "Бета/Гамма", "2", "83", "15"),
    ("Настуран (минерал)", "Смесь (ряд U)", "45", "40", "15"),
    ("Бананы (сушеные)", "Бета (K-40)", "0", "90", "10"),
    ("Газокалильные сетки (ториевые)", "Смесь (ряд Th)", "30", "50", "20"),
    ("Радиевый циферблат (часы)", "Смесь (ряд Ra)", "25", "55", "20"),
    ("Америций (дымовой датчик)", "Альфа", "95", "1", "4"),
    ("Плитка (урановая глазурь)", "Бета", "10", "75", "15"),
    ("Тритиевая подсветка", "Бета (мягкое)", "0", "100", "0"),
    ("Сварочные электроды (красные)", "Альфа/Бета", "40", "50", "10"),
    ("Замена линз (Th-стекло)", "Бета/Гамма", "5", "60", "35"),
    ("Белые грибы (сушеные)", "Бета (Cs-137)", "0", "90", "10"),
    ("Базальт (горная порода)", "Гамма/Бета", "2", "48", "50"),
    ("Монацитовый песок", "Альфа/Бета", "45", "40", "15"),
    ("Цирконовый песок", "Альфа/Бета", "30", "50", "20"),
    ("Газовые сетки (современные)", "Бета доминанта", "5", "85", "10"),
    ("Раухтопаз (дымчатый кварц)", "Гамма", "0", "10", "90"),
    ("Античная керамика (красная)", "Бета", "10", "70", "20"),
    ("Отунит (минерал)", "Альфа/Бета", "50", "40", "10"),
    ("Эвклаз (минерал)", "Гамма", "0", "20", "80"),
    ("Торбернит (минерал)", "Альфа/Бета", "45", "45", "10"),
    ("Разрыхлитель (поташ)", "Бета", "0", "90", "10"),
    ("Техническая соль (KCl)", "Бета", "0", "92", "8"),
    ("Силикатный кирпич", "Гамма", "2", "28", "70"),
    ("Медицинский I-131", "Гамма", "0", "10", "90"),
    ("Технеций-99м (медицина)", "Гамма", "0", "1", "99"),
    ("Торианит (минерал)", "Альфа доминанта", "60", "30", "10"),
    ("Берилл (минерал)", "Гамма", "0", "15", "85"),
    ("Сланец (Эйфель/Хунсрюк)", "Бета/Гамма", "5", "55", "40"),
    ("Глинистый сланец", "Гамма доминанта", "3", "37", "60"),
    ("Кирпич (красный)", "Бета/Гамма", "4", "46", "50"),
    ("Бразильский орех (пепел)", "Альфа/Бета", "30", "60", "10"),
    ("Табачный пепел", "Альфа (Po-210)", "40", "50", "10"),
    ("Бетон (старое здание)", "Гамма", "5", "45", "50"),
    ("Гипс (промышленный)", "Бета/Гамма", "2", "58", "40"),
    ("Нитрат уранила (лаб.)", "Альфа/Бета", "40", "50", "10"),
    ("Карнотит (руда)", "Смесь", "40", "45", "15"),
    ("Слюда (фуксит)", "Бета", "0", "85", "15"),
    ("Полевой шпат (минерал)", "Бета/Гамма", "0", "80", "20"),
    ("Светящийся компас (старый)", "Альфа/Бета", "30", "50", "20"),
    ("Калийная соль (пищевая)", "Бета", "0", "90", "10"),
    ("Гранитная брусчатка", "Гамма", "5", "40", "55"),
    ("Угольная зола", "Бета/Гамма", "10", "60", "30"),
    ("Вольфрамовый электрод (Th)", "Альфа/Бета", "40", "50", "10"),
    ("Кобальт-60 (пром.)", "Гамма", "0", "5", "95"),
    ("Цезий-137 (выпадения)", "Бета/Гамма", "0", "70", "30"),
    ("Самарскит (минерал)", "Альфа доминанта", "50", "40", "10"),
    ("Уранинит (руда)", "Альфа/Beta", "45", "45", "10"),
    ("Лютеций (минерал)", "Бета/Гамма", "0", "70", "30")]
        for item in data: tree.insert("", "end", values=item)
        tree.pack(fill="both", expand=True)

    def run_nuklid_exe(self):
        try: subprocess.Popen(["Nukliddaten.exe"])
        except: messagebox.showerror("Ошибка", "Файл Nukliddaten.exe не найден в каталоге программы.")

    def show_anleitung(self):
        win = Toplevel(self.root)
        win.title("Руководство и информация")
        win.geometry("1000x600")
        win.configure(bg=BG)

        frame = tk.Frame(win, bg=BG)
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        scrollbar = tk.Scrollbar(frame)
        scrollbar.pack(side="right", fill="y")

        txt_win = tk.Text(frame, bg=BG, fg=FG_W, font=("Arial", 10), wrap="word", 
                          yscrollcommand=scrollbar.set, bd=0, highlightthickness=0)
        txt_win.pack(side="left", fill="both", expand=True)
        
        scrollbar.config(command=txt_win.yview)
        anleitung_text = """Данная программа предоставляется как некоммерческое бесплатное программное обеспечение. Использование в иных целях возможно на условиях, указанных ниже.

РУКОВОДСТВО ПОЛЬЗОВАТЕЛЯ

Ввод в эксплуатацию начинается с настройки уровня сигнала. В качестве входного сигнала автоматически выбирается стандартное устройство записи Windows. Таким образом, в качестве источника сигнала в тихой обстановке можно использовать микрофон, поднесенный к «кликеру» (акустическому сигнализатору или импульсному выходу) любого счетчика Гейгера. Если у счетчика Гейгера нет акустического сигнализатора, значения времени измерения и распадов можно ввести вручную (ручной ввод).

Δ Зонд: Специфическая чувствительность используемого зонда (значение отсч/мин для 1 мкЗв/ч).
Δ α-эффективность зонда: Здесь устанавливается специфическая эффективность (чувствительность) для альфа-нуклидов.
Эти значения берутся из технических описаний или документации к самому зонду и являются решающими для точности измерения. Ниже приведены значения для некоторых распространенных зондов.

Δ αβ-фильтр (Алюминий): Толщина алюминиевого фильтра (экрана) в мм, который используется при гамма-измерении для отсечения бета-частиц и дифференциации измерения. Программа точно рассчитывает долю гамма-излучения, также поглощенную фильтром, и проницаемость для бета-частиц.

Аудиовходной сигнал: Если устройство записи активно и готово к работе, горит зеленый светодиод статуса. Каждое аудиосигнал, который расценивается как распад, отображается миганием красного светодиода статуса. Здесь важно настроить чувствительность уровня так, чтобы только один «клик» вызывал срабатывание красного светодиода, но при этом каждый импульс был учтен.

Настройка времени блокировки (Debounce): Это значение определяет время блокировки в миллисекундах, которое выдерживается после обнаруженного импульса, чтобы предотвратить повторные срабатывания из-за колебаний сигнала и обеспечить чистый результат измерения. Если один клик засчитывается дважды или более, время блокировки необходимо увеличить. По умолчанию установлено значение 50 мс, что достаточно для объектов со слабой и средней радиоактивностью.
Рекомендуемые уровни:
Низкая доза (< 5 мкЗв/ч): 30–50 мс.
Средняя доза (5–50 мкЗв/ч): Постепенно снижать до 10–15 мс для уменьшения потерь счета (мертвого времени).
Высокая доза (> 100 мкЗв/ч): Установить на абсолютный минимум оборудования (часто 1–5 мс).

Значение индикаторов
Время (с): Продолжительность текущего измерения в секундах.
Импульсы: Количество обнаруженных импульсов с начала измерения.
отсч/мин (CPM): Импульсов в минуту как мера интенсивности.
%: Процентная доля каждого вида излучения в общем валовом объеме.
Зв/ч / Гр/ч: Рассчитанная мощность дозы группы измерений на основе калибровки зонда.
Зв/ч / Гр/ч (оранжевый): Рассчитанная и дифференцированная мощность дозы отдельного вида излучения на основе калибровки зонда.

РЕЖИМ
Вручную: При выборе этого режима значения времени измерения (всегда в секундах) и импульсов можно ввести вручную. Это полезно, если нет возможности записать звук кликера через компьютер (например, при отсутствии кликера, аудиовхода или микрофона) или для проверки уже проведенных измерений. После ввода чисел подтвердите их нажатием УСТАНОВИТЬ. Общий расчет и взвешивание происходят после нажатия УСТАНОВИТЬ в области гамма-излучения.
Режим измер.: При выборе этого режима измерение можно запустить кнопкой ПУСК, приостановить кнопкой ПАУЗА и завершить кнопкой СТОП. После нажатия СТОП можно продолжить измерение с помощью ПУСК. Рекомендуемая последовательность: МАЭД (фон), Альфа, Бета, Гамма. Любое из этих измерений можно повторить при возникновении сомнений. Общий расчет и взвешивание происходят после нажатия СТОП в области гамма-излучения.
Серый фон области сигнализирует об активном и текущем измерении. Если фон мигает серым — измерение поставлено на паузу.

ПРОТОКОЛИРОВАНИЕ

Новый журнал: Кнопка «Новый журнал» удаляет все значения.
Печать журнала: Эта кнопка вызывает диалоговое окно, в котором фиксируются дополнительные метаданные об измерении. В протокол вносятся только заполненные значения. После подтверждения генерируется отформатированный текстовый файл, который отображается после сохранения. Документ содержит, помимо пользовательских данных, все полученные результаты измерений, статистическое распределение видов излучения, коэффициент сравнения с фоновым излучением (МАЭД), а также Δ-значения зонда и фильтра.

БИБЛИОТЕКА ИЗОТОПОВ

Вызывает список из 50 наиболее часто встречающихся радиоактивных изотопов. Это может помочь определить изотоп на основе видов излучения. Данный список не является обязательным, его следует рассматривать как вспомогательное средство оценки вероятности. Указанные значения консистентны, однако точность определения зависит от статистической погрешности (длительности измерения) и энергетической чувствительности прибора. Некоторые вещества имеют хорошо различимый профиль, так как сильно излучают (например, Технеций-99м), другие же имеют слабое излучение и схожие профили (например, бананы и техническая соль). Список отображает более редкие изотопы ближе к концу, поэтому при идентичных профилях вещества, находящиеся выше в списке, следует считать более вероятными.

ДАННЫЕ НУКЛИДОВ

Открывает внешнюю полезную программу Nukliddaten.exe, которая служит физическим справочником для точного соотнесения измеренных видов излучения (альфа, бета, гамма) с конкретным химическим элементом путем сопоставления энергий распада и периодов полураспада. Кнопка открывает файл Nukliddaten.exe, который должен находиться в папке программы. Для корректного отображения этой программе требуется папка Data. При необходимости в папку программы можно поместить другую программу, которая будет открываться этой кнопкой, при условии, что она называется Nukliddaten.exe и находится в той же папке, что и Messreihe.exe.

РУКОВОДСТВО

Открывает руководство пользователя, которое содержит информацию о видах излучения, данных зондов и логике расчетов.

ПОСЛЕДОВАТЕЛЬНОСТЬ ИЗМЕРЕНИЙ

Процесс измерения проводится в строгом порядке:

МАЭД (Σ): Измеряется фоновое излучение для определения нулевого уровня.
Альфа (α): Измерение проводится без фильтра непосредственно на объекте.
Бета (β): Измерение проводится с использованием фильтра.
Гамма (γ): При указании толщины алюминиевого фильтра (поле Δ αβ-фильтр) определяется высокоэнергетическая составляющая.

Чем дольше длится измерение, тем оно точнее. Это особенно актуально для слабоактивных веществ и измерения альфа-частиц.

ВНИМАНИЕ (α)

Не каждый зонд детектирует альфа-нуклиды! Если зонд не может детектировать альфа-излучение или делает это ненадежно, после измерения МАЭД в разделе «Альфа-нуклиды» следует сразу нажать СТОП и, при необходимости, сделать пометку в протоколе.

ЗОНДЫ

Чувствительность зонда и определение
Под чувствительностью измерительного зонда понимается соотношение между зарегистрированной скоростью счета (импульсов в минуту — отсч/мин) и фактической мощностью дозы в микрозивертах в час (мкЗв/ч). Определение этого значения обычно происходит по техническому паспорту производителя или путем сверки с откалиброванным эталонным прибором при известном источнике излучения (например, Cs-137). Значение 1000 отсч/мин ≙ 1 мкЗв/ч означает, например, что при мощности дозы в 1 микрозиверт в час программное обеспечение должно зафиксировать ровно одну тысячу импульсов в минуту.

Типичные стандартные значения популярных счетчиков (ориентировочные значения для 1 мкЗв/ч), где из-за эффективности альфа-детекции необходимо учитывать дополнительный коэффициент коррекции при альфа-измерении:

СИ8Б: 550 отсч/мин (35% α-эффективность)
LND-712 (Gammascout): 108 отсч/мин (10% α-эффективность)
LND-7121: 150 отсч/мин (12% α-эффективность)
LND-7311: 340 отсч/мин (35% α-эффективность)
LND-7317: 345 отсч/мин (34% α-эффективность) 
СБТ-9: 77 отсч/мин (5% α-эффективность)
СБТ-10: 2000 отсч/мин (40% α-эффективность)
СБТ-11: 285 отсч/мин (30% α-эффективность)
СБТ-11А: 300 отсч/мин (30% α-эффективность)
Valvo ZP1401: 120 отсч/мин (15% α-эффективность)

Следующие счетчики широко распространены, но непроницаемы для альфа-нуклидов и не детектируют их:

ZP1320 (стандарт Бундесвера): 53 отсч/мин
СБМ-20 / СТС-5: 160 отсч/мин
СИ-29БГ: 50 отсч/мин
J305: 150 отсч/мин
M4011: 145 отсч/мин
СИ-3БГ: <1 отсч/мин
СТС-6 (STS-6): 460 отсч/мин

ПРИМЕЧАНИЕ ДЛЯ ИЗМЕРЕНИЙ НА УЛИЦЕ

При проведении измерений на открытом воздухе рекомендуется защитить микрофон куском поролона или ткани от ветра и окружающего шума. Это предотвращает так называемые «фантомные распады», так как шум ветра может быть ошибочно принят программой за импульсы-клики.

ВИДЫ ИЗЛУЧЕНИЯ

Альфа (α): Состоит из ядер гелия. Высокая ионизирующая способность при малой дальности полета. Задерживается листом бумаги.
Бета (β): Состоит из электронов или позитронов. Средняя дальность полета. Возможно экранирование алюминиевым листом.
Гамма (γ): Электромагнитные волны (фотоны). Высокая проникающая способность. Требует плотных материалов, таких как свинец, для экранирования.
Рентгеновское (x): Электромагнитные волны (фотоны), физически очень похожие на гамма-излучение, поэтому большинство бытовых счетчиков Гейгера без проблем детектируют их и идентифицируют как гамма-излучение.
Бета (β+): Протон превращается в нейтрон. Этот процесс проявляется в измерениях через возникающее при этом гамма-излучение (аннигиляционное излучение).
Нейтронное излучение: Может быть обнаружено только косвенно путем размещения перед зондом слоя кадмия или бора и измерения гамма-излучения, которое отсутствовало бы без этого фильтра. Нейтроны реагируют с материалом, порождая гамма-излучение.
Эпсилон-излучение (ϵ): Процесс электронного захвата. Образующееся дочернее ядро испускает избыточную энергию в виде рентгеновского и гамма-излучения.

МОЩНОСТЬ АМБИЕНТНОГО ЭКВИВАЛЕНТА ДОЗЫ (МАЭД)

Это естественный радиационный фон из двух основных источников:
Земное излучение: Происходит от естественных радиоактивных веществ в почве (например, уран, торий и продукты их распада, такие как радон). Типичные значения составляют от 0,04 до 0,10 мкЗв/ч (сильно зависит от горной породы). Следует учитывать, что МАЭД может колебаться даже внутри здания (например, из-за стройматериалов, таких как гранит, или наличия радона).
Галактическое излучение (около четверти МАЭД): Состоит из высокоэнергетических частиц из космоса (Солнце и далекие галактики), которые постоянно бомбардируют атмосферу Земли. Типичное значение — около 0,03 мкЗв/ч на уровне моря (удваивается примерно каждые 1500 метров высоты).

ЛОГИКА РАСЧЕТОВ

Определение значений основано на вычитании ранее измеренных референтных значений (нетто-измерение). При расчете общей дозы (Итого αβγ) применяется биологическое взвешивание, при котором альфа-распады умножаются на коэффициент 20. Коррекция гамма-значений происходит автоматически с учетом установленной толщины фильтра и соответствующего коэффициента поглощения.

Δ Зонд: Определяет значение Гр/Зв. Каждый зонд имеет специфическую чувствительность — сколько импульсов он фиксирует при излучении в 1 мкЗв/ч. Чем чувствительнее зонд, тем больше импульсов он регистрирует при той же мощности излучения.

Δ α-эффективность: Проницаемость для альфа-нуклидов (которые затем детектируются как распад) различается у разных зондов в зависимости от входного окна. В то время как массивные ГМ-трубки из стекла или металла не пропускают альфа-нуклиды (эффективность = 0%), тонкие слюдяные мембраны пропускают определенное их количество. Программа учитывает это и экстраполирует приближенное реальное значение альфа-нуклидов. Поскольку альфа-нуклиды имеют в 20 раз большее воздействие (= Зв), доля α (= Гр) увеличивается в двадцать раз, что также учитывается в общей дозе (Итого (α+β+γ)).

Δ αβ-фильтр (Алюминий): Алгоритм программы абсолютно надежен для полупрофессионального инструмента, так как алюминиевый фильтр уверенно блокирует альфа- и бета-излучение, а математическая коррекция компенсирует минимальную потерю гамма-квантов при прохождении через материал. Используемая формула опирается на закон Бугера — Ламберта — Бера, где измеренное значение отсч/мин делится на экспоненциальную функцию от коэффициента материала (μ) и толщины фильтра (d) для восстановления исходной интенсивности излучения перед фильтром:

C[Korr.] = C[Mess.] ÷ e^-(µ × d) | d = Δαβ-фильтр | µ = 0,0202

АВТОРЫ И ПРАВОВАЯ ИНФОРМАЦИЯ

Разработчик: Мехмет С. Троян (Mehmet S. Trojan), Авторское право 2026

Лицензия: Данная программа предоставляется как бесплатное ПО (Freeware). Использование ограничено исключительно частной сферой. Коммерческое использование разрешено только после уплаты соответствующего сбора. Условия и оформление по адресу: m-trojan@mail.ru

Отказ от ответственности:
Разработчик не несет ответственности за точность значений или погрешности, вызванные используемым оборудованием (счетчик Гейгера, зонд, фильтр, микрофон, компьютер и т. д.), а также за материальный ущерб или вред здоровью, возникший в результате использования программного обеспечения или обращения с радиоактивными материалами.

Примечание к внешним программам:
Функция «Данные нуклидов» открывает внешнее приложение Nukliddaten.exe. Это программное обеспечение стороннего разработчика, которое не является частью данного программного пакета и разрабатывалось независимо. Разработчик СерияМес не несет ответственности за содержание, функции или отсутствие ошибок в этом внешнем ПО. Ссылка служит исключительно для удобства пользователя как физический справочник."""
        

        txt_win.insert("1.0", anleitung_text)
        txt_win.config(state="disabled")

    def show_print_window(self):
        win = Toplevel(self.root); win.title("Дополнительные данные"); win.geometry("400x450")
        flds = [
            ("Протоколист:", ""), 
            ("Счетчик Гейгера:", ""), 
            ("Измерительный зонд:", ""), 
            ("Объект измерения:", ""), 
            ("Источник излучения:", ""), 
            ("Расстояние (см):", " см"), 
            ("Температура (°C):", " °C"), 
            ("Влажность (%):", " %")
        ]
        ents = {}
        for f, unit in flds:
            fr = tk.Frame(win); fr.pack(fill="x", padx=10, pady=2)
            tk.Label(fr, text=f, width=20, anchor="w").pack(side="left")
            e = tk.Entry(fr); e.pack(side="right", expand=True, fill="x"); ents[f] = (e, unit)
        tk.Button(win, text="OK", command=lambda: self.generate_txt(ents, win)).pack(pady=20)

    def generate_txt(self, ents, win):
        path = filedialog.asksaveasfilename(defaultextension=".txt", initialfile=f"Протокол_{datetime.now().strftime('%d%m%Y')}.txt")
        if not path: return
        tot_str = self.lbl_total_val.cget("text"); odl_sv = self.v_lbls["odl"][4].cget("text")
        try:
            v_tot = float(tot_str.split(" ")[0].replace(",", "."))
            v_odl = float(odl_sv.split(" ")[0].replace(",", "."))
            factor = round(v_tot / v_odl, 1) if v_odl > 0 else 0.0
        except: factor = 0.0
        
        with open(path, "w", encoding="utf-8") as f:
            f.write("+++++ ПРОТОКОЛ ИЗМЕРЕНИЯ +++++\n\СерияМес: Альфа-, бета-, гамма-излучение\n\n")
            f.write(f"Дата: {datetime.now().strftime('%d.%m.%Y')}\n")
            f.write(f"Время: {self.odl_start_time} - {self.gamma_stop_time}\n\nДополнительные данные:\n")
            
            for k, (e, unit) in ents.items():
                val = e.get()
                if val: f.write(f"{k} {val}{unit}\n")
            
            f.write(f"\n+++++ РЕЗУЛЬТАТ +++++\n\nИзмеряемый материал имеет радиоактивность {tot_str} Зв/ч.\n")
            f.write(f"Это соответствует {str(factor).replace('.', ',')}-кратному превышению естественного фона (МАЭД).\n")
            
            f.write(f"\n+++++ ДЕТАЛИ +++++\n\nМАЭД (Фоновое излучение):\n{odl_sv} Зв/ч\n")
            f.write(f"{self.v_lbls['odl'][2].cget('text')} отсч/мин ({self.v_lbls['odl'][1].cget('text')} имп. за {self.v_lbls['odl'][0].cget('text')} с)\n")
            f.write(f"Доля измерения: {self.v_lbls['odl'][3].cget('text')} %\n")
            
            a_gy = self.v_lbls["alpha"][5].cget("text")
            try: a_sv_calc = self.format_val(float(a_gy.split(" ")[0].replace(",", ".")) * 20)
            except: a_sv_calc = "0,000 мк"
            
            f.write(f"\nАльфа-нуклиды (распады ядер гелия):\n{a_gy} Гр/ч (≙ {a_sv_calc} Зв/ч)\n")
            f.write(f"{self.v_lbls['alpha'][2].cget('text')} отсч/мин ({self.v_lbls['alpha'][1].cget('text')} имп. за {self.v_lbls['alpha'][0].cget('text')} с)\n")
            f.write(f"Доля измерения: {self.v_lbls['alpha'][3].cget('text')} % (вкл. МАЭД)\n")
            
            for k, n in [("beta", "Бета-частицы (распады электронов или позитронов)"), ("gamma", "Гамма-излучение (распады гамма-фотонов)")]:
                f.write(f"\n{n}:\n{self.v_lbls[k][5].cget('text')} Гр/ч (Вес x1 для Зиверта)\n")
                f.write(f"{self.v_lbls[k][2].cget('text')} отсч/мин ({self.v_lbls[k][1].cget('text')} имп. за {self.v_lbls[k][0].cget('text')} с)\n")
                f.write(f"Доля измерения: {self.v_lbls[k][3].cget('text')} % (вкл. МАЭД)\n")
            
            f.write(f"\n+++++ Δ Коррекция зонда +++++\n\nΔ - Чувствительность: 1 мкЗв/ч ≙ {self.cpm_pro_sv} отсч/мин\n\n")
            f.write(f"Δ - α-эффективность: {self.alpha_eff} %\n\n")
            f.write(f"Δ - αβ-фильтр (Алюминий): {str(round(self.filter_mm, 2)).replace('.', ',')} мм\n\n\n")
            
            f.write(f"{datetime.now().strftime('%d.%m.%Y')}, _________________________________\n\nПримечания:\n\n" + "_"*60 + "\n\n" + "_"*60 + "\n")
        
        win.destroy(); os.startfile(path)

    def calculate_results(self):
        mu, val_odl = 0.0202, self.data["odl"]["cpm"]
        val_a_n = max(0, self.data["alpha"]["cpm"] - self.data["beta"]["cpm"]) / (self.alpha_eff/100)
        val_b_n = max(0, self.data["beta"]["cpm"] - self.data["gamma"]["cpm"])
        val_g_n = max(0, self.data["gamma"]["cpm"] - val_odl) / math.exp(-mu * self.filter_mm)
        tsum = val_odl + val_a_n + val_b_n + val_g_n
        if tsum > 0:
            for k, v in [("odl", val_odl), ("alpha", val_a_n), ("beta", val_b_n), ("gamma", val_g_n)]:
                self.v_lbls[k][3].config(text=f"{int((v/tsum)*100)}")
        self.v_lbls["alpha"][5].config(text=self.format_val(val_a_n / self.cpm_pro_sv))
        self.v_lbls["beta"][5].config(text=self.format_val(val_b_n / self.cpm_pro_sv))
        self.v_lbls["gamma"][5].config(text=self.format_val(val_g_n / self.cpm_pro_sv))
        self.lbl_total_val.config(text=self.format_val((val_a_n * 20 + val_b_n + val_g_n) / self.cpm_pro_sv))

    def update_loop(self):
        self.clock_lbl.config(text=datetime.now().strftime("%d.%m.%Y - %H:%M:%S"))
        if not self.manual_mode:
            for k in self.keys:
                v = self.data[k]
                if v["run"] and not v["p"]: v["s"] += 1
                v["cpm"] = v["z"] / (v["s"] / 60) if v["s"] > 0 else 0
                self.v_lbls[k][0].config(text=str(v["s"])); self.v_lbls[k][1].config(text=str(v["z"]))
                self.v_lbls[k][2].config(text=str(int(v["cpm"]))); self.v_lbls[k][4].config(text=self.format_val(v["cpm"] / self.cpm_pro_sv))
            if not self.data["gamma"]["run"] and self.data["gamma"]["s"] > 0: self.calculate_results()
        self.root.after(1000, self.update_loop)

if __name__ == "__main__":
    root = tk.Tk(); app = MessreiheApp(root); root.mainloop()