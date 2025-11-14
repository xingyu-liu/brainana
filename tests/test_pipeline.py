# %%
from pathlib import Path
import os
import logging
import time
from macacaMRIprep.workflow import AnatomicalProcessor, FunctionalProcessor
from macacaMRIprep.utils import setup_logging, get_logger, ensure_workflow_log_exists
from macacaMRIprep.environment import check_environment
from macacaMRIprep.config import get_config

# %%
# Get logger for this module
logger = get_logger(__name__)

def test_anat2template_preprocessing():
    # Get the test data directory using absolute paths
    test_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "test_datasets"))
    dataset_dir = os.path.join(test_dir, "newcastle")
    assert os.path.exists(dataset_dir), f"Test directory not found: {dataset_dir}"
    
    pipeline_name = "anat2template"  # Change this to "func2template" to test functional pipeline
    output_dir = dataset_dir + "_derivatives"

    # Define anat file
    anatf = os.path.join(dataset_dir, "sub-032104", "anat", "sub-032104_ses-003_run-1_T1w.nii.gz")
    assert os.path.exists(anatf), f"Input file not found: {anatf}"

    # template spec
    template_spec = "NMT2Sym:res-1"

    # Get default configuration
    config = get_config()
    
    # Update configuration for testing
    config.update({
        "general": {
            "verbose": 2,
            "overwrite": 1,
        },
        "anat": {
            "bias_correction": {
                "enabled": True,
            },
            "skullstripping": {
                "enabled": True
            }
        }
    })

    # Check environment variables
    check_environment(skullstripping=config.get("anat", {}).get("skullstripping", {}).get("enabled"))

    if pipeline_name == "anat2template":
        pipeline_output_dir = str(Path(output_dir) / 'anat')
        workflow = AnatomicalProcessor(
            anat_file=anatf,
            template_spec=template_spec,
            output_dir=pipeline_output_dir,
            config=config,
        )
        workflow_description = "anatomical to template registration"
   
    # Log test configuration
    logger.info("Test: starting test_anat2template_preprocessing")
    logger.debug(f"Data: test directory - {test_dir}")
    logger.debug(f"Data: input anatomical file - {anatf}")
    logger.debug(f"Data: template file - {template_spec}")
    
    # Verify that workflow.log was created during initialization
    working_dir = os.path.join(pipeline_output_dir, "working_dir")
    assert ensure_workflow_log_exists(working_dir), "workflow.log was not created during workflow initialization"
    logger.info("Test: ✓ workflow.log created successfully during workflow initialization")
    
    # Run the workflow
    logger.info(f"Test: running {pipeline_name} workflow")
    workflow.run()
    
    # Verify comprehensive logging
    workflow_log_file = os.path.join(working_dir, "workflow.log")
    assert os.path.exists(workflow_log_file), "workflow.log file not found"
    
    # Read and verify workflow.log content
    with open(workflow_log_file, 'r') as f:
        log_content = f.read()
    
    # Verify key log entries based on pipeline type
    expected_start_message = f"Starting {workflow_description} pipeline"
    assert expected_start_message in log_content, f"Workflow start not logged: expected '{expected_start_message}'"
    assert "Registration QC created" in log_content, "Workflow completion not logged"
    assert "Workflow logging initialization" in log_content or "Workflow logging initialized" in log_content, "Workflow logging initialization not logged"
    assert "Workflow initialized" in log_content, "Workflow initialization not logged"
    
    logger.info("✓ Comprehensive logging verified in workflow.log")

    # Verify pipeline state file
    logs_dir = os.path.join(working_dir, "logs")
    pipeline_state_file = os.path.join(logs_dir, "pipeline_state.json")
    assert os.path.exists(pipeline_state_file), "Pipeline state file not found"
    logger.info("✓ Pipeline state file created")
    
    logger.info("✓ All logging verification tests passed!")

