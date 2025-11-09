import os
import subprocess
import json
import sys
import concurrent.futures
import multiprocessing
import time
import tempfile

# --- Error Handling ---
# This list will be populated by the main thread after results are collected
errorArrayWithFilepaths = []
def printErrorArray():
    """ MODIFIED: All print statements now go to sys.stderr """
    if len(errorArrayWithFilepaths) == 0:
        return
    print(f'\n--- ⚠️ Encountered Errors ---', file=sys.stderr)
    for error in errorArrayWithFilepaths:
        print(f"  Function: {error['function']}", file=sys.stderr)
        print(f"  File: {error['filepath']}", file=sys.stderr)
        print(f"  Error: {error['errorMessage'].strip()}", file=sys.stderr)
        print(f"  ---------------------", file=sys.stderr)
    print(f'--- End of Error Report ---\n', file=sys.stderr)

# --- Argument Parsing ---
# MODIFIED: Removed all --quiet logic

if len(sys.argv) < 3:
    # MODIFIED: All error/usage prints go to sys.stderr
    print("ERROR: Missing arguments.", file=sys.stderr)
    print("Usage: python py.py <source_folder> <destination_folder> [exclude_info_plist_boolean]", file=sys.stderr)
    print("  <source_folder>: e.g., ./mounted_dmg/System", file=sys.stderr)
    print("  <destination_folder>: e.g., ./beta/iOS/System", file=sys.stderr)
    print("  [exclude_info_plist_boolean]: (Optional) 'true' or 'false' to skip Info.plist files. Defaults to 'false'.", file=sys.stderr)
    sys.exit(1)

parsedFolderPath = sys.argv[1]
finalBaseRepoPath = sys.argv[2]

# --- NEW: Check for skip_info_plist flag ---
SKIP_INFO_PLIST = False
if len(sys.argv) > 3:
    SKIP_INFO_PLIST = sys.argv[3].lower() == 'true'
# ---

osSpecificRootPath = os.path.dirname(finalBaseRepoPath)
finalBaseRepoImagesPath = os.path.join(osSpecificRootPath, "images")

# MODIFIED: All startup prints go to sys.stderr
print(f"--- Starting Python Script ---", file=sys.stderr)
print(f"Reading from DMG folder: {parsedFolderPath}", file=sys.stderr)
print(f"Writing to repo folder:  {finalBaseRepoPath}", file=sys.stderr)
print(f"Writing images to:       {finalBaseRepoImagesPath}", file=sys.stderr)
print(f"Exclude Info.plist:      {SKIP_INFO_PLIST}", file=sys.stderr)
print(f"------------------------------", file=sys.stderr)

def convert_loctable_to_strings(loctable_file):
    """
    MODIFIED: Uses tempfile.NamedTemporaryFile to avoid writing
    the intermediate JSON file to the mounted DMG.
    """
    relPathInDMG = loctable_file.replace(parsedFolderPath, "")
    if relPathInDMG.startswith('/'):
        relPathInDMG = relPathInDMG[1:]

    try:
        # Create a temp file in the runner's /tmp directory
        with tempfile.NamedTemporaryFile(suffix=".json") as tmp:
            strings_file_path = tmp.name
            
            subprocess.run(
                ['plutil', '-convert', 'json', loctable_file, '-o', strings_file_path], 
                check=True, 
                capture_output=True, 
                text=True
            )
            
            with open(strings_file_path, "r") as jsonFile:
                data = json.load(jsonFile)
            
            enContent = data.get('en', {})
            if not enContent:
                return None

            outputDir = os.path.join(finalBaseRepoPath, os.path.dirname(relPathInDMG), "en.lproj")
            os.makedirs(outputDir, exist_ok=True)

            finalStringsFilename = os.path.basename(loctable_file).replace('.loctable', '.strings')
            outputFile = os.path.join(outputDir, finalStringsFilename) 

            with open(outputFile, 'w') as file:
                for key in enContent:
                    file.write(f'"{key}" = "{enContent[key]}";\n')
            
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
    """
    MODIFIED: Uses tempfile.NamedTemporaryFile to avoid writing
    the intermediate XML file to the mounted DMG.
    """
    try:
        relPathInDMG = file_path.replace(parsedFolderPath, "")
        if relPathInDMG.startswith('/'):
            relPathInDMG = relPathInDMG[1:]
        
        if '.lproj' in relPathInDMG and 'en.lproj' not in relPathInDMG:
            return None
        if '.xml.plist' in file_path:
            return None

        outputPath = os.path.join(finalBaseRepoPath, os.path.dirname(relPathInDMG))
        os.makedirs(outputPath, exist_ok=True)
        
        # Create a temp file in the runner's /tmp directory
        with tempfile.NamedTemporaryFile(suffix=".xml.plist") as tmp:
            plist_xml_temp_path = tmp.name

            # 1. Convert .plist from DMG -> temp XML file
            subprocess.run(
                ['plutil', '-convert', 'xml1', file_path, '-o', plist_xml_temp_path], 
                check=True, 
                capture_output=True, 
                text=True
            )
            
            # 2. Copy temp XML file -> final repo path
            subprocess.run(['cp', plist_xml_temp_path, outputPath], check=True, capture_output=True)
            
            # 3. The temp file is automatically deleted when 'with' block exits
            return None

    except subprocess.CalledProcessError as e:
        error_message = e.stderr or e.stdout or str(e)
        return {"filepath": file_path, "errorMessage": error_message, "function": "add_plist_file_to_repo"}
    except Exception as e:
        return {"filepath": file_path, "errorMessage": str(e), "function": "add_plist_file_to_repo"}

