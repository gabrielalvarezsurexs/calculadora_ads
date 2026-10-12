"""Ventana del nodo: el control de conexiones activas y el tráfico en vivo.

Muestra lo que pide el §10.1 (qué entidades están conectadas y de qué tipo) y lo
que pide el §11 (qué se reenvió, qué se descartó como duplicado y dónde se agotó
el TTL). El núcleo corre en sus hilos y solo empuja eventos a una cola; esta
ventana la vacía cada 100 ms desde el hilo de Tkinter.
"""

import queue
import time
import tkinter as tk
from tkinter import ttk

from comun import config, huella

MAX_FILAS = 500
COLORES = {
    "FWD": "#0b6e99", "DUP": "#a15c00", "TTL": "#8a6d00", "DROP": "#b00020",
    "CONEXION": "#1b7f3a", "DESCONEXION": "#8e2c8e", "LENTO": "#b00020",
    "DUPLICADO": "#777777",
}
_TIPOS = {"INTERFAZ": "GUI", "SERVIDOR": "servidor", "SONDA": "sonda"}


def _hora(t: float) -> str:
    return time.strftime("%H:%M:%S", time.localtime(t))


class VentanaNodo:
    def __init__(self, nodo, geometria: str | None = None):
        self.nodo = nodo
        self.raiz = tk.Tk()
        self.raiz.title(f"{nodo.nombre} · Campo de Datos")
        self.raiz.geometry(geometria or "720x450")
        self.raiz.minsize(600, 380)
        self.raiz.protocol("WM_DELETE_WINDOW", self._cerrar)
        self._ocultar_latidos = tk.BooleanVar(value=True)
        self._pausar = tk.BooleanVar(value=False)
        self._construir()
        self._refrescar_tablas()

    # ------------------------------------------------------------ construcción

    def _construir(self) -> None:
        estilo = ttk.Style(self.raiz)
        estilo.configure("Treeview", font=("Segoe UI", 9), rowheight=18)
        estilo.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))
        raiz = self.raiz
        raiz.columnconfigure(0, weight=1)
        raiz.rowconfigure(3, weight=1)

        tk.Label(raiz, anchor="w", font=("Segoe UI", 11, "bold"),
                 text=f"{self.nodo.nombre} · {huella.corto(self.nodo.hash)} · escucha "
                      f"{self.nodo.endpoint}").grid(row=0, column=0, sticky="ew", padx=8,
                                                    pady=(6, 0))
        self._lbl_contadores = tk.Label(raiz, anchor="w", font=("Segoe UI", 9), fg="#333")
        self._lbl_contadores.grid(row=1, column=0, sticky="ew", padx=8)

        tablas = tk.Frame(raiz)
        tablas.grid(row=2, column=0, sticky="nsew", padx=6, pady=(4, 2))
        tablas.columnconfigure(0, weight=1)
        tablas.columnconfigure(1, weight=1)
        self._lbl_vecinos = tk.Label(tablas, anchor="w", font=("Segoe UI", 9, "bold"))
        self._lbl_vecinos.grid(row=0, column=0, sticky="ew")
        self._lbl_celulas = tk.Label(tablas, anchor="w", font=("Segoe UI", 9, "bold"))
        self._lbl_celulas.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self._vecinos = self._tabla(tablas, [("nombre", 64), ("hash", 66), ("endpoint", 104),
                                             ("sentido", 62), ("desde", 58)], alto=5)
        self._vecinos.grid(row=1, column=0, sticky="nsew")
        self._celulas = self._tabla(tablas, [("tipo", 62), ("servicio", 56), ("nombre", 84),
                                             ("hash", 66), ("desde", 58)], alto=5)
        self._celulas.grid(row=1, column=1, sticky="nsew", padx=(6, 0))
        barra_c = ttk.Scrollbar(tablas, orient="vertical", command=self._celulas.yview)
        barra_c.grid(row=1, column=2, sticky="ns")
        self._celulas.configure(yscrollcommand=barra_c.set)

        trafico = tk.Frame(raiz)
        trafico.grid(row=3, column=0, sticky="nsew", padx=6, pady=(2, 6))
        trafico.columnconfigure(0, weight=1)
        trafico.rowconfigure(1, weight=1)
        barra = tk.Frame(trafico)
        barra.grid(row=0, column=0, columnspan=2, sticky="ew")
        tk.Label(barra, text="Tráfico", font=("Segoe UI", 9, "bold")).pack(side="left")
        ttk.Checkbutton(barra, text="pausar", variable=self._pausar).pack(side="right")
        ttk.Checkbutton(barra, text="ocultar latidos",
                        variable=self._ocultar_latidos).pack(side="right", padx=8)
        # Anchos para que quepan "DESCONEXION" y "SONDA_PRUEBA" a 720 px.
        self._trafico = self._tabla(trafico, [("hora", 58), ("evento", 96), ("código", 100),
                                              ("id", 62), ("origen", 66), ("de", 62),
                                              ("ruta", 92), ("destinos", 140)], alto=8)
        self._trafico.grid(row=1, column=0, sticky="nsew")
        barra_v = ttk.Scrollbar(trafico, orient="vertical", command=self._trafico.yview)
        barra_v.grid(row=1, column=1, sticky="ns")
        self._trafico.configure(yscrollcommand=barra_v.set)
        for evento, color in COLORES.items():
            self._trafico.tag_configure(evento, foreground=color)

    def _tabla(self, padre, columnas, alto: int) -> ttk.Treeview:
        tabla = ttk.Treeview(padre, columns=[c for c, _ in columnas], show="headings",
                             height=alto, selectmode="browse")
        for nombre, ancho in columnas:
            tabla.heading(nombre, text=nombre, anchor="w")
            tabla.column(nombre, width=ancho, minwidth=40, anchor="w", stretch=True)
        return tabla

    # ------------------------------------------------------------- eventos

    def ejecutar(self) -> None:
        self.raiz.after(100, self._vaciar_cola)
        self.raiz.after(500, self._refrescar_contadores)
        self.raiz.mainloop()

    def _vaciar_cola(self) -> None:
        filas, tablas = [], False
        cola = self.nodo.eventos
        if cola is not None:
            try:
                for _ in range(2000):  # tope por tick: la ventana nunca se congela
                    tipo, datos = cola.get_nowait()
                    if tipo == "tablas":
                        tablas = True
                    elif tipo == "trafico":
                        filas.append(datos)
            except queue.Empty:
                pass
        if tablas:
            self._refrescar_tablas()
        if filas and not self._pausar.get():
            self._agregar_trafico(filas)
        if self.nodo.activo:
            self.raiz.after(100, self._vaciar_cola)

    def _agregar_trafico(self, filas: list[dict]) -> None:
        ocultar = self._ocultar_latidos.get()
        insertadas = 0
        for f in filas:
            if ocultar and f.get("codigo") in config.CODIGOS_SILENCIOSOS:
                continue
            evento = f.get("evento", "?")
            valores = (f.get("hora", ""), evento, f.get("codigo", ""), f.get("id8", ""),
                       f.get("origen", ""), f.get("de", "") or "", f.get("ruta", ""),
                       f.get("destinos") or f.get("detalle", ""))
            self._trafico.insert("", "end", values=valores, tags=(evento,))
            insertadas += 1
        if not insertadas:
            return
        hijos = self._trafico.get_children()
        if len(hijos) > MAX_FILAS:
            self._trafico.delete(*hijos[:len(hijos) - MAX_FILAS])
        self._trafico.yview_moveto(1.0)

    def _refrescar_tablas(self) -> None:
        foto = self.nodo.instantanea()
        self._llenar(self._vecinos, [
            (v["nombre"], huella.corto(v["hash"]), v["endpoint"], v["sentido"], _hora(v["desde"]))
            for v in sorted(foto["vecinos"], key=lambda v: v["nombre"] or "")])
        celulas = sorted(foto["celulas"], key=lambda c: (c["entidad"] != "INTERFAZ",
                                                          c["servicio"] or "", c["nombre"] or ""))
        self._llenar(self._celulas, [
            (_TIPOS.get(c["entidad"], c["entidad"]), c["servicio"] or "—", c["nombre"],
             huella.corto(c["hash"]), _hora(c["desde"])) for c in celulas])
        guis = sum(1 for c in celulas if c["entidad"] == "INTERFAZ")
        servidores = sum(1 for c in celulas if c["entidad"] == "SERVIDOR")
        otras = len(celulas) - guis - servidores
        detalle = f"{guis} GUI + {servidores} servidores" + (f" + {otras} otra(s)" if otras else "")
        self._lbl_vecinos.config(text=f"Vecinos: {len(foto['vecinos'])}")
        self._lbl_celulas.config(text=f"Células: {len(celulas)} ({detalle})")

    @staticmethod
    def _llenar(tabla: ttk.Treeview, filas) -> None:
        tabla.delete(*tabla.get_children())
        for fila in filas:
            tabla.insert("", "end", values=fila)

    def _refrescar_contadores(self) -> None:
        foto = self.nodo.instantanea()
        c = foto["contadores"]
        self._lbl_contadores.config(
            text=f"recibidos {c['recibidos']} · reenviados {c['reenviados']} · "
                 f"duplicados descartados {c['duplicados']} · TTL agotado {c['ttl_agotado']} · "
                 f"descartados {c['descartados']} · ids en el registro temporal "
                 f"{foto['vistos']} ({config.VISTOS_VIGENCIA:g} s)")
        if self.nodo.activo:
            self.raiz.after(500, self._refrescar_contadores)

    def _cerrar(self) -> None:
        self.nodo.detener()  # cierra los sockets: los pares lo detectan
        self.raiz.destroy()
