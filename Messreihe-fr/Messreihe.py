import tkinter as tk
from tkinter import messagebox, filedialog, Toplevel, ttk
import sounddevice as sd
import numpy as np
from datetime import datetime
import math
import time
import os
import subprocess
import json

BG = "#000"
FG_W, FG_Y, FG_R, FG_O, FG_B, FG_G = "#fff", "#ff0", "#f00", "#f60", "#36f", "#0f0"
FG_DR, FG_GR = "#800000", "#777"
GRAY_FOC = "#3f3f3f"
FG_DG = "#006400"

class MessreiheApp:
    def __init__(self, root):
        self.root = root
        self.root.title("SérieMes - Outil de mesure des rayonnements - M. Trojan")
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
        self.odl_start_time = "--h--:--"
        self.gamma_stop_time = "--h--:--"
        self.hold_job = None
        self.hold_start_time = 0
        self.profiles = {}
        self.setup_ui()
        self.load_config()
        self.start_audio()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(100, self.update_loop)

    def on_close(self):
        try:
            self.save_config()
        except:
            pass
        self.root.destroy()

    def format_val(self, val):
        return f"{val:.3f} µ".replace(".", ",")

    def setup_ui(self):
        self.footer = tk.Frame(self.root, bg="#0a0a0a", bd=1, relief="raised")
        self.footer.pack(side="bottom", fill="x", ipady=5)
        self.btn_manual = tk.Button(self.footer, text="Mode manuel", bg="#222", fg=FG_W, font=("Arial", 9), padx=10, command=self.toggle_manual_mode)
        self.btn_manual.pack(side="left", padx=5, pady=5)
        tk.Button(self.footer, text="Nouveau log", bg="#222", fg=FG_W, font=("Arial", 9), padx=10, command=self.neues_protokoll).pack(side="left", padx=5, pady=5)
        tk.Button(self.footer, text="Imprimer le log", bg="#222", fg=FG_W, font=("Arial", 9), padx=10, command=self.show_print_window).pack(side="left", padx=5, pady=5)
        tk.Button(self.footer, text="Bibliothèque d'isotopes", bg="#222", fg=FG_W, font=("Arial", 9), padx=10, command=self.open_isotopes_table).pack(side="left", padx=5, pady=5)
        tk.Button(self.footer, text="Données des nucléides", bg="#222", fg=FG_W, font=("Arial", 9), padx=10, command=self.run_nuklid_exe).pack(side="left", padx=5, pady=5)
        tk.Button(self.footer, text="Mode d'emploi", bg="#222", fg=FG_W, font=("Arial", 9), padx=10, command=self.show_anleitung).pack(side="left", padx=5, pady=5)
        for p in ["P1", "P2", "P3"]:
            btn = tk.Button(self.footer, text=f"P.{p[1]}", bg="#ddd", fg=FG_B, font=("Arial", 9, "bold"), padx=10)
            btn.pack(side="left", padx=2, pady=5)
            btn.bind("<ButtonPress-1>", lambda e, x=p: self.p_press(x))
            btn.bind("<ButtonRelease-1>", lambda e, x=p: self.p_release(x))
            self.add_tooltip(btn, "Maintenir pour enregistrer")

        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=20, pady=10)
        try:
            if os.path.exists("Messreihe.png"):
                self.logo_full = tk.PhotoImage(file="Messreihe.png")
                self.logo_img = self.logo_full.subsample(3, 3)
                tk.Label(header, image=self.logo_img, bg=BG).pack(side="left", padx=(0, 20))
        except: pass
        tk.Label(header, text="SérieMes", fg=FG_W, bg=BG, font=("Arial", 60, "bold")).pack(side="left")
        self.clock_lbl = tk.Label(header, text="", fg=FG_B, bg=BG, font=("Arial", 30))
        self.clock_lbl.pack(side="left", padx=30)
        tot_f = tk.Frame(header, bg=BG)
        tot_f.pack(side="right")
        tk.Label(tot_f, text="Total (α+β+γ)", fg=FG_W, bg=BG).pack()
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
            ("odl", "EDMA - Équivalent de Dose Ambiant", "Σ", ["Temps (s)", "Coups", "CPM", "% (Σαβγ)", "Sv/h (EDMA)"]),
            ("alpha", "Nucléides Alpha", "α", ["Temps (s)", "Coups", "CPM", "% (αβγ)", "Gy/h (α+β+γ)", "Gy/h (α)"]),
            ("beta", "Particules Bêta", "β", ["Temps (s)", "Coups", "CPM", "% (αβγ)", "Gy/h (β+γ)", "Gy/h (β)"]),
            ("gamma", "Rayonnement Gamma", "γ", ["Temps (s)", "Coups", "CPM", "% (αβγ)", "Gy/h ((β)+γ)", "Gy/h (γ)"])
        ]
        for k, name, sym, units in confs:
            f = tk.Frame(left, bg=BG, bd=1, relief="flat", highlightbackground="#333", highlightthickness=1)
            f.pack(fill="x", pady=5); self.rows[k] = f
            tk.Label(f, text=sym, fg=FG_Y, bg=BG, font=("Arial", 70, "bold"), width=2).pack(side="left", padx=10)
            bf = tk.Frame(f, bg=BG); bf.pack(side="left", padx=10)
            b_start = tk.Button(bf, text="DÉMARRER", width=8, command=lambda x=k: self.press_start(x))
            b_start.grid(row=0, column=0, padx=1, pady=1)
            b_pause = tk.Button(bf, text="PAUSE", width=8, command=lambda x=k: self.press_pause(x))
            b_pause.grid(row=0, column=1, padx=1, pady=1)
            b_stopp = tk.Button(bf, text="ARRÊTER", width=8, command=lambda x=k: self.press_stopp(x))
            b_stopp.grid(row=1, column=0, padx=1, pady=1)
            b_reset = tk.Button(bf, text="RÉINIT", width=8, command=lambda x=k: self.press_reset(x))
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
            self.v_lbls["odl"][3].config(fg=FG_GR)
        self.setup_sidebar(right)

    def setup_sidebar(self, parent):
        configs = [("cpm", "Δ sonde 1 µSv/h ≙", FG_B, 1), ("eff", "Δ efficacité α de la sonde", FG_O, 1), ("fil", "Δ filtre αβ (alu.)", FG_B, 0.05), ("sig", "signal d'entrée audio", FG_G, 1), ("deb", "réglage du temps de blocage", FG_DG, 5)]
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
                pf = tk.Frame(fr, bg=BG); pf.pack(); tk.Label(pf, text="Niveau:", fg=col, bg=BG).pack(side="left")
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
        self.btn_manual.config(text="Mode mesure" if self.manual_mode else "Mode manuel")
        if not self.manual_mode: self.neues_protokoll()
        for k in self.keys:
            btns = self.action_btns[k]
            btns[0].config(text="VALIDER" if self.manual_mode else "DÉMARRER")
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
                if k == "odl": self.odl_start_time = "manuel"
                if k == "gamma": self.gamma_stop_time = "manuel"; self.calculate_results()
            except: messagebox.showerror("Erreur", "Veuillez ne saisir que des chiffres.")
        else:
            self.data[k]["run"], self.data[k]["p"] = True, False
            self.rows[k].config(bg=GRAY_FOC)
            if k == "odl": self.odl_start_time = datetime.now().strftime("%Hh%M:%S")

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
        if t=="fil": 
            self.filter_mm = max(0.01, self.filter_mm + d)
            self.res_fil.config(text=f"{str(round(self.filter_mm, 2)).replace('.', ',')} mm")
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
        if k == "gamma": self.gamma_stop_time = datetime.now().strftime("%Hh%M:%S")

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
        if messagebox.askyesno("Série de mesures", "Effacer toutes les mesures et commencer une nouvelle mesure?"):
            for k in self.keys: self.press_reset(k)
            self.lbl_total_val.config(text="0,000 µ"); self.odl_start_time = "--h--:--"; self.gamma_stop_time = "--h--:--"

    def open_isotopes_table(self):
        win = tk.Toplevel(self.root); win.geometry("950x600"); win.title("Valeurs de référence des isotopes radioactifs"); win.configure(bg=BG)
        tk.Label(win, text="Empreintes isotopiques (Top 50, triées par fréquence)", fg=FG_Y, bg=BG, font=("Arial", 20, "bold")).pack(pady=10)
        frame = tk.Frame(win, bg=BG); frame.pack(fill="both", expand=True, padx=20, pady=10)
        scrollbar = tk.Scrollbar(frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")
        style = ttk.Style(); style.theme_use("clam")
        style.configure("Treeview", background="#1a1a1a", foreground="white", fieldbackground="#1a1a1a", rowheight=25)
        style.configure("Treeview.Heading", background="#333", foreground="white", font=("Arial", 10, "bold"))
        tree = ttk.Treeview(frame, columns=("name", "dom", "alpha", "beta", "gamma"), show="headings")
        headings = [("name", "Produit / Matériau", 300), ("dom", "Dominance", 150), ("alpha", "α %", 70), ("beta", "β %", 70), ("gamma", "γ %", 70)]
        for col, txt, w in headings:
            tree.heading(col, text=txt); tree.column(col, width=w, anchor="center" if col != "name" else "w")
        scrollbar.config(command=tree.yview)
        data = [            ("Granit (matériau de construction)", "Gamma/Bêta", "5", "45", "50"),
            ("Engrais potassique (potasse)", "Bêta", "0", "90", "10"),
            ("Ouraline (antiquité)", "Bêta/Gamma", "2", "83", "15"),
            ("Pechblende (minéral)", "Mix (série U)", "45", "40", "15"),
            ("Bananes (séchées)", "Bêta (K-40)", "0", "90", "10"),
            ("Manchons à incandescence (Th-ancien)", "Mix (série Th)", "30", "50", "20"),
            ("Cadran au radium (montre)", "Mix (série Ra)", "25", "55", "20"),
            ("Américium (détecteur de fumée)", "Alpha", "95", "1", "4"),
            ("Carreaux (glaçure à l'uranium)", "Bêta", "10", "75", "15"),
            ("Peinture lumineuse au tritium", "Bêta (mou)", "0", "100", "0"),
            ("Électrodes de soudage (rouge)", "Alpha/Bêta", "40", "50", "10"),
            ("Lentille de rechange (verre au Th)", "Bêta/Gamma", "5", "60", "35"),
            ("Champignons (séchés)", "Bêta (Cs-137)", "0", "90", "10"),
            ("Basalte (roche)", "Gamma/Bêta", "2", "48", "50"),
            ("Sable monazite", "Alpha/Bêta", "45", "40", "15"),
            ("Sable de zircon", "Alpha/Bêta", "30", "50", "20"),
            ("Manchons à gaz (moderne)", "Bêta dominant", "5", "85", "10"),
            ("Quartz fumé", "Gamma", "0", "10", "90"),
            ("Céramique antique (rouge)", "Bêta", "10", "70", "20"),
            ("Autunite (minéral)", "Alpha/Bêta", "50", "40", "10"),
            ("Euclase (minéral)", "Gamma", "0", "20", "80"),
            ("Torbernite (minéral)", "Alpha/Bêta", "45", "45", "10"),
            ("Levure chimique à la potasse", "Bêta", "0", "90", "10"),
            ("Sel de déneigement (chlorure de potassium)", "Bêta", "0", "92", "8"),
            ("Brique silico-calcaire", "Gamma", "2", "28", "70"),
            ("Iode-131 médical", "Gamma", "0", "10", "90"),
            ("Technétium-99m (médecine)", "Gamma", "0", "1", "99"),
            ("Thorianite (minéral)", "Alpha dominant", "60", "30", "10"),
            ("Béryl (minéral)", "Gamma", "0", "15", "85"),
            ("Schiste (Eifel/Hunsrück)", "Bêta/Gamma", "5", "55", "40"),
            ("Schiste argileux", "Gamma dominant", "3", "37", "60"),
            ("Brique (rouge)", "Bêta/Gamma", "4", "46", "50"),
            ("Noix du Brésil (cendres)", "Alpha/Bêta", "30", "60", "10"),
            ("Cendres de tabac", "Alpha (Po-210)", "40", "50", "10"),
            ("Béton (bâtiment ancien)", "Gamma", "5", "45", "50"),
            ("Plâtre (industriel)", "Bêta/Gamma", "2", "58", "40"),
            ("Nitrate d'uranyle (labo)", "Alpha/Bêta", "40", "50", "10"),
            ("Carnotite (minerai)", "Mix", "40", "45", "15"),
            ("Mica (fuchsite)", "Bêta", "0", "85", "15"),
            ("Feldspath (minéral)", "Bêta/Gamma", "0", "80", "20"),
            ("Boussole lumineuse (ancienne)", "Alpha/Bêta", "30", "50", "20"),
            ("Sel de potassium (alimentaire)", "Bêta", "0", "90", "10"),
            ("Pavé de granit", "Gamma", "5", "40", "55"),
            ("Cendres de charbon", "Bêta/Gamma", "10", "60", "30"),
            ("Électrode de tungstène (Th)", "Alpha/Bêta", "40", "50", "10"),
            ("Cobalt-60 (industrie)", "Gamma", "0", "5", "95"),
            ("Césium-137 (retombées)", "Bêta/Gamma", "0", "70", "30"),
            ("Samarskite (minéral)", "Alpha dominant", "50", "40", "10"),
            ("Uraninite (minerai)", "Alpha/Bêta", "45", "45", "10"),
            ("Lutécium (minéral)", "Bêta/Gamma", "0", "70", "30")]
        for item in data: tree.insert("", "end", values=item)
        tree.pack(fill="both", expand=True)

    def run_nuklid_exe(self):
        try: subprocess.Popen(["Nukliddaten.exe"])
        except: messagebox.showerror("Erreur", "Le fichier Nukliddaten.exe n'a pas été trouvé dans le répertoire du programme.")

    def show_anleitung(self):
        win = Toplevel(self.root)
        win.title("Instructions et informations")
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
        anleitung_text = """Ce programme est mis à disposition en tant que freeware non commercial. D'autres utilisations peuvent être acquises selon les conditions mentionnées ci-dessous.

MODE D'EMPLOI

La mise en service s'effectue par l'ajustement du niveau du signal. Le périphérique d'enregistrement standard sous Windows est automatiquement utilisé comme signal d'entrée. Ainsi, un micro placé sur le klinker (émetteur de signal acoustique ou sortie d'impulsion) de n'importe quel compteur Geiger peut être utilisé comme source d'entrée dans un environnement calme. Si le compteur Geiger n'a pas de klinker, les valeurs du temps de mesure et des désintégrations peuvent également être saisies manuellement (mode manuel).

Δ Sonde: La sensibilité spécifique de la sonde utilisée (valeur CPM pour 1 µSv/h).
Δ efficacité α de la sonde: permet de régler l'efficacité spécifique (sensibilité) pour les nucléides alpha.
Ces valeurs sont tirées des descriptions techniques ou des documents de la sonde elle-même et sont cruciales pour la mesure. Les valeurs de certaines sondes courantes sont indiquées plus bas.

Δ filtre αβ (alu.): L'épaisseur en mm du filtre en aluminium ou du blindage en aluminium avec lequel on bloque les particules bêta lors de la mesure gamma pour différencier cette mesure. En effet, la part de rayonnement gamma également absorbée et la perméabilité aux particules bêta sont également calculées avec précision par le programme.

Signal d'entrée audio: Si le périphérique d'enregistrement est actif et prêt, la LED d'état verte s'allume. Chaque signal audio interprété comme une désintégration est indiqué par l'allumage de la LED d'état rouge. Ici, il est important de régler la sensibilité du niveau de sorte qu'un seul clic déclenche la LED rouge, mais que chaque clic soit comptabilisé.

Réglage du temps de blocage: Cette valeur définit le temps de blocage en millisecondes qui est attendu après une impulsion détectée afin d'éviter les doubles comptages dus aux oscillations du signal et garantir ainsi un résultat de mesure propre. Si un clic est compté deux fois ou plus, le temps de blocage doit être augmenté. Par défaut, il est de 50 ms, ce qui est suffisant pour les objets faiblement à moyennement radioactifs.
Niveaux recommandés:
Dose faible (< 5 µSv/h): 30–50 ms.
Dose moyenne (5–50 µSv/h): Réduire progressivement à 10–15 ms pour réduire la perte de comptage (temps mort).
Dose élevée (> 100 µSv/h): Aller au minimum absolu du matériel (souvent 1–5 ms).

Signification des affichages
Temps (s): Durée de la mesure actuelle en secondes.
Coups: Nombre d'impulsions détectées depuis le début de la mesure.
CPM: Impulsions par minute (Counts Per Minute) comme mesure de l'intensité.
%: Part en pourcentage de chaque type de rayonnement dans la quantité brute totale.
Sv/h / Gy/h: Débit de dose calculé du groupe de mesure basé sur le calibrage de la sonde.
Sv/h / Gy/h (orange): Débit de dose calculé et différencié du rayonnement individuel basé sur le calibrage de la sonde.

MODE
Mode manuel: Une fois sélectionné, les valeurs du temps de mesure (toujours en secondes) et des désintégrations peuvent être saisies manuellement. Cela est utile s'il n'y a aucune possibilité d'enregistrer le klinker via l'ordinateur (par exemple, absence de klinker, d'entrée audio ou de micro) ou pour vérifier des mesures déjà effectuées. Après avoir saisi les chiffres, on les confirme avec RÉINIT. (SET). Le calcul global et la pondération s'effectuent après avoir sélectionné RÉINIT. dans la zone Rayonnement Gamma.
Mode mesure: Une fois sélectionné, une mesure peut être lancée avec DÉMARRER, mise en pause avec PAUSE et terminée avec ARRÊTER. Après ARRÊTER, la mesure peut être poursuivie via DÉMARRER. L'ordre logique est: EDMA (ODL), Alpha, Bêta, Gamma. En cas de doute, l'une de ces mesures individuelles peut être répétée. Le calcul global et la pondération s'effectuent après ARRÊTER dans la zone Rayonnement Gamma.
Un fond gris sur une zone signale une mesure active et en cours. Si elle clignote en gris, la mesure est en pause.

PROTOCOLE

Nouveau log: Le bouton Nouveau log (nouveau registre) efface toutes les valeurs.
Imprimer le log: Ce bouton ouvre une fenêtre de dialogue. Dans cette zone, des métadonnées supplémentaires sur la mesure sont saisies. Seules les valeurs renseignées sont reprises dans le protocole. Après confirmation, un fichier texte formaté est généré et affiché après enregistrement. Ce document contient, outre les saisies de l'utilisateur, toutes les valeurs mesurées déterminées, la répartition statistique des types de rayonnements ainsi que le facteur de comparaison avec le rayonnement de fond (EDMA) ainsi que les valeurs Δ de la sonde et du filtre.

BIBLIOTHÈQUE D'ISOTOPES

Affiche une liste des 50 isotopes radioactifs les plus fréquents. Cela peut aider à identifier l'isotope à l'aide des types de rayonnements. Cette liste n'est pas contractuelle, mais doit être considérée comme un outil de probabilité. Les valeurs indiquées sont certes cohérentes, mais la distinction dépend de la précision statistique (durée de mesure) et de la sensibilité énergétique de l'appareil de mesure. Certaines substances ont un profil très facile à distinguer car elles rayonnent fortement (par ex. Technétium-99m), d'autres sont faiblement radioactives et ont des profils très similaires (par ex. bananes et sel de déneigement) ; la liste affichant les isotopes les plus rares vers le bas, les substances listées plus haut sont à considérer comme plus probables en cas de profils identiques.

DONNÉES DES NUCLÉIDES

Ouvre un programme externe et très utile nommé Nukliddaten.exe, qui sert d'ouvrage de référence physique à ce programme pour attribuer les types de rayonnements mesurés (Alpha, Bêta, Gamma) à un élément chimique exact en comparant les énergies de désintégration et les demi-vies. Le bouton ouvre Nukliddaten.exe qui doit se trouver dans le dossier du programme. Ce programme nécessite le dossier Data pour l'affichage du contenu. Si nécessaire, un autre programme peut être inséré dans le dossier du programme pour être ouvert avec ce bouton. La condition est qu'il s'appelle Nukliddaten.exe et se trouve dans le même dossier que Messreihe.exe.

MANUEL UTILISATEUR

Ouvre le mode d'emploi qui contient entre autres des infos sur les types de rayonnements, les données des sondes et la logique de calcul.

P.1 / P.2 / P.3

Sont des boutons de préréglage permettant d'enregistrer toutes les valeurs saisies sur le côté droit du programme en tant que préréglages (maintenir > 3 secondes) ou de les charger (clic simple).

-----------------------------------

SÉQUENCE DE MESURE

Le processus de mesure est effectué dans un ordre fixe :

EDMA (Σ): Le rayonnement de fond est mesuré pour déterminer la référence zéro.
Alpha (α): La mesure s'effectue sans filtre directement sur l'objet à mesurer.
Bêta (β): La mesure est effectuée en utilisant un filtre.
Gamma (γ): En indiquant l'épaisseur du filtre en aluminium (boîte Δ filtre αβ), la part de haute énergie est déterminée.

Plus la mesure est longue, plus elle est précise. Cela vaut particulièrement pour les substances faiblement radioactives et la mesure des particules alpha.

ATTENTION (α)

Toutes les sondes ne détectent pas les nucléides alpha ! Si celle-ci ne peut pas détecter les nucléides alpha ou les détermine de manière peu fiable, il faut appuyer directement sur ARRÊTER dans la section Nucléides Alpha après la mesure EDMA et mentionner cela, le cas échéant, dans le protocole de mesure.

SONDES

Sensibilité de la sonde et détermination
La sensibilité d'une sonde de mesure s'entend comme le rapport entre le taux d'impulsions détecté (Counts Per Minute - CPM) et le débit de dose réellement présent en microsieverts par heure (µSv/h). La détermination de cette valeur s'effectue habituellement via la fiche technique du fabricant ou par comparaison avec un appareil de mesure de référence calibré avec une source de rayonnement connue (par ex. Cs-137). Une valeur de 1000 CPM ≙ 1 µSv/h signifie par exemple que pour une exposition d'un microsievert par heure, exactement mille impulsions par minute doivent être enregistrées par le logiciel.

Pour les valeurs standards typiques des tubes compteurs courants, les valeurs d'orientation suivantes pour 1 µSv/h sont souvent utilisées, pour lesquelles il faut tenir compte d'un autre facteur de correction lors de la mesure alpha en raison de l'efficacité de détection alpha :

Si8B: 550 CPM (35% efficacité alpha)
LND-712 (Gammascout): 108 CPM (10% efficacité alpha)
LND-7121: 150 CPM (12% efficacité alpha)
LND-7311: 340 CPM (35% efficacité alpha)
LND-7317: 345 CPM (34% efficacité alpha) 
SBT-9: 77 CPM (5% efficacité alpha)
SBT-10: 2000 CPM (40% efficacité alpha)
SBT-11: 285 CPM (30% efficacité alpha)
SBT-11A: 300 CPM (30% efficacité alpha)
Valvo ZP1401: 120 CPM (15% efficacité alpha)

Les tubes compteurs suivants sont très répandus, mais sont imperméables aux nucléides alpha et ne les détectent pas :

ZP1320 (Standard de l'armée): 53 CPM
SBM-20 / STS-5: 160 CPM
SI-29BG: 50 CPM
J305: 150 CPM
M4011: 145 CPM
SI-3BG: < 1 CPM
STS-6 (СТС-6): 460 CPM

REMARQUE POUR LES MESURES EXTÉRIEURES

Lors de mesures en plein air, il est recommandé de protéger le micro contre le vent et les bruits ambiants avec un morceau de mousse ou un chiffon. Cela évite les "désintégrations fantômes", car les bruits de vent pourraient être interprétés à tort par le programme comme des impulsions de clic.

-----------------------------------

TYPES DE RAYONNEMENTS

Alpha (α): Composé de noyaux d'hélium. Fort pouvoir ionisant avec une faible portée. Peut être arrêté par du papier.
Bêta (β): Composé d'électrons ou de positrons. Portée moyenne. Blindage possible par une feuille d'aluminium.
Gamma (γ): Ondes électromagnétiques (photons). Fort pouvoir de pénétration. Nécessite des matériaux denses comme le plomb pour le blindage.
Rayons X (x): Ondes électromagnétiques (photons) et physiquement très similaires au rayonnement gamma, c'est pourquoi la plupart des compteurs Geiger du commerce les détectent sans problème et les identifient comme rayonnement gamma.
Bêta (β+): Un proton se transforme en neutron. Ce processus se manifeste techniquement par le rayonnement gamma qui en résulte (rayonnement d'annihilation).
Rayonnement neutronique: Ne peut être détecté qu'indirectement en plaçant une couche de cadmium ou de bore devant la sonde et en mesurant le rayonnement gamma qui serait absent sans le filtre cadmium ou bore. Les neutrons réagissent avec ce matériau, ce qui produit du rayonnement gamma.
Rayonnement Epsilon (ϵ): Est le processus de capture électronique. Le noyau fils qui en résulte libère l'énergie excédentaire sous forme de rayons X et de rayons gamma.

ÉQUIVALENT DE DOSE AMBIANT (EDMA)

C'est le rayonnement de fond naturel provenant de 2 sources différentes:
Rayonnement tellurique: Provient de substances radioactives naturelles dans le sol (par ex. uranium, thorium et leurs produits de désintégration comme le radon). Les valeurs typiques sont d'environ 0,04 à 0,10 μSv/h (dépend fortement de la roche, plus élevé en Forêt-Noire que dans le Nord). À noter que l'EDMA peut également varier à l'intérieur d'une maison (par ex. à cause de matériaux de construction comme le granit ou le radon).
Rayonnement galactique (environ un quart de l'EDMA): Composé de particules de haute énergie provenant de l'espace (soleil et galaxies lointaines) qui frappent constamment l'atmosphère terrestre. Les valeurs typiques sont d'environ 0,03 μSv/h au niveau de la mer (doublent environ tous les 1 500 mètres d'altitude).

-----------------------------------

LOGIQUE DE CALCUL

La détermination des valeurs est basée sur la soustraction des valeurs de référence mesurées précédemment (mesure nette). Lors du calcul de la dose totale (Total αβγ), une pondération biologique est effectuée, dans laquelle les désintégrations alpha sont multipliées par le facteur 20. La correction des valeurs gamma s'effectue automatiquement en tenant compte de l'épaisseur du filtre réglée et du taux d'absorption correspondant.

Δ Sonde: Détermine la valeur Gy/Sv. Chaque sonde a une sensibilité spécifique quant au nombre de désintégrations qu'elle mesure pour un rayonnement de 1 µSv/h. Plus la sonde est sensible, plus elle détecte de désintégrations pour un même rayonnement.

Δ efficacité α: La perméabilité aux nucléides alpha (qui sont alors détectés comme désintégrations) diffère selon les sondes au niveau de la perméabilité de la fenêtre de la sonde. Alors que les tubes GM massifs en verre ou en métal ne laissent passer aucun nucléide alpha (efficacité = 0%), les membranes minces en mica en laissent passer un certain nombre. Le programme en tient compte et extrapole ainsi la valeur réelle approximative des nucléides alpha. Comme les nucléides alpha ont un impact 20 fois supérieur (= Sv), la part α (= Gy) est multipliée par vingt, ce qui est également pris en compte dans la dose totale (Total (α+β+γ)).

Δ filtre αβ (alu.): Le calcul du programme est tout à fait plausible pour un outil semi-professionnel, car le filtre alu bloque de manière fiable les rayonnements alpha et bêta, tandis que la correction mathématique compense la perte minimale de quanta gamma lors du passage à travers le matériau. La formule sous-jacente utilise la loi de Beer-Lambert, dans laquelle la valeur CPM mesurée est divisée par la fonction exponentielle issue du coefficient du matériau (μ) et de l'épaisseur du filtre (d), afin de reconstruire l'intensité initiale du rayonnement avant le filtre :

C[corr.] = C[mes.] ÷ e^-(µ × d) | d = Δ filtre αβ | µ = 0,0202

-----------------------------------

CRÉDITS & MENTIONS LÉGALES

Développeur: Mehmet S. Trojan, Tous droits réservés / Copyright 2026

Licence: Ce programme est mis à disposition en tant que freeware. L'utilisation est exclusivement limitée au cadre privé. Une utilisation commerciale n'est autorisée qu'après paiement d'une redevance correspondante. Conditions et modalités sur: m-trojan@mail.ru

Exclusion de responsabilité:
Aucune responsabilité n'est assumée pour l'exactitude des valeurs ou l'imprécision due à la technique utilisée (compteur Geiger, sonde, filtre, micro, ordinateur, etc.) ainsi que pour les dommages matériels ou corporels résultant de l'utilisation du logiciel ou de la manipulation de matériaux radioactifs.

Remarque sur les programmes externes:
La fonction Données des nucléides ouvre l'application externe Nukliddaten.exe. Il s'agit d'un logiciel tiers qui ne fait pas partie de ce pack logiciel et qui a été développé indépendamment. Le développeur de SérieMes n'assume aucune responsabilité quant aux contenus, fonctions ou à l'absence d'erreurs de ce logiciel externe. Le lien sert uniquement d'ouvrage de référence physique pratique pour l'utilisateur."""
        
        txt_win.insert("1.0", anleitung_text)
        txt_win.config(state="disabled")

    def show_print_window(self):
        win = Toplevel(self.root); win.title("Informations complémentaires"); win.geometry("400x450")
        flds = [("Examinateur :", ""), ("Compteur Geiger :", ""), ("Sonde :", ""), ("Objet de mesure :", ""), ("Matériau :", ""), ("Distance (cm) :", " cm"), ("Température (°C) :", " °C"), ("Humidité (%) :", " %")]
        ents = {}
        for f, unit in flds:
            fr = tk.Frame(win); fr.pack(fill="x", padx=10, pady=2)
            tk.Label(fr, text=f, width=18, anchor="w").pack(side="left")
            e = tk.Entry(fr); e.pack(side="right", expand=True, fill="x"); ents[f] = (e, unit)
        tk.Button(win, text="OK", command=lambda: self.generate_txt(ents, win)).pack(pady=20)

    def generate_txt(self, ents, win):
        path = filedialog.asksaveasfilename(defaultextension=".txt", initialfile=f"Protocole_{datetime.now().strftime('%d_%m_%Y')}.txt")
        if not path: return
        tot_str = self.lbl_total_val.cget("text"); odl_sv = self.v_lbls["odl"][4].cget("text")
        try:
            v_tot = float(tot_str.split(" ")[0].replace(",", "."))
            v_odl = float(odl_sv.split(" ")[0].replace(",", "."))
            factor = round(v_tot / v_odl, 1) if v_odl > 0 else 0.0
        except: factor = 0.0
        with open(path, "w", encoding="utf-8") as f:
            f.write("+++++ PROTOCOLE DE MESURE +++++\n\nSérie de mesures: Rayonnement Alpha, Bêta, Gamma\n\n")
            f.write(f"Date: {datetime.now().strftime('%d/%m/%Y')}\nHeure: {self.odl_start_time} à {self.gamma_stop_time}\n\nInformations complémentaires :\n")
            for k, (e, unit) in ents.items():
                val = e.get()
                if val: f.write(f"{k} {val}{unit}\n")
            f.write(f"\n+++++ RÉSULTAT +++++\n\nLe matériau mesuré présente une radioactivité de {tot_str} Sv/h.\nCela correspond à {str(factor).replace('.', ',')} fois le rayonnement de l'EDMA naturel.\n")
            f.write(f"\n+++++ DÉTAILS +++++\n\nÉquivalent de Dose Ambiant (EDMA) :\n{odl_sv} Sv/h\n{self.v_lbls['odl'][2].cget('text')} CPM ({self.v_lbls['odl'][1].cget('text')} coups en {self.v_lbls['odl'][0].cget('text')} secondes)\nPart de la mesure: {self.v_lbls['odl'][3].cget('text')} %\n")
            a_gy = self.v_lbls["alpha"][5].cget("text")
            try: a_sv_calc = self.format_val(float(a_gy.split(" ")[0].replace(",", ".")) * 20)
            except: a_sv_calc = "0,000 µ"
            f.write(f"\nNucléides Alpha (Désintégrations par noyaux d'hélium) :\n{a_gy} Gy/h (≙ {a_sv_calc} Sv/h)\n{self.v_lbls['alpha'][2].cget('text')} CPM ({self.v_lbls['alpha'][1].cget('text')} coups en {self.v_lbls['alpha'][0].cget('text')} secondes)\nPart de la mesure: {self.v_lbls['alpha'][3].cget('text')} % (incl. EDMA)\n")
            for k, n in [("beta", "Particules Bêta (Désintégrations par électrons ou positrons)"), ("gamma", "Rayonnement Gamma (Désintégrations par photons gamma)")]:
                f.write(f"\n{n} :\n{self.v_lbls[k][5].cget('text')} Gy/h (Pondération x1 pour Sievert)\n{self.v_lbls[k][2].cget('text')} CPM ({self.v_lbls[k][1].cget('text')} coups en {self.v_lbls[k][0].cget('text')} secondes)\nPart de la mesure: {self.v_lbls[k][3].cget('text')} % (incl. EDMA)\n")
            f.write(f"\n+++++ Δ Correction de sonde +++++\n\nΔ sonde: 1 µSv/h ≙ {self.cpm_pro_sv} CPM\n\nΔ efficacité α de la sonde: {self.alpha_eff} %\n\nΔ filtre αβ (Alu.): {str(round(self.filter_mm, 2)).replace('.', ',')} mm\n\n\n")
            f.write(f"{datetime.now().strftime('%d/%m/%Y')}, _________________________________\n\nRemarques :\n\n" + "_"*60 + "\n\n" + "_"*60 + "\n")
        win.destroy(); os.startfile(path)

    def calculate_results(self):
        mu, val_odl = 0.0202, self.data["odl"]["cpm"]
        val_a_n = max(0, self.data["alpha"]["cpm"] - self.data["beta"]["cpm"]) / (self.alpha_eff/100)
        val_b_n = max(0, self.data["beta"]["cpm"] - self.data["gamma"]["cpm"])
        val_g_n = max(0, self.data["gamma"]["cpm"] - val_odl) / math.exp(-mu * self.filter_mm)
        
        sum_abg = val_a_n + val_b_n + val_g_n
        if sum_abg > 0:
            for k, v in [("alpha", val_a_n), ("beta", val_b_n), ("gamma", val_g_n)]:
                self.v_lbls[k][3].config(text=f"{int((v/sum_abg)*100)}")
        
        sum_total = sum_abg + val_odl
        if sum_total > 0:
            self.v_lbls["odl"][3].config(text=f"{int((val_odl/sum_total)*100)}")

        self.v_lbls["alpha"][5].config(text=self.format_val(val_a_n / self.cpm_pro_sv))
        self.v_lbls["beta"][5].config(text=self.format_val(val_b_n / self.cpm_pro_sv))
        self.v_lbls["gamma"][5].config(text=self.format_val(val_g_n / self.cpm_pro_sv))
        self.lbl_total_val.config(text=self.format_val((val_a_n * 20 + val_b_n + val_g_n) / self.cpm_pro_sv))

    def update_loop(self):
        self.clock_lbl.config(text=datetime.now().strftime("%d/%m/%Y - %Hh%M:%S"))
        if not self.manual_mode:
            for k in self.keys:
                v = self.data[k]
                if v["run"] and not v["p"]: v["s"] += 1
                v["cpm"] = v["z"] / (v["s"] / 60) if v["s"] > 0 else 0
                self.v_lbls[k][0].config(text=str(v["s"])); self.v_lbls[k][1].config(text=str(v["z"]))
                self.v_lbls[k][2].config(text=str(int(v["cpm"]))); self.v_lbls[k][4].config(text=self.format_val(v["cpm"] / self.cpm_pro_sv))
            if not self.data["gamma"]["run"] and self.data["gamma"]["s"] > 0: self.calculate_results()
        self.root.after(1000, self.update_loop)

    def load_config(self):
        if os.path.exists("config.json"):
            try:
                with open("config.json", "r") as f:
                    cfg = json.load(f)
                    last = cfg.get("last", {})
                    if last: self.apply_cfg(last)
                    self.profiles = cfg.get("profiles", {})
            except: self.profiles = {}
        else: self.profiles = {}

    def save_config(self, profile_key="last"):
        current = {
            "cpm": self.cpm_pro_sv,
            "eff": self.alpha_eff,
            "fil": self.filter_mm,
            "sig": self.thresh_idx,
            "deb": self.debounce_ms
        }
        cfg = {"last": current, "profiles": self.profiles}
        if os.path.exists("config.json"):
            try:
                with open("config.json", "r") as f:
                    old_cfg = json.load(f)
                    cfg["profiles"] = old_cfg.get("profiles", self.profiles)
            except: pass
        
        if profile_key == "last": cfg["last"] = current
        else: cfg["profiles"][profile_key] = current
        
        with open("config.json", "w") as f:
            json.dump(cfg, f)
        self.profiles = cfg["profiles"]

    def apply_cfg(self, c):
        self.cpm_pro_sv = c.get("cpm", 1000)
        self.alpha_eff = c.get("eff", 40)
        self.filter_mm = c.get("fil", 0.50)
        self.thresh_idx = c.get("sig", 10)
        self.debounce_ms = c.get("deb", 50)
        try:
            self.res_sonde.config(text=str(self.cpm_pro_sv))
            self.res_eff.config(text=f"{self.alpha_eff} %")
            self.res_fil.config(text=f"{self.filter_mm:.2f} mm")
            self.lbl_p_val.config(text=f"{self.thresh_idx*5}%")
            self.res_deb.config(text=f"{self.debounce_ms} ms")
        except: pass

    def p_press(self, k):
        self.p_start = time.time()

    def p_release(self, k):
        if hasattr(self, "p_start"):
            if (time.time() - self.p_start) >= 3.0:
                self.save_config(k)
                messagebox.showinfo("OK", f"Paramètres enregistrés dans le preset {k}.")
            else:
                cfg = self.profiles.get(k)
                if cfg: self.apply_cfg(cfg)

    def add_tooltip(self, widget, text):
        def show(e):
            self.tip = tk.Toplevel(widget)
            self.tip.wm_overrideredirect(True)
            self.tip.wm_geometry(f"+{e.x_root+10}+{e.y_root+10}")
            tk.Label(self.tip, text=text, bg="#ff0", fg="#000", relief="solid", borderwidth=1, font=("Arial", 8)).pack()
        def hide(e):
            if hasattr(self, "tip"): self.tip.destroy()
        widget.bind("<Enter>", show)
        widget.bind("<Leave>", hide)

if __name__ == "__main__":
    root = tk.Tk(); app = MessreiheApp(root); root.mainloop()