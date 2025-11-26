"""
Command-line interface for FastSurfer surface reconstruction.

Uses Typer for a modern, type-hint based CLI.
"""

from pathlib import Path
from typing import Optional
import logging
import sys

import typer
from rich.console import Console
from rich.logging import RichHandler

from . import __version__
from .config import ReconSurfConfig, AtlasConfig, ProcessingConfig
from .pipeline import ReconSurfPipeline

# Initialize Typer app
app = typer.Typer(
    name="fastsurfer-recon",
    help="FastSurfer surface reconstruction pipeline for neuroimaging.",
    add_completion=False,
    rich_markup_mode="rich",
)

console = Console()


def setup_logging(verbose: int = 1) -> None:
    """
    Set up logging with Rich handler.
    
    Parameters
    ----------
    verbose : int
        Verbosity level (0=WARNING, 1=INFO, 2=DEBUG)
    """
    level_map = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    level = level_map.get(verbose, logging.INFO)
    
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"[bold blue]FastSurfer Recon[/bold blue] version {__version__}")
        raise typer.Exit()


@app.command("run")
def run(
    # Required arguments
    subject_id: str = typer.Option(
        ..., 
        "--sid", 
        help="Subject ID",
    ),
    subjects_dir: Path = typer.Option(
        ..., 
        "--sd", 
        help="Subjects directory (SUBJECTS_DIR)",
        exists=False,  # Will be created if needed
    ),
    t1: Optional[Path] = typer.Option(
        None, 
        "--t1", 
        help="T1-weighted input image (conformed). Optional - if not provided, assumes orig.mgz exists in mri/",
        exists=True,
    ),
    segmentation: Optional[Path] = typer.Option(
        None, 
        "--seg", "--asegdkt_segfile",
        help="Segmentation file (aparc+aseg). Optional - if not provided, assumes aparc+aseg.orig.mgz exists in mri/",
        exists=True,
    ),
    # Atlas options
    atlas: str = typer.Option(
        "ARM2", 
        "--atlas", 
        help="Atlas name (ARM2, DKT, etc.)",
    ),
    # Processing options
    threads: int = typer.Option(
        1, 
        "--threads", 
        help="Number of threads",
        min=1,
    ),
    # Non-human options (defaults for macaque)
    skip_cc: bool = typer.Option(
        True, 
        "--no-cc/--cc", 
        help="Skip corpus callosum segmentation",
    ),
    skip_talairach: bool = typer.Option(
        True, 
        "--no-talairach/--talairach", 
        help="Skip Talairach registration",
    ),
    skip_topology_fix: bool = typer.Option(
        False, 
        "--nofix/--fix", 
        help="Skip topology fix",
    ),
    # Surface registration
    do_surf_reg: bool = typer.Option(
        False, 
        "--surfreg/--no-surfreg", 
        help="Run surface registration to fsaverage",
    ),
    # Method options
    fs_tessellation: bool = typer.Option(
        False, 
        "--fstess/--mctess", 
        help="Use FreeSurfer tessellation instead of marching cubes",
    ),
    fs_qsphere: bool = typer.Option(
        False, 
        "--fsqsphere/--spectral", 
        help="Use FreeSurfer qsphere instead of spectral projection",
    ),
    fs_aparc: bool = typer.Option(
        False, 
        "--fsaparc/--mapped-aparc", 
        help="Use FreeSurfer aparc instead of mapped parcellation",
    ),
    # Optional inputs
    mask: Optional[Path] = typer.Option(
        None, 
        "--mask", 
        help="Brain mask file",
        exists=True,
    ),
    # Config file
    config_file: Optional[Path] = typer.Option(
        None, 
        "--config", "-c",
        help="YAML configuration file (overrides other options)",
        exists=True,
    ),
    # Output options
    verbose: int = typer.Option(
        1, 
        "--verbose", "-v", 
        help="Verbosity level (0-2)",
        min=0,
        max=2,
    ),
    # Version
    version: bool = typer.Option(
        False, 
        "--version", 
        callback=version_callback,
        is_eager=True,
        help="Show version and exit",
    ),
) -> None:
    """
    Run the surface reconstruction pipeline.
    
    This command expects files prepared by FastSurferCNN post-processing:
    - mri/orig.mgz (conformed T1)
    - mri/aparc.{atlas}atlas+aseg.orig.mgz (copy of .orig.mgz)
    - mri/mask.mgz (brain mask, optional)
    
    The --t1 and --seg options are optional. If not provided, the pipeline
    assumes these files already exist in the subject's mri/ directory.
    
    Produces FreeSurfer-compatible surface outputs including white matter
    and pial surfaces, cortical parcellation, and morphometric measures.
    
    [bold]Example:[/bold]
    
        # Files already prepared by FastSurferCNN:
        fastsurfer-recon run --sid sub-001 --sd /data/subjects --atlas ARM2
        
        # Or provide explicit paths:
        fastsurfer-recon run --sid sub-001 --sd /data/subjects \\
            --t1 /data/subjects/sub-001/mri/orig.mgz \\
            --seg /data/subjects/sub-001/mri/aparc.ARM2atlas+aseg.orig.mgz \\
            --atlas ARM2 --threads 8
    """
    setup_logging(verbose)
    logger = logging.getLogger(__name__)
    
    console.print(f"\n[bold blue]FastSurfer Surface Reconstruction[/bold blue] v{__version__}\n")
    
    try:
        # Build configuration
        if config_file:
            logger.info(f"Loading configuration from {config_file}")
            config = ReconSurfConfig.from_yaml(
                config_file,
                subject_id=subject_id,
                subjects_dir=subjects_dir,
                t1_input=t1,
                segmentation=segmentation,
            )
        else:
            config = ReconSurfConfig(
                subject_id=subject_id,
                subjects_dir=subjects_dir,
                t1_input=t1,
                segmentation=segmentation,
                mask=mask,
                atlas=AtlasConfig(name=atlas),
                processing=ProcessingConfig(
                    threads=threads,
                    skip_cc=skip_cc,
                    skip_talairach=skip_talairach,
                    skip_topology_fix=skip_topology_fix,
                    do_surf_reg=do_surf_reg,
                    use_fs_tessellation=fs_tessellation,
                    use_fs_qsphere=fs_qsphere,
                    use_fs_aparc=fs_aparc,
                ),
                verbose=verbose,
            )
        
        # Print configuration summary
        console.print("[bold]Configuration:[/bold]")
        console.print(f"  Subject ID: {config.subject_id}")
        console.print(f"  Subjects Dir: {config.subjects_dir}")
        console.print(f"  Atlas: {config.atlas.name}")
        console.print(f"  Threads: {config.processing.threads}")
        console.print(f"  Skip CC: {config.processing.skip_cc}")
        console.print(f"  Skip Talairach: {config.processing.skip_talairach}")
        console.print(f"  Skip Topology Fix: {config.processing.skip_topology_fix}")
        console.print()
        
        # Run pipeline
        pipeline = ReconSurfPipeline(config)
        pipeline.run()
        
        console.print("\n[bold green]✓ Pipeline completed successfully![/bold green]\n")
        
    except Exception as e:
        console.print(f"\n[bold red]✗ Error:[/bold red] {e}\n")
        logger.exception("Pipeline failed")
        raise typer.Exit(1)