# --- New Processing and Discovery Functions ---

def process_file_by_extension(file_path):
    """Dispatch file to appropriate processor based on extension."""
    
    # --- NEW: Skip Info.plist if flag is set ---
    if SKIP_INFO_PLIST and os.path.basename(file_path) == 'Info.plist':
        return None # Skip this file
    # ---
    
    if file_path.endswith('.loctable'):
        return convert_loctable_to_strings(file_path)
    elif file_path.endswith(('.png', '.jpg', '.heif', '.ico')):
        return add_image_file_to_repo(file_path)
    elif file_path.endswith('.plist'):
        return add_plist_file_to_repo(file_path)
    return None


def discover_files_fast(root_path, extensions):
    """
    Fast, optimized file discovery using os.walk.
    Filters files by extension during discovery to minimize memory.
    
    os.walk is highly optimized in Python and faster than custom implementations
    for most use cases, especially on macOS with APFS.
    """
    target_files = []
    
    try:
        for dirpath, dirnames, filenames in os.walk(root_path, topdown=True, followlinks=False):
            for filename in filenames:
                if any(filename.endswith(ext) for ext in extensions):
                    file_path = os.path.join(dirpath, filename)
                    target_files.append(file_path)
            
            # --- REDUNDANT BLOCK REMOVED ---
            # The os.scandir loop that was here was adding symlinks
            # a second time. It has been removed.
                
    except (PermissionError, OSError) as e:
        # MODIFIED: Print warning to sys.stderr
        print(f"Warning: Could not access {root_path}: {e}", file=sys.stderr)
    
    return target_files


def find_and_process_files_streaming(folder_path): # MODIFIED: Removed IS_QUIET_FLAG
    """
    Optimized for GitHub Actions 3-core runner.
    """
    
    cpu_count = multiprocessing.cpu_count()
    max_workers = cpu_count
    
    # MODIFIED: All progress prints go to sys.stderr
    print(f"Detected {cpu_count} CPU cores, using {max_workers} workers for processing...", file=sys.stderr)
    print(f"Starting file discovery in: {folder_path}", file=sys.stderr)
    
    extensions = ('.loctable', '.png', '.jpg', '.heif', '.ico', '.plist')
    
    start_time = time.time()
    target_files = discover_files_fast(folder_path, extensions)
    discovery_time = time.time() - start_time
    
    # MODIFIED: All progress prints go to sys.stderr
    print(f"Discovery complete in {discovery_time:.2f}s: found {len(target_files)} files to process", file=sys.stderr)
    
    if len(target_files) == 0:
        # MODIFIED: All progress prints go to sys.stderr
        print("No files to process.", file=sys.stderr)
        return {
            "discovery_time_s": discovery_time,
            "files_found": 0,
            "valid_files_processed": 0,
            "total_time_s": time.time() - start_time,
            "avg_time_s": 0,
            "error_count": 0
        }
    
    valid_files = []
    for file_path in target_files:
        if not os.path.exists(file_path):
            errorArrayWithFilepaths.append({
                "filepath": file_path, 
                "errorMessage": "Broken symlink or file not found", 
                "function": "find_and_process_files_streaming (validation)"
            })
        else:
            valid_files.append(file_path)
    
    # MODIFIED: All progress prints go to sys.stderr
    print(f"Processing {len(valid_files)} valid files with {max_workers} workers...", file=sys.stderr)
    
    futures = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
        for file_path in valid_files:
            future = executor.submit(process_file_by_extension, file_path)
            futures.append(future)
        
        # MODIFIED: All progress prints go to sys.stderr
        print(f"All {len(futures)} tasks submitted. Waiting for completion...", file=sys.stderr)
        
        completed = 0
        for future in concurrent.futures.as_completed(futures):
            completed += 1
            
            # MODIFIED: Progress updates go to sys.stderr
            if completed % max(1, len(futures) // 20) == 0:
                progress = (completed / len(futures)) * 100
                print(f"Progress: {completed}/{len(futures)} ({progress:.1f}%)", file=sys.stderr)
            
            try:
                result = future.result()
                if result:
                    errorArrayWithFilepaths.append(result)
            except Exception as e:
                # MODIFIED: Error print goes to sys.stderr
                print(f"Unexpected error in worker: {e}", file=sys.stderr)

    total_time = time.time() - start_time
    avg_time = (total_time / len(valid_files)) if len(valid_files) > 0 else 0
    
    stats = {
        "discovery_time_s": discovery_time,
        "files_found": len(target_files),
        "valid_files_processed": len(valid_files),
        "total_time_s": total_time,
        "avg_time_s": avg_time,
        "error_count": len(errorArrayWithFilepaths)
    }

    # MODIFIED: Final human-readable summary goes to sys.stderr
    print(f"\nAll processing complete in {stats['total_time_s']:.2f}s ({stats['total_time_s']/60:.2f} minutes)", file=sys.stderr)
    if stats['valid_files_processed'] > 0:
        print(f"Average: {stats['avg_time_s']:.3f}s per file", file=sys.stderr)
    printErrorArray() # This function already prints to stderr

    return stats


# --- Main execution ---
if __name__ == "__main__":
    if not os.path.isdir(parsedFolderPath):
        print(f"ERROR: Provided folder path does not exist: {parsedFolderPath}", file=sys.stderr)
        sys.exit(1)
    stats = find_and_process_files_streaming(parsedFolderPath)
    stats['errors'] = errorArrayWithFilepaths
    print(json.dumps(stats))