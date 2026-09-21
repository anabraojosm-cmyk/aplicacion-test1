"""Generador de preguntas tipo test a partir de documentos (resúmenes, libros, leyes).

Uso:
    python generador_tests.py mi_resumen.pdf --preguntas 5 --salida test.json
    python generador_tests.py --practicar test.json
"""
import argparse
import json
import random
import time
from pathlib import Path

from google import genai
from google.genai import types

MODELO = "gemini-3.6-flash"  # si da error de modelo, mira el nombre actual en aistudio.google.com
TAM_FRAGMENTO = 6000  # caracteres por fragmento enviado al modelo
PAUSA_SEGUNDOS = 7  # espera entre peticiones para respetar el límite gratuito

INSTRUCCIONES = """Eres un profesor que crea preguntas tipo test de calidad a partir de un texto de estudio.
Reglas:
- Usa SOLO información presente en el texto.
- Cada pregunta tiene 4 opciones, una sola correcta y tres distractores plausibles.
- Varía la posición de la respuesta correcta.
- Si el texto es legal, cita el artículo o apartado en la explicación cuando aparezca.
Devuelve ÚNICAMENTE un JSON válido: una lista de objetos con las claves
"pregunta" (str), "opciones" (lista de 4 str), "correcta" (índice 0-3) y "explicacion" (str)."""


def leer_documento(ruta: Path) -> str:
    ext = ruta.suffix.lower()
    if ext in {".txt", ".md"}:
        return ruta.read_text(encoding="utf-8", errors="ignore")
    if ext == ".pdf":
        from pypdf import PdfReader
        return "\n".join(p.extract_text() or "" for p in PdfReader(ruta).pages)
    if ext == ".docx":
        from docx import Document
        return "\n".join(p.text for p in Document(ruta).paragraphs)
    raise ValueError(f"Formato no soportado: {ext} (usa .txt, .md, .pdf o .docx)")


def dividir(texto: str, tam: int = TAM_FRAGMENTO) -> list[str]:
    fragmentos, actual = [], ""
    for linea in texto.splitlines():
        if len(actual) + len(linea) > tam and actual:
            fragmentos.append(actual)
            actual = ""
        actual += linea + "\n"
    if actual.strip():
        fragmentos.append(actual)
    return fragmentos


def generar_preguntas(cliente: genai.Client, fragmento: str, n: int) -> list[dict]:
    for intento in range(3):
        try:
            respuesta = cliente.models.generate_content(
                model=MODELO,
                contents=f"Genera {n} preguntas de este texto:\n\n{fragmento}",
                config=types.GenerateContentConfig(
                    system_instruction=INSTRUCCIONES,
                    response_mime_type="application/json",
                ),
            )
            return json.loads(respuesta.text)
        except json.JSONDecodeError:
            raise
        except Exception as e:  # normalmente límite de uso (429): esperamos y reintentamos
            if "NOT_FOUND" in str(e):
                raise SystemExit(f"Modelo no disponible: {e}\nCambia MODELO por el nombre actual en aistudio.google.com")
            print(f"  Aviso: {e}. Reintentando en 30 s...")
            time.sleep(30)
    raise RuntimeError("No se pudo generar tras 3 intentos")


def crear_test(ruta: Path, por_fragmento: int) -> list[dict]:
    cliente = genai.Client()  # lee la clave de la variable de entorno GEMINI_API_KEY
    fragmentos = dividir(leer_documento(ruta))
    preguntas = []
    for i, frag in enumerate(fragmentos, 1):
        print(f"Procesando fragmento {i}/{len(fragmentos)}...")
        try:
            preguntas.extend(generar_preguntas(cliente, frag, por_fragmento))
        except (json.JSONDecodeError, RuntimeError) as e:
            print(f"  Fragmento {i} omitido ({e})")
        time.sleep(PAUSA_SEGUNDOS)
    return preguntas


def practicar(preguntas: list[dict]) -> None:
    random.shuffle(preguntas)
    aciertos = 0
    for n, p in enumerate(preguntas, 1):
        print(f"\n{n}. {p['pregunta']}")
        for letra, opcion in zip("abcd", p["opciones"]):
            print(f"   {letra}) {opcion}")
        resp = input("Tu respuesta (a-d): ").strip().lower()
        correcta = "abcd"[p["correcta"]]
        if resp == correcta:
            aciertos += 1
            print("✔ Correcto")
        else:
            print(f"✘ Era la {correcta}")
        print(f"   {p['explicacion']}")
    print(f"\nResultado: {aciertos}/{len(preguntas)}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Genera y practica tests desde documentos")
    ap.add_argument("documento", nargs="?", help="Archivo .txt, .md, .pdf o .docx")
    ap.add_argument("--preguntas", type=int, default=5, help="Preguntas por fragmento")
    ap.add_argument("--salida", default="test.json", help="Archivo JSON de salida")
    ap.add_argument("--practicar", metavar="TEST_JSON", help="Hacer un test ya generado")
    args = ap.parse_args()

    if args.practicar:
        practicar(json.loads(Path(args.practicar).read_text(encoding="utf-8")))
    elif args.documento:
        preguntas = crear_test(Path(args.documento), args.preguntas)
        Path(args.salida).write_text(json.dumps(preguntas, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n{len(preguntas)} preguntas guardadas en {args.salida}")
    else:
        ap.print_help()


if __name__ == "__main__":
    main()