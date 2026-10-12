"""Ventana del panel de despliegue. NO forma parte del sistema ADS.

Matriz nodo × tipo de célula para levantar y tumbar procesos, botón de
configuración mínima (4 nodos × 5 células), lista de procesos con su comando
exacto y la bitácora en vivo del proceso seleccionado.
"""

import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

from comun import codigos
from panel.procesos import COLUMNAS, GUI, NODO, Gestor, Proceso

RÓTULO = ("Herramienta de despliegue: no forma parte del sistema ADS; solo lanza procesos del "
          "sistema operativo. Todo se puede lanzar a mano.")
FILAS_MINIMAS = 4
VERDE, GRIS = "#1b7f3a", "#888888"
TITULOS = {NODO: "Nodo", GUI: "GUI", **{s: codigos.SIMBOLOS[s] for s in codigos.SERVICIOS}}


class VentanaPanel:
    def __init__(self, gestor: Gestor):
        self.gestor = gestor
        self.raiz = tk.Tk()
        self.raiz.title("Panel de despliegue · Calculadora ADS")
        self.ancho_pantalla = self.raiz.winfo_screenwidth()
        self.alto_pantalla = self.raiz.winfo_screenheight()
        self.raiz.geometry(f"780x640+{max(0, self.ancho_pantalla // 2 - 390)}+40")
        self.raiz.minsize(700, 560)
        self.raiz.protocol("WM_DELETE_WINDOW", self._cerrar)

        self._n_filas = FILAS_MINIMAS
        self._casillas: dict[tuple[int, str], tk.Label] = {}
        self._filas_construidas = 0
        self._iids: dict[int, str] = {}           # id(proceso) -> iid del Treeview
        self._por_iid: dict[str, Proceso] = {}
        self._visto: tuple[str | None, int] = (None, 0)  # (iid mostrado, líneas ya pintadas)
        self._retardo = tk.StringVar(value="0")
        self._construir()

    # ------------------------------------------------------------ construcción

    def _construir(self) -> None:
        r = self.raiz
        tk.Label(r, text=RÓTULO, anchor="w", justify="left", wraplength=740, fg="#555",
                 font=("Segoe UI", 9, "italic")).pack(fill="x", padx=10, pady=(8, 4))

        self._matriz = tk.Frame(r)
        self._matriz.pack(fill="x", padx=10)
        tk.Label(self._matriz, text="", width=7).grid(row=0, column=0)
        for j, col in enumerate(COLUMNAS, start=1):
            self._matriz.columnconfigure(j, weight=1, uniform="col")
            tk.Label(self._matriz, text=TITULOS[col], font=("Segoe UI", 10, "bold")).grid(
                row=0, column=j)
        self._asegurar_filas()

        botones = tk.Frame(r)
        botones.pack(fill="x", padx=10, pady=6)
        ttk.Button(botones, text="Levantar configuración mínima",
                   command=self._configuracion_minima).pack(side="left")
        ttk.Button(botones, text="+ Nodo", command=self._agregar_nodo).pack(side="left", padx=6)
        ttk.Button(botones, text="Detener todo", command=self._detener_todo).pack(side="left")
        tk.Spinbox(botones, from_=0, to=20000, increment=500, width=6,
                   textvariable=self._retardo).pack(side="right")
        tk.Label(botones, text="retardo ms de los servidores (▶):",
                 font=("Segoe UI", 9)).pack(side="right", padx=4)

        lista = tk.Frame(r)
        lista.pack(fill="both", expand=True, padx=10)
        lista.columnconfigure(0, weight=1)
        lista.rowconfigure(1, weight=1)
        cabecera = tk.Frame(lista)
        cabecera.grid(row=0, column=0, columnspan=2, sticky="ew")
        tk.Label(cabecera, text="Procesos", font=("Segoe UI", 9, "bold")).pack(side="left")
        ttk.Button(cabecera, text="Tumbar seleccionado",
                   command=self._tumbar_seleccionado).pack(side="right")
        columnas = [("nombre", 80), ("tipo", 55), ("nodo", 45), ("PID", 55), ("estado", 95),
                    ("comando", 420)]
        self._arbol = ttk.Treeview(lista, columns=[c for c, _ in columnas], show="headings",
                                   height=7, selectmode="browse")
        for nombre, ancho in columnas:
            self._arbol.heading(nombre, text=nombre, anchor="w")
            self._arbol.column(nombre, width=ancho, minwidth=40, anchor="w",
                               stretch=nombre == "comando")
        self._arbol.grid(row=1, column=0, sticky="nsew")
        barra = ttk.Scrollbar(lista, orient="vertical", command=self._arbol.yview)
        barra.grid(row=1, column=1, sticky="ns")
        self._arbol.configure(yscrollcommand=barra.set)
        self._arbol.tag_configure("muerto", foreground=GRIS)
        self._arbol.bind("<<TreeviewSelect>>", lambda e: self._pintar_bitacora(reiniciar=True))

        self._lbl_bitacora = tk.Label(r, text="Bitácora en vivo: (selecciona un proceso)",
                                      anchor="w", font=("Segoe UI", 9, "bold"))
        self._lbl_bitacora.pack(fill="x", padx=10, pady=(6, 0))
        self._txt = scrolledtext.ScrolledText(r, height=10, wrap="none", state="disabled",
                                              font=("Consolas", 8))
        self._txt.pack(fill="both", expand=True, padx=10, pady=(0, 8))

    def _asegurar_filas(self) -> None:
        objetivo = max(self._n_filas, *(self.gestor.filas() or [0]))
        while self._filas_construidas < objetivo:
            self._filas_construidas += 1
            k = self._filas_construidas
            tk.Label(self._matriz, text=f"Nodo {k}", font=("Segoe UI", 9, "bold"),
                     anchor="w").grid(row=k, column=0, sticky="w")
            for j, col in enumerate(COLUMNAS, start=1):
                celda = tk.Frame(self._matriz, bd=1, relief="groove")
                celda.grid(row=k, column=j, sticky="ew", padx=1, pady=1)
                lbl = tk.Label(celda, text="○ 0", fg=GRIS, width=4, font=("Segoe UI", 9))
                lbl.pack(side="left")
                tk.Button(celda, text="▶", width=2, relief="flat", fg=VERDE,
                          command=lambda k=k, c=col: self._levantar(k, c)).pack(side="left")
                tk.Button(celda, text="■", width=2, relief="flat", fg="#b00020",
                          command=lambda k=k, c=col: self._tumbar(k, c)).pack(side="left")
                self._casillas[(k, col)] = lbl

    # ------------------------------------------------------------- geometría

    def _geometria_nodo(self, k: int) -> str:
        w = min(720, (self.ancho_pantalla - 20) // 2)
        h = min(450, (self.alto_pantalla - 90) // 2)
        i = (k - 1) % 4
        extra = 30 * ((k - 1) // 4)
        return f"{w}x{h}+{(i % 2) * (w + 8) + extra}+{(i // 2) * (h + 36) + extra}"

    def _geometria_gui(self, k: int) -> str:
        w, h = 440, min(720, self.alto_pantalla - 120)
        i = (k - 1) % 4
        x = max(0, self.ancho_pantalla - w - 20 - 45 * (3 - i))
        return f"{w}x{h}+{x}+{10 + 30 * i}"

    # --------------------------------------------------------------- acciones

    def _levantar(self, k: int, col: str) -> None:
        if col == NODO:
            if self.gestor.vivos(k, NODO):
                messagebox.showinfo("Panel", f"El Nodo {k} ya está vivo (puerto ocupado).")
                return
            self.gestor.lanzar_nodo(k, geometria=self._geometria_nodo(k))
        elif col == GUI:
            self.gestor.lanzar_celula(k, GUI, geometria=self._geometria_gui(k))
        else:
            try:
                retardo = max(0, int(self._retardo.get()))
            except ValueError:
                retardo = 0
            self.gestor.lanzar_celula(k, col, retardo_ms=retardo)
        self._refrescar()

    def _tumbar(self, k: int, col: str) -> None:
        self.gestor.tumbar_reciente(k, col)
        self._refrescar()

    def _configuracion_minima(self) -> None:
        """Levanta solo lo que falte de 4 nodos × 5 células: primero los nodos y ~1 s
        después las células."""
        for k in range(1, FILAS_MINIMAS + 1):
            if not self.gestor.vivos(k, NODO):
                self.gestor.lanzar_nodo(k, geometria=self._geometria_nodo(k))
        self.raiz.after(1200, self._celulas_minimas)
        self._refrescar()

    def _celulas_minimas(self) -> None:
        for k in range(1, FILAS_MINIMAS + 1):
            for col in COLUMNAS[1:]:
                if not self.gestor.vivos(k, col):
                    geometria = self._geometria_gui(k) if col == GUI else None
                    self.gestor.lanzar_celula(k, col, geometria=geometria)
        self._refrescar()

    def _agregar_nodo(self) -> None:
        self._n_filas = max(self._n_filas, self._filas_construidas) + 1
        self._asegurar_filas()
        self._levantar(self._n_filas, NODO)

    def _detener_todo(self) -> None:
        self.gestor.detener_todo()
        self._refrescar()

    def _tumbar_seleccionado(self) -> None:
        sel = self._arbol.selection()
        if sel and sel[0] in self._por_iid:
            self.gestor.tumbar(self._por_iid[sel[0]])
            self._refrescar()

    # ------------------------------------------------------------- refresco

    def ejecutar(self) -> None:
        self.raiz.after(500, self._ciclo)
        self.raiz.mainloop()

    def _ciclo(self) -> None:
        self._refrescar()
        self.raiz.after(500, self._ciclo)

    def _refrescar(self) -> None:
        self._asegurar_filas()
        for (k, col), lbl in self._casillas.items():
            n = len(self.gestor.vivos(k, col))
            lbl.config(text=f"● {n}" if n else "○ 0", fg=VERDE if n else GRIS)
        for p in list(self.gestor.procesos):
            valores = (p.nombre, p.tipo, p.fila, p.pid, p.estado, p.comando_legible())
            etiqueta = () if p.vivo else ("muerto",)
            iid = self._iids.get(id(p))
            if iid is None:
                iid = self._arbol.insert("", "end", values=valores, tags=etiqueta)
                self._iids[id(p)] = iid
                self._por_iid[iid] = p
            else:
                self._arbol.item(iid, values=valores, tags=etiqueta)
        self._pintar_bitacora()

    def _pintar_bitacora(self, reiniciar: bool = False) -> None:
        sel = self._arbol.selection()
        if not sel or sel[0] not in self._por_iid:
            return
        iid = sel[0]
        p = self._por_iid[iid]
        mostrado, vistas = self._visto
        if reiniciar or mostrado != iid:
            vistas = None
        nuevas, total_lineas = p.lineas_desde(vistas)
        t = self._txt
        t.config(state="normal")
        if vistas is None:
            t.delete("1.0", "end")
            self._lbl_bitacora.config(text=f"Bitácora en vivo: {p.nombre} (PID {p.pid}) · "
                                           f"{p.comando_legible()}")
        if nuevas:
            abajo = t.yview()[1] > 0.98
            t.insert("end", "\n".join(nuevas) + "\n")
            total = int(t.index("end-1c").split(".")[0])
            if total > 2000:
                t.delete("1.0", f"{total - 2000}.0")
            if abajo or vistas is None:
                t.see("end")
        t.config(state="disabled")
        self._visto = (iid, total_lineas)

    def _cerrar(self) -> None:
        if self.gestor.vivos():
            r = messagebox.askyesnocancel(
                "Cerrar el panel",
                "¿Detener también todos los procesos?\n\n"
                "Sí: se detienen.\nNo: siguen vivos; su bitácora sigue en logs/.")
            if r is None:
                return
            if r:
                self.gestor.detener_todo()
        self.raiz.destroy()
