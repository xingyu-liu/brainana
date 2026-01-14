def apply_mask(input: StepInput, brain_mask: Path, generate_tmean: bool = True) -> StepOutput:
    """
    Apply mask to image.
    
    Args:
        input: StepInput with input_file (4d or 3d), working_dir, config, metadata
        brain_mask: Path to brain mask
        generate_tmean: Whether to generate tmean
        
    Returns:
        StepOutput with masked image and tmean (if generated)
    """
    # Ensure working directory exists
    input.working_dir.mkdir(parents=True, exist_ok=True)

    if not brain_mask.exists():
        raise FileNotFoundError(f"Brain mask not found: {brain_mask}")

    # Apply mask
    from ..operations.preprocessing import apply_mask

    output_name = input.output_name or "func_brain.nii.gz"
    result = apply_mask(
        imagef=str(input.input_file),
        maskf=str(brain_mask),
        working_dir=str(input.working_dir),
        output_name=output_name,
        logger=logger,
        generate_tmean=generate_tmean
    )

    output_file = Path(result["imagef_masked"])  # type: ignore[arg-type]
    additional_files = {"brain_mask": brain_mask}
    if generate_tmean and result.get("imagef_masked_tmean"):
        additional_files["tmean"] = Path(result["imagef_masked_tmean"])

    return StepOutput(
        output_file=output_file,
        metadata={
            "step": "apply_brain_mask",
            "modality": modality,
        },
        additional_files=additional_files,
    )