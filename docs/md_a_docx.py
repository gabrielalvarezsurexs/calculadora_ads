"""Convierte REPORTE_TECNICO.md a .docx con la librería estándar (sin pandoc).

Herramienta de documentación, fuera del sistema. Entiende el subconjunto de
Markdown que usa el reporte: encabezados (#, ##, ###, ####), párrafos, listas
con viñeta o numeradas (dos niveles), tablas, bloques de código, citas (>),
separadores (---), imágenes ![pie](ruta.png) en su propio renglón, y en línea
**negritas**, *cursivas*, `código` y [texto](liga).

    py docs/md_a_docx.py                       # REPORTE_TECNICO.md -> Reporte_Tecnico_Calculadora_ADS.docx
    py docs/md_a_docx.py entrada.md salida.docx

Cada "# PARTE ..." empieza en página nueva. Hoja carta, márgenes de 1".
"""

import re
import struct
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

RAIZ = Path(__file__).resolve().parent.parent
ANCHO_TEXTO = 9360        # dxa (1/20 pt): 8.5" - 2" de márgenes = 6.5"
EMU_POR_PX = 9525         # a 96 ppp
ANCHO_IMAGEN_MAX = 6.3 * 914400
ALTO_IMAGEN_MAX = 5.2 * 914400  # las ventanas de la GUI son altas
FUENTE, MONO = "Calibri", "Consolas"
AZUL = "1F3864"


def x(texto: str) -> str:
    return escape(texto, {'"': "&quot;"})


# ----------------------------------------------------------------- en línea

_EN_LINEA = re.compile(r"(`[^`]+`|\*\*.+?\*\*|(?<![\w*])\*(?!\s).+?(?<!\s)\*(?![\w*])|"
                       r"\[[^\]]+\]\([^)]+\))")


def corridas(texto: str, *, negrita=False, cursiva=False, tam=None, color=None) -> str:
    """Texto con formato en línea -> <w:r>..."""
    salida = []
    for parte in _EN_LINEA.split(texto):
        if not parte:
            continue
        if parte.startswith("`") and parte.endswith("`") and len(parte) > 1:
            salida.append(_corrida(parte[1:-1], negrita, cursiva, tam, color, mono=True))
        elif parte.startswith("**") and parte.endswith("**") and len(parte) > 4:
            salida.append(corridas(parte[2:-2], negrita=True, cursiva=cursiva, tam=tam,
                                   color=color))
        elif parte.startswith("*") and parte.endswith("*") and len(parte) > 2:
            salida.append(corridas(parte[1:-1], negrita=negrita, cursiva=True, tam=tam,
                                   color=color))
        elif parte.startswith("[") and "](" in parte:
            salida.append(corridas(parte[1:parte.index("](")], negrita=negrita,
                                   cursiva=cursiva, tam=tam, color=color))
        else:
            salida.append(_corrida(parte.replace("\\|", "|"), negrita, cursiva, tam, color))
    return "".join(salida)


def _corrida(texto, negrita, cursiva, tam, color, mono=False) -> str:
    props = []
    if mono:
        props.append(f'<w:rFonts w:ascii="{MONO}" w:hAnsi="{MONO}" w:cs="{MONO}"/>')
    if negrita:
        props.append("<w:b/>")
    if cursiva:
        props.append("<w:i/>")
    if color:
        props.append(f'<w:color w:val="{color}"/>')
    if mono:  # Consolas se ve más grande que Calibri al mismo tamaño
        tam = (tam or 22) - 2
    if tam:
        props.append(f'<w:sz w:val="{tam}"/><w:szCs w:val="{tam}"/>')
    rpr = f"<w:rPr>{''.join(props)}</w:rPr>" if props else ""
    return f'<w:r>{rpr}<w:t xml:space="preserve">{x(texto)}</w:t></w:r>'


def parrafo(contenido: str, *, estilo=None, extra="") -> str:
    ppr = ""
    if estilo or extra:
        ppr = f"<w:pPr>{f'<w:pStyle w:val=\"{estilo}\"/>' if estilo else ''}{extra}</w:pPr>"
    return f"<w:p>{ppr}{contenido}</w:p>"


# ----------------------------------------------------------------- bloques

