"""
FastAPI Project Structure Generator

Run this script to create a minimal FastAPI project structure.

Usage:
    python template_creator.py

This will create the following structure:
    rag-qa-project/
    ├── app/
    │   ├── api/routes/
    │   ├── core/
    │   └── utils/
    └── tests/
"""

import os
from pathlib import Path

# Project root directory name
PROJECT_NAME = "rag-qa-project"

# Directory structure
DIRECTORIES = [
    "app",
    "app/api",
    "app/api/routes",
    "app/core",
    "app/utils",
    "tests",
]

# Files to create with their content
FILES = {
    # Root configuration files
    "requirements.txt": """fastapi>=0.109.0
uvicorn[standard]>=0.27.0
python-dotenv>=1.0.0
pydantic>=2.5.0
pydantic-settings>=2.1.0
""",

    ".env.example": """# Environment Variables
# Add your configuration here
""",

    ".gitignore": """# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
dist/
*.egg-info/

# Virtual environments
.env
.venv
env/
venv/

# IDE
.idea/
.vscode/
*.swp

# Testing
.pytest_cache/
.coverage

# OS
.DS_Store
""",

    # App files
    "app/__init__.py": """""",

    "app/main.py": """from fastapi import FastAPI

app = FastAPI(title="FastAPI Application")


@app.get("/")
async def root():
    return {"message": "Welcome to FastAPI"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
""",

    "app/api/__init__.py": """""",

    "app/api/routes/__init__.py": """""",

    "app/core/__init__.py": """""",

    "app/utils/__init__.py": """""",

    # Tests
    "tests/__init__.py": """""",
}


def create_project_structure():
    """Create the complete project structure."""
    # Get the directory where the script is run
    base_path = Path.cwd()

    # Check if we should create in current directory or new directory
    if base_path.name == PROJECT_NAME:
        project_path = base_path
    else:
        project_path = base_path / PROJECT_NAME

    print(f"Creating project structure in: {project_path}")
    print("=" * 50)

    # Create directories
    for directory in DIRECTORIES:
        dir_path = project_path / directory
        dir_path.mkdir(parents=True, exist_ok=True)
        print(f"Created directory: {directory}/")

    print()

    # Create files
    for file_path, content in FILES.items():
        full_path = project_path / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)
        print(f"Created file: {file_path}")

    print()
    print("=" * 50)
    print("Project structure created successfully!")
    print()
    print("Next steps:")
    print(f"  1. cd {PROJECT_NAME}")
    print("  2. python -m venv venv")
    print("  3. source venv/bin/activate  # or venv\\Scripts\\activate on Windows")
    print("  4. pip install -r requirements.txt")
    print("  5. cp .env.example .env")
    print("  6. uvicorn app.main:app --reload")
    print()
    print("Open http://localhost:8000/docs for API documentation")


if __name__ == "__main__":
    create_project_structure()
