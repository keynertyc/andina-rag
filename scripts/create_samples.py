"""Regenerate synthetic PDF/products/cases from human-readable local sources."""

import csv
import json
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    styles = getSampleStyleSheet()
    source = ROOT / "samples/guides/kintu-cuidado.md"
    blocks = []
    for paragraph in source.read_text().split("\n\n"):
        heading = paragraph.startswith("#")
        blocks.append(
            Paragraph(
                paragraph.lstrip("# ").replace("\n", " "),
                styles["Heading2"] if heading else styles["BodyText"],
            )
        )
        blocks.append(Spacer(1, 12))
    SimpleDocTemplate(str(source.with_suffix(".pdf")), pagesize=A4).build(blocks)
    specs = [
        (
            "Puna",
            "textiles",
            "BUFANDA DE ALPACA AZUL",
            "Bufanda con 60 % alpaca, color azul.",
            "PUNA-01",
        ),
        ("Valle", "cafe", "CAFÉ MOLIDO 250 G", "Café molido, tueste medio, 250 g.", "VALLE-01"),
        ("Kintu", "cuidado", "JABÓN DE AVENA 90 G", "Jabón con avena, 90 g. El mejor!", "KINTU-01"),
        ("Puna", "textiles", "GORRO ROJO", "Gorro de lana, color rojo.", "PUNA-02"),
        ("Valle", "cafe", "CAFÉ EN GRANO CUSCO", "Café en grano de Cusco, 500 g.", "VALLE-02"),
        (
            "Kintu",
            "cuidado",
            "CREMA DE MANOS 60 ML",
            "Crema de manos con karité, 60 ml.",
            "KINTU-02",
        ),
        (
            "Orbita",
            "electronica",
            "Controlador de señales digitales",
            "Módulo FPGA para prototipado electrónico.",
            None,
        ),
        (
            "Puna",
            "textiles",
            "Licencia de software contable",
            "Programa de contabilidad empresarial, cálculo de impuestos y nóminas.",
            None,
        ),
        ("Puna", "textiles", "CHALINA VERDE", "Chalina de lana verde, 150 cm.", "PUNA-02"),
        ("Puna", "textiles", "MANTA GRIS", "Manta gris, 120 por 180 cm.", "PUNA-02"),
        ("Puna", "textiles", "PONCHO DE LANA", "Poncho de lana marrón. Garantizado!", "PUNA-01"),
        ("Puna", "textiles", "GUANTES DE ALPACA", "Guantes con 40 % alpaca, talla M.", "PUNA-02"),
        (
            "Valle",
            "cafe",
            "CAFÉ MOLIDO CAJAMARCA",
            "Café de Cajamarca, molienda fina, 250 g.",
            "VALLE-02",
        ),
        (
            "Valle",
            "cafe",
            "CAFÉ DE ESPECIALIDAD 1 KG",
            "Café en grano, 1 kg, tueste oscuro.",
            "VALLE-01",
        ),
        (
            "Valle",
            "cafe",
            "CAFÉ TUeste CLARO",
            "Café molido, tueste claro, 200 g. El mejor!",
            "VALLE-02",
        ),
        ("Kintu", "cuidado", "CHAMPÚ 250 ML", "Champú con romero, 250 ml.", "KINTU-02"),
        ("Kintu", "cuidado", "BÁLSAMO LABIAL 10 G", "Bálsamo labial con cacao, 10 g.", "KINTU-01"),
        ("Kintu", "cuidado", "JABÓN LÍQUIDO 300 ML", "Jabón líquido con aloe, 300 ml.", "KINTU-02"),
        (
            "Orbita",
            "electronica",
            "Osciloscopio digital",
            "Instrumento de medición de circuitos, dos canales.",
            None,
        ),
        (
            "Valle",
            "cafe",
            "Osciloscopio digital",
            "Instrumento de medición de circuitos, dos canales.",
            None,
        ),
    ]
    cases = []
    for index, (brand, category, title, description, rule) in enumerate(specs, 1):
        product = {
            "id": f"MA-{index:03d}",
            "brand": brand,
            "category": category,
            "title": title,
            "description": description,
            "tags": [],
        }
        cases.append(
            {
                "split": "calibration" if index <= 8 else "verification",
                "product": product,
                "expected_rule": rule,
                "should_block": rule is None,
            }
        )
    (ROOT / "samples/cases.json").write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n")
    products = [case["product"] for case in cases]
    (ROOT / "samples/products/productos.json").write_text(
        json.dumps(products, ensure_ascii=False, indent=2) + "\n"
    )
    with (ROOT / "samples/products/productos.csv").open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(products[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows([{**product, "tags": ""} for product in products])


if __name__ == "__main__":
    main()