class Documento:
    def __init__(self, base: Path):
        self.base = base
        self.cuerpo: list[str] = []
        self.imagenes: list[tuple[str, bytes]] = []
        self.listas_numeradas = 0
        self.primera_parte = True

    # --- encabezados y texto
    def encabezado(self, nivel: int, texto: str) -> None:
        extra = ""
        if nivel == 1:
            if not self.primera_parte:
                extra = "<w:pageBreakBefore/>"
            self.primera_parte = False
        self.cuerpo.append(parrafo(corridas(texto), estilo=f"Heading{nivel}", extra=extra))

    def titulo(self, texto: str) -> None:
        self.cuerpo.append(parrafo(corridas(texto), estilo="Title"))

    def texto(self, texto: str) -> None:
        self.cuerpo.append(parrafo(corridas(texto)))

    def cita(self, texto: str) -> None:
        self.cuerpo.append(parrafo(corridas(texto, cursiva=True), estilo="Cita"))

    def separador(self) -> None:
        self.cuerpo.append(parrafo("", extra='<w:pBdr><w:bottom w:val="single" w:sz="6" '
                                             'w:space="1" w:color="BFBFBF"/></w:pBdr>'))

    # --- listas
    def lista(self, items: list[tuple[int, bool, str]]) -> None:
        num_id = 1
        if items and items[0][1]:
            self.listas_numeradas += 1
            num_id = 1 + self.listas_numeradas  # cada lista numerada reinicia en 1
        for nivel, _, texto in items:
            extra = f'<w:numPr><w:ilvl w:val="{nivel}"/><w:numId w:val="{num_id}"/></w:numPr>'
            self.cuerpo.append(parrafo(corridas(texto), estilo="Lista", extra=extra))

    # --- código
    def codigo(self, lineas: list[str]) -> None:
        juntas = len(lineas) <= 40
        for i, linea in enumerate(lineas):
            extra = "<w:keepNext/>" if juntas and i < len(lineas) - 1 else ""
            run = (f'<w:r><w:t xml:space="preserve">{x(linea) if linea else ""}</w:t></w:r>')
            self.cuerpo.append(parrafo(run, estilo="Codigo", extra=extra))
        self.cuerpo.append(parrafo("", estilo="TrasCodigo"))

    # --- tablas
    def tabla(self, filas: list[list[str]]) -> None:
        n = max(len(f) for f in filas)
        filas = [f + [""] * (n - len(f)) for f in filas]
        if not any(c.strip() for c in filas[0]):
            filas = filas[1:]  # encabezado vacío (tabla de portada)
            sin_cabecera = True
        else:
            sin_cabecera = False
        tam = 18 if n >= 5 else 19
        anchos = self._anchos(filas, n, tam)
        self._tabla_xml(filas, anchos, tam, sin_cabecera)

    @staticmethod
    def _anchos(filas: list[list[str]], n: int, tam: int) -> list[int]:
        """Proporcional al contenido, pero ninguna columna más angosta que su palabra
        más larga (hasta un tope), para que nada como `<mm:ss>` se parta."""
        dxa_por_car = tam * 5.6  # ~0.56 em por carácter; tam en medios puntos
        pesos, minimos = [], []
        for j in range(n):
            textos = [re.sub(r"[`*]", "", f[j]).strip() for f in filas]
            pesos.append(min(max(max(len(t) for t in textos), 4), 60) ** 0.8)
            palabra = max((len(p) for t in textos for p in t.split()), default=1)
            minimos.append(min(int(palabra * dxa_por_car) + 200, 2600))
        anchos = [ANCHO_TEXTO * p / sum(pesos) for p in pesos]
        for _ in range(n):  # fija las que quedan cortas y reparte el resto entre las demás
            cortas = [j for j in range(n) if anchos[j] < minimos[j]]
            if not cortas:
                break
            fijo = sum(minimos[j] for j in cortas)
            libres = [j for j in range(n) if j not in cortas]
            resto = ANCHO_TEXTO - fijo
            peso_libre = sum(pesos[j] for j in libres) or 1
            for j in cortas:
                anchos[j] = minimos[j]
            for j in libres:
                anchos[j] = resto * pesos[j] / peso_libre
        anchos = [int(a) for a in anchos]
        anchos[-1] += ANCHO_TEXTO - sum(anchos)
        return anchos

    def _tabla_xml(self, filas, anchos, tam, sin_cabecera) -> None:
        xml = [('<w:tbl><w:tblPr><w:tblStyle w:val="Tabla"/>'
                f'<w:tblW w:w="{ANCHO_TEXTO}" w:type="dxa"/><w:tblLayout w:type="fixed"/>'
                '<w:tblLook w:val="04A0" w:firstRow="1" w:lastRow="0" w:firstColumn="0" '
                'w:lastColumn="0" w:noHBand="0" w:noVBand="1"/></w:tblPr><w:tblGrid>')]
        xml += [f'<w:gridCol w:w="{a}"/>' for a in anchos]
        xml.append("</w:tblGrid>")
        for i, fila in enumerate(filas):
            cabecera = i == 0 and not sin_cabecera
            trpr = "<w:trPr><w:tblHeader/><w:cantSplit/></w:trPr>" if cabecera \
                else "<w:trPr><w:cantSplit/></w:trPr>"
            xml.append(f"<w:tr>{trpr}")
            for a, celda in zip(anchos, fila):
                sombra = ('<w:shd w:val="clear" w:color="auto" w:fill="D9E2F3"/>'
                          if cabecera else "")
                xml.append(f'<w:tc><w:tcPr><w:tcW w:w="{a}" w:type="dxa"/>{sombra}</w:tcPr>')
                # El encabezado se queda con la primera fila (nunca huérfano al pie).
                xml.append(parrafo(corridas(celda.strip(), negrita=cabecera, tam=tam),
                                   estilo="Celda", extra="<w:keepNext/>" if cabecera else ""))
                xml.append("</w:tc>")
            xml.append("</w:tr>")
        xml.append("</w:tbl>")
        self.cuerpo.append("".join(xml))
        self.cuerpo.append(parrafo("", estilo="TrasCodigo"))

    # --- imágenes
    def imagen(self, pie: str, ruta: str) -> None:
        archivo = (self.base / ruta).resolve()
        datos = archivo.read_bytes()
        if datos[:8] != b"\x89PNG\r\n\x1a\n":
            raise SystemExit(f"solo PNG: {ruta}")
        ancho_px, alto_px = struct.unpack(">II", datos[16:24])
        cx, cy = ancho_px * EMU_POR_PX, alto_px * EMU_POR_PX
        escala = min(1.0, ANCHO_IMAGEN_MAX / cx, ALTO_IMAGEN_MAX / cy)
        cx, cy = int(cx * escala), int(cy * escala)
        n = len(self.imagenes) + 1
        self.imagenes.append((f"imagen{n}.png", datos))
        rid = f"rIdImg{n}"
        dibujo = (
            f'<w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0">'
            f'<wp:extent cx="{cx}" cy="{cy}"/><wp:docPr id="{n}" name="Imagen {n}" '
            f'descr="{x(pie)}"/><a:graphic xmlns:a="http://schemas.openxmlformats.org/'
            f'drawingml/2006/main"><a:graphicData uri="http://schemas.openxmlformats.org/'
            f'drawingml/2006/picture"><pic:pic xmlns:pic="http://schemas.openxmlformats.org/'
            f'drawingml/2006/picture"><pic:nvPicPr><pic:cNvPr id="{n}" name="imagen{n}.png"/>'
            f'<pic:cNvPicPr/></pic:nvPicPr><pic:blipFill><a:blip r:embed="{rid}"/>'
            f'<a:stretch><a:fillRect/></a:stretch></pic:blipFill><pic:spPr><a:xfrm>'
            f'<a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom '
            f'prst="rect"><a:avLst/></a:prstGeom><a:ln w="6350"><a:solidFill><a:srgbClr '
            f'val="BFBFBF"/></a:solidFill></a:ln></pic:spPr></pic:pic></a:graphicData>'
            f'</a:graphic></wp:inline></w:drawing></w:r>')
        self.cuerpo.append(parrafo(dibujo, estilo="Figura", extra="<w:keepNext/>"))
        self.cuerpo.append(parrafo(corridas(pie, cursiva=True, tam=18), estilo="Pie"))


