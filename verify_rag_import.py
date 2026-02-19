
import sys
import os

# Add src to python path so we can import the module like the application does
sys.path.append(os.path.join(os.getcwd(), 'src'))

try:
    from medical_workflow.nodes.rag import build_medical_vector_db
    print("SUCCESS: Successfully imported build_medical_vector_db from medical_workflow.nodes.rag")
except ImportError as e:
    print(f"FAILURE: Failed to import medical_workflow.nodes.rag: {e}")
except Exception as e:
    print(f"ERROR: Unexpected error importing medical_workflow.nodes.rag: {e}")
