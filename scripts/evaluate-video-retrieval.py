from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from sqlmodel import Session

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import get_settings
from app.database import create_db_and_tables, engine
from app.embeddings import deserialize_vector
from app.face_tuning import FaceRuntimeConfigService
from app.repository import GalleryRepository
from app.schemas import decode_json_list
from app.video_search_service import VideoSearchService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate person-to-video retrieval quality.")
    parser.add_argument("--top-k", nargs="+", type=int, default=[1, 5, 10], help="Top-K hit rates to report.")
    parser.add_argument(
        "--retrieval-limit",
        type=int,
        default=200,
        help="Maximum number of retrieved videos per query.",
    )
    parser.add_argument(
        "--person-limit",
        type=int,
        default=500,
        help="Maximum number of person profiles to evaluate.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional JSON output path for the full evaluation report.",
    )
    return parser.parse_args()


def collect_ground_truth(repository: GalleryRepository, person_id: int) -> set[int]:
    cluster_labels = {
        cluster.label
        for cluster in repository.list_face_clusters_by_person(person_id, limit=5000)
    }
    if not cluster_labels:
        return set()

    relevant_video_ids: set[int] = set()
    for video in repository.list_searchable_videos(limit=5000):
        if cluster_labels.intersection(decode_json_list(video.face_clusters)):
            if video.id:
                relevant_video_ids.add(video.id)
    return relevant_video_ids


def main() -> int:
    args = parse_args()
    top_k_values = sorted({value for value in args.top_k if value > 0})
    if not top_k_values:
        raise SystemExit("At least one positive top-k value is required.")

    settings = get_settings()
    settings.ensure_directories()
    FaceRuntimeConfigService(settings).apply_persisted_thresholds()
    create_db_and_tables()

    max_results = max(max(top_k_values), args.retrieval_limit)
    report: dict[str, object] = {
        "thresholds": FaceRuntimeConfigService(settings).current_thresholds(),
        "queries": [],
        "summary": {},
    }

    with Session(engine) as session:
        repository = GalleryRepository(session)
        search_service = VideoSearchService(session)
        people = repository.list_person_profiles(limit=args.person_limit)

        total_queries = 0
        total_mrr = 0.0
        hit_counts = {value: 0 for value in top_k_values}

        for person in people:
            relevant_video_ids = collect_ground_truth(repository, person.id or 0)
            if not relevant_video_ids:
                continue

            person_query_count = 0
            person_hit_counts = {value: 0 for value in top_k_values}
            person_mrr = 0.0

            for sample in repository.list_person_samples(person.id or 0):
                embedding = deserialize_vector(sample.embedding)
                if not embedding:
                    continue

                result = search_service.search_by_person_embedding(embedding, limit=max_results)
                ranks = [
                    index + 1
                    for index, hit in enumerate(result.hits)
                    if hit.video.id in relevant_video_ids
                ]
                best_rank = min(ranks) if ranks else None

                total_queries += 1
                person_query_count += 1
                if best_rank:
                    reciprocal_rank = 1.0 / best_rank
                    total_mrr += reciprocal_rank
                    person_mrr += reciprocal_rank
                    for value in top_k_values:
                        if best_rank <= value:
                            hit_counts[value] += 1
                            person_hit_counts[value] += 1

                report["queries"].append(
                    {
                        "person_id": person.id,
                        "person_name": person.name,
                        "sample_id": sample.id,
                        "best_rank": best_rank,
                        "relevant_video_count": len(relevant_video_ids),
                        "retrieved_count": result.total,
                    }
                )

            if not person_query_count:
                continue

            report.setdefault("people", []).append(
                {
                    "person_id": person.id,
                    "person_name": person.name,
                    "query_count": person_query_count,
                    "mrr": round(person_mrr / person_query_count, 6),
                    "hit_rate": {
                        f"top_{value}": round(person_hit_counts[value] / person_query_count, 6)
                        for value in top_k_values
                    },
                }
            )

        if not total_queries:
            print("No evaluable video queries were found. Add person samples and labeled videos first.")
            return 0

        summary = {
            "query_count": total_queries,
            "mrr": round(total_mrr / total_queries, 6),
            "hit_rate": {
                f"top_{value}": round(hit_counts[value] / total_queries, 6)
                for value in top_k_values
            },
        }
        report["summary"] = summary

    print("Video Retrieval Evaluation")
    print(f"Queries: {summary['query_count']}")
    print(f"MRR: {summary['mrr']:.6f}")
    for value in top_k_values:
        score = summary["hit_rate"][f"top_{value}"]
        print(f"Hit@{value}: {score:.6f}")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Saved detailed report to {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
