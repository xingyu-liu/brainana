#!/usr/bin/env python3

# %%
import os
import subprocess
import sys
import shutil
import time

# %%
def count_user_jobs():
    """
    Count the number of current user's jobs (any state) in the Slurm queue.
    Returns 0 if squeue is not available or on error.
    """
    try:
        result = subprocess.run(
            [
                "squeue",
                "-u",
                os.environ.get("USER", ""),
                "-h",
                "-o",
                "%i %t",  # job id and state
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            lines = [line for line in result.stdout.splitlines() if line.strip()]
            return len(lines)
        return 0
    except FileNotFoundError:
        return 0
    except Exception as e:
        print(f"Warning: Could not check user job count: {e}")
        return 0

def wait_for_user_job_slot(max_concurrent_jobs, check_interval=60):
    """
    Wait until the current user's total Slurm jobs are below max_concurrent_jobs.
    """
    while True:
        n_running = count_user_jobs()
        if n_running < max_concurrent_jobs:
            print(f"Your Slurm jobs: {n_running}/{max_concurrent_jobs}. Proceeding...")
            break
        print(f"Your Slurm jobs: {n_running}/{max_concurrent_jobs}. Waiting {check_interval}s...")
        time.sleep(check_interval)

# %%
def main():

    # Default n_procs, can be overridden by SLURM_CPUS_PER_TASK
    # This ensures nhp_mri_prep uses the same number of CPUs that Slurm allocated
    n_procs = int(os.environ.get("SLURM_CPUS_PER_TASK", "40"))
    # Maximum concurrent jobs to submit to Slurm (configurable via environment variable)
    max_concurrent_jobs = int(os.environ.get("MAX_CONCURRENT_JOBS", "1"))

    # ------------------------------------------------------------
    # Configuration variables
    # uwmadison
    dataset_dir = "/mnt/DataDrive2/macaque/data_raw/macaque_mri/PRIME-DE"
    output_dir = "/mnt/DataDrive2/macaque/data_preproc/macaque_mri/PRIME-DE_res-1"
    site = "site-uwmadison"
    input_path = os.path.join(dataset_dir, site)
    output_path = os.path.join(output_dir, site)
    config_path = os.path.join(output_dir, "configs", f"func2anat2template_{site}.json")
    job_name_prefix = "uwmadison_b"

    # # arcaro
    # input_path = "/mnt/DataDrive2/macaque/data_raw/macaque_mri/arcaro"
    # output_path = "/mnt/DataDrive2/macaque/data_preproc/macaque_mri/arcaro_res-1"
    # config_path = os.path.join(output_path, f"config.json")
    # job_name_prefix = "arcaro_b"

    # # unc
    # input_path = "/mnt/DataDrive2/macaque/data_raw/macaque_mri/UNC-Wisconsine/bids"
    # output_path = "/mnt/DataDrive2/macaque/data_preproc/macaque_mri/UNC-Wisconsine_res-1"
    # config_path = os.path.join(output_path, "config.json")
    # job_name_prefix = "unc_b"

    # ------------------------------------------------------------
    # get sublist
    sublist = os.listdir(input_path)
    sublist = [sub for sub in sublist if os.path.isdir(os.path.join(input_path, sub))]
    sublist = [i for i in sublist if i.startswith("sub-")]
    sublist = sorted(sublist)
    
    # Prepare Slurm options (via environment variables when available)
    sbatch_path = shutil.which("sbatch")
    slurm_partition = os.environ.get("SLURM_PARTITION")
    slurm_time = os.environ.get("SLURM_TIME")  # e.g., "02:00:00"
    slurm_mem = os.environ.get("SLURM_MEM")    # e.g., "16G"
    slurm_qos = os.environ.get("SLURM_QOS")
    slurm_account = os.environ.get("SLURM_ACCOUNT")
    slurm_gres = os.environ.get("SLURM_GRES")  # e.g., "gpu:1"

    # Logs directory for Slurm outputs
    logs_dir = os.path.join(output_path, "slurm_logs")
    os.makedirs(logs_dir, exist_ok=True)

    # Build list of subjects that still need processing (by missing QC html)
    pending_subjects = []
    for sub in sublist:
        sub_qc_path = os.path.join(output_path, f'{sub}.html')
        if not os.path.exists(sub_qc_path):
            pending_subjects.append(sub)

    for sub in sublist:

        # Check if the sub_batch_candidate has any existing output by QC html
        sub_qc_path = os.path.join(output_path, f'{sub}.html')
        if os.path.exists(sub_qc_path):
            print(f"Output for {sub} already exists. Skipping...")
            continue
        
        # Build command arguments
        cmd = [
            sys.executable, "-m", "nhp_mri_prep.cli.preproc",
            input_path,
            output_path,
            "--config", config_path,
            "--n-procs", str(n_procs),
            "--participant-label", sub
        ]
        
        print(f"Command: {' '.join(cmd)}")
        
        try:
            # If we're inside a Slurm allocation, prefer srun
            if os.environ.get("SLURM_JOB_ID") and shutil.which("srun"):
                srun_cmd = [
                    "srun",
                    "--ntasks=1",
                    f"--cpus-per-task={n_procs}",
                ] + cmd
                print(f"Submitting via srun (within allocation): {' '.join(srun_cmd)}")
                subprocess.run(srun_cmd, check=True)
                print(f"Processing completed successfully for {sub}!")

            # Else, if sbatch is available, submit a batch job per sub-batch
            elif sbatch_path is not None:
                # Wait for available job slot before submitting
                wait_for_user_job_slot(max_concurrent_jobs)
                
                # Build sbatch command
                job_name = f"{job_name_prefix}{sub}"
                sbatch_cmd = [
                    sbatch_path,
                    f"--job-name={job_name}",
                    f"--cpus-per-task={n_procs}",
                    f"--output={os.path.join(logs_dir, 'slurm-%j.out')}",
                ]
                if slurm_partition:
                    sbatch_cmd.append(f"--partition={slurm_partition}")
                if slurm_time:
                    sbatch_cmd.append(f"--time={slurm_time}")
                if slurm_mem:
                    sbatch_cmd.append(f"--mem={slurm_mem}")
                if slurm_qos:
                    sbatch_cmd.append(f"--qos={slurm_qos}")
                if slurm_account:
                    sbatch_cmd.append(f"--account={slurm_account}")
                if slurm_gres:
                    sbatch_cmd.append(f"--gres={slurm_gres}")

                # Use --wrap to run the Python command in the batch job
                wrapped = " ".join(cmd)
                full_sbatch = sbatch_cmd + ["--wrap", wrapped]
                print(f"Submitting via sbatch: {' '.join(full_sbatch)}")
                result = subprocess.run(full_sbatch, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                print(result.stdout.strip())

            # Fallback: run locally without Slurm
            else:
                print("Slurm not detected/available. Running locally.")
                subprocess.run(cmd, check=True)
                print(f"Processing completed successfully for {sub}!")
        except subprocess.CalledProcessError as e:
            print(f"Error running preprocessing for {sub}: {e}")
            return e.returncode
        except FileNotFoundError:
            print("Error: nhp_mri_prep module not found. Make sure it's installed and in your Python path.")
            return 1
    
    print("All batches processed successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
