# Copyright 2022 Image Analysis Lab, German Center for Neurodegenerative Diseases (DZNE), Bonn
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# IMPORTS
import os
from collections.abc import MutableSequence
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Literal, TypedDict, cast, overload

import requests
import torch
import yacs.config
import yaml

from FastSurferCNN.utils import Plane, logging
from FastSurferCNN.utils.parser_defaults import FASTSURFER_ROOT

if TYPE_CHECKING:
    from torch.optim import lr_scheduler as Scheduler
else:
    class Scheduler:
        ...

LOGGER = logging.getLogger(__name__)

# Defaults
YAML_DEFAULT = FASTSURFER_ROOT / "FastSurferCNN/config/checkpoint_paths.yaml"


class CheckpointConfigDict(TypedDict, total=False):
    url: list[str]
    checkpoint: dict[Plane, Path]
    config: dict[Plane, Path]


CheckpointConfigFields = Literal["checkpoint", "config", "url"]


@lru_cache
def load_checkpoint_config(filename: Path | str = YAML_DEFAULT) -> CheckpointConfigDict:
    """
    Load the plane dictionary from the yaml file.

    Parameters
    ----------
    filename : Path, str
        Path to the yaml file. Either absolute or relative to the FastSurfer root
        directory.

    Returns
    -------
    CheckpointConfigDict
        A dictionary representing the contents of the yaml file.
    """
    if not filename.absolute():
        filename = FASTSURFER_ROOT / filename

    with open(filename) as file:
        data = yaml.load(file, Loader=yaml.FullLoader)

    # Only "checkpoint" is required; "url" is optional (for local checkpoints)
    required_fields = ("checkpoint",)
    checks = [k not in data for k in required_fields]
    if any(checks):
        missing = tuple(k for k, c in zip(required_fields, checks, strict=False) if c)
        message = f"The file {filename} is not valid, missing key(s): {missing}"
        raise OSError(message)
    
    # Make "url" optional - default to empty list if not provided
    if "url" not in data:
        data["url"] = []
    elif isinstance(data["url"], str):
        data["url"] = [data["url"]]
    else:
        data["url"] = list(data["url"])
    for key in ("config", "checkpoint"):
        if key in data:
            data[key] = {k: Path(v) for k, v in data[key].items()}
    return data


@overload
def load_checkpoint_config_defaults(
        filetype: Literal["checkpoint", "config"],
        filename: str | Path = YAML_DEFAULT,
) -> dict[Plane, Path]: ...


@overload
def load_checkpoint_config_defaults(
        configtype: Literal["url"],
        filename: str | Path = YAML_DEFAULT,
) -> list[str]: ...

@lru_cache
def load_checkpoint_config_defaults(
        configtype: CheckpointConfigFields,
        filename: str | Path = YAML_DEFAULT,
) -> dict[Plane, Path] | list[str]:
    """
    Get the default value for a specific plane or the url.

    Parameters
    ----------
    configtype : "checkpoint", "config", "url"
        Type of value.
    filename : str, Path
        The path to the yaml file. Either absolute or relative to the FastSurfer root
        directory.

    Returns
    -------
    dict[Plane, Path], list[str]
        Default value for the plane.
    """
    if not isinstance(filename, Path):
        filename = Path(filename)

    configtype = cast(CheckpointConfigFields, configtype.lower())
    if configtype not in ("url", "checkpoint", "config"):
        raise ValueError("Type must be 'url', 'checkpoint' or 'config'")

    return load_checkpoint_config(filename)[configtype]


def create_checkpoint_dir(expr_dir: os.PathLike, expr_num: int):
    """
    Create the checkpoint dir if not exists.

    Parameters
    ----------
    expr_dir : Union[os.PathLike]
        Directory to create.
    expr_num : int
        Experiment number.

    Returns
    -------
    checkpoint_dir
        Directory of the checkpoint.
    """
    checkpoint_dir = os.path.join(expr_dir, "checkpoints", str(expr_num))
    os.makedirs(checkpoint_dir, exist_ok=True)
    return checkpoint_dir