def test_func2target_preprocessing():
    """Test func2template pipeline specifically"""
    # Get the test data directory using absolute paths
    test_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "test_datasets"))
    dataset_dir = os.path.join(test_dir, "newcastle")
    output_dir = dataset_dir + "_derivatives"

    funcf = os.path.join(dataset_dir, "sub-032104", "func", "sub-032104_ses-003_task-resting_run-1_bold.nii.gz")

    anatf = os.path.join(output_dir, "anat", "sub-032104_ses-003_run-1_desc-preproc_T1w_brain.nii.gz")
    anat2template_transform = os.path.join(output_dir, "anat", "sub-032104_ses-003_run-1_from-t1w_to-NMT2Sym_mode-image_xfm.h5")

    # test_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "test_datasets"))
    # dataset_dir = os.path.join(test_dir, "arcaro")
    # output_dir = dataset_dir + "_derivatives"
    # funcf = os.path.join(dataset_dir, "sub-baby6", "ses-150809", "func", "sub-baby6_ses-150809_task-vision_run-12_bold.nii.gz")
    
    # template spec
    template_spec = "NMT2Sym:res-1"

    # Get default configuration
    config = get_config()
    
    # Update configuration for testing
    config.update({
        "general": {
            "verbose": 2,
            "overwrite": 1,
        },
        "func": {
            "slice_timing": {
                "enabled": False
            },
            "motion_correction": {
                "dof": 6,
                "cost": "mutualinfo",
                "smooth": 1.0,
                "ref_vol": 'mid',   # int, 'Tmean', 'mid'
            },
            "skullstripping": {
                "enabled": False
            },
        },
        "registration": {
            "func2template_xfm_type": "syn"
        }
    })

    # Check environment variables
    check_environment(skullstripping=False)

    # Create functional processor
    func_output_dir = str(Path(output_dir) / 'func')
    workflow = FunctionalProcessor(
        func_file=funcf,
        target_type="anat",
        target2template=True,
        target_file=anatf,
        output_dir=func_output_dir,
        config=config,
        template_spec=template_spec,
        target2template_transform=anat2template_transform
    )

    # Log test configuration
    logger.info("Starting test_func2template_preprocessing")
    logger.debug(f"Test directory: {test_dir}")
    logger.debug(f"Input functional file: {funcf}")
    logger.debug(f"Template spec: {template_spec}")
    
    # Verify that workflow.log was created during initialization
    working_dir = os.path.join(func_output_dir, "working_dir")
    assert ensure_workflow_log_exists(working_dir), "workflow.log was not created during workflow initialization"
    logger.info("✓ workflow.log created successfully during workflow initialization")
    
    # Run the workflow
    logger.info("Running func2template workflow...")
    workflow.run()
    
    # Verify comprehensive logging
    workflow_log_file = os.path.join(working_dir, "workflow.log")
    assert os.path.exists(workflow_log_file), "workflow.log file not found"
    
    # Read and verify workflow.log content
    with open(workflow_log_file, 'r') as f:
        log_content = f.read()
    
        # Verify key log entries for func2template workflow  
    assert "Starting functional processing pipeline" in log_content, "Workflow start not logged"
    logger.info("✓ Workflow start message found in log")
    
    # Check for motion correction and registration QC
    assert "Motion correction QC created" in log_content or "Report generation completed" in log_content, "Motion correction QC not logged"
    logger.info("✓ Motion correction QC logged")
    
    assert "registration QC created" in log_content or "Functional registration QC created" in log_content or "Report generation completed" in log_content, "Registration QC not logged"
    logger.info("✓ Registration QC logged")
    
    # Check workflow completion
    assert "WORKFLOW COMPLETED SUCCESSFULLY" in log_content, "Workflow completion not logged"
    logger.info("✓ Workflow completion logged")
    

    logger.info("✓ All func2template logging verification tests passed!")

if __name__ == "__main__":
    test_anat2template_preprocessing() 
    test_func2target_preprocessing() 
    