"""La calculadora: lo único que ve el usuario final.

Adaptado del primer parcial (teclado, display, atajos y el patrón cola +
``after(100)``), con ``±`` y ``⌫``. Lo nuevo es lo que hace visible el
protocolo: el estado de la conexión al Campo de Datos, la disponibilidad de cada
operación según los latidos (con su mínimo de acuses ajustable en vivo), la
lista de mis operaciones y el mini log de protocolo.

La red corre en hilos del núcleo y NO toca widgets: el núcleo empuja eventos a
una ``queue.Queue`` y esta ventana la vacía desde el hilo de Tkinter.
"""

import queue
import tkinter as tk
from tkinter import scrolledtext

from comun import codigos, formato, huella
from interfaz.nucleo import EN_VUELO, FALLIDA, MINIMO_RANGO

VERDE, AMBAR, ROJO, GRIS = "#1b7f3a", "#a15c00", "#b00020", "#666666"
TECLA_SERVICIO = {"+": "SUM", "-": "SUB", "*": "MUL", "/": "DIV"}
COLORES_LOG = {
    "SOLICITUD": "#0b6e99", "ACUSE": "#555555", "QUÓRUM": "#1b7f3a", "RESULTADO": "#1b7f3a",
    "REINTENTO": "#a15c00", "RETENIDA": "#a15c00", "FALLIDA": "#b00020",
    "DESHABILITADA": "#b00020", "HABILITADA": "#1b7f3a", "FAILOVER": "#8e2c8e",
    "DESCONEXION": "#8e2c8e", "DUPLICADA": "#a15c00", "TARDÍA": "#a15c00",
    "NO_DISPONIBLE": "#b00020", "CONEXION": "#1b7f3a",
}
MAX_LINEAS_LOG = 400
MAX_OPERACIONES = 60


