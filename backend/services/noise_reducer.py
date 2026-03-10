"""Noise-reduction service — TF-IDF clustering to de-duplicate similar log messages.

Before feeding logs into the LLM, we cluster similar messages and only pass
representative samples.  This cuts token cost by ~80 % on noisy production
systems while preserving diagnostic signal.
"""

from dataclasses import dataclass, field
import numpy as np
from sklearn.cluster import DBSCAN
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_distances

from backend.config import get_settings


@dataclass
class ClusteredLog:
    """A representative log message selected from a cluster."""

    representative_message: str
    log_ids: list[str] = field(default_factory=list)
    cluster_size: int = 1


class NoiseReducer:
    """Cluster similar log messages using TF-IDF + DBSCAN.

    Parameters
    ----------
    distance_threshold:
        Maximum cosine distance for two log messages to be considered
        "similar".  Lower values → more clusters (less aggressive de-dup).
    """

    def __init__(self, distance_threshold: float | None = None) -> None:
        settings = get_settings()
        self._threshold = distance_threshold or (
            1.0 - settings.noise_reduction_threshold
        )
        self._vectorizer = TfidfVectorizer(
            max_features=5000,
            stop_words="english",
            ngram_range=(1, 2),
        )

    def reduce(
        self, messages: list[str], log_ids: list[str] | None = None
    ) -> list[ClusteredLog]:
        """Return de-duplicated representative log messages.

        Parameters
        ----------
        messages:
            Raw log message strings.
        log_ids:
            Optional parallel list of log IDs.  If provided, each
            ``ClusteredLog`` will carry the IDs of all logs in its cluster.

        Returns
        -------
        list[ClusteredLog]
            One entry per cluster, ordered largest-cluster-first.
        """
        if not messages:
            return []

        ids = log_ids or [str(i) for i in range(len(messages))]

        # Edge case: single message
        if len(messages) == 1:
            return [
                ClusteredLog(
                    representative_message=messages[0],
                    log_ids=[ids[0]],
                    cluster_size=1,
                )
            ]

        tfidf_matrix = self._vectorizer.fit_transform(messages)
        distance_matrix = cosine_distances(tfidf_matrix)

        clustering = DBSCAN(
            eps=self._threshold,
            min_samples=1,
            metric="precomputed",
        ).fit(distance_matrix)

        labels = clustering.labels_

        # Group messages by cluster label
        clusters: dict[int, list[int]] = {}
        for idx, label in enumerate(labels):
            clusters.setdefault(label, []).append(idx)

        # For each cluster pick the message closest to the centroid
        results: list[ClusteredLog] = []
        for label, indices in clusters.items():
            sub_matrix = distance_matrix[np.ix_(indices, indices)]
            centroid_idx = int(np.argmin(sub_matrix.sum(axis=1)))
            rep_idx = indices[centroid_idx]
            results.append(
                ClusteredLog(
                    representative_message=messages[rep_idx],
                    log_ids=[ids[i] for i in indices],
                    cluster_size=len(indices),
                )
            )

        # Largest clusters first — they represent the noisiest patterns
        results.sort(key=lambda c: c.cluster_size, reverse=True)
        return results