# ----------------------------------------------------------------- lectura

def convertir(md: str, base: Path) -> Documento:
    doc = Documento(base)
    lineas = md.splitlines()
    i = 0
    primer_titulo = True

    def es_especial(linea: str) -> bool:
        s = linea.strip()
        return (not s or s.startswith(("#", "```", "|", ">", "![")) or s == "---"
                or re.match(r"^\s*(?:[-*]|\d+\.)\s+", linea) is not None)

    while i < len(lineas):
        linea = lineas[i]
        s = linea.strip()
        if not s:
            i += 1
            continue
        if s.startswith("```"):
            i += 1
            bloque = []
            while i < len(lineas) and not lineas[i].strip().startswith("```"):
                bloque.append(lineas[i].rstrip())
                i += 1
            i += 1
            doc.codigo(bloque)
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", s)
        if m:
            nivel = len(m.group(1))
            if nivel == 1 and primer_titulo:
                doc.titulo(m.group(2))
                primer_titulo = False
            else:
                doc.encabezado(nivel, m.group(2))
            i += 1
            continue
        if s == "---":
            doc.separador()
            i += 1
            continue
        m = re.match(r"^!\[(.*)\]\((.+)\)$", s)
        if m:
            doc.imagen(m.group(1), m.group(2))
            i += 1
            continue
        if s.startswith("|"):
            filas = []
            while i < len(lineas) and lineas[i].strip().startswith("|"):
                celdas = re.split(r"(?<!\\)\|", lineas[i].strip())[1:-1]
                if not all(re.fullmatch(r"\s*:?-{2,}:?\s*", c) for c in celdas):
                    filas.append(celdas)
                i += 1
            doc.tabla(filas)
            continue
        if s.startswith(">"):
            partes = []
            while i < len(lineas) and lineas[i].strip().startswith(">"):
                partes.append(lineas[i].strip()[1:].strip())
                i += 1
            doc.cita(" ".join(p for p in partes if p))
            continue
        if re.match(r"^\s*(?:[-*]|\d+\.)\s+", linea):
            items = []
            while i < len(lineas):
                m = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", lineas[i])
                if m:
                    nivel = 1 if len(m.group(1)) >= 2 else 0
                    items.append([nivel, m.group(2)[0].isdigit(), m.group(3).strip()])
                    i += 1
                elif lineas[i].startswith("  ") and lineas[i].strip() and items:
                    items[-1][2] += " " + lineas[i].strip()  # continuación del ítem
                    i += 1
                else:
                    break
            doc.lista([tuple(it) for it in items])
            continue
        partes = [s]
        i += 1
        while i < len(lineas) and not es_especial(lineas[i]):
            partes.append(lineas[i].strip())
            i += 1
        doc.texto(" ".join(partes))
    return doc