class VentanaInterfaz:
    def __init__(self, interfaz, geometria: str | None = None):
        self.interfaz = interfaz
        self.raiz = tk.Tk()
        self.raiz.title(f"{interfaz.nombre} · Calculadora ADS")
        self.raiz.geometry(geometria or "440x720")
        self.raiz.minsize(400, 600)
        self.raiz.protocol("WM_DELETE_WINDOW", self._cerrar)

        # Captura "a op b", como una calculadora de verdad.
        self._acumulado = ""
        self._servicio: str | None = None
        self._entrada = "0"
        self._resultado_en_display = False  # el display muestra un resultado (para encadenar)
        self._mi_op: str | None = None      # operación en vuelo pedida desde esta ventana
        self._operaciones: dict[str, str] = {}  # id -> texto (en orden de llegada)

        self._botones_op: dict[str, tk.Button] = {}
        self._disp_widgets: dict[str, tuple] = {}
        self._construir()
        self._pintar_disponibilidad(self.interfaz.disponibilidad())

    # ------------------------------------------------------------ construcción

    def _construir(self) -> None:
        r = self.raiz
        self._lbl_conexion = tk.Label(r, anchor="w", font=("Segoe UI", 9), fg=AMBAR,
                                      text=f"● conectando a {self.interfaz.nodo_inicial}…")
        self._lbl_conexion.pack(fill="x", padx=10, pady=(6, 0))

        self._lbl_display = tk.Label(r, text="0", anchor="e", font=("Consolas", 24),
                                     bg="#101418", fg="#e8f0f2", padx=10, pady=6)
        self._lbl_display.pack(fill="x", padx=10, pady=(4, 0))
        self._lbl_estado = tk.Label(r, text="listo", anchor="e", fg=GRIS, font=("Segoe UI", 9))
        self._lbl_estado.pack(fill="x", padx=12)

        teclado = tk.Frame(r)
        teclado.pack(fill="x", padx=10, pady=(2, 4))
        filas = [["7", "8", "9", "/"], ["4", "5", "6", "*"], ["1", "2", "3", "-"],
                 ["0", ".", "±", "+"]]
        for i, fila in enumerate(filas):
            for j, tecla in enumerate(fila):
                teclado.columnconfigure(j, weight=1, uniform="tecla")
                servicio = TECLA_SERVICIO.get(tecla)
                texto = codigos.SIMBOLOS[servicio] if servicio else tecla
                b = tk.Button(teclado, text=texto, font=("Segoe UI", 13), height=1,
                              command=lambda t=tecla: self._tecla(t))
                b.grid(row=i, column=j, sticky="nsew", padx=2, pady=2)
                if servicio:
                    self._botones_op[servicio] = b
        tk.Button(teclado, text="C", font=("Segoe UI", 12),
                  command=lambda: self._tecla("C")).grid(row=4, column=0, sticky="nsew",
                                                         padx=2, pady=2)
        tk.Button(teclado, text="⌫", font=("Segoe UI", 12),
                  command=self._borrar_digito).grid(row=4, column=1, sticky="nsew", padx=2,
                                                    pady=2)
        self._btn_igual = tk.Button(teclado, text="=", font=("Segoe UI", 13, "bold"),
                                    bg="#1b6ec2", fg="white", activebackground="#155a9c",
                                    command=self._resolver)
        self._btn_igual.grid(row=4, column=2, columnspan=2, sticky="nsew", padx=2, pady=2)

        # Disponibilidad por latidos + mínimo de acuses por operación.
        disp = tk.LabelFrame(r, text="Disponibilidad (latidos)", font=("Segoe UI", 9, "bold"))
        disp.pack(fill="x", padx=10, pady=(2, 2))
        for i, s in enumerate(codigos.SERVICIOS):
            tk.Label(disp, text=f"{codigos.SIMBOLOS[s]}  {codigos.NOMBRES[s]}", anchor="w",
                     font=("Segoe UI", 9), width=16).grid(row=i, column=0, sticky="w", padx=4)
            vivas = tk.Label(disp, text="vivas: 0", anchor="w", font=("Segoe UI", 9), width=9)
            vivas.grid(row=i, column=1, sticky="w")
            tk.Label(disp, text="mín. acuses", font=("Segoe UI", 8), fg=GRIS).grid(
                row=i, column=2, sticky="e")
            var = tk.StringVar(value=str(self.interfaz.acuses_min[s]))
            caja = tk.Spinbox(disp, from_=MINIMO_RANGO[0], to=MINIMO_RANGO[1], width=3,
                              textvariable=var, font=("Segoe UI", 9),
                              command=lambda s=s: self._ajustar_minimo(s))
            caja.grid(row=i, column=3, padx=4, pady=1)
            caja.bind("<Return>", lambda e, s=s: self._ajustar_minimo(s))
            caja.bind("<FocusOut>", lambda e, s=s: self._ajustar_minimo(s))
            marca = tk.Label(disp, text="✗", font=("Segoe UI", 11, "bold"), fg=ROJO, width=2)
            marca.grid(row=i, column=4, padx=(0, 4))
            self._disp_widgets[s] = (vivas, var, marca)
        disp.columnconfigure(2, weight=1)

        tk.Label(r, text="Mis operaciones", anchor="w",
                 font=("Segoe UI", 9, "bold")).pack(fill="x", padx=12, pady=(4, 0))
        self._txt_ops = scrolledtext.ScrolledText(r, height=4, wrap="word", state="disabled",
                                                  font=("Consolas", 8))
        self._txt_ops.pack(fill="x", padx=10)
        self._txt_ops.tag_config("fallida", foreground=ROJO)
        self._txt_ops.tag_config("vuelo", foreground=AMBAR)

        tk.Label(r, text="Mini log de protocolo", anchor="w",
                 font=("Segoe UI", 9, "bold")).pack(fill="x", padx=12, pady=(4, 0))
        self._txt_log = scrolledtext.ScrolledText(r, height=8, wrap="word", state="disabled",
                                                  font=("Consolas", 8))
        self._txt_log.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        for evento, color in COLORES_LOG.items():
            self._txt_log.tag_config(evento, foreground=color)

        # El teclado físico también funciona.
        for tecla in "0123456789.+-*/":
            r.bind(tecla, lambda e: self._tecla_fisica(e))
        r.bind("<Return>", lambda e: self._resolver() if not self._en_spinbox(e) else None)
        r.bind("=", lambda e: self._resolver())
        r.bind("<Escape>", lambda e: self._tecla("C"))
        r.bind("<BackSpace>", lambda e: None if self._en_spinbox(e) else self._borrar_digito())

    @staticmethod
    def _en_spinbox(evento) -> bool:
        return isinstance(evento.widget, tk.Spinbox)

    def _editando_minimo(self) -> bool:
        try:
            return isinstance(self.raiz.focus_get(), tk.Spinbox)
        except (KeyError, tk.TclError):
            return False

    # ------------------------------------------------------------- captura

    def _tecla_fisica(self, evento) -> None:
        if not self._en_spinbox(evento):
            self._tecla(evento.char)

    def _tecla(self, tecla: str) -> None:
        nuevo_numero = self._resultado_en_display and (tecla.isdigit() or tecla == ".")
        self._resultado_en_display = False
        if nuevo_numero:  # tras un resultado, un dígito empieza otro número
            self._entrada = "0"
        if tecla == "C":
            self._acumulado, self._servicio, self._entrada = "", None, "0"
        elif tecla in TECLA_SERVICIO:
            servicio = TECLA_SERVICIO[tecla]
            if not self.interfaz.habilitadas[servicio]:
                self._decir(f"{servicio} no disponible", ROJO)
                return
            self._acumulado, self._servicio, self._entrada = self._entrada, servicio, "0"
        elif tecla == ".":
            if "." not in self._entrada:
                self._entrada += "."
        elif tecla == "±":
            if self._entrada not in ("0", "0."):
                self._entrada = (self._entrada[1:] if self._entrada.startswith("-")
                                 else "-" + self._entrada)
        elif tecla.isdigit():
            self._entrada = tecla if self._entrada in ("0", "ERROR") else self._entrada + tecla
        else:
            return
        self._refrescar_display()

    def _borrar_digito(self) -> None:
        self._entrada = self._entrada[:-1]
        if self._entrada in ("", "-"):
            self._entrada = "0"
        self._refrescar_display()

    def _refrescar_display(self) -> None:
        if self._servicio:
            texto = f"{self._acumulado} {codigos.SIMBOLOS[self._servicio]} {self._entrada}"
        else:
            texto = self._entrada
        self._lbl_display.config(text=texto)

    def _resolver(self) -> None:
        if self._mi_op is not None:
            self._decir("espera: hay una operación en vuelo", AMBAR)
            return
        if self._servicio is None:
            self._decir("escoge una operación primero", AMBAR)
            return
        try:
            a, b = float(self._acumulado), float(self._entrada)
        except ValueError:
            self._decir("números inválidos", ROJO)
            return
        id_op, texto = self.interfaz.solicitar(self._servicio, a, b)
        if id_op is None:
            self._decir(texto, ROJO)
            return
        self._mi_op = id_op
        self._btn_igual.config(state="disabled")
        self._decir(f"esperando acuses… (op {huella.corto(id_op)})", AMBAR)

    def _decir(self, texto: str, color: str = GRIS) -> None:
        self._lbl_estado.config(text=texto, fg=color)

    def _ajustar_minimo(self, servicio: str) -> None:
        _, var, _ = self._disp_widgets[servicio]
        try:
            pedido = int(var.get())
        except ValueError:
            pedido = self.interfaz.acuses_min[servicio]
        var.set(str(self.interfaz.ajustar_minimo(servicio, pedido)))

    # ------------------------------------------------------------- eventos

    def ejecutar(self) -> None:
        self.raiz.after(100, self._vaciar_cola)
        self.raiz.mainloop()

    def _vaciar_cola(self) -> None:
        lineas = []
        try:
            for _ in range(1000):
                tipo, datos = self.interfaz.eventos.get_nowait()
                if tipo == "log":
                    lineas.append(datos)
                elif tipo == "operacion":
                    self._pintar_operacion(datos)
                elif tipo == "disponibilidad":
                    self._pintar_disponibilidad(datos)
                elif tipo == "conexion":
                    self._pintar_conexion(datos)
        except queue.Empty:
            pass
        if lineas:
            self._agregar_log(lineas)
        if self.interfaz.activo:
            self.raiz.after(100, self._vaciar_cola)

    def _pintar_conexion(self, datos: dict) -> None:
        estado = datos.get("estado")
        if estado in ("conexion", "reconexion"):
            texto, color = f"● conectada a {datos['nodo']} ({datos['endpoint']})", VERDE
        elif estado == "failover":
            texto, color = f"● failover → {datos['nodo']} ({datos['endpoint']})", VERDE
        elif estado == "caida":
            texto, color = f"● se perdió {datos.get('nodo')}; buscando otro nodo…", AMBAR
        else:
            texto, color = "● sin Campo de Datos", ROJO
        self._lbl_conexion.config(text=texto, fg=color)

    def _pintar_disponibilidad(self, disp: dict) -> None:
        for s, d in disp.items():
            vivas, var, marca = self._disp_widgets[s]
            vivas.config(text=f"vivas: {d['vivas']}")
            if not self._editando_minimo():
                var.set(str(d["minimo"]))
            marca.config(text="✓" if d["habilitada"] else "✗",
                         fg=VERDE if d["habilitada"] else ROJO)
            self._botones_op[s].config(state="normal" if d["habilitada"] else "disabled")

    def _pintar_operacion(self, fila: dict) -> None:
        self._operaciones[fila["id"]] = fila
        while len(self._operaciones) > MAX_OPERACIONES:
            del self._operaciones[next(iter(self._operaciones))]
        self._txt_ops.config(state="normal")
        self._txt_ops.delete("1.0", "end")
        for f in self._operaciones.values():
            etiqueta = ("vuelo" if f["estado"] == EN_VUELO
                        else "fallida" if f["estado"] == FALLIDA else ())
            self._txt_ops.insert("end", f["texto"] + "\n", etiqueta)
        self._txt_ops.see("end")
        self._txt_ops.config(state="disabled")

        if fila["id"] != self._mi_op or fila["estado"] == EN_VUELO:
            if fila["id"] == self._mi_op:
                self._decir(f"intento {fila['intento']} · acuses {fila['acuses']}/"
                            f"{fila['minimo']}", AMBAR)
            return
        # Terminó mi operación: el resultado pasa al display para encadenar.
        self._mi_op = None
        self._btn_igual.config(state="normal")
        self._acumulado, self._servicio = "", None
        if fila["estado"] == FALLIDA:
            self._entrada = "0"
            self._lbl_display.config(text="ERROR")
            self._decir(f"FALLIDA: {fila['motivo']}", ROJO)
        elif fila["error"]:
            self._entrada = "0"
            self._lbl_display.config(text="ERROR")
            self._decir(fila["error"], ROJO)
        else:
            self._entrada = formato.numero(fila["resultado"])
            self._refrescar_display()
            self._resultado_en_display = True
            self._decir(f"{fila['rol']} {fila['respondio']} · acuses {fila['acuses']}/"
                        f"{fila['minimo']} · {fila['ms']} ms", VERDE)

    def _agregar_log(self, lineas) -> None:
        t = self._txt_log
        t.config(state="normal")
        for hora, evento, texto in lineas:
            t.insert("end", f"{hora[:8]} {evento} ", (evento,))
            t.insert("end", f"{texto}\n")
        total = int(t.index("end-1c").split(".")[0])
        if total > MAX_LINEAS_LOG:
            t.delete("1.0", f"{total - MAX_LINEAS_LOG}.0")
        t.see("end")
        t.config(state="disabled")

    def _cerrar(self) -> None:
        self.interfaz.detener()
        self.raiz.destroy()