def get_checkpoint(ckpt_dir: str, epoch: int) -> str:
    """
    Find the standardizes checkpoint name for the checkpoint in the directory
    ckpt_dir for the given epoch.

    Parameters
    ----------
    ckpt_dir : str
        Checkpoint directory.
    epoch : int
        Number of the epoch.

    Returns
    -------
    checkpoint_dir
        Standardizes checkpoint name.
    """
    checkpoint_dir = os.path.join(
        ckpt_dir, f"Epoch_{epoch:05d}_training_state.pkl"
    )
    return checkpoint_dir


def get_checkpoint_path(
        log_dir: Path | str, resume_experiment: str | int | None = None
) -> MutableSequence[Path]:
    """
    Find the paths to checkpoints from the experiment directory.

    Parameters
    ----------
    log_dir : Path, str
        Experiment directory.
    resume_experiment : Union[str, int, None]
        Sub-experiment to search in for a model (Default value = None).

    Returns
    -------
    prior_model_paths : MutableSequence[Path]
        A list of filenames for checkpoints.
    """
    if resume_experiment == "Default" or resume_experiment is None:
        return []
    if not isinstance(log_dir, Path):
        log_dir = Path(log_dir)
    checkpoint_path = log_dir / "checkpoints" / str(resume_experiment)
    prior_model_paths = sorted(
        checkpoint_path.glob("Epoch_*"), key=lambda p: p.stat().st_mtime
    )
    return list(prior_model_paths)


def load_from_checkpoint(
        checkpoint_path: str | Path,
        model: torch.nn.Module,
        optimizer: torch.optim.Optimizer | None = None,
        scheduler: Scheduler | None = None,
        fine_tune: bool = False,
        drop_classifier: bool = False,
):
    """
    Load the model from the given experiment number.

    Parameters
    ----------
    checkpoint_path : str, Path
        Path to the checkpoint.
    model : torch.nn.Module
        Network model.
    optimizer : Optional[torch.optim.Optimizer]
        Network optimizer (Default value = None).
    scheduler : Optional[Scheduler]
        Network scheduler (Default value = None).
    fine_tune : bool
        Whether to fine tune or not (Default value = False).
    drop_classifier : bool
        Whether to drop the classifier or not (Default value = False).

    Returns
    -------
    loaded_epoch : int
        Epoch number.
    """
    # WARNING: weights_only=False can cause unsafe code execution, but here the
    # checkpoint can be considered to be from a safe source
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)

    if drop_classifier:
        classifier_conv = ["classifier.conv.weight", "classifier.conv.bias"]
        for key in classifier_conv:
            if key in checkpoint["model_state"]:
                del checkpoint["model_state"][key]

    # if this is a multi-gpu model, get the underlying model
    mod = model.module if hasattr(model, "module") else model
    mod.load_state_dict(checkpoint["model_state"], strict=not drop_classifier)

    if not fine_tune:
        if optimizer is not None:
            optimizer.load_state_dict(checkpoint["optimizer_state"])
        if scheduler is not None and "scheduler_state" in checkpoint.keys():
            scheduler.load_state_dict(checkpoint["scheduler_state"])

    return checkpoint["epoch"] + 1, checkpoint.get("best_metric", None)


