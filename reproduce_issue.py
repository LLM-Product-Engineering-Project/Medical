
print("--- START TEST ---")
try:
    from langchain_community.vectorstores import Chroma
    print("SUCCESS: imported Chroma from langchain_community.vectorstores")
except ImportError as e:
    print(f"FAILURE: imported Chroma from langchain_community.vectorstores: {e}")
except Exception as e:
    print(f"ERROR: imported Chroma from langchain_community.vectorstores: {e}")

try:
    from langchain_chroma import Chroma
    print("SUCCESS: imported Chroma from langchain_chroma")
except ImportError as e:
    print(f"FAILURE: imported Chroma from langchain_chroma: {e}")
print("--- END TEST ---")
