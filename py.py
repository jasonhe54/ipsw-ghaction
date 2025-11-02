import os
import subprocess
import json
import sys
import concurrent.futures
import multiprocessing
import time

# --- Error Handling ---
# This list will be populated by the main thread after results are collected
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
    print("  <source_folder>: e.g., ./mounted_dmg/System")
    print("  <destination_folder>: e.g., ./beta/iOS/System")
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
            check=True, 
            capture_output=True, 
            text=True
        )
        
        with open(strings_file, "r") as jsonFile:
            data = json.load(jsonFile)
        
        enContent = data.get('en', {})
        if not enContent:
            os.remove(strings_file) 
            return None

        outputDir = os.path.join(finalBaseRepoPath, os.path.dirname(relPathInDMG), "en.lproj")
        os.makedirs(outputDir, exist_ok=True)

        finalStringsFilename = os.path.basename(strings_file).replace('-json.strings', '.strings')
        outputFile = os.path.join(outputDir, finalStringsFilename) 

        with open(outputFile, 'w') as file:
            for key in enContent:
                file.write(f'"{key}" = "{enContent[key]}";\n')
        
        os.remove(strings_file)
        return None
        
    except subprocess.CalledProcessError as e:
        error_message = e.stderr or e.stdout or str(e)
        return {"filepath": loctable_file, "errorMessage": error_message, "function": "convert_loctable_to_strings"}
    except json.JSONDecodeError as e:
        return {"filepath": loctable_file, "errorMessage": str(e), "function": "convert_loctable_to_strings"}
    except Exception as e:
        return {"filepath": loctable_file, "errorMessage": str(e), "function": "convert_loctable_to_strings"}

def add_image_file_to_repo(file_path):
    try:
        relPathInDMG = file_path.replace(parsedFolderPath, "")
        if relPathInDMG.startswith('/'):
            relPathInDMG = relPathInDMG[1:]
        
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
        if relPathInDMG.startswith('/'):
            relPathInDMG = relPathInDMG[1:]
        
        if '.lproj' in relPathInDMG and 'en.lproj' not in relPathInDMG:
            return None
        if '.xml.plist' in file_path:
            return None

        plist_xml_in_dmg = file_path.replace('.plist', '.xml.plist')
        
        outputPath = os.path.join(finalBaseRepoPath, os.path.dirname(relPathInDMG))
        os.makedirs(outputPath, exist_ok=True)
            
        result = subprocess.run(
            ['plutil', '-convert', 'xml1', file_path, '-o', plist_xml_in_dmg], 
            check=True, 
            capture_output=True, 
            text=True
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


def discover_files_fast(root_path, extensions):
    """
    Fast, optimized file discovery using a single os.walk.
    Validates files exist and separates broken symlinks IN A SINGLE PASS.
    Returns: (list_of_valid_files, list_of_error_dicts)
    """
    valid_files = []
    errors = []
    
    try:
        # We only need one walk.
        for dirpath, dirnames, filenames in os.walk(root_path, topdown=True, followlinks=False):
            
            # --- Check all files and symlinks-to-files ---
            for filename in filenames:
                if any(filename.endswith(ext) for ext in extensions):
                    file_path = os.path.join(dirpath, filename)
                    # --- VALIDATION MOVED HERE ---
                    if not os.path.exists(file_path):
                        errors.append({
                            "filepath": file_path, 
                            "errorMessage": "Broken symlink or file not found", 
                            "function": "discover_files_fast (scan)"
                        })
                    else:
                        valid_files.append(file_path)
            
            # --- Check symlinks-to-directories ---
            for dirname in dirnames:
                if any(dirname.endswith(ext) for ext in extensions):
                    file_path = os.path.join(dirpath, dirname)
                    if os.path.islink(file_path): # Only care if it's a symlink
                        # --- VALIDATION MOVED HERE ---
                        if not os.path.exists(file_path):
                            errors.append({
                                "filepath": file_path, 
                                "errorMessage": "Broken symlink or file not found", 
                                "function": "discover_files_fast (scan)"
                            })
                        else:
                            valid_files.append(file_path)
                        
    except (PermissionError, OSError) as e:
        print(f"Warning: Could not access {root_path}: {e}")
    
    return valid_files, errors # <-- Return both lists


def find_and_process_files_streaming(folder_path):
    """
    Optimized for GitHub Actions 3-core runner:
    1. Fast sequential discovery AND validation in one pass.
    2. All cores dedicated to parallel processing (CPU/I/O bound work)
    3. Batch submission with chunking for better process pool efficiency
    """
    
    cpu_count = multiprocessing.cpu_count()
    max_workers = cpu_count  # Use all available cores
    
    print(f"Detected {cpu_count} CPU cores, using {max_workers} workers for processing...")
    print(f"Starting file discovery and validation in: {folder_path}")
    
    # Target file extensions
    extensions = ('.loctable', '.png', '.jpg', '.heif', '.ico', '.plist')
    
    start_time = time.time()
    
    # --- MODIFIED CALL ---
    # Discovery and validation now happen in one function
    valid_files, discovery_errors = discover_files_fast(folder_path, extensions)
    errorArrayWithFilepaths.extend(discovery_errors) # Add scan errors to global list
    # --- END MODIFICATION ---
            
    discovery_time = time.time() - start_time
    
    print(f"Discovery complete in {discovery_time:.2f}s: found {len(valid_files)} files to process")
    
    if len(valid_files) == 0:
        print("No files to process.")
        printErrorArray() # Print errors found during scan
        return
    
    # --- THE SLOW VALIDATION LOOP IS NOW REMOVED ---
    
    print(f"Processing {len(valid_files)} valid files with {max_workers} workers...")
    
    # Process files in parallel using map with chunking
    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
        chunksize = max(1, len(valid_files) // (max_workers * 40))
        
        print(f"Using chunksize of {chunksize} (creates ~{len(valid_files)//chunksize} batches)")
        
        completed = 0
        total_files = len(valid_files)
        
        # Use a generator to print progress more naturally
        progress_points = {int(total_files * p / 100) for p in range(5, 101, 5)}
        
        for result in executor.map(process_file_by_extension, valid_files, chunksize=chunksize):
            completed += 1
            
            if completed in progress_points:
                progress = (completed / total_files) * 100
                print(f"Progress: {completed}/{total_files} ({progress:.0f}%)")
            
            # Handle errors returned from worker
            if result:  # Error dictionary
                errorArrayWithFilepaths.append(result)

    total_time = time.time() - start_time
    print(f"\nAll processing complete in {total_time:.2f}s ({total_time/60:.2f} minutes)")
    if total_files > 0:
        print(f"Average: {total_time/total_files:.3f}s per file")
    printErrorArray()


# --- Main execution ---
if __name__ == "__main__":
    if not os.path.isdir(parsedFolderPath):
        print(f"ERROR: Provided folder path does not exist: {parsedFolderPath}")
        sys.exit(1)
        
    find_and_process_files_streaming(parsedFolderPath)