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
        self.root.title("Messreihe - Strahlungsmessungstool - M. Trojan")
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
        return f"{val:.3f} µ".replace(".", ",")

    def setup_ui(self):
        self.footer = tk.Frame(self.root, bg="#0a0a0a", bd=1, relief="raised")
        self.footer.pack(side="bottom", fill="x", ipady=5)
        self.btn_manual = tk.Button(self.footer, text="manuelle Eingabe", bg="#222", fg=FG_W, font=("Arial", 9), padx=10, command=self.toggle_manual_mode)
        self.btn_manual.pack(side="left", padx=5, pady=5)
        tk.Button(self.footer, text="neues Protokoll", bg="#222", fg=FG_W, font=("Arial", 9), padx=10, command=self.neues_protokoll).pack(side="left", padx=5, pady=5)
        tk.Button(self.footer, text="Protokoll drucken", bg="#222", fg=FG_W, font=("Arial", 9), padx=10, command=self.show_print_window).pack(side="left", padx=5, pady=5)
        tk.Button(self.footer, text="Isotop-Referenz", bg="#222", fg=FG_W, font=("Arial", 9), padx=10, command=self.open_isotopes_table).pack(side="left", padx=5, pady=5)
        tk.Button(self.footer, text="Nuklid-Daten", bg="#222", fg=FG_W, font=("Arial", 9), padx=10, command=self.run_nuklid_exe).pack(side="left", padx=5, pady=5)
        tk.Button(self.footer, text="Anleitung", bg="#222", fg=FG_W, font=("Arial", 9), padx=10, command=self.show_anleitung).pack(side="left", padx=5, pady=5)
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=20, pady=10)
        try:
            if os.path.exists("Messreihe.png"):
                self.logo_full = tk.PhotoImage(file="Messreihe.png")
                self.logo_img = self.logo_full.subsample(2, 2)
                tk.Label(header, image=self.logo_img, bg=BG).pack(side="left", padx=(0, 20))
        except: pass
        tk.Label(header, text="Messreihe", fg=FG_W, bg=BG, font=("Arial", 60, "bold")).pack(side="left")
        self.clock_lbl = tk.Label(header, text="", fg=FG_B, bg=BG, font=("Arial", 30))
        self.clock_lbl.pack(side="left", padx=30)
        tot_f = tk.Frame(header, bg=BG)
        tot_f.pack(side="right")
        tk.Label(tot_f, text="Gesamt (αβγ)", fg=FG_W, bg=BG).pack()
        self.lbl_total_val = tk.Label(tot_f, text="0,000 µ", fg=FG_R, bg=BG, font=("Arial", 45, "bold"))
        self.lbl_total_val.pack()
        tk.Label(tot_f, text="Sv/h", fg=FG_R, bg=BG, font=("Arial", 10, "bold")).pack()
        main = tk.Frame(self.root, bg=BG)
        main.pack(fill="both", expand=True, padx=20)
        left = tk.Frame(main, bg=BG); left.pack(side="left", fill="both", expand=True)
        right = tk.Frame(main, bg=BG, width=300); right.pack(side="right", fill="y", padx=10)
        self.v_lbls = {}
        self.action_btns = {}
        confs = [
            ("odl", "ODL - Hintergrundstrahlung", "Σ", ["Zeit (s)", "Zerfälle", "CPM", "%", "Sv/h (ODL)"]),
            ("alpha", "Alpha-Nuklide", "α", ["Zeit (s)", "Zerfälle", "CPM", "%", "Gy/h (α+β+γ)", "Gy/h (α)"]),
            ("beta", "Beta-Teilchen", "β", ["Zeit (s)", "Zerfälle", "CPM", "%", "Gy/h (β+γ)", "Gy/h (β)"]),
            ("gamma", "Gamma-Strahlung", "γ", ["Zeit (s)", "Zerfälle", "CPM", "%", "Gy/h ((β)+γ)", "Gy/h (γ)"])
        ]
        for k, name, sym, units in confs:
            f = tk.Frame(left, bg=BG, bd=1, relief="flat", highlightbackground="#333", highlightthickness=1)
            f.pack(fill="x", pady=5); self.rows[k] = f
            tk.Label(f, text=sym, fg=FG_Y, bg=BG, font=("Arial", 70, "bold"), width=2).pack(side="left", padx=10)
            bf = tk.Frame(f, bg=BG); bf.pack(side="left", padx=10)
            b_start = tk.Button(bf, text="START", width=8, command=lambda x=k: self.press_start(x))
            b_start.grid(row=0, column=0, padx=1, pady=1)
            b_pause = tk.Button(bf, text="PAUSE", width=8, command=lambda x=k: self.press_pause(x))
            b_pause.grid(row=0, column=1, padx=1, pady=1)
            b_stopp = tk.Button(bf, text="STOPP", width=8, command=lambda x=k: self.press_stopp(x))
            b_stopp.grid(row=1, column=0, padx=1, pady=1)
            b_reset = tk.Button(bf, text="RESET", width=8, command=lambda x=k: self.press_reset(x))
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
                l = tk.Label(c, text="0" if i<4 else "0,000 µ", fg=col, bg=BG, font=("Arial", 30, "bold"))
                l.pack(side="bottom")
                tk.Label(c, text=units[i], fg=FG_GR, bg=BG, font=("Arial", 9)).pack(side="bottom")
                self.v_lbls[k].append(l)
        self.setup_sidebar(right)

    def setup_sidebar(self, parent):
        configs = [("cpm", "Δ Sonde 1 µSv/h ≙", FG_B, 1), ("eff", "Δ α-Effizienz Sonde", FG_O, 1), ("fil", "Δ αβ-Filter (Alu.)", FG_B, 0.05), ("sig", "Audio Eingangs-Signal", FG_G, 1), ("deb", "Debounce-Einstellung", FG_DG, 5)]
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
                pf = tk.Frame(fr, bg=BG); pf.pack(); tk.Label(pf, text="Pegel:", fg=col, bg=BG).pack(side="left")
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
        self.btn_manual.config(text="Mess-Modus" if self.manual_mode else "manuelle Eingabe")
        if not self.manual_mode: self.neues_protokoll()
        for k in self.keys:
            btns = self.action_btns[k]
            btns[0].config(text="SET" if self.manual_mode else "START")
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
                if k == "odl": self.odl_start_time = "Manuell"
                if k == "gamma": self.gamma_stop_time = "Manuell"; self.calculate_results()
            except: messagebox.showerror("Fehler", "Bitte nur Zahlen eingeben.")
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
        self.v_lbls[k][4].config(text="0,000 µ")
        if len(self.v_lbls[k]) > 5: self.v_lbls[k][5].config(text="0,000 µ")

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
        if messagebox.askyesno("Messreihe", "Alle Messungen löschen und neue Messung beginnen?"):
            for k in self.keys: self.press_reset(k)
            self.lbl_total_val.config(text="0,000 µ"); self.odl_start_time = "--:--:--"; self.gamma_stop_time = "--:--:--"

    def open_isotopes_table(self):
        win = tk.Toplevel(self.root); win.geometry("950x600"); win.title("Referenzwerte radioaktiver Isotope"); win.configure(bg=BG)
        tk.Label(win, text="Isotopen-Fingerabdrücke (Top 50, nach Häufigkeit sortiert)", fg=FG_Y, bg=BG, font=("Arial", 20, "bold")).pack(pady=10)
        frame = tk.Frame(win, bg=BG); frame.pack(fill="both", expand=True, padx=20, pady=10)
        scrollbar = tk.Scrollbar(frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")
        style = ttk.Style(); style.theme_use("clam")
        style.configure("Treeview", background="#1a1a1a", foreground="white", fieldbackground="#1a1a1a", rowheight=25)
        style.configure("Treeview.Heading", background="#333", foreground="white", font=("Arial", 10, "bold"))
        tree = ttk.Treeview(frame, columns=("name", "dom", "alpha", "beta", "gamma"), show="headings")
        headings = [("name", "Produkt / Material", 300), ("dom", "Dominanz", 150), ("alpha", "α %", 70), ("beta", "β %", 70), ("gamma", "γ %", 70)]
        for col, txt, w in headings:
            tree.heading(col, text=txt); tree.column(col, width=w, anchor="center" if col != "name" else "w")
        scrollbar.config(command=tree.yview)
        data = [            ("Granit (Baumaterial)", "Gamma/Beta", "5", "45", "50"),
            ("Kalidünger (Pottasche)", "Beta", "0", "90", "10"),
            ("Uranglas (Antiquität)", "Beta/Gamma", "2", "83", "15"),
            ("Pechblende (Mineral)", "Mix (U-Reihe)", "45", "40", "15"),
            ("Bananen (getrocknet)", "Beta (K-40)", "0", "90", "10"),
            ("Glühmäntel (Thorium-alt)", "Mix (Th-Reihe)", "30", "50", "20"),
            ("Radium-Zifferblatt (Uhr)", "Mix (Ra-Reihe)", "25", "55", "20"),
            ("Americium (Rauchmelder)", "Alpha", "95", "1", "4"),
            ("Fliesen (Uran-Glasur)", "Beta", "10", "75", "15"),
            ("Tritium-Leuchtfarbe", "Beta (weich)", "0", "100", "0"),
            ("Schweißelektroden (rot)", "Alpha/Beta", "40", "50", "10"),
            ("Linsenersatz (Th-Glas)", "Beta/Gamma", "5", "60", "35"),
            ("Stein-Pilze (getrocknet)", "Beta (Cs-137)", "0", "90", "10"),
            ("Basalt (Gestein)", "Gamma/Beta", "2", "48", "50"),
            ("Monazitsand", "Alpha/Beta", "45", "40", "15"),
            ("Zirkon-Sand", "Alpha/Beta", "30", "50", "20"),
            ("Gasglühstrümpfe (modern)", "Beta dominant", "5", "85", "10"),
            ("Rauchquarz", "Gamma", "0", "10", "90"),
            ("Antike Keramik (rot)", "Beta", "10", "70", "20"),
            ("Autunit (Mineral)", "Alpha/Beta", "50", "40", "10"),
            ("Euklas (Mineral)", "Gamma", "0", "20", "80"),
            ("Torbernit (Mineral)", "Alpha/Beta", "45", "45", "10"),
            ("Pottasche-Backpulver", "Beta", "0", "90", "10"),
            ("Streusalz (Kaliumchlorid)", "Beta", "0", "92", "8"),
            ("Kalksandstein", "Gamma", "2", "28", "70"),
            ("Medizinisches I-131", "Gamma", "0", "10", "90"),
            ("Technetium-99m (Medizin)", "Gamma", "0", "1", "99"),
            ("Thorianit (Mineral)", "Alpha dominant", "60", "30", "10"),
            ("Beryll (Mineral)", "Gamma", "0", "15", "85"),
            ("Schiefer (Eifel/Hunsrück)", "Beta/Gamma", "5", "55", "40"),
            ("Tonschiefer", "Gamma dominant", "3", "37", "60"),
            ("Ziegelstein (rot)", "Beta/Gamma", "4", "46", "50"),
            ("Brasilnuss (Asche)", "Alpha/Beta", "30", "60", "10"),
            ("Tabakasche", "Alpha (Po-210)", "40", "50", "10"),
            ("Beton (Altbau)", "Gamma", "5", "45", "50"),
            ("Gips (Industrie)", "Beta/Gamma", "2", "58", "40"),
            ("Uranyl-Nitrat (Labor)", "Alpha/Beta", "40", "50", "10"),
            ("Carnotit (Erz)", "Mix", "40", "45", "15"),
            ("Glimmer (Fuchsit)", "Beta", "0", "85", "15"),
            ("Feldspat (Mineral)", "Beta/Gamma", "0", "80", "20"),
            ("Leuchtkompass (alt)", "Alpha/Beta", "30", "50", "20"),
            ("K-Salz (Nahrung)", "Beta", "0", "90", "10"),
            ("Granit-Pflaster", "Gamma", "5", "40", "55"),
            ("Kohleasche", "Beta/Gamma", "10", "60", "30"),
            ("Wolfram-Elektrode (Th)", "Alpha/Beta", "40", "50", "10"),
            ("Kobalt-60 (Industrie)", "Gamma", "0", "5", "95"),
            ("Cäsium-137 (Fallout)", "Beta/Gamma", "0", "70", "30"),
            ("Samarskit (Mineral)", "Alpha dominant", "50", "40", "10"),
            ("Uraninit (Erz)", "Alpha/Beta", "45", "45", "10"),
            ("Lutetium (Mineral)", "Beta/Gamma", "0", "70", "30")]
        for item in data: tree.insert("", "end", values=item)
        tree.pack(fill="both", expand=True)

    def run_nuklid_exe(self):
        try: subprocess.Popen(["Nukliddaten.exe"])
        except: messagebox.showerror("Fehler", "Nukliddaten.exe wurde im Programmverzeichnis nicht gefunden.")

    def show_anleitung(self):
        win = Toplevel(self.root)
        win.title("Anleitung und Informationen")
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
        anleitung_text = """Dieses Programm wird als nicht-kommerzielle Freeware zur Verfügung gestellt. Andere Nutzungen sind unter unten genannten Bedingungen erwerbbar.

-----------------------------------

BEDIENUNGSANLEITUNG

Die Inbetriebnahme erfolgt über die Justierung des Signalpegels. Als Eingangssignal wird das Standard-Aufnahmegerät unter Windows automatisch genommen. Somit kann ein Mikrofon am Klicker (akustischem Signalgeber oder Impulsausgang) jedes Geigerzählers in ruhiger Umgebung als Eingangsquelle genutzt werden. Sollte der Geigerzähler kein Klicker haben, so können die Werte der Messzeit und Zerfälle auch manuell eingegeben werden (manuelle Eingabe).

Δ Sonde: Die spezifische Empfindlichkeit der verwendeten Sonde (CPM-Wert für 1 µSv/h). 
Δ α-Effizienz Sonde: wird die spezifische Effizienz (Empfindlichkeit) für Alpha-Nuklide eingestellt. 
Diese Werte werden den technischen Beschreibungen oder Unterlagen der Sonde selbst entnommen und sind entscheidend für die Messung. Weiter unten stehen die Werte einiger gängiger Sonden.

Δ αβ-Filter (Alu.): Die Stärke in mm, die der Aluminium-Filter bzw. Aluminiumabschirmung hat, mit der man bei der Gamma-Messung die Beta-Teilchen abschirmt und diese Messung differenziert. Denn die damit ebenfalls abgeschirmte Gamma-Anteile und die Durchlässigkeit für Beta-Teilchen wird von dem Programm ebenfalls präzise errechnet.

Audio Eingangs-Signal: Ist das Aufnahmegerät aktiv und bereit, leuchtet die grüne Status-LED. Jedes Audiosignal, welches als Zerfall gewertet wird, wird durch das Aufleuchten der roten Status-LED angezeigt. Hier ist es wichtig die Pegelempfindlichkeit so einzustellen, dass nur ein Klick die rote LED auslöst, aber jeder Klick gezählt wird.

Debounce-Einstellung: Dieser Wert legt die Sperrzeit in Millisekunden fest, die nach einem erkannten Impuls gewartet wird, um Mehrfachzählungen durch Signalschwingungen zu verhindern und so ein sauberes Messergebnis zu gewährleisten. Sollte ein Klick doppelt oder mehrfach gewertet werden, so muss die Sperrzeit erhöht werden. Diese liegt Standardmäßig bei 50 ms, was für schwach bis mittel radioaktiv-strahlende Objekte ausreichend ist.
Empfohlene Stufen:
    Niedrige Dosis (< 5 µSv/h): 30–50 ms. 
    Mittlere Dosis (5–50 µSv/h): Schrittweise auf 10–15 ms senken um Zählverlust (Totzeit) zu reduzieren.
    Hohe Dosis (> 100 µSv/h): Auf absolutes Minimum der Hardware gehen (oft 1–5 ms).

Bedeutung der Anzeigen
    Zeit (s): Dauer der aktuellen Messung in Sekunden.
    Zerfälle: Anzahl der detektierten Impulse seit Messbeginn.
    CPM: Impulse pro Minute (Counts Per Minute) als Maß der Intensität.
    %: Prozentualer Anteil der jeweiligen Strahlungsart an der Bruttogesamtmenge.
    Sv/h / Gy/h: Berechnete Dosisleistung der Messgruppe basierend auf der Sonden-Kalibrierung.
    Sv/h / Gy/h (orange): Berechnete und differenzierte Dosisleistung der Einzelstrahlung basierend auf der Sonden-Kalibrierung.

MODUS
manuelle Eingabe: Bei Auswahl, können die Werte der Mess-Zeit (immer in Sekunden) und Zerfälle manuell eingegeben werden. Das ist sinnvoll, wenn es keine Möglichkeit gibt, den Klicker über den Computer aufzunehmen (z.B. bei fehlenem Klicker oder fehlendem Audio-Eingang oder Mikrofon) oder um bereits getätigte Messungen zu prüfen. Nach Eingabe der Zahlen bestätigt man diese mit SET. Die Gesamt-Berechnung und Gewichtung erfolgt nach Auswahl SET im Bereich Gamma-Strahlung.
Mess-Modus: Bei Auswahl kann eine Messung mit START gestartet werden, mit PAUSE pausiert und mit STOPP abgeschlossen. Nach STOPP kann mittels START weiter gemessen werden. Die sinnvolle Reihenfolge ist: ODL, Alpha, Beta, Gamma. Eine dieser einzelnen Messung kann bei Zweifel wiederholt werden. Die Gesamtberechnung und Gewichtung erfolgt nach STOPP im Gamma-Strahlen-Bereich.
Eine graufarbige Hinterlegung eines Bereiches signalisiert eine aktive und laufende Messung. Blinkt diese grau, so ist die Messung pausiert.

PROTOKOLLIERUNG

neues Protokoll: Die Schaltfläche neues Protokoll löscht alle Werte. 
Protokoll drucken: Über diese Schaltfläche wird ein Dialogfenster aufgerufen. In diesem Bereich werden zusätzliche Metadaten zur Messung erfasst. Nur eingetragene Werte werden in das Protokoll übernommen. Nach der Bestätigung wird eine formatierte Textdatei generiert und nach Speichern angezeigt. Dieses Dokument enthält neben den Benutzereingaben alle ermittelten Messwerte, die statistische Verteilung der Strahlungsarten sowie den Vergleichsfaktor zur Hintergrundstrahlung (ODL) sowie die Δ-Werte der Sonde und Filter.

ISOTOP-REFERENZ

Ruft eine Liste der 50 am häufigsten vorkommenden radioaktiven Isotope auf. Das kann helfen, anhand der Strahlungsarten den Isotop zu ermitteln. Diese Liste ist nicht verbindlich, sondern als Hilfsmittel der Wahrscheinlichkeit anzusehen. Die angegebenen Werte sind zwar konsistent, jedoch ist die Unterscheidung abhängig von der statistischen Genauigkeit (Messdauer) und der Energieempfindlichkeit des Messgerätes. Einige Stoffe haben ein sehr gut unterscheidbares Profil da sie stark strahlen und sich stark von anderen unterscheiden (z.B. Technetium-99m), andere jedoch sind schwach-strahlend und sich im Profil sehr ähnlich (z.B. Bananen und Streusalz), wobei die Liste nach unten hin seltener vorkommende Isotope anzeigt, weshalb bei identischen Profilen die höher gelisteten Stoffe als wahrscheinlicher anzusehen sind.

NUKLID-DATEN

Öffnet ein externes und sehr brauchbares Programm namens Nukliddaten.exe, welches diesem Programm als physikalisches Nachschlagewerk dient, um die gemessenen Strahlungsarten (Alpha, Beta, Gamma) durch den Abgleich von Zerfallsenergien und Halbwertszeiten einem exakten chemischen Element zuzuordnen. Der Button öffnet Nukliddaten.exe das sich im Programmordner befinden muss. Dieses Programm benötigt für die Darstellung des Inhaltes den Ordner Data. Bei bedarf kann in dem Programmordner ein anderes Programm eingefügt werden, dass mit diesem Button geöffnet wird. Voraussetzung ist dass dieses Nukliddaten.exe heißt und sich im selben Ordner wie Messreihe.exe befindet.

ANLEITUNG

Öffnet die Bedienungsanleitung, die u.a. Infos zu Strahlungsarten, Sondendaten und Berechnungslogik enthält.

-----------------------------------

MESSABFOLGE

Der Messvorgang wird in einer festen Reihenfolge durchgeführt:

    ODL (Σ): Die Hintergrundstrahlung wird zur Ermittlung der Nullreferenz gemessen.
    Alpha (α): Die Messung erfolgt ohne Filter direkt am Messobjekt.
    Beta (β): Die Messung wird unter Verwendung eines Filters durchgeführt.
    Gamma (γ): Unter Angabe der Aluminium-Filterdicke (Kasten Δ γ-Filter) wird der hochenergetische Anteil bestimmt.
Je länger die Messung ist, umso präziser ist diese. Das gilt insbesondere für niedrig radioaktiv-strahlende Stoffe und Alpha-Teilchen-Messung.

ACHTUNG (α)

Nicht jede Sonde detektiert Alpha-Nuklide! Sollte diese keine Alpha-Nuklide detektieren können oder diese unzuverlässig ermitteln, dann ist nach der ODL-Messung in der Rubrik Alpha-Nuklide direkt STOPP zu drücken und dies ggf. im Messprotokoll zu vermerken.

SONDEN

Sondenempfindlichkeit und Ermittlung
Unter der Empfindlichkeit einer Messsonde wird das Verhältnis zwischen der detektierten Impulsrate (Counts Per Minute - CPM) und der tatsächlich vorliegenden Dosisleistung in Mikrosievert pro Stunde (µSv/h) verstanden. Die Ermittlung dieses Wertes erfolgt üblicherweise über das technische Datenblatt des Herstellers oder durch einen Abgleich mit einem kalibrierten Referenzmessgerät bei einer bekannten Strahlungsquelle (z. B. Cs-137). Ein Wert von 1000 CPM ≙ 1 µSv/h bedeutet beispielsweise, dass bei einer Belastung von einem Mikrosievert pro Stunde genau tausend Impulse pro Minute von der Software registriert werden müssen.

Typische Standardwerte von gängigen Zählrohren werden häufig folgende Orientierungswerte für 1 µSv/h herangezogen, bei denen man aufgrund der Alpha-Detektions-Effizienz einen weiteren Korrekturfaktor bei der Alpha-Messung berücksichtigen muss:

    Si8B: 550 CPM (35% Alpha-Effizienz)
    LND-712 (Gammascout): 108 CPM (10% Alpha-Effizienz)
    LND-7121: 150 CPM (12% Alpha-Effizienz)
    LND-7311: 340 CPM (35% Alpha-Effizienz)
    LND-7317: 345 CPM (34% Alpha-Effizienz) 
    SBT-9: 77 CPM (5% Alpha-Effizienz)
    SBT-10: 2000 CPM (40% Alpha-Effizienz)
    SBT-11: 285 CPM (30% Alpha-Effizienz)
    SBT-11A: 300 CPM (30% Alpha-Effizienz)
    Valvo ZP1401: 120 CPM (15% Alpha-Effizienz)

Folgende Zählrohre sind weit verbreitet, sind jedoch für Alpha-Nuklide undurchlässig und detektieren diese nicht:

    ZP1320 (Bundeswehr-Standard): 53 CPM
    SBM-20 / STS-5: 160 CPM
    SI-29BG: 50 CPM
    J305: 150 CPM
    M4011: 145 CPM
    SI-3BG: <1 CPM
    STS-6 (СТС-6):  460 CPM

HINWEIS FÜR AUSSENMESSUNGEN

Bei Messungen im Freien empfiehlt es sich, das Mikrofon mit einem Stück Schaumstoff oder einem Tuch gegen Wind und Umgebungsgeräusche abzuschirmen. Dies verhindert sogenannte Geister-Zerfälle, da Windgeräusche vom Programm fälschlicherweise als Klick-Impulse gewertet werden könnten.

-----------------------------------

STRAHLUNGSARTEN

    Alpha (α): Bestehend aus Heliumkernen. Hohe Ionisationskraft bei geringer Reichweite. Stoppbar durch Papier.
    Beta (β): Bestehend aus Elektronen oder Positronen. Mittlere Reichweite. Abschirmung durch Aluminiumblech möglich.
    Gamma (γ): Elektromagnetische Wellen (Photonen). Hohe Durchdringungskraft. Erfordert dichte Materialien wie Blei zur Abschirmung.
    Röntgen (x): Elektromagnetische Wellen (Photonen) und physikalisch der Gammastrahlung sehr ähnlich, weshalb die meisten handelsüblichen Geigerzähler sie problemlos detektieren und als Gammastrahlung identifizieren.
    Beta (β+): Ein Proton verwandelt sich in ein Neutron. Dieser Vorgang äußert sich messtechnisch durch die dadurch entstehende Gammastrahlung (Annihilationsstrahlung).
    Neutronenstrahlung: Können nur indirekt nachgewiesen werden, indem man vor die Sonde eine Schicht Cadmium oder Bor aufsetzt und die Gammastrahlung misst, die ohne den Cadmium- oder Bor-Filter ausbleiben würde. Die Neutronen reagieren mit diesem Material, dabei entsteht Gammastrahlung.
    Epsilon-Strahlung (ϵ): Ist der Prozess des Elektroneneinfangs. Der daraus entstehende Tochterkern gibt dabei überschüssige Energie als Röntgen- und Gammastrahlung ab.

ORTSDOSISLEISTUNG

Das ist die natürliche Hintergrundstrahlung aus 2 verschiedenen Quellen:
Terrestrische Strahlung: Stammt von natürlichen radioaktiven Stoffen im Boden (z. B. Uran, Thorium und deren Zerfallsprodukte wie Radon). Typisch sind ca. 0,04 bis 0,10 μSv/h (stark abhängig vom Gestein, im Schwarzwald höher als im Norden). Zu beachten ist, dass die ODL auch innerhalb eines Hauses schwanken kann (z.B. durch Baustoffe wie Granit oder Radon).
Galaktische Strahlung (ca. ein Viertel der ODL): Besteht aus hochenergetischen Teilchen aus dem Weltraum (Sonne und fernen Galaxien), die ständig auf die Erdatmosphäre treffen. Typisch sind ca. 0,03 μSv/h auf Meereshöhe (verdoppelt sich etwa alle 1.500 Höhenmeter).

-----------------------------------

BERECHNUNGSLOGIK

Die Ermittlung der Werte basiert auf der Subtraktion der zuvor gemessenen Referenzwerte (Netto-Messung). Bei der Berechnung der Gesamtdosis (Gesamt αβγ) wird eine biologische Gewichtung vorgenommen, bei der Alpha-Zerfälle mit dem Faktor 20 multipliziert werden. Die Korrektur der Gamma-Werte erfolgt automatisch unter Berücksichtigung der eingestellten Filterdicke und der entsprechenden Absorptionsrate.

Δ Sonde: Bestimmt den Gy/Sv-Wert. Jede Sonde hat eine spezifische Empfindlichkeit, wieviele Zerfälle sie bei einer Strahlung von 1 µSv/h misst. Je empfindlicher die Sonde ist, umso mehr Zerfälle detektiert sie bei gleicher Strahlung.

Δ α-Effizienz: Die Durchlässigkeit für Alpha-Nuklide (die dann als Zerfall detektiert werden) unterscheidet sich bei den Sonden in der Durchlässigkeit des Sondenfensters. Während massive GM-Zählrohre aus Glas oder Metall keine Alpha-Nuklide durchlassen (Effizienz = 0%), lassen dünne Glimmermembrane eine bestimmte Anzahl durch. Das Programm berücksichtigt dieses und rechnet damit den annähernden Realwert an Alpha-Nukliden hoch. Da Alpha-Nuklide eine 20fach höhere Auswirkung haben (= Sv) wird der α-Anteil (= Gy) verzwanzigfacht, was wiederum in der Gesamtdosis (Gesamt (α+β+γ)) ebenfalls berücksichtigt wird.  

Δ αβ-Filter (Alu.): Die Programm-Berechnung ist für ein semiprofessionelles Tool absolut plausibel, da der Alufilter die Alpha- und Beta-Strahlung zuverlässig blockiert, während die mathematische Korrektur den minimalen Verlust der Gamma-Quanten beim Durchgang durch das Material ausgleicht. Die zugrunde liegende Formel nutzt das Lambert-Beersche Gesetz, bei dem der gemessene CPM-Wert durch die Exponentialfunktion aus dem Materialkoeffizienten (μ) und der Filterdicke (d) geteilt wird, um die ursprüngliche Strahlungsintensität vor dem Filter zu rekonstruieren:

C[Korr.] = C[Mess.] ÷ e^-(µ × d) | d = Δαβ-Filter | µ = 0,0202

-----------------------------------


CREDITS & RECHTLICHE HINWEISE

Entwickler: Mehmet S. Trojan, Copyright 2026

Lizenz: Dieses Programm wird als Freeware zur Verfügung gestellt. Die Nutzung ist ausschließlich auf den privaten Bereich beschränkt. Eine kommerzielle Nutzung ist erst nach Entrichtung einer entsprechenden Gebühr gestattet. Konditionen und Abwicklung unter: m-trojan@mail.ru

Haftungsausschluss:
Für die Richtigkeit der Werte oder Ungenauigkeit durch die verwendete Technik (Geigerzähler, Sonde, Filter, Mikrofon, Computer etc.) sowie für Sach- oder Personenschäden, die aus der Nutzung der Software oder der Handhabung radioaktiver Materialien entstehen, wird keine Haftung übernommen.

Hinweis zu externen Programmen:
Die Funktion Nuklid-Daten öffnet die externe Anwendung Nukliddaten.exe. Hierbei handelt es sich um Software eines Drittanbieters, die nicht Teil dieses Programmpakets ist und unabhängig entwickelt wurde. Der Entwickler von Messreihe übernimmt keine Verantwortung für die Inhalte, Funktionen oder die Fehlerfreiheit dieser externen Software. Die Verknüpfung dient lediglich als komfortables physikalisches Nachschlagewerk für den Anwender."""
        

        txt_win.insert("1.0", anleitung_text)
        txt_win.config(state="disabled")

    def show_print_window(self):
        win = Toplevel(self.root); win.title("Ergänzende Angaben"); win.geometry("400x450")
        flds = [("Protokollant:", ""), ("Geiger-Zähler:", ""), ("Mess-Sonde:", ""), ("Messobjekt:", ""), ("Strahlungsmaterial:", ""), ("Mess-Abstand (cm):", " cm"), ("Raumtemperatur (°C):", " °C"), ("Luftfeuchtigkeit (%):", " %")]
        ents = {}
        for f, unit in flds:
            fr = tk.Frame(win); fr.pack(fill="x", padx=10, pady=2)
            tk.Label(fr, text=f, width=18, anchor="w").pack(side="left")
            e = tk.Entry(fr); e.pack(side="right", expand=True, fill="x"); ents[f] = (e, unit)
        tk.Button(win, text="OK", command=lambda: self.generate_txt(ents, win)).pack(pady=20)

    def generate_txt(self, ents, win):
        path = filedialog.asksaveasfilename(defaultextension=".txt", initialfile=f"Protokoll_{datetime.now().strftime('%d%m%Y')}.txt")
        if not path: return
        tot_str = self.lbl_total_val.cget("text"); odl_sv = self.v_lbls["odl"][4].cget("text")
        try:
            v_tot = float(tot_str.split(" ")[0].replace(",", "."))
            v_odl = float(odl_sv.split(" ")[0].replace(",", "."))
            factor = round(v_tot / v_odl, 1) if v_odl > 0 else 0.0
        except: factor = 0.0
        with open(path, "w", encoding="utf-8") as f:
            f.write("+++++ MESS-PROTOKOLL +++++\n\nMessreihe: Alpha-, Beta-, Gammastrahlung\n\n")
            f.write(f"Datum: {datetime.now().strftime('%d.%m.%Y')}\nUhrzeit: {self.odl_start_time} bis {self.gamma_stop_time}\n\nErgänzende Angaben:\n")
            for k, (e, unit) in ents.items():
                val = e.get()
                if val: f.write(f"{k} {val}{unit}\n")
            f.write(f"\n+++++ ERGEBNIS +++++\n\nDas gemessene Material weist eine Radioaktivität von {tot_str} Sv/h auf.\nDas entspricht der {str(factor).replace('.', ',')}-fachen Strahlung der natürlichen Ortsdosisleistung.\n")
            f.write(f"\n+++++ DETAILS +++++\n\nOrtsdosisleistung (Hintergrundstrahlung):\n{odl_sv} Sv/h\n{self.v_lbls['odl'][2].cget('text')} CPM ({self.v_lbls['odl'][1].cget('text')} Zerfälle in {self.v_lbls['odl'][0].cget('text')} Sekunden)\nAnteil der Messung: {self.v_lbls['odl'][3].cget('text')} %\n")
            a_gy = self.v_lbls["alpha"][5].cget("text")
            try: a_sv_calc = self.format_val(float(a_gy.split(" ")[0].replace(",", ".")) * 20)
            except: a_sv_calc = "0,000 µ"
            f.write(f"\nAlpha-Nuklide (Zerfälle durch Heliumkerne):\n{a_gy} Gy/h (≙ {a_sv_calc} Sv/h)\n{self.v_lbls['alpha'][2].cget('text')} CPM ({self.v_lbls['alpha'][1].cget('text')} Zerfälle in {self.v_lbls['alpha'][0].cget('text')} Sekunden)\nAnteil der Messung: {self.v_lbls['alpha'][3].cget('text')} % (inkl. ODL)\n")
            for k, n in [("beta", "Beta-Teilchen (Zerfälle durch Elektronen oder Positronen)"), ("gamma", "Gamma-Strahlung (Zerfälle durch Gamma-Photonen)")]:
                f.write(f"\n{n}:\n{self.v_lbls[k][5].cget('text')} Gy/h (Gewichtung x1 für Sievert)\n{self.v_lbls[k][2].cget('text')} CPM ({self.v_lbls[k][1].cget('text')} Zerfälle in {self.v_lbls[k][0].cget('text')} Sekunden)\nAnteil der Messung: {self.v_lbls[k][3].cget('text')} % (inkl. ODL)\n")
            f.write(f"\n+++++ Δ Sondenkorrektur +++++\n\nΔ - Empfindlichkeit: 1 µSv/h ≙ {self.cpm_pro_sv} CPM\n\nΔ - α-Effizienz: {self.alpha_eff} %\n\nΔ - αβ-Filter (Alu): {self.filter_mm:.2f} mm\n\n\n")
            f.write(f"{datetime.now().strftime('%d.%m.%Y')}, _________________________________\n\nAnmerkungen:\n\n" + "_"*60 + "\n\n" + "_"*60 + "\n")
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