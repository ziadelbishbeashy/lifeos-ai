"""Project-domain model facade.

The canonical model remains in legacy ``models.py`` during Foundation V2.
Moving physical model definitions happens only after the PostgreSQL baseline is
proven, avoiding migration metadata churn during the database cutover.
"""
from models import Project, ProjectQuestion
__all__ = ["Project", "ProjectQuestion"]
