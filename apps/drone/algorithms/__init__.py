from algorithms.base import Traversal
from algorithms.boustrophedon import BoustrophedonTraversal
from algorithms.greedy import GreedyNearestTraversal


def make_traversal(name: str, row_min: int, row_max: int, cols: int) -> Traversal:
    if name == "greedy":
        return GreedyNearestTraversal(row_min=row_min, row_max=row_max)
    return BoustrophedonTraversal(row_min=row_min, row_max=row_max, cols=cols)
