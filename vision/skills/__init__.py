"""V2 Vision Skills — stateless single-responsibility detectors / planners."""

from vision.skills.red_zone_polygon import RedZonePolygonSkill
from vision.skills.isometric_grid import IsometricGridSkill
from vision.skills.safe_corridor import SafeCorridorSkill
from vision.skills.obstacle_detector import ObstacleDetectorSkill
from vision.skills.target_locator import TargetLocatorSkill
from vision.skills.corner_selector import CornerSelectorSkill

__all__ = [
    "RedZonePolygonSkill",
    "IsometricGridSkill",
    "SafeCorridorSkill",
    "ObstacleDetectorSkill",
    "TargetLocatorSkill",
    "CornerSelectorSkill",
]
