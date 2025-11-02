import os
import subprocess
import json
import sys
import concurrent.futures

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

# The folder path from the mounted DMG, e.g., ./mounted_dmg/System
parsedFolderPath = sys.argv[1] 

# The relative path *in the repo* where files will be saved, e.g., beta/iOS/System
finalBaseRepoPath = sys.argv[2]

# The images path is built from the OS-specific root folder.
osSpecificRootPath = os.path.dirname(finalBaseRepoPath)
finalBaseRepoImagesPath = os.path.join(osSpecificRootPath, "images")


print(f"--- Starting Python Script ---")
print(f"Reading from DMG folder: {parsedFolderPath}")
print(f"Writing to repo folder:  {finalBaseRepoPath}")
print(f"Writing images to:       {finalBaseRepoImagesPath}")
print(f"------------------------------")

# --- Core Functions ---
# NOTE: These functions now RETURN an error dictionary instead of
# calling addErrorToArray, to make them process-safe.

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
            return None # Not an error, just no 'en' content

        outputDir = os.path.join(finalBaseRepoPath, os.path.dirname(relPathInDMG), "en.lproj")
        os.makedirs(outputDir, exist_ok=True) # <-- Safer directory creation

        finalStringsFilename = os.path.basename(strings_file).replace('-json.strings', '.strings')
        outputFile = os.path.join(outputDir, finalStringsFilename) 

        with open(outputFile, 'w') as file:
            for key in enContent:
                file.write(f'"{key}" = "{enContent[key]}";\n')
        
        os.remove(strings_file)
        return None # Success
        
    except subprocess.CalledProcessError as e:
        error_message = e.stderr or e.stdout or str(e)
        print(f"Error converting loctable: {loctable_file} - {error_message.strip()}")
        return {"filepath": loctable_file, "errorMessage": error_message, "function": "convert_loctable_to_strings"}
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from: {strings_file} - {e}")
        return {"filepath": loctable_file, "errorMessage": str(e), "function": "convert_loctable_to_strings"}
    except Exception as e:
        print(f"Unexpected error in convert_loctable_to_strings: {loctable_file} - {e}")
        return {"filepath": loctable_file, "errorMessage": str(e), "function": "convert_loctable_to_strings"}

def add_image_file_to_repo(file_path):
    try:
        relPathInDMG = file_path.replace(parsedFolderPath, "")
        if relPathInDMG.startswith('/'):
            relPathInDMG = relPathInDMG[1:]
        
        root_folder_name = os.path.basename(parsedFolderPath)
        outputPath = os.path.join(finalBaseRepoImagesPath, root_folder_name, os.path.dirname(relPathInDMG))

        os.makedirs(outputPath, exist_ok=True) # <-- Safer directory creation
            
        subprocess.run(['cp', file_path, outputPath], check=True, capture_output=True)
        return None # Success

    except subprocess.CalledProcessError as e:
        error_message = e.stderr or e.stdout or str(e)
        print(f"Error copying image: {file_path} - {error_message}")
        return {"filepath": file_path, "errorMessage": error_message, "function": "add_image_file_to_repo"}
    except Exception as e:
        print(f"Unexpected error in add_image_file_to_repo: {file_path} - {e}")
        return {"filepath": file_path, "errorMessage": str(e), "function": "add_image_file_to_repo"}


def add_plist_file_to_repo(file_path):
    try:
        relPathInDMG = file_path.replace(parsedFolderPath, "")
        if relPathInDMG.startswith('/'):
            relPathInDMG = relPathInDMG[1:]
        
        if '.lproj' in relPathInDMG and 'en.lproj' not in relPathInDMG:
            return None # Skip this file
        if '.xml.plist' in file_path:
            return None # Skip this file

        plist_xml_in_dmg = file_path.replace('.plist', '.xml.plist')
        
        outputPath = os.path.join(finalBaseRepoPath, os.path.dirname(relPathInDMG))
        os.makedirs(outputPath, exist_ok=True) # <-- Safer directory creation
            
        result = subprocess.run(
            ['plutil', '-convert', 'xml1', file_path, '-o', plist_xml_in_dmg], 
            check=True, 
            capture_output=True, 
            text=True
        )
        subprocess.run(['cp', plist_xml_in_dmg, outputPath], check=True, capture_output=True)
        os.remove(plist_xml_in_dmg)
        return None # Success

    except subprocess.CalledProcessError as e:
        error_message = e.stderr or e.stdout or str(e)
        print(f"Error processing plist: {file_path} - {error_message.strip()}")
        return {"filepath": file_path, "errorMessage": error_message, "function": "add_plist_file_to_repo"}
    except Exception as e:
        print(f"Unexpected error in add_plist_file_to_repo: {file_path} - {e}")
        return {"filepath": file_path, "errorMessage": str(e), "function": "add_plist_file_to_repo"}


def find_and_process_files(folder_path):
    loctable_files = []
    image_files = []
    plist_files = []

    print(f"Scanning {folder_path} to collect files...")
    file_count = 0
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            file_count += 1
            file_path = os.path.join(root, file)

            if not os.path.exists(file_path):
                # This error can be added directly, os.walk is still serial
                errorArrayWithFilepaths.append({
                    "filepath": file_path, 
                    "errorMessage": "Broken symlink or file not found", 
                    "function": "find_and_process_files (scan)"
                })
                continue 
            
            if file.endswith('.loctable'):
                loctable_files.append(file_path)
            elif file.endswith(('.png', '.jpg', '.heif', '.ico')):
                image_files.append(file_path)
            elif file.endswith('.plist'):
                plist_files.append(file_path)
    
    total_to_process = len(loctable_files) + len(image_files) + len(plist_files)
    print(f"Scan complete. Processed {file_count} total files, found {total_to_process} to process in parallel.")

    # --- Parallel Processing ---
    # Use ProcessPoolExecutor to run tasks in parallel using all available CPU cores.
    # This is ideal for CPU-bound tasks like 'plutil' and I/O-bound tasks like 'cp'.
    with concurrent.futures.ProcessPoolExecutor() as executor:
        
        print(f"Processing {len(loctable_files)} .loctable files...")
        future_to_file_loctable = {executor.submit(convert_loctable_to_strings, f): f for f in loctable_files}
        
        print(f"Processing {len(image_files)} image files...")
        future_to_file_image = {executor.submit(add_image_file_to_repo, f): f for f in image_files}
        
        print(f"Processing {len(plist_files)} .plist files...")
        future_to_file_plist = {executor.submit(add_plist_file_to_repo, f): f for f in plist_files}

        # --- Collect Results and Errors ---
        print("Waiting for all tasks to complete...")
        
        # Combine all futures into one set for easy iteration
        all_futures = [future_to_file_loctable, future_to_file_image, future_to_file_plist]
        
        for future_map in all_futures:
            for future in concurrent.futures.as_completed(future_map):
                result = future.result()
                if result: # If the function returned an error dictionary
                    errorArrayWithFilepaths.append(result)

    print(f"All processing complete.")
    printErrorArray()

# --- Main execution ---
if __name__ == "__main__":
    if not os.path.isdir(parsedFolderPath):
        print(f"ERROR: Provided folder path does not exist: {parsedFolderPath}")
        sys.exit(1)
        
    find_and_process_files(parsedFolderPath)