# ----------------------------------------------------------------- paquete

NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
      'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"')


def _estilo_parrafo(id_, nombre, ppr="", rpr="", basado="Normal", extra="") -> str:
    return (f'<w:style w:type="paragraph" w:styleId="{id_}"><w:name w:val="{nombre}"/>'
            f'<w:basedOn w:val="{basado}"/>{extra}<w:qFormat/><w:pPr>{ppr}</w:pPr>'
            f'<w:rPr>{rpr}</w:rPr></w:style>')


def estilos() -> str:
    titulo = [
        _estilo_parrafo("Title", "Title", '<w:spacing w:after="240"/><w:jc w:val="center"/>',
                        f'<w:b/><w:color w:val="{AZUL}"/><w:sz w:val="40"/>'),
        _estilo_parrafo("Heading1", "heading 1",
                        '<w:keepNext/><w:spacing w:before="240" w:after="240"/>'
                        '<w:pBdr><w:bottom w:val="single" w:sz="12" w:space="4" '
                        f'w:color="{AZUL}"/></w:pBdr><w:outlineLvl w:val="0"/>',
                        f'<w:b/><w:color w:val="{AZUL}"/><w:sz w:val="36"/>',
                        extra='<w:next w:val="Normal"/>'),
        _estilo_parrafo("Heading2", "heading 2",
                        '<w:keepNext/><w:spacing w:before="360" w:after="120"/>'
                        '<w:outlineLvl w:val="1"/>',
                        f'<w:b/><w:color w:val="{AZUL}"/><w:sz w:val="30"/>',
                        extra='<w:next w:val="Normal"/>'),
        _estilo_parrafo("Heading3", "heading 3",
                        '<w:keepNext/><w:spacing w:before="240" w:after="80"/>'
                        '<w:outlineLvl w:val="2"/>',
                        '<w:b/><w:color w:val="2E74B5"/><w:sz w:val="25"/>',
                        extra='<w:next w:val="Normal"/>'),
        _estilo_parrafo("Heading4", "heading 4",
                        '<w:keepNext/><w:spacing w:before="200" w:after="60"/>'
                        '<w:outlineLvl w:val="3"/>',
                        '<w:b/><w:i/><w:color w:val="2E74B5"/><w:sz w:val="22"/>',
                        extra='<w:next w:val="Normal"/>'),
        _estilo_parrafo("Codigo", "Código",
                        '<w:spacing w:before="0" w:after="0" w:line="228" w:lineRule="auto"/>'
                        '<w:shd w:val="clear" w:color="auto" w:fill="F2F2F2"/>'
                        '<w:ind w:left="113" w:right="113"/>',
                        f'<w:rFonts w:ascii="{MONO}" w:hAnsi="{MONO}" w:cs="{MONO}"/>'
                        '<w:sz w:val="15"/><w:szCs w:val="15"/>'),  # 7.5 pt: ~110 caracteres
        _estilo_parrafo("TrasCodigo", "Espacio", '<w:spacing w:before="0" w:after="60"/>',
                        '<w:sz w:val="8"/>'),
        _estilo_parrafo("Cita", "Cita", '<w:ind w:left="567"/><w:pBdr><w:left w:val="single" '
                        'w:sz="18" w:space="8" w:color="9DC3E6"/></w:pBdr>',
                        '<w:color w:val="404040"/>'),
        _estilo_parrafo("Lista", "Lista", '<w:spacing w:after="60"/>'),
        _estilo_parrafo("Celda", "Celda", '<w:spacing w:before="20" w:after="20" w:line="240" '
                        'w:lineRule="auto"/>'),
        _estilo_parrafo("Figura", "Figura", '<w:spacing w:before="120" w:after="40"/>'
                        '<w:jc w:val="center"/>'),
        _estilo_parrafo("Pie", "Pie de figura", '<w:spacing w:after="200"/><w:jc w:val="center"/>',
                        '<w:color w:val="595959"/>'),
    ]
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles {NS}>'
            f'<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="{FUENTE}" '
            f'w:hAnsi="{FUENTE}" w:eastAsia="{FUENTE}" w:cs="{FUENTE}"/><w:sz w:val="22"/>'
            '<w:szCs w:val="22"/><w:lang w:val="es-MX"/></w:rPr></w:rPrDefault><w:pPrDefault>'
            '<w:pPr><w:spacing w:after="120" w:line="264" w:lineRule="auto"/></w:pPr>'
            '</w:pPrDefault></w:docDefaults>'
            '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/>'
            '<w:qFormat/></w:style>'
            + "".join(titulo) +
            '<w:style w:type="table" w:styleId="Tabla"><w:name w:val="Tabla del reporte"/>'
            '<w:tblPr><w:tblBorders>'
            + "".join(f'<w:{b} w:val="single" w:sz="4" w:space="0" w:color="A6A6A6"/>'
                      for b in ("top", "left", "bottom", "right", "insideH", "insideV"))
            + '</w:tblBorders><w:tblCellMar><w:top w:w="40" w:type="dxa"/><w:left w:w="90" '
            'w:type="dxa"/><w:bottom w:w="40" w:type="dxa"/><w:right w:w="90" w:type="dxa"/>'
            '</w:tblCellMar></w:tblPr></w:style></w:styles>')


