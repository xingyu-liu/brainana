#!/usr/bin/env python3

# %%
import os
import subprocess
import sys

# %%
def main():
    # Configuration variables
    # # uwmadison
    # dataset_dir = "/mnt/DataDrive2/macaque/data_raw/macaque_mri/PRIME-DE"
    # output_dir = "/mnt/DataDrive2/macaque/data_preproc/macaque_mri/PRIME-DE_res-1"

    # site = "site-uwmadison"
    # input_path = os.path.join(dataset_dir, site)
    # output_path = os.path.join(output_dir, site)
    # config_path = os.path.join(output_dir, "configs", f"func2anat2template_{site}.json")

    # n_procs = 3
    # sub_batch_size = 3

    # arcaro
    input_path = "/mnt/DataDrive2/macaque/data_raw/macaque_mri/arcaro"
    output_path = "/mnt/DataDrive2/macaque/data_preproc/macaque_mri/arcaro_res-1"
    config_path = os.path.join(output_path, f"config.json")

    n_procs = 3
    sub_batch_size = 1

    # get sublist
    sublist = os.listdir(input_path)
    sublist = [sub for sub in sublist if os.path.isdir(os.path.join(input_path, sub))]
    sublist = [i for i in sublist if i.startswith("sub-")]
    sublist = sorted(sublist)
    
    for i in range(0, len(sublist), sub_batch_size):
        # get sub_batch_candidate
        if i + sub_batch_size >= len(sublist):
            sub_batch_candidate = sublist[i:]
        else:
            sub_batch_candidate = sublist[i:i+sub_batch_size]
        
        # Check if the sub_batch_candidate has any existing output by QC html
        sub_batch = []
        for sub in sub_batch_candidate:
            sub_qc_path = os.path.join(output_path, f'{sub}.html')
            if os.path.exists(sub_qc_path):
                print(f"Output for {sub} already exists. Skipping...")
                continue
            else:
                sub_batch.append(sub)
        
        if len(sub_batch) == 0:
            print(f"No subjects to run for batch {i}.")
            continue
        
        # Build command arguments
        cmd = [
            sys.executable, "-m", "macacaMRIprep.cli.preproc",
            input_path,
            output_path,
            "--config", config_path,
            "--n-procs", str(n_procs),
            "--participant-label"
        ] + sub_batch
        
        print(f"Running command: {' '.join(cmd)}")
        
        try:
            # Run the preprocessing command
            result = subprocess.run(cmd, check=True)
            print(f"Processing completed successfully for batch {i//sub_batch_size + 1}!")
        except subprocess.CalledProcessError as e:
            print(f"Error running preprocessing for batch {i//sub_batch_size + 1}: {e}")
            return e.returncode
        except FileNotFoundError:
            print("Error: macacaMRIprep module not found. Make sure it's installed and in your Python path.")
            return 1
    
    print("All batches processed successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
