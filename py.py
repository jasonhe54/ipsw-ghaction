import os
import subprocess
import json
import sys
import concurrent.futures
import multiprocessing
import time # Added for timing

# --- Error Handling ---
errorArrayWithFilepaths = []
def printErrorArray():
    if len(errorArrayWithFilepaths) == 0:
        return
    print(f'\n--- ⚠️ Encountered Errors ---')
    for error in errorArrayWithFilepaths:
        print(f"  Function: {error['function']}")
        print(f"  File: {error['filepath']}")
        print(f"  Error: {error['errorMessage'].strip()}")
        print(f"  ---------------------")
    print(f'--- End of Error Report ---\n')

# --- Argument Parsing ---
if len(sys.argv) < 3:
    print("ERROR: Missing arguments.")
    print("Usage: python py.py <source_folder> <destination_folder>")
    sys.exit(1)

parsedFolderPath = sys.argv[1]
finalBaseRepoPath = sys.argv[2]

osSpecificRootPath = os.path.dirname(finalBaseRepoPath)
finalBaseRepoImagesPath = os.path.join(osSpecificRootPath, "images")

print(f"--- Starting Python Script ---")
print(f"Reading from DMG folder: {parsedFolderPath}")
print(f"Writing to repo folder:  {finalBaseRepoPath}")
print(f"Writing images to:       {finalBaseRepoImagesPath}")
print(f"------------------------------")

# --- Core Functions (Unchanged) ---
def convert_loctable_to_strings(loctable_file):
    relPathInDMG = loctable_file.replace(parsedFolderPath, "")
    if relPathInDMG.startswith('/'):
        relPathInDMG = relPathInDMG[1:]
    strings_file = loctable_file.replace('.loctable', '-json.strings')
    try:
        subprocess.run(
            ['plutil', '-convert', 'json', loctable_file, '-o', strings_file], 
            check=True, capture_output=True, text=True
        )
        with open(strings_file, "r") as jsonFile: data = json.load(jsonFile)
        enContent = data.get('en', {})
        if not enContent:
            os.remove(strings_file); return None
        outputDir = os.path.join(finalBaseRepoPath, os.path.dirname(relPathInDMG), "en.lproj")
        os.makedirs(outputDir, exist_ok=True)
        finalStringsFilename = os.path.basename(strings_file).replace('-json.strings', '.strings')
        outputFile = os.path.join(outputDir, finalStringsFilename) 
        with open(outputFile, 'w') as file:
            for key in enContent: file.write(f'"{key}" = "{enContent[key]}";\n')
        os.remove(strings_file)
        return None
    except subprocess.CalledProcessError as e:
        error_message = e.stderr or e.stdout or str(e)
        return {"filepath": loctable_file, "errorMessage": error_message, "function": "convert_loctable_to_strings"}
    except Exception as e:
        return {"filepath": loctable_file, "errorMessage": str(e), "function": "convert_loctable_to_strings"}

def add_image_file_to_repo(file_path):
    try:
        relPathInDMG = file_path.replace(parsedFolderPath, "")
        if relPathInDMG.startswith('/'): relPathInDMG = relPathInDMG[1:]
        root_folder_name = os.path.basename(parsedFolderPath)
        outputPath = os.path.join(finalBaseRepoImagesPath, root_folder_name, os.path.dirname(relPathInDMG))
        os.makedirs(outputPath, exist_ok=True)
        subprocess.run(['cp', file_path, outputPath], check=True, capture_output=True)
        return None
    except subprocess.CalledProcessError as e:
        error_message = e.stderr or e.stdout or str(e)
        return {"filepath": file_path, "errorMessage": error_message, "function": "add_image_file_to_repo"}
    except Exception as e:
        return {"filepath": file_path, "errorMessage": str(e), "function": "add_image_file_to_repo"}


def add_plist_file_to_repo(file_path):
    try:
        relPathInDMG = file_path.replace(parsedFolderPath, "")
        if relPathInDMG.startswith('/'): relPathInDMG = relPathInDMG[1:]
        if '.lproj' in relPathInDMG and 'en.lproj' not in relPathInDMG: return None
        if '.xml.plist' in file_path: return None
        plist_xml_in_dmg = file_path.replace('.plist', '.xml.plist')
        outputPath = os.path.join(finalBaseRepoPath, os.path.dirname(relPathInDMG))
        os.makedirs(outputPath, exist_ok=True)
        result = subprocess.run(
            ['plutil', '-convert', 'xml1', file_path, '-o', plist_xml_in_dmg], 
            check=True, capture_output=True, text=True
        )
        subprocess.run(['cp', plist_xml_in_dmg, outputPath], check=True, capture_output=True)
        os.remove(plist_xml_in_dmg)
        return None
    except subprocess.CalledProcessError as e:
        error_message = e.stderr or e.stdout or str(e)
        return {"filepath": file_path, "errorMessage": error_message, "function": "add_plist_file_to_repo"}
    except Exception as e:
        return {"filepath": file_path, "errorMessage": str(e), "function": "add_plist_file_to_repo"}

