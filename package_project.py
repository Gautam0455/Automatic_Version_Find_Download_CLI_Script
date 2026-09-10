import os
import sys
import zipfile

sys.dont_write_bytecode = True

def create_project_zip():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    zip_name = "SoftwareUpdater.zip"
    zip_path = os.path.join(os.path.dirname(base_dir), zip_name)

    print(f"Creating ZIP package: {zip_path} ...")
    
    # Exclude temporary or heavy cache files
    exclude_dirs = {
        "__pycache__",
        ".git",
        ".venv",
        "venv",
        ".idea",
        ".vscode",
        "downloads",
        "reports",
    }
    exclude_files = {zip_name, ".DS_Store", "_readme_body.md"}

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(base_dir):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for file in files:
                if file in exclude_files or file.endswith(".pyc"):
                    continue
                full_path = os.path.join(root, file)
                # Save relative to SoftwareUpdater folder
                rel_path = os.path.join("SoftwareUpdater", os.path.relpath(full_path, base_dir))
                zipf.write(full_path, rel_path)
                
    print(f"ZIP creation complete! File saved at: {zip_path}")
    return zip_path

if __name__ == "__main__":
    create_project_zip()