@app.command("info")
def info() -> None:
    """
    Show version and environment information.
    
    Displays version, FreeSurfer configuration, and system information.
    """
    import os
    import platform
    
    console.print(f"\n[bold blue]FastSurfer Recon[/bold blue] v{__version__}\n")
    
    console.print("[bold]Environment:[/bold]")
    
    # FreeSurfer
    fs_home = os.environ.get("FREESURFER_HOME", "[not set]")
    console.print(f"  FREESURFER_HOME: {fs_home}")
    
    if fs_home != "[not set]":
        build_stamp = Path(fs_home) / "build-stamp.txt"
        if build_stamp.exists():
            console.print(f"  FreeSurfer version: {build_stamp.read_text().strip()}")
    
    # SUBJECTS_DIR
    subjects_dir = os.environ.get("SUBJECTS_DIR", "[not set]")
    console.print(f"  SUBJECTS_DIR: {subjects_dir}")
    
    console.print()
    console.print("[bold]System:[/bold]")
    console.print(f"  Python: {platform.python_version()}")
    console.print(f"  Platform: {platform.platform()}")
    console.print()


@app.command("validate")
def validate(
    config_file: Path = typer.Argument(
        ...,
        help="YAML configuration file to validate",
        exists=True,
    ),
) -> None:
    """
    Validate a configuration file.
    
    Checks that all required fields are present and valid,
    and that input files exist.
    """
    try:
        config = ReconSurfConfig.from_yaml(config_file)
        console.print(f"[bold green]✓ Configuration is valid[/bold green]")
        console.print(f"\n[bold]Summary:[/bold]")
        console.print(f"  Subject: {config.subject_id}")
        console.print(f"  Atlas: {config.atlas.name}")
        console.print(f"  Threads: {config.processing.threads}")
    except Exception as e:
        console.print(f"[bold red]✗ Configuration error:[/bold red] {e}")
        raise typer.Exit(1)


# Main entry point
if __name__ == "__main__":
    app()