def save_checkpoint(
        checkpoint_dir: str | Path,
        epoch: int,
        best_metric,
        num_gpus: int,
        cfg: yacs.config.CfgNode,
        model: torch.nn.Module,
        optimizer: torch.optim.Optimizer,
        scheduler: Scheduler | None = None,
        best: bool = False,
) -> None:
    """
    Save the state of training for resume or fine-tune.

    Parameters
    ----------
    checkpoint_dir : str, Path
        Path to the checkpoint directory.
    epoch : int
        Current epoch.
    best_metric : best_metric
        Best calculated metric.
    num_gpus : int
        Number of used gpus.
    cfg : yacs.config.CfgNode
        Configuration node.
    model : torch.nn.Module
        Used network model.
    optimizer : torch.optim.Optimizer
        Used network optimizer.
    scheduler : Optional[Scheduler]
        Used network scheduler. Optional (Default value = None).
    best : bool, default=False
        Whether this was the best checkpoint so far (Default value = False).
    """
    save_name = f"Epoch_{epoch:05d}_training_state.pkl"
    saving_model = model.module if num_gpus > 1 else model
    checkpoint = {
        "model_state": saving_model.state_dict(),
        "optimizer_state": optimizer.state_dict(),
        "epoch": epoch,
        "best_metric": best_metric,
        "config": cfg.dump(),
    }

    # Phase 2: Add atlas metadata to checkpoint for robust inference
    # This ensures the checkpoint is self-contained and doesn't rely on external LUT files
    try:
        from FastSurferCNN.atlas.atlas_manager import AtlasManager
        
        # Extract atlas name from config
        atlas_name = None
        if hasattr(cfg.DATA, 'CLASS_OPTIONS') and cfg.DATA.CLASS_OPTIONS:
            atlas_name = cfg.DATA.CLASS_OPTIONS[0]
        
        if atlas_name:
            # Initialize AtlasManager to get the dense_to_sparse mapping
            # This is the CRITICAL mapping that converts model output indices to label IDs
            atlas_manager = AtlasManager(atlas_name)
            dense_to_sparse = atlas_manager.get_dense_to_sparse_mapping()
            
            checkpoint["atlas_metadata"] = {
                "atlas_name": atlas_name.upper(),
                "num_classes": cfg.MODEL.NUM_CLASSES,
                "plane": cfg.DATA.PLANE,
                "dense_to_sparse_mapping": dense_to_sparse.tolist(),  # Convert numpy array to list for serialization
            }
            LOGGER.info(f"Saving checkpoint with atlas metadata: {atlas_name} ({cfg.MODEL.NUM_CLASSES} classes)")
        else:
            LOGGER.warning("Could not extract atlas name from config - checkpoint will not contain atlas metadata")
    except Exception as e:
        LOGGER.warning(f"Failed to add atlas metadata to checkpoint: {e}")
        # Continue saving without metadata (backward compatible)

    if scheduler is not None:
        checkpoint["scheduler_state"] = scheduler.state_dict()
    if not isinstance(checkpoint_dir, Path):
        checkpoint_dir = Path(checkpoint_dir)

    torch.save(checkpoint, checkpoint_dir / save_name)

    if best:
        remove_ckpt(checkpoint_dir / "Best_training_state.pkl")
        torch.save(checkpoint, checkpoint_dir / "Best_training_state.pkl")


def save_best_checkpoint(
        checkpoint_dir: str | Path,
        epoch: int,
        best_metric,
        num_gpus: int,
        cfg: yacs.config.CfgNode,
        model: torch.nn.Module,
        optimizer: torch.optim.Optimizer,
        scheduler: Scheduler | None = None,
) -> None:
    """
    Save only the best model checkpoint (overwrites previous best).
    This function only saves the Best_training_state.pkl file without creating individual epoch files.

    Parameters
    ----------
    checkpoint_dir : str, Path
        Path to the checkpoint directory.
    epoch : int
        Current epoch.
    best_metric : best_metric
        Best calculated metric.
    num_gpus : int
        Number of used gpus.
    cfg : yacs.config.CfgNode
        Configuration node.
    model : torch.nn.Module
        Used network model.
    optimizer : torch.optim.Optimizer
        Used network optimizer.
    scheduler : Optional[Scheduler]
        Used network scheduler. Optional (Default value = None).
    """
    saving_model = model.module if num_gpus > 1 else model
    checkpoint = {
        "model_state": saving_model.state_dict(),
        "optimizer_state": optimizer.state_dict(),
        "epoch": epoch,
        "best_metric": best_metric,
        "config": cfg.dump(),
    }

    # Phase 2: Add atlas metadata to checkpoint for robust inference
    # This ensures the checkpoint is self-contained and doesn't rely on external LUT files
    try:
        from FastSurferCNN.atlas.atlas_manager import AtlasManager
        
        # Extract atlas name from config
        atlas_name = None
        if hasattr(cfg.DATA, 'CLASS_OPTIONS') and cfg.DATA.CLASS_OPTIONS:
            atlas_name = cfg.DATA.CLASS_OPTIONS[0]
        
        if atlas_name:
            # Initialize AtlasManager to get the dense_to_sparse mapping
            # This is the CRITICAL mapping that converts model output indices to label IDs
            atlas_manager = AtlasManager(atlas_name)
            dense_to_sparse = atlas_manager.get_dense_to_sparse_mapping()
            
            checkpoint["atlas_metadata"] = {
                "atlas_name": atlas_name.upper(),
                "num_classes": cfg.MODEL.NUM_CLASSES,
                "plane": cfg.DATA.PLANE,
                "dense_to_sparse_mapping": dense_to_sparse.tolist(),  # Convert numpy array to list for serialization
            }
            LOGGER.info(f"Saving best checkpoint with atlas metadata: {atlas_name} ({cfg.MODEL.NUM_CLASSES} classes)")
        else:
            LOGGER.warning("Could not extract atlas name from config - checkpoint will not contain atlas metadata")
    except Exception as e:
        LOGGER.warning(f"Failed to add atlas metadata to checkpoint: {e}")
        # Continue saving without metadata (backward compatible)

    if scheduler is not None:
        checkpoint["scheduler_state"] = scheduler.state_dict()
    if not isinstance(checkpoint_dir, Path):
        checkpoint_dir = Path(checkpoint_dir)

    # Remove old best checkpoint and save new one
    remove_ckpt(checkpoint_dir / "Best_training_state.pkl")
    torch.save(checkpoint, checkpoint_dir / "Best_training_state.pkl")