def numeracion(n_numeradas: int) -> str:
    def nivel(i, formato, texto, sangria):
        fuente = ('<w:rPr><w:rFonts w:ascii="Symbol" w:hAnsi="Symbol" w:hint="default"/></w:rPr>'
                  if formato == "bullet" and i == 0 else "")
        return (f'<w:lvl w:ilvl="{i}"><w:start w:val="1"/><w:numFmt w:val="{formato}"/>'
                f'<w:lvlText w:val="{texto}"/><w:lvlJc w:val="left"/><w:pPr><w:ind '
                f'w:left="{sangria}" w:hanging="360"/></w:pPr>{fuente}</w:lvl>')
    vinetas = (f'<w:abstractNum w:abstractNumId="0"><w:multiLevelType w:val="hybridMultilevel"/>'
               f'{nivel(0, "bullet", "", 720)}{nivel(1, "bullet", "–", 1440)}'
               '</w:abstractNum>')
    numeros = (f'<w:abstractNum w:abstractNumId="1"><w:multiLevelType w:val="hybridMultilevel"/>'
               f'{nivel(0, "decimal", "%1.", 720)}{nivel(1, "bullet", "–", 1440)}'
               '</w:abstractNum>')
    nums = ['<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>']
    for k in range(n_numeradas):
        nums.append(f'<w:num w:numId="{k + 2}"><w:abstractNumId w:val="1"/><w:lvlOverride '
                    f'w:ilvl="0"><w:startOverride w:val="1"/></w:lvlOverride></w:num>')
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:numbering {NS}>'
            f'{vinetas}{numeros}{"".join(nums)}</w:numbering>')


