from flask import Flask, render_template
from src.transcript_cleaner.routes import transcript_cleaner_bp
import os

app = Flask(__name__, template_folder='src/templates', static_folder='src/static')

# Secret key for flashing messages
app.secret_key = os.urandom(24)

@app.route('/')
def index():
    return render_template('index.html')

app.register_blueprint(transcript_cleaner_bp)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
