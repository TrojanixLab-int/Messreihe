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
        self.root.title("MeasSeries - Radiation Survey Tool - M. Trojan")
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
        return f"{val:.3f} µ"

    def setup_ui(self):
        self.footer = tk.Frame(self.root, bg="#0a0a0a", bd=1, relief="raised")
        self.footer.pack(side="bottom", fill="x", ipady=5)
        self.btn_manual = tk.Button(self.footer, text="Manual Mode", bg="#222", fg=FG_W, font=("Arial", 9), padx=10, command=self.toggle_manual_mode)
        self.btn_manual.pack(side="left", padx=5, pady=5)
        tk.Button(self.footer, text="New Log", bg="#222", fg=FG_W, font=("Arial", 9), padx=10, command=self.neues_protokoll).pack(side="left", padx=5, pady=5)
        tk.Button(self.footer, text="Print Log", bg="#222", fg=FG_W, font=("Arial", 9), padx=10, command=self.show_print_window).pack(side="left", padx=5, pady=5)
        tk.Button(self.footer, text="Isotope Library", bg="#222", fg=FG_W, font=("Arial", 9), padx=10, command=self.open_isotopes_table).pack(side="left", padx=5, pady=5)
        tk.Button(self.footer, text="Nuclide Data", bg="#222", fg=FG_W, font=("Arial", 9), padx=10, command=self.run_nuklid_exe).pack(side="left", padx=5, pady=5)
        tk.Button(self.footer, text="Users Manual", bg="#222", fg=FG_W, font=("Arial", 9), padx=10, command=self.show_anleitung).pack(side="left", padx=5, pady=5)
        for p in ["P1", "P2", "P3"]:
            btn = tk.Button(self.footer, text=f"P.{p[1]}", bg="#ddd", fg=FG_B, font=("Arial", 9, "bold"), padx=10)
            btn.pack(side="left", padx=2, pady=5)
            btn.bind("<ButtonPress-1>", lambda e, x=p: self.p_press(x))
            btn.bind("<ButtonRelease-1>", lambda e, x=p: self.p_release(x))
            self.add_tooltip(btn, "Press long to save")

        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=20, pady=10)
        try:
            if os.path.exists("Messreihe.png"):
                self.logo_full = tk.PhotoImage(file="Messreihe.png")
                self.logo_img = self.logo_full.subsample(3, 3)
                tk.Label(header, image=self.logo_img, bg=BG).pack(side="left", padx=(0, 20))
        except: pass
        tk.Label(header, text="MeasSeries", fg=FG_W, bg=BG, font=("Arial", 60, "bold")).pack(side="left")
        self.clock_lbl = tk.Label(header, text="", fg=FG_B, bg=BG, font=("Arial", 30))
        self.clock_lbl.pack(side="left", padx=30)
        tot_f = tk.Frame(header, bg=BG)
        tot_f.pack(side="right")
        tk.Label(tot_f, text="Total (α+β+γ)", fg=FG_W, bg=BG).pack()
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
            ("odl", "ADER - Ambient Dose Equivalent Rate", "Σ", ["time (s)", "counts", "CPM", "% (Σαβγ)", "Sv/h (ADER)"]),
            ("alpha", "Alpha nuclides", "α", ["time (s)", "counts", "CPM", "% (αβγ)", "Gy/h (α+β+γ)", "Gy/h (α)"]),
            ("beta", "Beta particles", "β", ["time (s)", "counts", "CPM", "% (αβγ)", "Gy/h (β+γ)", "Gy/h (β)"]),
            ("gamma", "Gamma radiation", "γ", ["time (s)", "counts", "CPM", "% (αβγ)", "Gy/h ((β)+γ)", "Gy/h (γ)"])
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
            b_stopp = tk.Button(bf, text="STOP", width=8, command=lambda x=k: self.press_stopp(x))
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
                l = tk.Label(c, text="0" if i<4 else "0.000 µ", fg=col, bg=BG, font=("Arial", 30, "bold"))
                l.pack(side="bottom")
                tk.Label(c, text=units[i], fg=FG_GR, bg=BG, font=("Arial", 9)).pack(side="bottom")
                self.v_lbls[k].append(l)
            self.v_lbls["odl"][3].config(fg=FG_GR)
        self.setup_sidebar(right)

    def setup_sidebar(self, parent):
        configs = [("cpm", "Δ probe 1 µSv/h ≙", FG_B, 1), ("eff", "Δ α efficiency probe", FG_O, 1), ("fil", "Δ αβ filter (alloy)", FG_B, 0.05), ("sig", "audio input signal", FG_G, 1), ("deb", "debounce setting", FG_DG, 5)]
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
                pf = tk.Frame(fr, bg=BG); pf.pack(); tk.Label(pf, text="Level:", fg=col, bg=BG).pack(side="left")
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
        self.btn_manual.config(text="Meas. Mode" if self.manual_mode else "Manual Mode")
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
                if k == "odl": self.odl_start_time = "Manual"
                if k == "gamma": self.gamma_stop_time = "Manual"; self.calculate_results()
            except: messagebox.showerror("Error", "Please insert value.")
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
        if messagebox.askyesno("MeasSeries", "Delete all values and start a new measurement?"):
            for k in self.keys: self.press_reset(k)
            self.lbl_total_val.config(text="0.000 µ"); self.odl_start_time = "--:--:--"; self.gamma_stop_time = "--:--:--"

    def open_isotopes_table(self):
        win = tk.Toplevel(self.root); win.geometry("950x600"); win.title("Radioactive Isotope Reference"); win.configure(bg=BG)
        tk.Label(win, text="Isotope Fingerprints (Top 50 sorted by prevalence)", fg=FG_Y, bg=BG, font=("Arial", 20, "bold")).pack(pady=10)
        frame = tk.Frame(win, bg=BG); frame.pack(fill="both", expand=True, padx=20, pady=10)
        scrollbar = tk.Scrollbar(frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")
        style = ttk.Style(); style.theme_use("clam")
        style.configure("Treeview", background="#1a1a1a", foreground="white", fieldbackground="#1a1a1a", rowheight=25)
        style.configure("Treeview.Heading", background="#333", foreground="white", font=("Arial", 10, "bold"))
        tree = ttk.Treeview(frame, columns=("name", "dom", "alpha", "beta", "gamma"), show="headings")
        headings = [("name", "product / material", 300), ("dom", "dominance", 150), ("alpha", "α %", 70), ("beta", "β %", 70), ("gamma", "γ %", 70)]
        for col, txt, w in headings:
            tree.heading(col, text=txt); tree.column(col, width=w, anchor="center" if col != "name" else "w")
        scrollbar.config(command=tree.yview)
        data = [            ("Granite (Construction Material)", "Gamma/Beta", "5", "45", "50"),
            ("Potash Fertilizer", "Beta", "0", "90", "10"),
            ("Uranium Glass (Antique)", "Beta/Gamma", "2", "83", "15"),
            ("Pitchblende (Mineral)", "Mix (U-Series)", "45", "40", "15"),
            ("Bananas (Dried)", "Beta (K-40)", "0", "90", "10"),
            ("Gas Mantles (Thorium-old)", "Mix (Th-Series)", "30", "50", "20"),
            ("Radium Dial (Watch)", "Mix (Ra-Series)", "25", "55", "20"),
            ("Americium (Smoke Detector)", "Alpha", "95", "1", "4"),
            ("Tiles (Uranium Glaze)", "Beta", "10", "75", "15"),
            ("Tritium Luminous Paint", "Beta (soft)", "0", "100", "0"),
            ("Welding Electrodes (red)", "Alpha/Beta", "40", "50", "10"),
            ("Lens Replacement (Th-Glass)", "Beta/Gamma", "5", "60", "35"),
            ("Porcini Mushrooms (Dried)", "Beta (Cs-137)", "0", "90", "10"),
            ("Basalt (Rock)", "Gamma/Beta", "2", "48", "50"),
            ("Monazite Sand", "Alpha/Beta", "45", "40", "15"),
            ("Zircon Sand", "Alpha/Beta", "30", "50", "20"),
            ("Gas Mantles (modern)", "Beta dominant", "5", "85", "10"),
            ("Smoky Quartz", "Gamma", "0", "10", "90"),
            ("Antique Ceramics (red)", "Beta", "10", "70", "20"),
            ("Autunite (Mineral)", "Alpha/Beta", "50", "40", "10"),
            ("Euclase (Mineral)", "Gamma", "0", "20", "80"),
            ("Torbernite (Mineral)", "Alpha/Beta", "45", "45", "10"),
            ("Potash Baking Powder", "Beta", "0", "90", "10"),
            ("Road Salt (Potassium Chloride)", "Beta", "0", "92", "8"),
            ("Sand-lime Brick", "Gamma", "2", "28", "70"),
            ("Medical I-131", "Gamma", "0", "10", "90"),
            ("Technetium-99m (Medical)", "Gamma", "0", "1", "99"),
            ("Thorianite (Mineral)", "Alpha dominant", "60", "30", "10"),
            ("Beryl (Mineral)", "Gamma", "0", "15", "85"),
            ("Slate (Eifel/Hunsrück)", "Beta/Gamma", "5", "55", "40"),
            ("Shale", "Gamma dominant", "3", "37", "60"),
            ("Brick (red)", "Beta/Gamma", "4", "46", "50"),
            ("Brazil Nut (Ash)", "Alpha/Beta", "30", "60", "10"),
            ("Tobacco Ash", "Alpha (Po-210)", "40", "50", "10"),
            ("Concrete (Old Building)", "Gamma", "5", "45", "50"),
            ("Gypsum (Industrial)", "Beta/Gamma", "2", "58", "40"),
            ("Uranyl Nitrate (Lab)", "Alpha/Beta", "40", "50", "10"),
            ("Carnotite (Ore)", "Mix", "40", "45", "15"),
            ("Mica (Fuchsite)", "Beta", "0", "85", "15"),
            ("Feldspar (Mineral)", "Beta/Gamma", "0", "80", "20"),
            ("Luminous Compass (old)", "Alpha/Beta", "30", "50", "20"),
            ("K-Salt (Food Grade)", "Beta", "0", "90", "10"),
            ("Granite Cobblestone", "Gamma", "5", "40", "55"),
            ("Coal Ash", "Beta/Gamma", "10", "60", "30"),
            ("Tungsten Electrode (Th)", "Alpha/Beta", "40", "50", "10"),
            ("Cobalt-60 (Industrial)", "Gamma", "0", "5", "95"),
            ("Cesium-137 (Fallout)", "Beta/Gamma", "0", "70", "30"),
            ("Samarskite (Mineral)", "Alpha dominant", "50", "40", "10"),
            ("Uraninite (Ore)", "Alpha/Beta", "45", "45", "10"),
            ("Lutetium (Mineral)", "Beta/Gamma", "0", "70", "30")]
        for item in data: tree.insert("", "end", values=item)
        tree.pack(fill="both", expand=True)

    def run_nuklid_exe(self):
        try: subprocess.Popen(["Nukliddaten.exe"])
        except: messagebox.showerror("Error", "Nukliddaten.exe was not found in the path of the program.")

    def show_anleitung(self):
        win = Toplevel(self.root)
        win.title("Manual and informations")
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
        anleitung_text = """This program is provided as non-commercial freeware. Other uses can be acquired under the conditions mentioned below.

-----------------------------------

USERS MANUAL

Commissioning is performed by adjusting the signal level. The standard Windows recording device is automatically used as the audio input signal. Thus, a microphone at the clicker (acoustic signal generator or pulse output) of any Geiger counter in a quiet environment can be used as the input source. If the Geiger counter does not have a clicker, the values for measurement time and decays can also be entered manually (Manual Mode).

Δ probe: The specific sensitivity of the probe used (CPM value for 1 µSv/h). 
Δ α efficiency probe: Sets the specific efficiency (sensitivity) for Alpha nuclides. 
These values are taken from the technical descriptions or documentation of the probe itself and are crucial for the measurement. Below are the values for some common probes.

Δ αβ filter (alloy): The thickness in mm of the aluminum filter or aluminum shielding used to shield Beta particles during Gamma measurement and to differentiate this measurement. The program precisely calculates the Gamma components that are also shielded and the permeability for Beta particles.

audio input signal: If the recording device is active and ready, the green status LED lights up. Every audio signal counted as a decay is indicated by the red status LED. It is important to set the level sensitivity so that only a click triggers the red LED, but every click is counted.

debounce setting: This value defines the lockout time in milliseconds that is waited after a detected pulse to prevent multiple counts due to signal oscillations, ensuring a clean measurement result. If a click is counted twice or multiple times, the lockout time must be increased. The default is 50 ms, which is sufficient for low to medium radioactive objects.
Recommended levels:
    Low dose (< 5 µSv/h): 30–50 ms. 
    Medium dose (5–50 µSv/h): Gradually reduce to 10–15 ms to reduce count loss (dead time).
    High dose (> 100 µSv/h): Go to the hardware's absolute minimum (often 1–5 ms).

Meaning of Displays
    Time (s): Duration of the current measurement in seconds.
    counts: Number of detected pulses since the start of measurement.
    CPM: Counts Per Minute as a measure of intensity.
    %: Percentage share of the respective radiation type in the gross total.
    Sv/h / Gy/h: Calculated dose rate of the measurement group based on probe calibration.
    Sv/h / Gy/h (orange): Calculated and differentiated dose rate of individual radiation based on probe calibration.

MODE
Manual Mode: When selected, the values for measurement time (always in seconds) and counts can be entered manually. This is useful if it is not possible to record the clicker via computer (e.g., missing clicker, missing audio input, or microphone) or to check previous measurements. After entering the numbers, confirm them with SET. The total calculation and weighting occur after selecting SET in the Gamma radiation section.
Meas. Mode: When selected, a measurement can be started with START, paused with PAUSE, and finished with STOP. After STOP, measurement can continue using START. The recommended sequence is: ADER, Alpha, Beta, Gamma. Any of these individual measurements can be repeated if in doubt. The total calculation and weighting occur after STOP in the Gamma radiation section.
A gray background in a section signals an active and running measurement. If it flashes gray, the measurement is paused.

LOGGING

New Log: The New Log button clears all values. 
Print Log: This button opens a dialog window. In this area, additional metadata for the measurement is recorded. Only entered values are included in the log. After confirmation, a formatted text file is generated and displayed after saving. This document contains user entries, all determined measurement values, the statistical distribution of radiation types, the comparison factor to background radiation (ADER), as well as the Δ values of the probe and filter.

ISOTOPE LIBRARY

Opens a list of the 50 most common radioactive isotopes. This can help identify the isotope based on the radiation types. This list is not binding but should be seen as a tool for probability. The values provided are consistent, but the differentiation depends on the statistical accuracy (measurement duration) and the energy sensitivity of the measuring device. Some substances have a very distinct profile because they radiate strongly and differ significantly from others (e.g., Technetium-99m), while others radiate weakly and have very similar profiles (e.g., bananas and road salt), with the list showing rarer isotopes further down, making higher-listed substances more likely in case of identical profiles.

NUCLIDE DATA

Opens an external and very useful program called Nukliddaten.exe, which serves as a physical reference work for this program to assign measured radiation types (Alpha, Beta, Gamma) to an exact chemical element by comparing decay energies and half-lives. The button opens Nukliddaten.exe, which must be in the program folder. This program requires the "Data" folder to display content. If necessary, another program can be inserted in the program folder to be opened with this button, provided it is named Nukliddaten.exe and is in the same folder as MeasSeries.exe.

Users Manual

Opens the manual, which contains information on radiation types, probe data, and calculation logic.

P.1 / P.2 / P.3

Are preset buttons used to save all parameter values entered on the right side of the program as presets (press > 3 seconds) or to load them (single click).

-----------------------------------

MEASUREMENT SEQUENCE

The measurement process is carried out in a fixed sequence:

    ADER (Σ): Background radiation is measured to determine the zero reference.
    Alpha (α): Measurement is taken without a filter directly at the test object.
    Beta (β): Measurement is carried out using a filter.
    Gamma (γ): The high-energy component is determined by specifying the aluminum filter thickness (box Δ αβ filter).
The longer the measurement, the more precise it is. This is especially true for low radioactive substances and Alpha nuclide measurements.

ATTENTION (α)

Not every probe detects Alpha nuclides! If the probe cannot detect Alpha nuclides or determines them unreliably, STOP must be pressed immediately in the Alpha nuclides section after the ADER measurement and noted in the log if necessary.

PROBES

Probe Sensitivity and Determination
The sensitivity of a probe is the ratio between the detected count rate (Counts Per Minute - CPM) and the actual dose rate in microsieverts per hour (µSv/h). This value is usually determined via the manufacturer's technical data sheet or by comparison with a calibrated reference device at a known radiation source (e.g., Cs-137). A value of 1000 CPM ≙ 1 µSv/h means, for example, that at a load of one microsievert per hour, exactly one thousand pulses per minute must be registered by the software.

Typical standard values for common GM tubes are often based on the following orientation values for 1 µSv/h, where an additional correction factor must be considered for Alpha measurement due to Alpha detection efficiency:

    Si8B: 550 CPM (35% Alpha efficiency)
    LND-712 (Gammascout): 108 CPM (10% Alpha efficiency)
    LND-7121: 150 CPM (12% Alpha efficiency)
    LND-7311: 340 CPM (35% Alpha efficiency)
    LND-7317: 345 CPM (34% Alpha efficiency) 
    SBT-9: 77 CPM (5% Alpha efficiency)
    SBT-10: 2000 CPM (40% Alpha efficiency)
    SBT-11: 285 CPM (30% Alpha efficiency)
    SBT-11A: 300 CPM (30% Alpha efficiency)
    Valvo ZP1401: 120 CPM (15% Alpha efficiency)

The following tubes are widely used but are impermeable to Alpha nuclides and do not detect them:

    ZP1320 (Bundeswehr standard): 53 CPM
    SBM-20 / STS-5: 160 CPM
    SI-29BG: 50 CPM
    J305: 150 CPM
    M4011: 145 CPM
    SI-3BG: <1 CPM
    STS-6 (СТС-6): 460 CPM

NOTE FOR OUTDOOR MEASUREMENTS

For outdoor measurements, it is recommended to shield the microphone with a piece of foam or a cloth against wind and ambient noise. This prevents so-called "ghost decays," as wind noise could be falsely interpreted by the program as click pulses.

-----------------------------------

RADIATION TYPES

    Alpha (α): Consists of helium nuclei. High ionization power with short range. Can be stopped by paper.
    Beta (β): Consists of electrons or positrons. Medium range. Shielding by aluminum sheet possible.
    Gamma (γ): Electromagnetic waves (photons). High penetration power. Requires dense materials like lead for shielding.
    X-ray (x): Electromagnetic waves (photons) and physically very similar to Gamma radiation, which is why most commercial Geiger counters detect and identify them as Gamma radiation without issues.
    Beta (β+): A proton turns into a neutron. This process manifests measurably through the resulting Gamma radiation (annihilation radiation).
    Neutron radiation: Can only be detected indirectly by placing a layer of cadmium or boron in front of the probe and measuring the Gamma radiation that would be absent without the cadmium or boron filter. Neutrons react with this material, producing Gamma radiation.
    Epsilon radiation (ϵ): The process of electron capture. The resulting daughter nucleus releases excess energy as X-ray and Gamma radiation.

AMBIENT DOSE EQUIVALENT RATE (ADER)

This is the natural background radiation from 2 different sources:
Terrestrial radiation: Originates from natural radioactive substances in the ground (e.g., Uranium, Thorium, and their decay products like Radon). Typical values are approx. 0.04 to 0.10 μSv/h (strongly dependent on rock type, higher in the Black Forest than in the north). Note that ADER can also fluctuate inside a house (e.g., due to building materials like granite or radon).
Galactic radiation (approx. one quarter of ADER): Consists of high-energy particles from space (sun and distant galaxies) constantly hitting the Earth's atmosphere. Typical values are approx. 0.03 μSv/h at sea level (doubles roughly every 1.500 meters of altitude).

-----------------------------------

CALCULATION LOGIC

The determination of values is based on the subtraction of previously measured reference values (Net Measurement). When calculating the total dose (Total (αβγ)), a biological weighting is applied, where Alpha decays are multiplied by a factor of 20. Gamma values are corrected automatically, taking into account the set filter thickness and the corresponding absorption rate.

Δ probe: Determines the Gy/Sv value. Each probe has a specific sensitivity regarding how many counts it measures at a radiation of 1 µSv/h. The more sensitive the probe, the more counts it detects at the same radiation level.

Δ α efficiency probe: The permeability for Alpha nuclides (which are then detected as counts) differs among probes based on the permeability of the probe window. While massive GM tubes made of glass or metal do not allow Alpha nuclides through (efficiency = 0%), thin mica membranes allow a certain number through. The program takes this into account and extrapolates the approximate real value of Alpha nuclides. Since Alpha nuclides have a 20-fold higher impact (= Sv), the α-component (= Gy) is increased twentyfold, which in turn is reflected in the total dose (Total (αβγ)).  

Δ αβ filter (alloy): The program calculation is absolutely plausible for a semi-professional tool, as the alloy filter reliably blocks Alpha and Beta radiation, while the mathematical correction compensates for the minimal loss of Gamma quanta when passing through the material. The underlying formula uses the Beer-Lambert law, where the measured CPM value is divided by the exponential function of the material coefficient (μ) and the filter thickness (d) to reconstruct the original radiation intensity before the filter:

C[Corr.] = C[Meas.] ÷ e^-(µ × d) | d = Δ αβ filter | µ = 0.0202

-----------------------------------

CREDITS & LEGAL NOTICES

Developer: Mehmet S. Trojan, Copyright 2026

License: This program is provided as freeware. Use is strictly limited to the private sector. Commercial use is only permitted after payment of a corresponding fee. Conditions and processing at: m-trojan@mail.ru

Disclaimer:
No liability is assumed for the accuracy of the values or inaccuracies due to the technology used (Geiger counter, probe, filter, microphone, computer, etc.), nor for property damage or personal injury resulting from the use of the software or the handling of radioactive materials.

Note on external programs:
The Nuclide Data function opens the external application Nukliddaten.exe. This is third-party software that is not part of this program package and was developed independently. The developer of MeasSeries assumes no responsibility for the content, functions, or correctness of this external software. The link serves only as a convenient physical reference for the user."""
        

        txt_win.insert("1.0", anleitung_text)
        txt_win.config(state="disabled")

    def show_print_window(self):
        win = Toplevel(self.root); win.title("Additional Information"); win.geometry("400x450")
        flds = [("Inspector / Operator:", ""), ("Geiger Counter:", ""), ("Measurement Probe:", ""), ("Test Object:", ""), ("Radiation Material:", ""), ("Distance (inch):", " in."), ("Room Temperature (°F):", " °F"), ("Humidity (%):", " %")]
        ents = {}
        for f, unit in flds:
            fr = tk.Frame(win); fr.pack(fill="x", padx=10, pady=2)
            tk.Label(fr, text=f, width=18, anchor="w").pack(side="left")
            e = tk.Entry(fr); e.pack(side="right", expand=True, fill="x"); ents[f] = (e, unit)
        tk.Button(win, text="OK", command=lambda: self.generate_txt(ents, win)).pack(pady=20)

    def generate_txt(self, ents, win):
        path = filedialog.asksaveasfilename(defaultextension=".txt", initialfile=f"Log_{datetime.now().strftime('%Y%m%d')}.txt")
        if not path: return
        tot_str = self.lbl_total_val.cget("text"); odl_sv = self.v_lbls["odl"][4].cget("text")
        try:
            v_tot = float(tot_str.split(" ")[0])
            v_odl = float(odl_sv.split(" ")[0])
            factor = round(v_tot / v_odl, 1) if v_odl > 0 else 0.0
        except: factor = 0.0
        with open(path, "w", encoding="utf-8") as f:
            f.write("+++++ MEASUREMENT LOG +++++\n\nMeasSeries: Alpha, Beta, Gamma Radiation\n\n")
            f.write(f"Date: {datetime.now().strftime('%Y-%m-%d')}\nTime: {self.odl_start_time} to {self.gamma_stop_time}\n\nAdditional Information:\n")
            for k, (e, unit) in ents.items():
                val = e.get()
                if val: f.write(f"{k} {val}{unit}\n")
            f.write(f"\n+++++ RESULT +++++\n\nThe measured material shows a radioactivity of {tot_str} Sv/h.\nThis corresponds to {str(factor)} times the radiation of the natural ADER.\n")
            f.write(f"\n+++++ DETAILS +++++\n\nAmbient Dose Equivalent Rate (Background):\n{odl_sv} Sv/h\n{self.v_lbls['odl'][2].cget('text')} CPM ({self.v_lbls['odl'][1].cget('text')} decays in {self.v_lbls['odl'][0].cget('text')} seconds)\nMeasurement share: {self.v_lbls['odl'][3].cget('text')} %\n")
            a_gy = self.v_lbls["alpha"][5].cget("text")
            try: a_sv_calc = self.format_val(float(a_gy.split(" ")[0]) * 20)
            except: a_sv_calc = "0.000 µ"
            f.write(f"\nAlpha nuclides (Decays by helium nuclei):\n{a_gy} Gy/h (≙ {a_sv_calc} Sv/h)\n{self.v_lbls['alpha'][2].cget('text')} CPM ({self.v_lbls['alpha'][1].cget('text')} decays in {self.v_lbls['alpha'][0].cget('text')} seconds)\nMeasurement share: {self.v_lbls['alpha'][3].cget('text')} % (without ADER)\n")
            for k, n in [("beta", "Beta particles (Decays by electrons or positrons)"), ("gamma", "Gamma radiation (Decays by gamma photons)")]:
                f.write(f"\n{n}:\n{self.v_lbls[k][5].cget('text')} Gy/h (Weighting x1 for Sievert)\n{self.v_lbls[k][2].cget('text')} CPM ({self.v_lbls[k][1].cget('text')} decays in {self.v_lbls[k][0].cget('text')} seconds)\nMeasurement share: {self.v_lbls[k][3].cget('text')} % (without ADER)\n")
            f.write(f"\n+++++ Δ Probe Correction +++++\n\nΔ - Sensitivity: 1 µSv/h ≙ {self.cpm_pro_sv} CPM\n\nΔ - α efficiency probe: {self.alpha_eff} %\n\nΔ - αβ filter (alloy): {self.filter_mm:.2f} mm\n\n\n")
            f.write(f"{datetime.now().strftime('%Y-%m-%d')}, _________________________________\n\nNotes:\n\n" + "_"*60 + "\n\n" + "_"*60 + "\n")
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
        self.clock_lbl.config(text=datetime.now().strftime("%Y-%m-%d - %H:%M:%S"))
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
                messagebox.showinfo("OK", f"Parameters in preset {k} saved.")
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