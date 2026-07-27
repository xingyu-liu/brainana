"""
Base class for pipeline stages.

All pipeline stages inherit from PipelineStage and implement
the _run() method.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, TYPE_CHECKING
import logging
import time

if TYPE_CHECKING:
    from ..config import ReconSurfConfig
    from ..io.subjects_dir import SubjectsDir


class StageOutputError(RuntimeError):
    """A stage returned successfully but did not produce its declared outputs.

    Usually means an external command exited 0 without writing, or an early
    `return` inside the stage skipped work it was supposed to do.
    """


class PipelineStage(ABC):
    """
    Abstract base class for pipeline stages.

    Each stage represents a discrete processing step in the
    surface reconstruction pipeline.

    Parameters
    ----------
    config : ReconSurfConfig
        Pipeline configuration
    subjects_dir : SubjectsDir
        Subject directory manager
    hemi : str, optional
        Hemisphere ('lh' or 'rh') for hemisphere-specific stages
    """

    # Stage name (override in subclasses)
    name: str = "base_stage"

    # Stage description
    description: str = "Base pipeline stage"

    def __init__(
        self,
        config: "ReconSurfConfig",
        subjects_dir: "SubjectsDir",
        hemi: Optional[str] = None,
    ):
        self.config = config
        self.sd = subjects_dir
        self.hemi = hemi
        self.logger = logging.getLogger(f"fastsurfer_surfrecon.stages.{self.name}")

        # Timing
        self._start_time: Optional[float] = None
        self._end_time: Optional[float] = None

    def run(self) -> None:
        """
        Run the stage with timing and logging.

        This method handles:
        - Skip checking
        - Logging
        - Timing
        - Error handling
        """
        # Get stage identifier for command logging
        stage_id = self._get_stage_id()

        # Extract stage number prefix (e.g., "s01" from "s01_volume_prep")
        stage_prefix = ""
        if stage_id:
            # Extract "s##" from stage_id like "s01_volume_prep"
            parts = stage_id.split("_", 1)
            if parts and parts[0].startswith("s") and len(parts[0]) >= 2:
                stage_prefix = parts[0] + " "

        stage_desc = f"{stage_prefix}{self.name}" if stage_prefix else f"{self.name}"
        if self.hemi:
            stage_desc += f" ({self.hemi})"

        # Check if disabled
        if self.is_disabled():
            self.logger.info(f"Skipping {stage_desc} (disabled)")
            return

        # Check if should skip (already complete)
        if self.should_skip():
            self.logger.info(f"Skipping {stage_desc} (already complete)")
            return

        # Apply per-stage numerical library thread caps. For hemisphere stages
        # this uses the already-halved thread budget when parallel hemis are on.
        from ..utils.threading import set_numerical_threads

        set_numerical_threads(self.threads)

        # Set current stage identifier for command logging
        if stage_id:
            from ..wrappers.base import set_current_stage_id

            set_current_stage_id(stage_id)

        self.logger.info(f"Starting {stage_desc}")
        self._start_time = time.time()

        try:
            self._run()
        except Exception as e:
            self.logger.error(f"Failed {stage_desc}: {e}")
            raise
        finally:
            # Clear stage identifier after stage completes
            if stage_id:
                from ..wrappers.base import set_current_stage_id

                set_current_stage_id(None)

        # Postcondition. Runs before "Completed" is logged, so that message
        # means the stage produced what it promised rather than merely that
        # _run() returned without raising.
        try:
            self.verify_outputs()
        except Exception as e:
            self.logger.error(f"Failed {stage_desc} (postcondition): {e}")
            raise

        self._end_time = time.time()
        elapsed = self._end_time - self._start_time
        self.logger.info(f"Completed {stage_desc} in {elapsed:.1f}s")

    def _get_stage_id(self) -> Optional[str]:
        """
        Get stage identifier (e.g., 's07_wm_filled') from module name.

        Extracts the identifier from the module name which follows
        the pattern 'fastsurfer_surfrecon.stages.s##_name'.

        Returns
        -------
        str, optional
            Stage identifier like 's07_wm_filled', or None if not found
        """
        import inspect

        module = inspect.getmodule(self)
        if module:
            module_name = module.__name__
            # Extract stage identifier from module name
            # e.g., 'fastsurfer_surfrecon.stages.s07_wm_filled' -> 's07_wm_filled'
            if ".stages." in module_name:
                stage_id = module_name.split(".stages.")[-1]
                return stage_id
        return None

    @abstractmethod
    def _run(self) -> None:
        """
        Actual stage implementation.

        Subclasses must implement this method with the actual
        processing logic.
        """
        pass

    def is_disabled(self) -> bool:
        """
        Check if stage is disabled via configuration.

        Override in subclasses to check config flags that disable the stage.
        This is separate from should_skip() which checks if outputs exist.

        Returns
        -------
        bool
            True if stage is disabled
        """
        return False

    def expected_outputs(self) -> list[Path]:
        """
        Files this stage guarantees to have produced when it succeeds.

        Declaring these drives both the skip check and the postcondition, so a
        stage cannot claim to be complete without them. Return an empty list
        for stages that are not cacheable (they will always run).

        IMPORTANT: list what this stage writes *last*, not just its headline
        artifact. A stage that writes output A early and output B at the end
        must declare both, or a run that died between them looks complete on
        the next invocation and its later steps are silently skipped.

        Returns
        -------
        list[Path]
            Output paths, or [] if the stage should never be skipped.
        """
        return []

    def verify_outputs(self) -> None:
        """
        Postcondition checked after _run() and before the stage is logged done.

        The default asserts every declared output exists. Override to add
        semantic checks (e.g. mesh invariants) and call super() first.

        Raises
        ------
        StageOutputError
            If any declared output is missing.
        """
        missing = [p for p in self.expected_outputs() if not p.exists()]
        if missing:
            where = f" ({self.hemi})" if self.hemi else ""
            raise StageOutputError(
                f"{self.name}{where} finished without producing: "
                + ", ".join(str(m) for m in missing)
            )

    def should_skip(self) -> bool:
        """
        Check if stage should be skipped (outputs already exist).

        Defaults to "every declared output exists". Override in subclasses only
        where that rule does not apply -- e.g. stages whose outputs vary by
        config branch, or which must always re-run. This should NOT check if
        the stage is disabled - use is_disabled() for that.

        Returns
        -------
        bool
            True if stage should be skipped (outputs exist)
        """
        outputs = self.expected_outputs()
        return bool(outputs) and self.outputs_exist(*outputs)

    def outputs_exist(self, *paths: Path) -> bool:
        """
        Check if all output files exist.

        Utility method for implementing should_skip().

        Parameters
        ----------
        *paths : Path
            Output file paths to check

        Returns
        -------
        bool
            True if all files exist
        """
        return all(p.exists() for p in paths)

    @property
    def elapsed_time(self) -> Optional[float]:
        """Get elapsed time in seconds, or None if not run yet."""
        if self._start_time is None or self._end_time is None:
            return None
        return self._end_time - self._start_time

    # Convenience properties for common paths

    @property
    def mdir(self) -> Path:
        """MRI directory path."""
        return self.sd.mri_dir

    @property
    def sdir(self) -> Path:
        """Surface directory path."""
        return self.sd.surf_dir

    @property
    def ldir(self) -> Path:
        """Label directory path."""
        return self.sd.label_dir

    @property
    def threads(self) -> int:
        """Number of threads to use."""
        if self.hemi and self.config.processing.parallel_hemis:
            # Use half threads when processing hemispheres in parallel
            return max(1, self.config.processing.threads // 2)
        return self.config.processing.threads


class HemisphereStage(PipelineStage):
    """
    Base class for hemisphere-specific stages.

    Requires hemi parameter and provides hemisphere-specific utilities.
    """

    def __init__(
        self, config: "ReconSurfConfig", subjects_dir: "SubjectsDir", hemi: str
    ):
        if hemi not in ("lh", "rh"):
            raise ValueError(f"hemi must be 'lh' or 'rh', got '{hemi}'")
        super().__init__(config, subjects_dir, hemi)

    @property
    def hemi_value(self) -> int:
        """Hemisphere value for filled volume (255 for lh, 127 for rh)."""
        return 255 if self.hemi == "lh" else 127

    def hemi_path(self, filename: str) -> Path:
        """
        Get hemisphere-prefixed path in surf directory.

        Parameters
        ----------
        filename : str
            Filename without hemisphere prefix

        Returns
        -------
        Path
            Full path with hemisphere prefix
        """
        return self.sdir / f"{self.hemi}.{filename}"

    def hemi_label(self, filename: str) -> Path:
        """
        Get hemisphere-prefixed path in label directory.

        Parameters
        ----------
        filename : str
            Filename without hemisphere prefix

        Returns
        -------
        Path
            Full path with hemisphere prefix
        """
        return self.ldir / f"{self.hemi}.{filename}"
