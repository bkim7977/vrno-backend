import sys
import os

# Add the current directory to Python path for local imports
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

try:
    # Try to import the main app from the copied app.py
    if os.path.exists(os.path.join(current_dir, 'app.py')):
        from app import app
        print("Successfully imported app from local api/app.py")
        
        # Update static folder paths to use local copies
        app.static_folder = os.path.join(current_dir, 'dist', 'public')
        app.static_url_path = ''
        print(f"Updated static folder to: {app.static_folder}")
    else:
        # Fallback to parent directory import
        parent_dir = os.path.dirname(current_dir)
        sys.path.insert(0, parent_dir)
        from app import app
        print("Successfully imported app from parent directory")
        
except Exception as e:
    print(f"Error importing main app: {e}")
    # Create a fallback app for debugging
    from flask import Flask, jsonify
    app = Flask(__name__)
    
    @app.route('/api/health')
    def health():
        return jsonify({"status": "fallback", "error": str(e)})
    
    @app.route('/api/debug/error')
    def debug_error():
        return jsonify({
            "error": str(e),
            "current_dir": current_dir,
            "files_in_current_dir": os.listdir(current_dir) if os.path.exists(current_dir) else [],
            "python_path": sys.path[:3]
        })

# For Vercel Python runtime: expose the Flask app as WSGI application
# This is the key change - Vercel looks for 'app' variable for WSGI apps

# Add a test route directly in index.py to verify routing works
@app.route('/api/test')
def test_route():
    """Simple test route added directly in index.py"""
    return {"message": "Test route in index.py works!", "working": True}

# This line is required for Vercel to recognize the WSGI app
# The variable name 'app' is what Vercel expects