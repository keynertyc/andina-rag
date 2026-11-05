"""Compare real pgvector/E5 retrieval to a lexical baseline; roll back all fixture rows."""

import argparse
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.db import get_engine
from app.embeddings import get_embedder
from app.ingestion import Section, chunk_sections, extract_sections
from app.llm import generate_validated, get_llm
from app.models import Chunk, Document, DocumentVersion, new_id
from app.retrieval import retrieve
from app.schemas import Product
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
THRESHOLDS = [0.70, 0.75, 0.80, 0.85, 0.90]


def prepare(session: Session, embedder: Any) -> tuple[list[str], list[dict[str, Any]]]:
    versions = []
    baseline = []
    for brand, category, filename in [
        ("puna", "textiles", "puna-textiles-v1.md"),
        ("valle", "cafe", "valle-cafe-v1.md"),
        ("kintu", "cuidado", "kintu-cuidado.pdf"),
    ]:
        path = ROOT / "samples/guides" / filename
        sections = extract_sections(filename, path.read_bytes())
        document = Document(id=new_id(), title=filename, brand=brand, category=category)
        session.add(document)
        session.flush()
        version = DocumentVersion(
            id=new_id(),
            document_id=document.id,
            number=1,
            checksum=hashlib.sha256(path.read_bytes()).hexdigest(),
            filename=filename,
            source_path=str(path),
            status="ready",
            is_active=True,
            embedding_model=embedder.model_id,
            configuration={"chunk_tokens": 400, "chunk_overlap": 60},
        )
        session.add(version)
        session.flush()
        versions.append(version.id)
        chunks = chunk_sections(sections, embedder.tokenizer)
        vectors = embedder.passages([chunk.text for chunk in chunks])
        for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
            session.add(
                Chunk(
                    id=new_id(),
                    version_id=version.id,
                    position=index,
                    text=chunk.text,
                    page=chunk.page,
                    heading=chunk.heading,
                    embedding=vector,
                )
            )
        fixed = chunk_sections(
            [Section("\n\n".join(section.text for section in sections))],
            embedder.tokenizer,
            max_tokens=400,
            overlap=0,
            respect_paragraphs=False,
        )
        for index, chunk in enumerate(fixed):
            baseline.append(
                {
                    "id": f"lexical-{brand}-{index}",
                    "text": chunk.text,
                    "brand": brand,
                    "category": category,
                }
            )
    session.flush()
    return versions, baseline