# --- New Processing and Discovery Functions ---

def process_file_by_extension(file_path):
    """Dispatch file to appropriate processor based on extension."""
    if file_path.endswith('.loctable'):
        return convert_loctable_to_strings(file_path)
    elif file_path.endswith(('.png', '.jpg', '.heif', '.ico')):
        return add_image_file_to_repo(file_path)
    elif file_path.endswith('.plist'):
        return add_plist_file_to_repo(file_path)
    return None


def discover_and_validate_files(root_path, extensions):
    """
    Fast, optimized file discovery using os.walk.
    Filters files by extension during discovery to minimize memory.
    
    os.walk is highly optimized in Python and faster than custom implementations
    for most use cases, especially on macOS with APFS.
    """
    valid_files = []
    
    try:
        for dirpath, dirnames, filenames in os.walk(root_path, topdown=True, followlinks=False):
            # Filter files by extension during walk (memory efficient)
            for filename in filenames:
                if any(filename.endswith(ext) for ext in extensions):
                    file_path = os.path.join(dirpath, filename)
                    target_files.append(file_path)
            
            # Also check for symlinks that might be files
            # os.walk doesn't yield symlinks separately, so we scan them
            try:
                for entry in os.scandir(dirpath):
                    if entry.is_symlink():
                        full_path = entry.path
                        if any(full_path.endswith(ext) for ext in extensions):
                            target_files.append(full_path)
            except (PermissionError, OSError):
                continue
                
    except (PermissionError, OSError) as e:
        print(f"Warning: Could not access {root_path}: {e}")
    
    return valid_files


def find_and_process_files_streaming(folder_path):
    """
    Optimized:
    1. Single-pass discovery AND validation.
    2. All cores dedicated to parallel processing.
    3. Reverted to executor.submit() which was empirically faster.
    """
    
    cpu_count = multiprocessing.cpu_count()
    max_workers = cpu_count  # Use all available cores
    
    print(f"Detected {cpu_count} CPU cores, using {max_workers} workers for processing...")
    print(f"Starting single-pass file discovery and validation in: {folder_path}")
    
    extensions = ('.loctable', '.png', '.jpg', '.heif', '.ico', '.plist')
    
    start_time = time.time()
    
    # --- THIS IS THE FIX ---
    # One function call to discover and validate.
    valid_files = discover_and_validate_files(folder_path, extensions)
    # --- END FIX ---
    
    discovery_time = time.time() - start_time
    
    print(f"Discovery complete in {discovery_time:.2f}s: found {len(valid_files)} files to process")
    
    if len(valid_files) == 0:
        print("No files to process.")
        printErrorArray()
        return
    
    # --- The "Validate-Twice" loop is GONE ---
    
    print(f"Processing {len(valid_files)} valid files with {max_workers} workers...")
    
    # Process files in parallel
    futures = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
        # Submit all files for processing
        # Process pool handles queueing automatically
        for file_path in valid_files:
            future = executor.submit(process_file_by_extension, file_path)
            futures.append(future)
        
        print(f"All {len(futures)} tasks submitted. Waiting for completion...")
        
        # Collect results with progress tracking
        completed = 0
        for future in concurrent.futures.as_completed(futures):
            completed += 1
            
            # Progress updates every 5%
            if completed % max(1, len(futures) // 20) == 0:
                progress = (completed / len(futures)) * 100
                print(f"Progress: {completed}/{len(futures)} ({progress:.1f}%)")
            
            try:
                result = future.result()
                if result:  # Error dictionary
                    errorArrayWithFilepaths.append(result)
            except Exception as e:
                # Unexpected crash in worker
                print(f"Unexpected error in worker: {e}")

    total_time = time.time() - start_time
    print(f"\nAll processing complete in {total_time:.2f}s ({total_time/60:.2f} minutes)")
    if len(valid_files) > 0:
        print(f"Average: {total_time/len(valid_files):.3f}s per file")
    printErrorArray()


# --- Main execution ---
if __name__ == "__main__":
    if not os.path.isdir(parsedFolderPath):
        print(f"ERROR: Provided folder path does not exist: {parsedFolderPath}")
        sys.exit(1)
        
    find_and_process_files_streaming(parsedFolderPath)