import os
import subprocess
import json
import sys

# --- Error Handling ---
errorArrayWithFilepaths = [] # array contents should be json with filepath, error message, and the function that called it
def addErrorToArray(filepath, errorMessage, function):
    errorArrayWithFilepaths.append({
        "filepath": filepath,
        "errorMessage": errorMessage,
        "function": function
    })
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
    print("Usage: python py.py <path_to_mounted_folder> <relative_repo_path>")
    print("  <path_to_mounted_folder>: e.g., /Volumes/DMG_Mount/System/Library")
    print("  <relative_repo_path>: e.g., beta")
    sys.exit(1)

# The folder path from the mounted DMG, e.g., /Volumes/DMG_Mount/System/Library
parsedFolderPath = sys.argv[1] 

# The relative path *in the repo* where files will be saved, e.g., "beta"
relPathFromRoot = sys.argv[2]

# Get the base repo path from the GitHub environment variable
baseGithubRepoLocation = os.environ.get('GITHUB_WORKSPACE', '.')

# Combine the repo root with the relative path to get the final output directory
finalBaseRepoPath = os.path.join(baseGithubRepoLocation, relPathFromRoot)
finalBaseRepoImagesPath = os.path.join(finalBaseRepoPath, "images")

print(f"--- Starting Python Script ---")
print(f"Reading from DMG folder: {parsedFolderPath}")
print(f"Writing to repo folder:  {finalBaseRepoPath}")
print(f"Writing images to:       {finalBaseRepoImagesPath}")
print(f"------------------------------")

# --- Core Functions ---

def convert_loctable_to_strings(loctable_file):
    relPathInDMG = loctable_file.replace(parsedFolderPath, "")
    if relPathInDMG.startswith('/'):
        relPathInDMG = relPathInDMG[1:]

    strings_file = loctable_file.replace('.loctable', '-json.strings')
    try:
        # Run plutil, capturing output for better error logging
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
            # print(f"No 'en' content found in {loctable_file}, skipping.")
            os.remove(strings_file) # Clean up the intermediate JSON
            return

        outputDir = os.path.join(finalBaseRepoPath, os.path.dirname(relPathInDMG), "en.lproj")
        if not os.path.exists(outputDir):
            os.makedirs(outputDir)

        finalStringsFilename = os.path.basename(strings_file).replace('-json.strings', '.strings')
        outputFile = os.path.join(outputDir, finalStringsFilename) 

        with open(outputFile, 'w') as file:
            for key in enContent:
                file.write(f'"{key}" = "{enContent[key]}";\n')
        
        os.remove(strings_file)
        
    except subprocess.CalledProcessError as e:
        # Catch plutil errors, log the stderr, and continue
        error_message = e.stderr or e.stdout or str(e)
        print(f"Error converting loctable: {loctable_file} - {error_message.strip()}")
        addErrorToArray(loctable_file, error_message, "convert_loctable_to_strings")
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from: {strings_file} - {e}")
        addErrorToArray(loctable_file, str(e), "convert_loctable_to_strings")
    except Exception as e:
        # Catch any other unexpected errors
        print(f"Unexpected error in convert_loctable_to_strings: {loctable_file} - {e}")
        addErrorToArray(loctable_file, str(e), "convert_loctable_to_strings")

def add_image_file_to_repo(file_path):
    relPathInDMG = file_path.replace(parsedFolderPath, "")
    if relPathInDMG.startswith('/'):
        relPathInDMG = relPathInDMG[1:]
        
    outputPath = os.path.join(finalBaseRepoImagesPath, os.path.dirname(relPathInDMG))
    if not os.path.exists(outputPath):
        os.makedirs(outputPath)
        
    try:
        subprocess.run(['cp', file_path, outputPath], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error copying image: {file_path} - {e}")
        addErrorToArray(file_path, str(e), "add_image_file_to_repo")
    except Exception as e:
        print(f"Unexpected error in add_image_file_to_repo: {file_path} - {e}")
        addErrorToArray(file_path, str(e), "add_image_file_to_repo")


def add_plist_file_to_repo(file_path):
    relPathInDMG = file_path.replace(parsedFolderPath, "")
    if relPathInDMG.startswith('/'):
        relPathInDMG = relPathInDMG[1:]
    
    if '.lproj' in relPathInDMG and 'en.lproj' not in relPathInDMG:
        return
    if '.xml.plist' in file_path:
        return

    plist_xml_in_dmg = file_path.replace('.plist', '.xml.plist')
    
    outputPath = os.path.join(finalBaseRepoPath, os.path.dirname(relPathInDMG))
    if not os.path.exists(outputPath):
        os.makedirs(outputPath)
        
    try:    
        # Run plutil, capturing output for better error logging
        result = subprocess.run(
            ['plutil', '-convert', 'xml1', file_path, '-o', plist_xml_in_dmg], 
            check=True, 
            capture_output=True, 
            text=True
        )
        subprocess.run(['cp', plist_xml_in_dmg, outputPath], check=True)
        os.remove(plist_xml_in_dmg)
    except subprocess.CalledProcessError as e:
        # Catch plutil errors, log the stderr, and continue
        error_message = e.stderr or e.stdout or str(e)
        print(f"Error processing plist: {file_path} - {error_message.strip()}")
        addErrorToArray(file_path, error_message, "add_plist_file_to_repo")
    except Exception as e:
        # Catch any other unexpected errors
        print(f"Unexpected error in add_plist_file_to_repo: {file_path} - {e}")
        addErrorToArray(file_path, str(e), "add_plist_file_to_repo")


def find_loctable_files(folder_path):
    print(f"Scanning {folder_path}...")
    file_count = 0
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            file_count += 1
            file_path = os.path.join(root, file)

            # --- THIS IS THE FIX ---
            # Check for broken symlinks. os.path.exists() returns False for them.
            if not os.path.exists(file_path):
                # print(f"Skipping broken symlink: {file_path}") # Optional: for less verbose logs
                addErrorToArray(file_path, "Broken symlink or file not found", "find_loctable_files")
                continue # Skip to the next file
            # --- END FIX ---
            
            if file.endswith('.loctable'):
                convert_loctable_to_strings(file_path)
            elif file.endswith(('.png', '.jpg', '.heif', '.ico')):
                add_image_file_to_repo(file_path)
            elif file.endswith('.plist'):
                add_plist_file_to_repo(file_path)
    
    print(f"Scan complete. Processed {file_count} files.")
    # Print errors at the end of this specific run
    printErrorArray()

# --- Main execution ---
if __name__ == "__main__":
    if not os.path.isdir(parsedFolderPath):
        print(f"ERROR: Provided folder path does not exist: {parsedFolderPath}")
        sys.exit(1)
        
    find_loctable_files(parsedFolderPath)