PIE_PAGINA = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:ftr {NS}><w:p><w:pPr>'
              '<w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:color w:val="808080"/><w:sz '
              'w:val="18"/></w:rPr><w:t xml:space="preserve">Calculadora ADS · Reporte técnico · '
              '</w:t></w:r><w:r><w:rPr><w:color w:val="808080"/><w:sz w:val="18"/></w:rPr>'
              '<w:fldChar w:fldCharType="begin"/></w:r><w:r><w:rPr><w:color w:val="808080"/>'
              '<w:sz w:val="18"/></w:rPr><w:instrText xml:space="preserve"> PAGE </w:instrText>'
              '</w:r><w:r><w:rPr><w:color w:val="808080"/><w:sz w:val="18"/></w:rPr><w:fldChar '
              'w:fldCharType="separate"/></w:r><w:r><w:rPr><w:color w:val="808080"/><w:sz '
              'w:val="18"/></w:rPr><w:t>1</w:t></w:r><w:r><w:rPr><w:color w:val="808080"/>'
              '<w:sz w:val="18"/></w:rPr><w:fldChar w:fldCharType="end"/></w:r></w:p></w:ftr>')


def empaquetar(doc: Documento, salida: Path) -> None:
    seccion = ('<w:sectPr><w:footerReference w:type="default" r:id="rIdPie"/>'
               '<w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" '
               'w:bottom="1440" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/>'
               '</w:sectPr>')
    documento = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {NS}>'
                 f'<w:body>{"".join(doc.cuerpo)}{seccion}</w:body></w:document>')
    tipos = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://'
             'schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" '
             'ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default '
             'Extension="xml" ContentType="application/xml"/><Default Extension="png" '
             'ContentType="image/png"/><Override PartName="/word/document.xml" ContentType='
             '"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
             '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-'
             'officedocument.wordprocessingml.styles+xml"/><Override PartName="/word/numbering.'
             'xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.'
             'numbering+xml"/><Override PartName="/word/footer1.xml" ContentType="application/'
             'vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/><Override PartName='
             '"/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-'
             'properties+xml"/></Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://'
            'schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
            'officeDocument" Target="word/document.xml"/><Relationship Id="rId2" Type="http://'
            'schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" '
            'Target="docProps/core.xml"/></Relationships>')
    base_rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
    doc_rels = [f'<Relationship Id="rIdEstilos" Type="{base_rel}styles" Target="styles.xml"/>',
                f'<Relationship Id="rIdNum" Type="{base_rel}numbering" Target="numbering.xml"/>',
                f'<Relationship Id="rIdPie" Type="{base_rel}footer" Target="footer1.xml"/>']
    doc_rels += [f'<Relationship Id="rIdImg{k}" Type="{base_rel}image" Target="media/{nombre}"/>'
                 for k, (nombre, _) in enumerate(doc.imagenes, start=1)]
    core = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties '
            'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Reporte Técnico — Calculadora '
            'ADS</dc:title><dc:language>es-MX</dc:language></cp:coreProperties>')
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", tipos)
        z.writestr("_rels/.rels", rels)
        z.writestr("docProps/core.xml", core)
        z.writestr("word/document.xml", documento)
        z.writestr("word/styles.xml", estilos())
        z.writestr("word/numbering.xml", numeracion(doc.listas_numeradas))
        z.writestr("word/footer1.xml", PIE_PAGINA)
        z.writestr("word/_rels/document.xml.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships '
                   'xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   + "".join(doc_rels) + "</Relationships>")
        for nombre, datos in doc.imagenes:
            z.writestr(f"word/media/{nombre}", datos)


def main(argv: list[str]) -> int:
    entrada = Path(argv[0]) if argv else RAIZ / "REPORTE_TECNICO.md"
    salida = Path(argv[1]) if len(argv) > 1 else RAIZ / "Reporte_Tecnico_Calculadora_ADS.docx"
    doc = convertir(entrada.read_text(encoding="utf-8"), entrada.resolve().parent)
    empaquetar(doc, salida)
    print(f"{salida} · {len(doc.cuerpo)} bloques · {len(doc.imagenes)} imagen(es)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