def extract_atlas_metadata(checkpoint_path: str | Path) -> dict | None:
    """
    Extract atlas metadata from a checkpoint without loading the full model.
    
    This function reads only the metadata from a checkpoint to determine:
    - Which atlas the model was trained on
    - The dense-to-sparse label mapping
    - Number of classes and plane
    
    Supports both new checkpoints (with atlas_metadata) and legacy checkpoints
    (extracts from config YAML).
    
    Parameters
    ----------
    checkpoint_path : str, Path
        Path to the checkpoint file.
    
    Returns
    -------
    dict, None
        Dictionary with keys:
        - atlas_name: str (e.g., "ARM2", "ARM3")
        - num_classes: int
        - plane: str
        - dense_to_sparse_mapping: np.ndarray or None
        - source: str ("atlas_metadata" or "config_fallback")
        Returns None if extraction fails.
    
    Examples
    --------
    >>> metadata = extract_atlas_metadata("checkpoint.pkl")
    >>> print(f"Atlas: {metadata['atlas_name']}, Classes: {metadata['num_classes']}")
    Atlas: ARM2, Classes: 71
    """
    try:
        # Load checkpoint without loading model weights
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
        
        # Try new format first (Phase 2: with atlas_metadata)
        if "atlas_metadata" in checkpoint:
            metadata = checkpoint["atlas_metadata"]
            import numpy as np
            return {
                "atlas_name": metadata["atlas_name"],
                "num_classes": metadata["num_classes"],
                "plane": metadata["plane"],
                "dense_to_sparse_mapping": np.array(metadata["dense_to_sparse_mapping"], dtype=np.int32),
                "source": "atlas_metadata",
            }
        
        # Fallback: extract from config (legacy checkpoints)
        if "config" in checkpoint:
            config_str = checkpoint["config"]
            config_dict = yaml.safe_load(config_str)
            
            atlas_name = None
            if "DATA" in config_dict and "CLASS_OPTIONS" in config_dict["DATA"]:
                class_options = config_dict["DATA"]["CLASS_OPTIONS"]
                if class_options:
                    atlas_name = class_options[0].upper()
            
            num_classes = config_dict.get("MODEL", {}).get("NUM_CLASSES")
            plane = config_dict.get("DATA", {}).get("PLANE")
            
            if atlas_name:
                # Try to reconstruct dense_to_sparse mapping from AtlasManager
                try:
                    from FastSurferCNN.atlas.atlas_manager import AtlasManager
                    atlas_manager = AtlasManager(atlas_name)
                    dense_to_sparse = atlas_manager.get_dense_to_sparse_mapping()
                except Exception:
                    dense_to_sparse = None
                
                return {
                    "atlas_name": atlas_name,
                    "num_classes": num_classes,
                    "plane": plane,
                    "dense_to_sparse_mapping": dense_to_sparse,
                    "source": "config_fallback",
                }
        
        LOGGER.warning(f"Could not extract atlas metadata from checkpoint {checkpoint_path}")
        return None
        
    except Exception as e:
        LOGGER.error(f"Failed to extract atlas metadata from {checkpoint_path}: {e}")
        return None


