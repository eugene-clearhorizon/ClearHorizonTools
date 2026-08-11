from flask import Blueprint, render_template, request, send_from_directory, after_this_request, flash
from werkzeug.utils import secure_filename
import os
import uuid
import zipfile
import shutil
from .utils import process_vtt_to_docx
from src.auth.utils import login_required

transcript_cleaner_bp = Blueprint('transcript_cleaner', __name__, template_folder='../templates')

BASE_UPLOAD_FOLDER = 'uploads'
BASE_OUTPUT_FOLDER = 'output'

@transcript_cleaner_bp.route('/transcript-cleaner', methods=['GET', 'POST'])
@login_required
def transcript_cleaner():
    if request.method == 'POST':
        request_id = str(uuid.uuid4())
        upload_dir = os.path.join(BASE_UPLOAD_FOLDER, request_id)
        output_dir = os.path.join(BASE_OUTPUT_FOLDER, request_id)
        os.makedirs(upload_dir, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)

        @after_this_request
        def cleanup(response):
            shutil.rmtree(upload_dir, ignore_errors=True)
            shutil.rmtree(output_dir, ignore_errors=True)
            return response

        files = request.files.getlist('files[]')

        invalid_files = []
        valid_files = []
        for file in files:
            if file.filename == '':
                continue
            if file and file.filename.endswith('.vtt'):
                valid_files.append(file)
            else:
                invalid_files.append(file.filename)

        if invalid_files:
            for filename in invalid_files:
                flash(f'Invalid file type: "{filename}". Only .vtt files are accepted.', 'error')
            return render_template('transcript_cleaner.html')

        if not valid_files:
            flash('No files were selected. Please upload one or more .vtt files.', 'warning')
            return render_template('transcript_cleaner.html')

        output_paths = []

        for file in valid_files:
            filename = secure_filename(file.filename)
            filepath = os.path.join(upload_dir, filename)
            file.save(filepath)

            output_filename = f"cleaned_{os.path.splitext(filename)[0]}.docx"
            output_filepath = os.path.join(output_dir, output_filename)
            output_paths.append(output_filepath)

            process_vtt_to_docx(filepath, output_filepath)

        if len(output_paths) == 1:
            return send_from_directory(
                os.path.abspath(output_dir),
                os.path.basename(output_paths[0]),
                as_attachment=True
            )
        else:
            zip_filename = "cleaned_transcripts.zip"
            zip_filepath = os.path.join(output_dir, zip_filename)
            with zipfile.ZipFile(zip_filepath, 'w') as zipf:
                for path in output_paths:
                    zipf.write(path, os.path.basename(path))
            return send_from_directory(
                os.path.abspath(output_dir),
                zip_filename,
                as_attachment=True
            )

    return render_template('transcript_cleaner.html')