def lexical_retrieve(product: Product, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    terms = set(re.findall(r"\w{3,}", (product.title + " " + product.description).casefold()))
    scored = []
    for chunk in chunks:
        if (
            chunk["brand"] != product.brand.casefold()
            or chunk["category"] != product.category.casefold()
        ):
            continue
        words = set(re.findall(r"\w{3,}", chunk["text"].casefold()))
        score = len(terms & words) / max(len(terms), 1)
        if score > 0:
            scored.append({**chunk, "similarity": score})
    return sorted(scored, key=lambda chunk: (-chunk["similarity"], chunk["id"]))[:5]


def rule_compliance(product: Product, proposal: Any) -> bool:
    forbidden = r"\b(el mejor|la mejor|garantizado|cura|milagroso)\b"
    return (
        proposal.title.casefold().startswith(product.brand.casefold())
        and len(proposal.title) <= 80
        and not proposal.title.isupper()
        and "!" not in proposal.title
        and not re.search(forbidden, proposal.description, flags=re.IGNORECASE)
        and all(tag == tag.casefold() for tag in proposal.tags)
    )


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    generated = [row for row in rows if row["generated"]]
    positive = [row for row in rows if not row["should_block"]]
    negative = [row for row in rows if row["should_block"]]
    ratio = lambda count, total: round(count / total, 4) if total else None  # noqa: E731
    return {
        "cases": len(rows),
        "generated": len(generated),
        "generation_coverage": ratio(len(generated), len(rows)),
        "positive_coverage": ratio(sum(row["generated"] for row in positive), len(positive)),
        "valid_citations": ratio(sum(row["valid_citations"] for row in generated), len(generated)),
        "rule_compliance": ratio(sum(row["rules_pass"] for row in generated), len(generated)),
        "recall_at_5": ratio(
            sum(row["expected_evidence_found"] for row in positive), len(positive)
        ),
        "correct_insufficient_evidence_blocking": ratio(
            sum(row["blocked"] for row in negative), len(negative)
        ),
        "mean_latency_ms": round(sum(row["latency_ms"] for row in rows) / max(len(rows), 1), 2),
    }


def run_cases(
    cases: list[dict[str, Any]], contexts: dict[str, list[dict[str, Any]]], threshold: float
) -> list[dict[str, Any]]:
    rows = []
    for case in cases:
        product = Product.model_validate(case["product"])
        context = [chunk for chunk in contexts[product.id] if chunk["similarity"] >= threshold]
        started = time.perf_counter()
        blocked = not bool(context)
        generated = not blocked
        valid_citations, rules_pass = False, False
        error = None
        if generated:
            try:
                proposal = generate_validated(get_llm(), product, context)
                valid_citations = bool(proposal.citations) and set(proposal.citations) <= {
                    chunk["id"] for chunk in context
                }
                rules_pass = rule_compliance(product, proposal)
            except Exception as exc:
                generated, error = False, type(exc).__name__
        rows.append(
            {
                "product_id": product.id,
                "should_block": case["should_block"],
                "generated": generated,
                "blocked": blocked,
                "valid_citations": valid_citations,
                "rules_pass": rules_pass,
                "expected_evidence_found": bool(case["expected_rule"])
                and any(case["expected_rule"] in chunk["text"] for chunk in context),
                "best_similarity": contexts[product.id][0]["similarity"]
                if contexts[product.id]
                else None,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "error": error,
            }
        )
    return rows


def select_threshold(
    calibration: list[dict[str, Any]], contexts: dict[str, list[dict[str, Any]]]
) -> tuple[float, list[dict[str, Any]]]:
    candidates = []
    for threshold in THRESHOLDS:
        false_generations, true_generations, evidence_found = 0, 0, 0
        for case in calibration:
            has_evidence = any(
                chunk["similarity"] >= threshold for chunk in contexts[case["product"]["id"]]
            )
            false_generations += int(has_evidence and case["should_block"])
            true_generations += int(has_evidence and not case["should_block"])
            evidence_found += int(
                bool(case["expected_rule"])
                and any(
                    case["expected_rule"] in chunk["text"] and chunk["similarity"] >= threshold
                    for chunk in contexts[case["product"]["id"]]
                )
            )
        candidates.append(
            {
                "threshold": threshold,
                "false_generations": false_generations,
                "true_generations": true_generations,
                "expected_evidence_found": evidence_found,
            }
        )
    best = min(
        candidates,
        key=lambda row: (
            row["false_generations"],
            -row["expected_evidence_found"],
            -row["true_generations"],
            -row["threshold"],
        ),
    )
    return best["threshold"], candidates


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="reports/evaluation.json")
    parser.add_argument(
        "--check", action="store_true", help="Fallar si no se alcanzan los objetivos"
    )
    args = parser.parse_args()
    settings = get_settings()
    if settings.embedding_provider != "fastembed":
        raise SystemExit(
            "La evaluación de calidad exige EMBEDDING_PROVIDER=fastembed, no el doble hash"
        )
    cases = json.loads((ROOT / "samples/cases.json").read_text())
    calibration = [case for case in cases if case["split"] == "calibration"]
    verification = [case for case in cases if case["split"] == "verification"]
    embedder = get_embedder()
    contexts, lexical_contexts = {}, {}
    retrieval_ms = []
    with Session(get_engine()) as session:
        try:
            versions, baseline = prepare(session, embedder)
            for case in cases:
                product = Product.model_validate(case["product"])
                started = time.perf_counter()
                contexts[product.id] = retrieve(session, product, versions, embedder, threshold=-1)
                retrieval_ms.append((time.perf_counter() - started) * 1000)
                lexical_contexts[product.id] = lexical_retrieve(product, baseline)
            threshold, calibration_report = select_threshold(calibration, contexts)
            calibration_rows = run_cases(calibration, contexts, threshold)
            rows = run_cases(verification, contexts, threshold)
            baseline_rows = run_cases(verification, lexical_contexts, 0)
            metrics = summarize(rows)
            overall = summarize(calibration_rows + rows)
            checks = {
                "valid_citations": overall["valid_citations"] == 1,
                "rule_compliance": (overall["rule_compliance"] or 0) >= 0.9,
                "recall_at_5": (overall["recall_at_5"] or 0) >= 0.9,
                "positive_coverage": (overall["positive_coverage"] or 0) >= 0.9,
                "correct_blocking": overall["correct_insufficient_evidence_blocking"] == 1,
            }
            report = {
                "dataset_sha256": hashlib.sha256(
                    (ROOT / "samples/cases.json").read_bytes()
                ).hexdigest(),
                "embedding_model": embedder.model_id,
                "llm_provider": settings.llm_provider,
                "llm_model": settings.gemini_model
                if settings.llm_provider == "gemini"
                else "template-v1",
                "chunking": {"tokens": 400, "overlap": 60},
                "threshold": threshold,
                "calibration": calibration_report,
                "calibration_summary": summarize(calibration_rows),
                "calibration_cases": calibration_rows,
                "overall": overall,
                "verification": metrics,
                "baseline": {
                    "description": "400 tokens, no overlap, lexical matching, same generator",
                    "verification": summarize(baseline_rows),
                    "cases": baseline_rows,
                },
                "retrieval_mean_latency_ms": round(sum(retrieval_ms) / len(retrieval_ms), 2),
                "cases": rows,
                "checks": checks,
                "limitations": [
                    "Small synthetic dataset, not a general quality benchmark.",
                    "Citation membership does not prove semantic entailment.",
                    "Mock generator results do not establish Gemini quality.",
                    "Latency measured locally; model warmup excluded.",
                ],
            }
        finally:
            session.rollback()
    path = ROOT / args.output
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            {"threshold": threshold, "overall": overall, "verification": metrics, "checks": checks},
            indent=2,
        )
    )
    print(f"Informe: {path}")
    if args.check and not all(checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
