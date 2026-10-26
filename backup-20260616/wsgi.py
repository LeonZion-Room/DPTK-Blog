import sys
import os

# Add the server directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'server'))

from server import app

if __name__ == '__main__':
    app.run()
