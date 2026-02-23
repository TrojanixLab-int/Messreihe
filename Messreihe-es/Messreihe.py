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
        self.root.title("SerieMed - Herramienta de medición de radiación - M. Trojan")
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
        return f"{val:.3f} µ"

    def setup_ui(self):
        self.footer = tk.Frame(self.root, bg="#0a0a0a", bd=1, relief="raised")
        self.footer.pack(side="bottom", fill="x", ipady=5)
        self.btn_manual = tk.Button(self.footer, text="Modo Manual", bg="#222", fg=FG_W, font=("Arial", 9), padx=10, command=self.toggle_manual_mode)
        self.btn_manual.pack(side="left", padx=5, pady=5)
        tk.Button(self.footer, text="Nuevo Registro", bg="#222", fg=FG_W, font=("Arial", 9), padx=10, command=self.neues_protokoll).pack(side="left", padx=5, pady=5)
        tk.Button(self.footer, text="Imprimir Registro", bg="#222", fg=FG_W, font=("Arial", 9), padx=10, command=self.show_print_window).pack(side="left", padx=5, pady=5)
        tk.Button(self.footer, text="Biblioteca de Isótopos", bg="#222", fg=FG_W, font=("Arial", 9), padx=10, command=self.open_isotopes_table).pack(side="left", padx=5, pady=5)
        tk.Button(self.footer, text="Datos de Núclidos", bg="#222", fg=FG_W, font=("Arial", 9), padx=10, command=self.run_nuklid_exe).pack(side="left", padx=5, pady=5)
        tk.Button(self.footer, text="Manual de Usuario", bg="#222", fg=FG_W, font=("Arial", 9), padx=10, command=self.show_anleitung).pack(side="left", padx=5, pady=5)
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=20, pady=10)
        try:
            if os.path.exists("Messreihe.png"):
                self.logo_full = tk.PhotoImage(file="Messreihe.png")
                self.logo_img = self.logo_full.subsample(2, 2)
                tk.Label(header, image=self.logo_img, bg=BG).pack(side="left", padx=(0, 20))
        except: pass
        tk.Label(header, text="SerieMed", fg=FG_W, bg=BG, font=("Arial", 60, "bold")).pack(side="left")
        self.clock_lbl = tk.Label(header, text="", fg=FG_B, bg=BG, font=("Arial", 30))
        self.clock_lbl.pack(side="left", padx=30)
        tot_f = tk.Frame(header, bg=BG)
        tot_f.pack(side="right")
        tk.Label(tot_f, text="Total (αβγ)", fg=FG_W, bg=BG).pack()
        self.lbl_total_val = tk.Label(tot_f, text="0.000 µ", fg=FG_R, bg=BG, font=("Arial", 45, "bold"))
        self.lbl_total_val.pack()
        tk.Label(tot_f, text="Sv/h", fg=FG_R, bg=BG, font=("Arial", 10, "bold")).pack()
        main = tk.Frame(self.root, bg=BG)
        main.pack(fill="both", expand=True, padx=20)
        left = tk.Frame(main, bg=BG); left.pack(side="left", fill="both", expand=True)
        right = tk.Frame(main, bg=BG, width=300); right.pack(side="right", fill="y", padx=10)
        self.v_lbls = {}
        self.action_btns = {}
        confs = [
            ("odl", "TDAA - Tasa de Dosis Ambiental Equivalente", "Σ", ["tiempo (s)", "pulsos", "CPM", "%", "Sv/h (TDAA)"]),
            ("alpha", "Núclidos alfa", "α", ["tiempo (s)", "pulsos", "CPM", "%", "Gy/h (α+β+γ)", "Gy/h (α)"]),
            ("beta", "Partículas beta", "β", ["tiempo (s)", "pulsos", "CPM", "%", "Gy/h (β+γ)", "Gy/h (β)"]),
            ("gamma", "Radiación gamma", "γ", ["tiempo (s)", "pulsos", "CPM", "%", "Gy/h ((β)+γ)", "Gy/h (γ)"])
        ]
        for k, name, sym, units in confs:
            f = tk.Frame(left, bg=BG, bd=1, relief="flat", highlightbackground="#333", highlightthickness=1)
            f.pack(fill="x", pady=5); self.rows[k] = f
            tk.Label(f, text=sym, fg=FG_Y, bg=BG, font=("Arial", 70, "bold"), width=2).pack(side="left", padx=10)
            bf = tk.Frame(f, bg=BG); bf.pack(side="left", padx=10)
            b_start = tk.Button(bf, text="INICIAR", width=8, command=lambda x=k: self.press_start(x))
            b_start.grid(row=0, column=0, padx=1, pady=1)
            b_pause = tk.Button(bf, text="PAUSA", width=8, command=lambda x=k: self.press_pause(x))
            b_pause.grid(row=0, column=1, padx=1, pady=1)
            b_stopp = tk.Button(bf, text="DETENER", width=8, command=lambda x=k: self.press_stopp(x))
            b_stopp.grid(row=1, column=0, padx=1, pady=1)
            b_reset = tk.Button(bf, text="REINICIAR", width=8, command=lambda x=k: self.press_reset(x))
            b_reset.grid(row=1, column=1, padx=1, pady=1)
            self.action_btns[k] = (b_start, b_pause, b_stopp, b_reset)
            vf = tk.Frame(f, bg=BG); vf.pack(side="left", fill="x", expand=True, padx=20)
            tk.Label(vf, text=name, fg=FG_W, bg=BG, font=("Arial", 12, "bold")).grid(row=0, column=0, columnspan=6, sticky="w")
            self.v_lbls[k] = []
            self.manual_entries[k] = {}
            for i in range(len(units)):
                c = tk.Frame(vf, bg=BG); c.grid(row=1, column=i, sticky="nsew", padx=15)
                if i in [0, 1]:
                    e = tk.Entry(c, width=6, font=("Arial", 10), justify="center")
                    self.manual_entries[k][i] = e
                col = [FG_R, FG_R, FG_R, FG_Y, FG_DR, FG_O][i]
                l = tk.Label(c, text="0" if i<4 else "0.000 µ", fg=col, bg=BG, font=("Arial", 30, "bold"))
                l.pack(side="bottom")
                tk.Label(c, text=units[i], fg=FG_GR, bg=BG, font=("Arial", 9)).pack(side="bottom")
                self.v_lbls[k].append(l)
        self.setup_sidebar(right)

    def setup_sidebar(self, parent):
        configs = [("cpm", "Δ sonda 1 µSv/h ≙", FG_B, 1), ("eff", "Δ α eficiencia sonda", FG_O, 1), ("fil", "Δ αβ filtro (Alu.)", FG_B, 0.05), ("sig", "señal de entrada de audio", FG_G, 1), ("deb", "tiempo de debounce", FG_DG, 5)]
        for t, txt, col, d in configs:
            fr = tk.LabelFrame(parent, text=txt, fg=col, bg=BG, bd=1, relief="solid")
            fr.pack(fill="x", pady=5, ipady=5)
            if t == "cpm":
                self.res_sonde = tk.Label(fr, text=str(self.cpm_pro_sv), fg=col, bg=BG, font=("Arial", 25, "bold")); self.res_sonde.pack()
                tk.Label(fr, text="CPM", fg=col, bg=BG).pack()
            elif t == "eff":
                self.res_eff = tk.Label(fr, text=f"{self.alpha_eff} %", fg=col, bg=BG, font=("Arial", 25, "bold")); self.res_eff.pack()
            elif t == "fil":
                self.res_fil = tk.Label(fr, text=f"{self.filter_mm:.2f} mm", fg=col, bg=BG, font=("Arial", 25, "bold")); self.res_fil.pack()
            elif t == "sig":
                self.canv = tk.Canvas(fr, width=120, height=35, bg=BG, highlightthickness=0); self.canv.pack()
                self.l_grn = self.canv.create_oval(35, 5, 55, 25, fill="#030"); self.l_red = self.canv.create_oval(65, 5, 85, 25, fill="#300")
                pf = tk.Frame(fr, bg=BG); pf.pack(); tk.Label(pf, text="Nivel:", fg=col, bg=BG).pack(side="left")
                self.lbl_p_val = tk.Label(pf, text=f"{self.thresh_idx*5}%", fg=FG_W, bg="#222"); self.lbl_p_val.pack(side="left", padx=5)
            elif t == "deb":
                self.res_deb = tk.Label(fr, text=f"{self.debounce_ms} ms", fg=col, bg=BG, font=("Arial", 25, "bold")); self.res_deb.pack()
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
        self.btn_manual.config(text="Modo Medición" if self.manual_mode else "Modo Manual")
        if not self.manual_mode: self.neues_protokoll()
        for k in self.keys:
            btns = self.action_btns[k]
            btns[0].config(text="ENTRADA" if self.manual_mode else "INICIAR")
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
                if k == "odl": self.odl_start_time = "Manual"
                if k == "gamma": self.gamma_stop_time = "Manual"; self.calculate_results()
            except: messagebox.showerror("Error", "Por favor, introduzca solo números.")
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
        self.v_lbls[k][4].config(text="0.000 µ")
        if len(self.v_lbls[k]) > 5: self.v_lbls[k][5].config(text="0.000 µ")

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
        if t=="fil": self.filter_mm = max(0.01, self.filter_mm + d); self.res_fil.config(text=f"{self.filter_mm:.2f} mm")
        if t=="deb": self.debounce_ms = max(0, self.debounce_ms + d); self.res_deb.config(text=f"{self.debounce_ms} ms")

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
        if messagebox.askyesno("SerieMed", "¿Borrar todas las mediciones y comenzar una nueva?"):
            for k in self.keys: self.press_reset(k)
            self.lbl_total_val.config(text="0.000 µ"); self.odl_start_time = "--:--:--"; self.gamma_stop_time = "--:--:--"

    def open_isotopes_table(self):
        win = tk.Toplevel(self.root); win.geometry("950x600"); win.title("Valores de referencia de isótopos radiactivos"); win.configure(bg=BG)
        tk.Label(win, text="Huellas de isótopos (Top 50, ordenadas por frecuencia)", fg=FG_Y, bg=BG, font=("Arial", 20, "bold")).pack(pady=10)
        frame = tk.Frame(win, bg=BG); frame.pack(fill="both", expand=True, padx=20, pady=10)
        scrollbar = tk.Scrollbar(frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")
        style = ttk.Style(); style.theme_use("clam")
        style.configure("Treeview", background="#1a1a1a", foreground="white", fieldbackground="#1a1a1a", rowheight=25)
        style.configure("Treeview.Heading", background="#333", foreground="white", font=("Arial", 10, "bold"))
        tree = ttk.Treeview(frame, columns=("name", "dom", "alpha", "beta", "gamma"), show="headings")
        headings = [("name", "Producto / Material", 300), ("dom", "Dominancia", 150), ("alpha", "α %", 70), ("beta", "β %", 70), ("gamma", "γ %", 70)]
        for col, txt, w in headings:
            tree.heading(col, text=txt); tree.column(col, width=w, anchor="center" if col != "name" else "w")
        scrollbar.config(command=tree.yview)
        data = [
            ("Granito (material de construcción)", "Gamma/Beta", "5", "45", "50"),
            ("Fertilizante de potasa", "Beta", "0", "90", "10"),
            ("Vidrio de uranio (antigüedad)", "Beta/Gamma", "2", "83", "15"),
            ("Pechblenda (mineral)", "Mix (serie de U)", "45", "40", "15"),
            ("Plátanos (deshidratados)", "Beta (K-40)", "0", "90", "10"),
            ("Camisas de gas (torio-antiguo)", "Mix (serie de Th)", "30", "50", "20"),
            ("Esfera de radio (reloj)", "Mix (serie de Ra)", "25", "55", "20"),
            ("Americio (detector de humo)", "Alfa", "95", "1", "4"),
            ("Azulejos (esmaltado de uranio)", "Beta", "10", "75", "15"),
            ("Pintura luminosa de tritio", "Beta (suave)", "0", "100", "0"),
            ("Electrodos de soldadura (rojo)", "Alfa/Beta", "40", "50", "10"),
            ("Lente de repuesto (vidrio de Th)", "Beta/Gamma", "5", "60", "35"),
            ("Setas de piedra (deshidratadas)", "Beta (Cs-137)", "0", "90", "10"),
            ("Basalto (roca)", "Gamma/Beta", "2", "48", "50"),
            ("Arena de monacita", "Alfa/Beta", "45", "40", "15"),
            ("Arena de circón", "Alfa/Beta", "30", "50", "20"),
            ("Camisas de gas (modernas)", "Beta dominante", "5", "85", "10"),
            ("Cuarzo ahumado", "Gamma", "0", "10", "90"),
            ("Cerámica antigua (roja)", "Beta", "10", "70", "20"),
            ("Autunita (mineral)", "Alfa/Beta", "50", "40", "10"),
            ("Euclasa (mineral)", "Gamma", "0", "20", "80"),
            ("Torbernita (mineral)", "Alfa/Beta", "45", "45", "10"),
            ("Potasa (levadura en polvo)", "Beta", "0", "90", "10"),
            ("Sal de deshielo (cloruro de potasio)", "Beta", "0", "92", "8"),
            ("Ladrillo silicocalcáreo", "Gamma", "2", "28", "70"),
            ("I-131 médico", "Gamma", "0", "10", "90"),
            ("Tecnecio-99m (medicina)", "Gamma", "0", "1", "99"),
            ("Torianita (mineral)", "Alfa dominante", "60", "30", "10"),
            ("Berilo (mineral)", "Gamma", "0", "15", "85"),
            ("Pizarra (Eifel/Hunsrück)", "Beta/Gamma", "5", "55", "40"),
            ("Pizarra arcillosa", "Gamma dominante", "3", "37", "60"),
            ("Ladrillo (rojo)", "Beta/Gamma", "4", "46", "50"),
            ("Nuez de Brasil (ceniza)", "Alfa/Beta", "30", "60", "10"),
            ("Ceniza de tabaco", "Alfa (Po-210)", "40", "50", "10"),
            ("Hormigón (construcción antigua)", "Gamma", "5", "45", "50"),
            ("Yeso (industrial)", "Beta/Gamma", "2", "58", "40"),
            ("Nitrato de uranilo (laboratorio)", "Alfa/Beta", "40", "50", "10"),
            ("Carnotita (mineral)", "Mix", "40", "45", "15"),
            ("Mica (fuchsita)", "Beta", "0", "85", "15"),
            ("Feldespato (mineral)", "Beta/Gamma", "0", "80", "20"),
            ("Brújula luminosa (antigua)", "Alfa/Beta", "30", "50", "20"),
            ("Sal de potasio (alimento)", "Beta", "0", "90", "10"),
            ("Adoquines de granito", "Gamma", "5", "40", "55"),
            ("Ceniza de carbón", "Beta/Gamma", "10", "60", "30"),
            ("Electrodo de tungsteno (Th)", "Alfa/Beta", "40", "50", "10"),
            ("Cobalto-60 (industrial)", "Gamma", "0", "5", "95"),
            ("Cesio-137 (fallout)", "Beta/Gamma", "0", "70", "30"),
            ("Samarskita (mineral)", "Alfa dominante", "50", "40", "10"),
            ("Uraninita (mineral)", "Alfa/Beta", "45", "45", "10"),
            ("Lutecio (mineral)", "Beta/Gamma", "0", "70", "30")]
        for item in data: tree.insert("", "end", values=item)
        tree.pack(fill="both", expand=True)

    def run_nuklid_exe(self):
        try: subprocess.Popen(["Nukliddaten.exe"])
        except: messagebox.showerror("Error de sistema", "No se encontró el archivo Nukliddaten.exe en el directorio del programa.")

    def show_anleitung(self):
        win = Toplevel(self.root)
        win.title("Guía e información")
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
        anleitung_text = """Este programa se ofrece como software gratuito (Freeware) no comercial. Otros usos pueden adquirirse bajo las condiciones mencionadas al final.

MANUAL DE USUARIO

La puesta en marcha se realiza mediante el ajuste del nivel de señal (señal de entrada de audio). Como señal de entrada se toma automáticamente el dispositivo de grabación estándar de Windows. Por lo tanto, se puede utilizar un micrófono en el clicker (generador de señal acústica o salida de impulsos) de cualquier contador Geiger en un entorno silencioso como fuente de entrada. Si el contador Geiger no tiene clicker, los valores del tiempo de medición y las desintegraciones también pueden introducirse manualmente (Modo Manual).

Δ sonda 1 µSv/h ≙: La sensibilidad específica de la sonda utilizada (valor CPM para 1 µSv/h).
Δ α eficiencia sonda: Se ajusta la eficiencia específica (sensibilidad) para los Núclidos alfa.
Estos valores se extraen de las descripciones técnicas o documentos de la propia sonda y son decisivos para la medición. Más abajo se encuentran los valores de algunas sondas comunes.

Δ αβ filtro (alu.): El espesor en mm del filtro de aluminio o blindaje de aluminio con el que se blindan las Partículas beta durante la medición de Radiación gamma para diferenciar esta medición. El programa también calcula con precisión la parte de gamma que también queda blindada y la permeabilidad para las Partículas beta.

señal de entrada de audio: Si el dispositivo de grabación está activo y listo, se ilumina el LED de estado verde. Cada señal de audio que se evalúa como desintegración se indica mediante la iluminación del LED de estado rojo. Aquí es importante ajustar la sensibilidad del nivel de modo que solo un click active el LED rojo, pero que cada click sea contabilizado.

tiempo de debounce: Este valor establece el tiempo de bloqueo en milisegundos que se espera después de un impulso detectado para evitar conteos múltiples por oscilaciones de la señal y garantizar así un resultado de medición limpio. Si un click se cuenta doble o múltiplemente, se debe aumentar el tiempo de bloqueo. Por defecto es de 50 ms, lo cual es suficiente para objetos con radiación débil a media.
Niveles recomendados:
Dosis baja (< 5 µSv/h): 30–50 ms.
Dosis media (5–50 µSv/h): Reducir gradualmente a 10–15 ms para reducir la pérdida de conteo (tiempo muerto).
Dosis alta (> 100 µSv/h): Ir al mínimo absoluto del hardware (a menudo 1–5 ms).

Significado de las pantallas
Tiempo (s): Duración de la medición actual en segundos.
pulsos: Número de impulsos detectados desde el inicio de la medición.
CPM: Impulsos por minuto (Counts Per Minute) como medida de la intensidad.
%: Porcentaje de cada tipo de radiación en el total bruto.
Sv/h / Gy/h: Tasa de dosis calculada del grupo de medición basada en la calibración de la sonda.
Sv/h / Gy/h (naranja): Tasa de dosis calculada y diferenciada de la radiación individual basada en la calibración de la sonda.

MODO
Modo Manual: Al seleccionarlo, se pueden introducir manualmente los valores del tiempo de medición (siempre en segundos) y los pulsos. Esto es útil si no hay posibilidad de grabar el clicker a través del ordenador (p. ej., si falta el clicker, la entrada de audio o el micrófono) o para comprobar mediciones ya realizadas. Tras introducir los números, se confirman con Aceptar. El cálculo total y la ponderación se realizan tras seleccionar Aceptar en el área de Radiación gamma.
Modo Medición: Al seleccionarlo, se puede iniciar una medición con INICIAR, pausarla con PAUSA y finalizarla con DETENER. Después de DETENER, se puede seguir midiendo mediante INICIAR. El orden lógico es: TDAA, Núclidos alfa, Partículas beta, Radiación gamma. Una de estas mediciones individuales puede repetirse en caso de duda. El cálculo total y la ponderación se realizan tras DETENER en el área de Radiación gamma.
Un fondo de color gris en un área señaliza una medición activa y en curso. Si parpadea en gris, la medición está en pausa.

PROTOCOLO

Nuevo Registro: El botón Nuevo Registro borra todos los valores.
Imprimir Registro: A través de este botón se abre una ventana de diálogo. En esta área se registran metadatos adicionales de la medición. Solo los valores introducidos se incorporarán al protocolo. Tras la confirmación, se genera un archivo de texto formateado y se muestra después de guardar. Este documento contiene, además de las entradas del usuario, todos los valores de medición determinados, la distribución estadística de los tipos de radiación, así como el factor de comparación con la radiación de fondo (TDAA) y los valores Δ de la sonda y el filtro.

BIBLIOTECA DE ISOTOPOS

Abre una lista de los 50 isótopos radiactivos más frecuentes. Esto puede ayudar a determinar el isótopo basándose en los tipos de radiación. Esta lista no es vinculante, sino que debe considerarse como una herramienta de probabilidad. Los valores indicados son consistentes, pero la distinción depende de la precisión estadística (duración de la medición) y de la sensibilidad energética del dispositivo de medición. Algunas sustancias tienen un perfil muy distinguible ya que radian con fuerza y se diferencian mucho de otras (p. ej., Tecnecio-99m), pero otras son de radiación débil y muy similares en su perfil (p. ej., plátanos y sal de deshielo); la lista muestra hacia abajo los isótopos que ocurren con menos frecuencia, por lo que en caso de perfiles idénticos, las sustancias listadas más arriba deben considerarse más probables.

DATOS DE NUCLIDOS

Abre un programa externo y muy útil llamado Nukliddaten.exe, que sirve a este programa como obra de consulta física para asignar los tipos de radiación medidos (Núclidos alfa, Partículas beta, Radiación gamma) a un elemento químico exacto mediante la comparación de energías de desintegración y vidas medias. El botón abre Nukliddaten.exe, que debe encontrarse en la carpeta del programa. Este programa requiere la carpeta Data para mostrar el contenido. En caso necesario, se puede insertar otro programa en la carpeta del programa que se abra con este botón, siempre que se llame Nukliddaten.exe y esté en la misma carpeta que SerieMed.exe.

MANUAL DE USUARIO

Abre las instrucciones de uso, que contienen, entre otra cosa, información sobre tipos de radiación, datos de la sonda y lógica de cálculo.

SECUENCIA DE MEDICIÓN

El proceso de medición se realiza en un orden fijo:

TDAA (Σ): Se mide la radiación de fondo para determinar la referencia cero.
Núclidos alfa (α): La medición se realiza sin filtro directamente en el objeto a medir.
Partículas beta (β): La medición se realiza utilizando un filtro.
Radiación gamma (γ): Indicando el espesor del filtro de aluminio (cuadro Δ αβ filtro (alu.)) se determina la parte de alta energía.

Cuanto más larga sea la medición, más precisa será. Esto se aplica especialmente a sustancias de baja radiactividad y a la medición de partículas alfa.

ATENCIÓN (α)

¡No todas las sondas detectan Núclidos alfa! Si la sonda no puede detectarlos o los determina de forma poco fiable, se debe presionar DETENER directamente en la sección de Núclidos alfa tras la medición de TDAA y anotarlo en el registro de medición si es necesario.

SONDAS

Sensibilidad de la sonda y determinación
Se entiende por sensibilidad de una sonda de medición la relación entre la tasa de impulsos detectada (CPM) y la tasa de dosis real presente en microsieverts por hora (µSv/h). La determinación de este valor se realiza habitualmente a través de la ficha técnica del fabricante o mediante una comparación con un dispositivo de referencia calibrado ante una fuente de radiación conocida (p. ej., Cs-137). Un valor de 1000 CPM ≙ 1 µSv/h significa, por ejemplo, que ante una carga de un microsievert por hora, el software debe registrar exactamente mil impulsos por minuto.

Valores estándar típicos de tubos contadores comunes; a menudo se utilizan los siguientes valores de orientación para 1 µSv/h, en los que se debe tener en cuenta otro factor de corrección en la medición alfa debido a la eficiencia de detección alfa:

Si8B: 550 CPM (35% eficiencia alfa)
LND-712 (Gammascout): 108 CPM (10% eficiencia alfa)
LND-7121: 150 CPM (12% eficiencia alfa)
LND-7311: 340 CPM (35% eficiencia alfa)
LND-7317: 345 CPM (34% eficiencia alfa) 
SBT-9: 77 CPM (5% eficiencia alfa)
SBT-10: 2000 CPM (40% eficiencia alfa)
SBT-11: 285 CPM (30% eficiencia alfa)
SBT-11A: 300 CPM (30% eficiencia alfa)
Valvo ZP1401: 120 CPM (15% eficiencia alfa)

Los siguientes tubos contadores están muy extendidos, pero son impermeables a los Núclidos alfa y no los detectan:

ZP1320 (Estándar de las Fuerzas Armadas Alemanas): 53 CPM
SBM-20 / STS-5: 160 CPM
SI-29BG: 50 CPM
J305: 150 CPM
M4011: 145 CPM
SI-3BG: <1 CPM
STS-6 (СТС-6): 460 CPM

NOTA PARA MEDICIONES EN EXTERIORES

En mediciones al aire libre, se recomienda proteger el micrófono con un trozo de espuma o un paño contra el viento y los ruidos ambientales. Esto evita las llamadas desintegraciones fantasma, ya que el programa podría interpretar erróneamente el ruido del viento como impulsos de click.

TIPOS DE RADIACIÓN

Núclidos alfa (α): Compuestos por núcleos de helio. Alto poder de ionización con corto alcance. Se detiene con papel.
Partículas beta (β): Compuestas por electrones o positrones. Alcance medio. Blindaje posible mediante chapa de aluminio.
Radiación gamma (γ): Ondas electromagnéticas (fotones). Alto poder de penetración. Requiere materiales densos como el plomo para el blindaje.
Rayos X (x): Ondas electromagnéticas (fotones) y físicamente muy similares a la radiación gamma, por lo que la mayoría de los contadores Geiger comerciales los detectan sin problemas y los identifican como radiación gamma.
Beta (β+): Un protón se transforma en un neutrón. Este proceso se manifiesta en la medición a través de la radiación gamma resultante (radiación de aniquilación).
Radiación de neutrones: Solo pueden detectarse indirectamente colocando una capa de cadmio o boro frente a la sonda y midiendo la radiación gamma que faltaría sin el filtro de cadmio o boro. Los neutrones reaccionan con este material, produciendo radiación gamma.
Radiación épsilon (ϵ): Es el proceso de captura de electrones. El núcleo hijo resultante libera el exceso de energía en forma de rayos X y radiación gamma.

TASA DE DOSIS AMBIENTAL EQUIVALENTE (TDAA)

Es la radiación de fondo natural de 2 fuentes distintas:
Radiación terrestre: Proviene de sustancias radiactivas naturales en el suelo (p. ej., uranio, torio y sus productos de desintegración como el radón). Lo típico es de aprox. 0.04 a 0.10 μSv/h (depende mucho de la roca, mayor en la Selva Negra que en el norte). Hay que tener en cuenta que la TDAA también puede fluctuar dentro de una casa (p. ej., por materiales de construcción como el granito o el radón).
Radiación galáctica (aprox. una cuarta parte de la TDAA): Consiste en partículas de alta energía del espacio (sol y galaxias lejanas) que chocan constantemente con la atmósfera terrestre. Lo típico es aprox. 0.03 μSv/h al nivel del mar (se duplica aproximadamente cada 1.500 metros de altitud).

LÓGICA DE CÁLCULO

La determinación de los valores se basa en la sustracción de los valores de referencia medidos previamente (medición neta). En el cálculo de la dosis total (Total (αβγ)) se realiza una ponderación biológica en la que las desintegraciones alfa se multiplican por el factor 20. La corrección de los valores gamma se realiza automáticamente teniendo en cuenta el espesor del filtro ajustado y la tasa de absorción correspondiente.

Δ sonda 1 µSv/h ≙: Determina el valor Gy/Sv. Cada sonda tiene una sensibilidad específica de cuántas desintegraciones mide ante una radiación de 1 µSv/h. Cuanto más sensible sea la sonda, más desintegraciones detectará ante la misma radiación.

Δ α eficiencia sonda: La permeabilidad para los Núclidos alfa (que luego se detectan como desintegración) difiere en las sondas según la permeabilidad de la ventana de la sonda. Mientras que los tubos contadores GM masivos de vidrio o metal no dejan pasar los Núclidos alfa (eficiencia = 0%), las membranas finas de mica dejan pasar una cantidad determinada. El programa tiene esto en cuenta y calcula el valor real aproximado de Núclidos alfa. Como los Núclidos alfa tienen un efecto 20 veces mayor (= Sv), la parte α (= Gy) se multiplica por veinte, lo que a su vez se tiene en cuenta en la dosis total (Total (αβγ)).

Δ αβ filtro (alu.): El cálculo del programa es absolutamente plausible para una herramienta semiprofesional, ya que el filtro de aluminio bloquea de forma fiable la radiación alfa y beta, mientras que la corrección matemática compensa la pérdida mínima de cuantos gamma al atravesar el material. La fórmula subyacente utiliza la ley de Beer-Lambert, en la que el valor CPM medido se divide por la función exponencial del coeficiente del material (μ) y el espesor del filtro (d) para reconstruir la intensidad de radiación original antes del filtro:

C[Korr.] = C[Mess.] ÷ e^-(µ × d) | d = Δ αβ filtro (alu.) | µ = 0.0202

CRÉDITOS Y AVISOS LEGALES

Desarrollador: Mehmet S. Trojan, Copyright 2026

Licencia: Este programa se ofrece como Freeware. El uso está limitado exclusivamente al ámbito privado. El uso comercial solo está permitido tras el pago de la tasa correspondiente. Condiciones y gestión en: m-trojan@mail.ru

Exención de responsabilidad:
No se asume ninguna responsabilidad por la exactitud de los valores o la inexactitud debida a la técnica utilizada (contador Geiger, sonda, filtro, micrófono, ordenador, etc.), así como por daños materiales o personales derivados del uso del software o del manejo de materiales radiactivos.

Nota sobre programas externos:
La función Datos de Núclidos abre la aplicación externa Nukliddaten.exe. Se trata de software de un tercero que no forma parte de este paquete de programas y ha sido desarrollado de forma independiente. El desarrollador de SerieMed no asume ninguna responsabilidad por los contenidos, funciones o la ausencia de errores de este software externo. El enlace sirve meramente como una cómoda obra de consulta física para el usuario."""
        

        txt_win.insert("1.0", anleitung_text)
        txt_win.config(state="disabled")

    def show_print_window(self):
        win = Toplevel(self.root); win.title("Datos complementarios"); win.geometry("400x450")
        flds = [("Registrador:", ""), ("Contador Geiger:", ""), ("Sonda de medición:", ""), ("Objeto de medición:", ""), ("Material radiactivo:", ""), ("Distancia (cm):", " cm"), ("Temp. ambiente (°C):", " °C"), ("Humedad (%):", " %")]
        ents = {}
        for f, unit in flds:
            fr = tk.Frame(win); fr.pack(fill="x", padx=10, pady=2)
            tk.Label(fr, text=f, width=18, anchor="w").pack(side="left")
            e = tk.Entry(fr); e.pack(side="right", expand=True, fill="x"); ents[f] = (e, unit)
        tk.Button(win, text="OK", command=lambda: self.generate_txt(ents, win)).pack(pady=20)

    def generate_txt(self, ents, win):
        path = filedialog.asksaveasfilename(defaultextension=".txt", initialfile=f"Registro_{datetime.now().strftime('%d%m%Y')}.txt")
        if not path: return
        tot_str = self.lbl_total_val.cget("text"); odl_sv = self.v_lbls["odl"][4].cget("text")
        try:
            v_tot = float(tot_str.split(" ")[0].replace(",", "."))
            v_odl = float(odl_sv.split(" ")[0].replace(",", "."))
            factor = round(v_tot / v_odl, 1) if v_odl > 0 else 0.0
        except: factor = 0.0
        with open(path, "w", encoding="utf-8") as f:
            f.write("+++++ REGISTRO DE MEDICIÓN +++++\n\nSerie de medición: Radiación alfa, beta y gamma\n\n")
            f.write(f"Fecha: {datetime.now().strftime('%d.%m.%Y')}\nHora: {self.odl_start_time} hasta {self.gamma_stop_time}\n\nInformación adicional:\n")
            for k, (e, unit) in ents.items():
                val = e.get()
                if val: f.write(f"{k} {val}{unit}\n")
            f.write(f"\n+++++ RESULTADO +++++\n\nEl material medido muestra una radiactividad de {tot_str} Sv/h.\nEsto corresponde a {str(factor)}-veces la Tasa de Dosis Ambiental Equivalente (TDAA) natural.\n")
            f.write(f"\n+++++ DETALLES +++++\n\nTasa de Dosis Ambiental Equivalente (Radiación de fondo):\n{odl_sv} Sv/h\n{self.v_lbls['odl'][2].cget('text')} CPM ({self.v_lbls['odl'][1].cget('text')} desintegraciones en {self.v_lbls['odl'][0].cget('text')} segundos)\nProporción de la medición: {self.v_lbls['odl'][3].cget('text')} %\n")
            a_gy = self.v_lbls["alpha"][5].cget("text")
            try: a_sv_calc = self.format_val(float(a_gy.split(" ")[0].replace(",", ".")) * 20)
            except: a_sv_calc = "0.000 µ"
            f.write(f"\nNúclidos alfa (Desintegraciones por núcleos de helio):\n{a_gy} Gy/h (≙ {a_sv_calc} Sv/h)\n{self.v_lbls['alpha'][2].cget('text')} CPM ({self.v_lbls['alpha'][1].cget('text')} desintegraciones en {self.v_lbls['alpha'][0].cget('text')} segundos)\nProporción de la medición: {self.v_lbls['alpha'][3].cget('text')} % (incl. TDAA)\n")
            for k, n in [("beta", "Partículas beta (Desintegraciones por electrones o positrones)"), ("gamma", "Radiación gamma (Desintegraciones por fotones gamma)")]:
                f.write(f"\n{n}:\n{self.v_lbls[k][5].cget('text')} Gy/h (Ponderación x1 para Sievert)\n{self.v_lbls[k][2].cget('text')} CPM ({self.v_lbls[k][1].cget('text')} desintegraciones en {self.v_lbls[k][0].cget('text')} segundos)\nProporción de la medición: {self.v_lbls[k][3].cget('text')} % (incl. TDAA)\n")
            f.write(f"\n+++++ Corrección Δ sonda +++++\n\nΔ sonda 1 µSv/h ≙: {self.cpm_pro_sv} CPM\n\nΔ α eficiencia sonda: {self.alpha_eff} %\n\nΔ αβ filtro (alu.): {self.filter_mm:.2f} mm\n\n\n")
            f.write(f"{datetime.now().strftime('%d.%m.%Y')}, _________________________________\n\nNotas:\n\n" + "_"*60 + "\n\n" + "_"*60 + "\n")
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