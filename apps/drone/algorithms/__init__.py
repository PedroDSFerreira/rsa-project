from algorithms.base import Algorithm
from algorithms.boustrophedon import BoustrophedonTraversal
from algorithms.greedy import GreedyNearestTraversal

AVAILABLE_ALGORITHMS: list[str] = ["boustrophedon", "greedy"]


def make_algorithm(name: str) -> Algorithm:
    if name == "greedy":
        return GreedyNearestTraversal()
    return BoustrophedonTraversal()