def remove_ckpt(ckpt: str | Path):
    """
    Remove the checkpoint.

    Parameters
    ----------
    ckpt : str, Path
        Path and filename to the checkpoint.
    """
    try:
        Path(ckpt).unlink()
    except FileNotFoundError:
        pass


def download_checkpoint(
        checkpoint_name: str,
        checkpoint_path: str | Path,
        urls: list[str],
) -> None:
    """
    Download a checkpoint file.

    Raises an HTTPError if the file is not found or the server is not reachable.

    Parameters
    ----------
    checkpoint_name : str
        Name of checkpoint.
    checkpoint_path : Path, str
        Path of the file in which the checkpoint will be saved.
    urls : list[str]
        List of URLs of checkpoint hosting sites.
    """
    response = None
    for url in urls:
        try:
            LOGGER.info(f"Downloading checkpoint {checkpoint_name} from {url}")
            response = requests.get(
                url + "/" + checkpoint_name,
                verify=True,
                timeout=(5, None),  # (connect timeout: 5 sec, read timeout: None)
            )
            # Raise error if file does not exist:
            response.raise_for_status()
            break

        except requests.exceptions.RequestException as e:
            LOGGER.warning(f"Server {url} not reachable ({type(e).__name__}): {e}")
            if isinstance(e, requests.exceptions.HTTPError):
                LOGGER.warning(f"Response code: {e.response.status_code}")

    if response is None:
        links = ', '.join(u.removeprefix('https://')[:22] + "..." for u in urls)
        raise requests.exceptions.RequestException(
            f"Failed downloading the checkpoint {checkpoint_name} from {links}."
        )
    else:
        response.raise_for_status()  # Raise error if no server is reachable

    with open(checkpoint_path, "wb") as f:
        f.write(response.content)


def check_and_download_ckpts(checkpoint_path: Path | str, urls: list[str]) -> None:
    """
    Check and download a checkpoint file, if it does not exist.

    Parameters
    ----------
    checkpoint_path : Path, str
        Path of the file in which the checkpoint will be saved.
    urls : list[str]
        URLs of checkpoint hosting site.
    """
    if not isinstance(checkpoint_path, Path):
        checkpoint_path = Path(checkpoint_path)
    # Download checkpoint file from url if it does not exist
    if not checkpoint_path.exists():
        if not urls:
            # No URLs provided, cannot download - raise error
            raise FileNotFoundError(
                f"Checkpoint file {checkpoint_path} does not exist and no download URLs provided. "
                f"Please ensure the checkpoint file exists at the specified path."
            )
        # create dir if it does not exist
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        download_checkpoint(checkpoint_path.name, checkpoint_path, urls)


def get_checkpoints(*checkpoints: Path | str | None, urls: list[str]) -> None:
    """
    Check and download checkpoint files if not exist.

    Parameters
    ----------
    *checkpoints : Path, str, None
        Paths of the files in which the checkpoint will be saved.
        None values are skipped (for optional planes).
    urls : Path, str
        URLs of checkpoint hosting sites.
    """
    try:
        # Filter out None values to support optional planes
        valid_checkpoints = [ckpt for ckpt in checkpoints if ckpt is not None]
        for file in map(Path, valid_checkpoints):
            if not file.is_absolute() and file.parts[0] != ".":
                file = FASTSURFER_ROOT / file
            check_and_download_ckpts(file, urls)
    except requests.exceptions.HTTPError:
        LOGGER.error(f"Could not find nor download checkpoints from {urls}")
        raise
